"""Test CD Device."""

from datetime import datetime
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.cd import DeviceAttributes, LuaProtocol, MideaCDDevice
from midealan.devices.cd.message import (
    MessageQuery,
    MessageQueryB1,
    MessageQueryDaily,
    MessageQueryWeekly,
    MessageSetDaily,
    MessageSetMaintenance,
    MessageSetSterilize,
    MessageSetWeekly,
)
from midealan.exceptions import SocketException
from midealan.message import MessageType


def _make_device(model: str = "test_model", customize: str = "") -> MideaCDDevice:
    """Build a Midea CD device with a specific model/customize."""
    return MideaCDDevice(
        name="Test Device",
        device_id=1,
        ip_address="192.168.1.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model=model,
        subtype=1,
        customize=customize,
    )


def _build_message(message_type: MessageType, body: bytearray) -> bytes:
    """Build a full CD response message."""
    header = bytearray([0xAA, 0x00, 0xCD, 0x00, 0x00, 0x00, 0x00, 0x00])
    header += bytearray([ProtocolVersion.V1, message_type])
    return bytes(header + body + bytearray([0x00]))


def _general_body() -> bytearray:
    """Build a general status body (old-protocol raw temperature values)."""
    body = bytearray(63)
    body[0] = 0x01  # body_type
    body[2] = 0x05  # power on + standard mode
    body[3] = 110  # target temperature -> (110 - 30) / 2 = 40
    body[4] = 100  # current temperature -> 35
    body[5] = 45  # top temperature (raw)
    body[7] = 90  # condenser temperature -> 30
    body[8] = 70  # outdoor temperature -> 20
    body[9] = 110  # compressor temperature -> 40
    body[10] = 160  # max temperature -> 65
    body[11] = 100  # min temperature -> 35
    body[20] = 3  # error code
    body[27] = 0x10  # wind middle
    body[34] = 50  # water level
    body[61] = 65  # disinfection temperature 65.0
    return body


class TestMideaCDDevice:
    """Test Midea CD Device."""

    device: MideaCDDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea CD Device setup."""
        self.device = MideaCDDevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="test_model",
            subtype=1,
            customize="",
        )

    # ------------------------------------------------------------------ #
    # MessageSet 25-byte body / tsMax (issue #468)                        #
    # ------------------------------------------------------------------ #

    def test_preset_modes_excludes_vacation_from_selectable_modes(self) -> None:
        """Vacation is readable state, not directly selectable operation mode."""
        assert "vacation" not in self.device.preset_modes
        assert self.device._modes[0x05] == "vacation"

    def test_set_mode_vacation_is_rejected(self) -> None:
        """Direct Vacation operation mode writes are blocked."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "vacation")
            mock_send.assert_not_called()

    def test_set_power_uses_ts_max_at_body_23(self) -> None:
        """Plain SET uses device max_temperature as full[23] tsMax (#468)."""
        self.device._attributes[DeviceAttributes.max_temperature] = 70.0
        self.device._attributes[DeviceAttributes.vacation_temperature] = 65.0

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.ts_max == 70
            assert len(msg.body) == 25
            assert msg.body[23] == 70  # tsMax
            assert msg.body[21] == 0  # vacationTs left 0 on plain set
            assert msg.body[4] != 0  # target present

    @pytest.mark.parametrize("model", ["RSJ000CB", "RSJRAC07"])
    def test_new_protocol_control_writes_local_clock_and_vacation_date(
        self,
        model: str,
    ) -> None:
        """New-protocol controls set clock fields without clearing vacation date."""
        device = _make_device(model=model)
        device._attributes[DeviceAttributes.vacation_start_year] = 26
        device._attributes[DeviceAttributes.vacation_start_month] = 12
        device._attributes[DeviceAttributes.vacation_start_day] = 31
        fixed_now = datetime(2026, 10, 26, 14, 35).astimezone()

        with (
            patch("midealan.devices.cd.datetime") as mock_datetime,
            patch.object(device, "build_send") as mock_send,
        ):
            mock_datetime.now.return_value = fixed_now
            device.set_attribute(DeviceAttributes.target_temperature.value, 55.0)

        msg = mock_send.call_args[0][0]
        assert msg.body[11:18] == bytearray([20, 26, 10, 26, 2, 14, 35])
        assert msg.body[18:21] == bytearray([26, 12, 31])

    def test_non_rsj000cb_control_does_not_invent_clock(self) -> None:
        """Legacy CD controls do not receive an undocumented host clock."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)

        msg = mock_send.call_args[0][0]
        assert msg.body[11:18] == bytearray(7)

    def test_set_target_temperature_body_length_and_ts_max(self) -> None:
        """set_temperature builds 25-byte body with non-zero tsMax."""
        # RSJRAC07 uses the new (raw °C) Lua protocol — matches issue #468.
        self.device.set_customize('{"lua_protocol": "new"}')
        self.device._attributes[DeviceAttributes.max_temperature] = 65.0
        self.device._attributes[DeviceAttributes.target_temperature] = 60.0
        self.device._attributes[DeviceAttributes.power] = True
        self.device._attributes[DeviceAttributes.mode] = "standard"

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.target_temperature.value, 63.0)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.target_temperature == 63.0
            assert msg.use_old_protocol is False
            assert len(msg.body) == 25
            assert msg.body[4] == 63
            assert msg.body[23] == 65

    def test_disable_vacation_sets_flag_and_mode(self) -> None:
        """Disabling vacation clears flag and forces Energy-save mode."""
        self.device._attributes[DeviceAttributes.max_temperature] = 65.0
        self.device._attributes[DeviceAttributes.vacation_mode] = True

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.vacation_mode.value, False)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.vacation_flag is False
            assert msg.vacation_days == 0
            assert msg.mode == 0x01
            assert msg.body[23] == 65

    def test_set_vacation_days_encodes_days(self) -> None:
        """vacation_days SET keeps tsMax and marks vacation flag."""
        self.device._attributes[DeviceAttributes.max_temperature] = 65.0

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.vacation_days.value, 30)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.vacation_flag is True
            assert msg.vacation_days == 30
            assert msg.body[10] == 30  # vacation days low
            assert msg.body[23] == 65

    def test_ts_max_falls_back_when_max_missing(self) -> None:
        """Missing max_temperature still yields non-zero tsMax via MessageSet."""
        self.device._attributes[DeviceAttributes.max_temperature] = None

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.body[23] != 0

    def test_ts_max_falls_back_when_max_unconvertible(self) -> None:
        """A stored max_temperature that fails int() conversion sends tsMax=0."""

        class UnconvertibleFloat(float):
            """A float that raises when int() is attempted on it."""

            def __int__(self) -> int:
                raise ValueError("cannot convert")

        self.device._attributes[DeviceAttributes.max_temperature] = UnconvertibleFloat(
            70.0,
        )

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.ts_max == 0

    # ------------------------------------------------------------------ #
    # disinfect set_attribute                                              #
    # ------------------------------------------------------------------ #

    def test_set_disinfect_true_is_read_only(self) -> None:
        """Immediate disinfection writes are disabled."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
            mock_send.assert_not_called()

    def test_set_disinfect_true_does_not_echo_temperature(self) -> None:
        """Known disinfection_temperature must not be written."""
        self.device._attributes[DeviceAttributes.disinfection_temperature] = 67.0
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
            mock_send.assert_not_called()

    def test_set_disinfect_true_does_not_write_valid_schedule(self) -> None:
        """Toggling disinfect is intentionally read-only even with valid schedule."""
        self.device._attributes[DeviceAttributes.auto_sterilize_week] = 4
        self.device._attributes[DeviceAttributes.auto_sterilize_hour] = 18
        self.device._attributes[DeviceAttributes.auto_sterilize_minute] = 30
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
            mock_send.assert_not_called()

    def test_set_disinfect_false_is_read_only(self) -> None:
        """Disabling immediate disinfect from HA must not send the unsafe command."""
        self.device._attributes[DeviceAttributes.auto_sterilize_week] = 4
        self.device._attributes[DeviceAttributes.auto_sterilize_hour] = 18
        self.device._attributes[DeviceAttributes.auto_sterilize_minute] = 30
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, False)
            mock_send.assert_not_called()

    def test_set_disinfect_true_does_not_write_invalid_schedule(self) -> None:
        """Invalid current schedule values are not written through disinfect."""
        self.device._attributes[DeviceAttributes.auto_sterilize_week] = 133
        self.device._attributes[DeviceAttributes.auto_sterilize_hour] = 168
        self.device._attributes[DeviceAttributes.auto_sterilize_minute] = 86
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
            mock_send.assert_not_called()

    def test_process_message_drops_invalid_auto_sterilize_values(self) -> None:
        """Impossible status schedule values are not published as HA state."""

        class FakeMessage:
            auto_sterilize_week = 21
            auto_sterilize_hour = 133
            auto_sterilize_minute = 168

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")

        assert status[DeviceAttributes.auto_sterilize_week.value] is None
        assert status[DeviceAttributes.auto_sterilize_hour.value] is None
        assert status[DeviceAttributes.auto_sterilize_minute.value] is None
        assert self.device._attributes[DeviceAttributes.auto_sterilize_week] is None
        assert self.device._attributes[DeviceAttributes.auto_sterilize_hour] is None
        assert self.device._attributes[DeviceAttributes.auto_sterilize_minute] is None

    def test_process_message_publishes_valid_auto_sterilize_values(self) -> None:
        """Valid status schedule values still update HA state."""

        class FakeMessage:
            auto_sterilize_week = 4
            auto_sterilize_hour = 14
            auto_sterilize_minute = 5

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")

        assert status[DeviceAttributes.auto_sterilize_week.value] == 4
        assert status[DeviceAttributes.auto_sterilize_hour.value] == 14
        assert status[DeviceAttributes.auto_sterilize_minute.value] == 5

    # ------------------------------------------------------------------ #
    # power must survive a SET echo (midea_ac_lan#768)                    #
    # ------------------------------------------------------------------ #

    def test_set_echo_does_not_clobber_power(self) -> None:
        """A SET echo with power=False must not overwrite a trusted ON state.

        Otherwise the stale OFF is replayed into the next temperature/mode
        control frame and silently switches the unit off.
        """
        self.device._attributes[DeviceAttributes.power] = True

        class FakeSetEcho:
            message_type = MessageType.set
            power = False

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeSetEcho(),
        ):
            status = self.device.process_message(b"")

        assert self.device._attributes[DeviceAttributes.power] is True
        assert status[DeviceAttributes.power.value] is True

    def test_status_frame_updates_power(self) -> None:
        """A genuine status/notify frame still updates the power state."""
        self.device._attributes[DeviceAttributes.power] = True

        class FakeStatus:
            message_type = MessageType.notify1
            power = False

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeStatus(),
        ):
            status = self.device.process_message(b"")

        assert self.device._attributes[DeviceAttributes.power] is False
        assert status[DeviceAttributes.power.value] is False

    def test_set_power_persists_requested_state(self) -> None:
        """A power write must store the requested state immediately.

        The SET-echo guard distrusts the power bit from echoes, so the
        explicitly requested power must be persisted in set_attribute.
        Otherwise a temperature/mode write before the next genuine status
        frame would replay the stale value as an OFF command (midea_ac_lan#768).
        """
        self.device._attributes[DeviceAttributes.power] = False

        with patch.object(self.device, "build_send"):
            self.device.set_attribute(DeviceAttributes.power.value, True)

        assert self.device._attributes[DeviceAttributes.power] is True

    def test_set_power_off_persists_requested_state(self) -> None:
        """A power-off write is persisted immediately too."""
        self.device._attributes[DeviceAttributes.power] = True

        with patch.object(self.device, "build_send"):
            self.device.set_attribute(DeviceAttributes.power.value, False)

        assert self.device._attributes[DeviceAttributes.power] is False

    # ------------------------------------------------------------------ #
    # disinfection_temperature is read-only for CD                         #
    # ------------------------------------------------------------------ #

    def test_set_disinfection_temperature_is_not_settable(self) -> None:
        """Disinfection temperature does not send controlType=0x06."""
        self.device._attributes[DeviceAttributes.disinfect] = True
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(
                DeviceAttributes.disinfection_temperature.value,
                65.0,
            )
            mock_send.assert_not_called()

    # ------------------------------------------------------------------ #
    # max_temperature                                                       #
    # ------------------------------------------------------------------ #

    def test_set_max_temperature_sends_clamped_message(self) -> None:
        """max_temperature is read-only until the write payload is safe."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.max_temperature.value, 70.0)
            mock_send.assert_not_called()

    def test_set_vacation_temperature_is_not_settable(self) -> None:
        """vacation_temperature is not settable."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("vacation_temperature", 65.0)
            mock_send.assert_not_called()

    # ------------------------------------------------------------------ #
    # maintenance_reminder (official app naming)                         #
    # ------------------------------------------------------------------ #

    def test_set_maintenance_reminder_requires_weekly_schedule(self) -> None:
        """Setting maintenance_reminder must not send a command."""
        self.device._attributes[DeviceAttributes.weekly_schedule] = None
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.maintenance_reminder.value, True)
            mock_send.assert_not_called()

    def test_set_maintenance_reminder_is_read_only(self) -> None:
        """maintenance_reminder writes are disabled until the payload is safe."""
        empty_slot = {
            "effect": False,
            "opentime": 0,
            "closetime": 0,
            "temperature": 0,
            "mode": 0,
        }
        weekly_schedule = {
            day: [dict(empty_slot) for _ in range(6)] for day in range(7)
        }
        self.device._attributes[DeviceAttributes.weekly_schedule] = weekly_schedule
        self.device._attributes[DeviceAttributes.maintain_warn] = False

        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.maintenance_reminder.value, True)
            mock_send.assert_not_called()

    # ------------------------------------------------------------------ #
    # properties and query                                                #
    # ------------------------------------------------------------------ #

    def test_temperature_step_property(self) -> None:
        """Default temperature step is 1.0."""
        assert self.device.temperature_step == 1.0

    def test_build_query(self) -> None:
        """Build query returns status, weekly and daily queries."""
        queries = self.device.build_query()
        assert len(queries) == 3
        assert isinstance(queries[0], MessageQuery)
        assert isinstance(queries[1], MessageQueryWeekly)
        assert isinstance(queries[2], MessageQueryDaily)

    # ------------------------------------------------------------------ #
    # temperature conversion helpers                                       #
    # ------------------------------------------------------------------ #

    def test_value_to_temperature_old_protocol(self) -> None:
        """Old protocol decodes (value - 30) / 2."""
        assert self.device._lua_protocol == LuaProtocol.old
        assert self.device._value_to_temperature(110, False, False) == 40

    def test_value_to_temperature_fahrenheit(self) -> None:
        """Fahrenheit device state converts to celsius."""
        self.device._fahrenheit = True
        assert self.device._value_to_temperature(104, False, False) == 40.0

    def test_value_to_temperature_force_fahrenheit(self) -> None:
        """force_fahrenheit converts even when the device reports celsius."""
        assert self.device._fahrenheit is False
        assert self.device._value_to_temperature(104, True, False) == 40.0

    def test_value_to_temperature_new_protocol(self) -> None:
        """New protocol passes the value through, force_old still decodes."""
        self.device.set_customize('{"lua_protocol": "new"}')
        assert self.device._value_to_temperature(40.0, False, False) == 40.0
        assert self.device._value_to_temperature(110, False, True) == 40

    def test_temperature_to_value_old_protocol(self) -> None:
        """Old protocol encodes value * 2 + 30."""
        assert self.device._temperature_to_value(40) == 110

    def test_temperature_to_value_fahrenheit(self) -> None:
        """Fahrenheit device state converts celsius to fahrenheit."""
        self.device._fahrenheit = True
        assert self.device._temperature_to_value(40) == 104.0

    def test_temperature_to_value_new_protocol(self) -> None:
        """New protocol passes the value through."""
        self.device.set_customize('{"lua_protocol": "new"}')
        assert self.device._temperature_to_value(40.0) == 40.0

    # ------------------------------------------------------------------ #
    # process_message with real frames                                     #
    # ------------------------------------------------------------------ #

    def test_process_general_status_message(self) -> None:
        """A general status frame decodes power, mode and temperatures."""
        new_status = self.device.process_message(
            _build_message(MessageType.query, _general_body()),
        )
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.mode] == "standard"
        assert self.device.attributes[DeviceAttributes.target_temperature] == 40
        assert self.device.attributes[DeviceAttributes.current_temperature] == 35
        assert self.device.attributes[DeviceAttributes.outdoor_temperature] == 20
        assert self.device.attributes[DeviceAttributes.condenser_temperature] == 30
        assert self.device.attributes[DeviceAttributes.compressor_temperature] == 40
        assert self.device.attributes[DeviceAttributes.max_temperature] == 65
        assert self.device.attributes[DeviceAttributes.min_temperature] == 35
        assert self.device.attributes[DeviceAttributes.top_temperature] == 45.0
        assert self.device.attributes[DeviceAttributes.wind] == "middle"
        assert self.device.attributes[DeviceAttributes.water_level] == 50
        assert self.device.attributes[DeviceAttributes.error_code] == 3
        assert self.device.attributes[DeviceAttributes.disinfection_temperature] == 65.0
        assert self.device.attributes[DeviceAttributes.fahrenheit] is False
        assert new_status[DeviceAttributes.mode.value] == "standard"

    def test_process_vacation_status_message(self) -> None:
        """Vacation bit in body[35] maps to Vacation mode and days."""
        body = _general_body()
        body[35] = 0x01
        body[36] = 0x00
        body[37] = 30
        self.device.process_message(_build_message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.mode] == "vacation"
        assert self.device.attributes[DeviceAttributes.vacation_mode] is True
        assert self.device.attributes[DeviceAttributes.vacation_days] == 30

    def test_process_fahrenheit_status_message(self) -> None:
        """Fahrenheit flag switches temperature decoding to F -> C."""
        body = _general_body()
        body[35] = 0x80  # fahrenheit
        body[3] = 104  # -> 40.0 C
        body[4] = 95  # -> 35.0 C
        body[10] = 149  # -> 65.0 C
        body[11] = 95  # -> 35.0 C
        self.device.process_message(_build_message(MessageType.query, body))
        assert self.device._fahrenheit is True
        assert self.device.attributes[DeviceAttributes.fahrenheit] is True
        assert self.device.attributes[DeviceAttributes.target_temperature] == 40.0
        assert self.device.attributes[DeviceAttributes.current_temperature] == 35.0
        assert self.device.attributes[DeviceAttributes.max_temperature] == 65.0

    def test_process_set_echo_updates_fields(self) -> None:
        """A controlType=0x01 SET echo stores fields for later writes."""
        # Pre-set power so the SET echo guard doesn't change test behavior
        self.device._attributes[DeviceAttributes.power] = True
        body = bytearray([0x01, 0x01, 0x01, 0x02, 110, 1, 2, 3, 0x10, 0x00, 30])
        new_status = self.device.process_message(
            _build_message(MessageType.set, body),
        )
        assert self.device._fields == {
            "trValue": 1,
            "openPTC": 2,
            "ptcTemp": 3,
            "byte8": 0x10,
        }
        # Power is not updated from SET echoes (midea_ac_lan#768 fix)
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.mode] == "standard"
        assert self.device.attributes[DeviceAttributes.target_temperature] == 40
        assert self.device.attributes[DeviceAttributes.vacation_mode] is True
        assert self.device.attributes[DeviceAttributes.vacation_days] == 30
        assert new_status[DeviceAttributes.vacation_days.value] == 30

    def test_sanitize_set_fields_drops_unconvertible_tr_value(self) -> None:
        """A non-numeric trValue echo is dropped instead of raising."""
        clean = MideaCDDevice._sanitize_set_fields(
            {"trValue": "abc", "openPTC": 1, "ptcTemp": 2, "byte8": 0x10},
        )
        assert clean == {}

    def test_sanitize_set_fields_keeps_valid_tr_value_only(self) -> None:
        """A valid trValue survives while unsafe SET echo fields are dropped."""
        clean = MideaCDDevice._sanitize_set_fields(
            {"trValue": "5", "openPTC": 1, "ptcTemp": 2, "byte8": 0x10},
        )
        assert clean == {"trValue": "5"}

    def test_process_weekly_schedule_message(self) -> None:
        """A weekly schedule frame stores the parsed schedule."""
        body = bytearray(177)
        body[0] = 0x02
        body[2] = 0x01  # day 0 timer 1 effect
        body[9] = 10  # opentime
        body[10] = 20  # closetime
        body[11] = 45  # temperature
        body[12] = 2  # mode
        self.device.process_message(_build_message(MessageType.query, body))
        schedule = self.device.attributes[DeviceAttributes.weekly_schedule]
        assert schedule is not None
        assert schedule[0][0] == {
            "effect": True,
            "opentime": 10,
            "closetime": 20,
            "temperature": 45,
            "mode": 2,
        }
        assert schedule[6][5]["effect"] is False

    def test_process_daily_timer_message(self) -> None:
        """A daily timer frame stores the parsed timer programme."""
        body = bytearray(40)
        body[0] = 0x03
        body[2] = 2  # amount
        body[3] = 0x41  # timer 1 effect + single_timer_on
        body[4] = 6
        body[5] = 30
        body[6] = 8
        body[7] = 15
        body[8] = 45
        body[9] = 2
        self.device.process_message(_build_message(MessageType.query, body))
        schedule = self.device.attributes[DeviceAttributes.daily_timer_schedule]
        assert schedule is not None
        assert schedule["amount"] == 2
        assert schedule["single_timer_on"] is True
        assert schedule["single_timer_off"] is False
        assert schedule["timers"][0] == {
            "effect": True,
            "openhour": 6,
            "openmin": 30,
            "closehour": 8,
            "closemin": 15,
            "temperature": 45,
            "mode": 2,
        }

    def test_daily_timer_response_does_not_overwrite_temperatures(self) -> None:
        """body_type 03 contributes schedule data, not competing temperatures."""
        self.device.set_customize('{"lua_protocol": "new"}')
        status_body = _general_body()
        status_body[3] = 55
        status_body[4] = 30
        status = self.device.process_message(
            _build_message(MessageType.query, status_body),
        )
        current = self.device.attributes[DeviceAttributes.current_temperature]
        target = self.device.attributes[DeviceAttributes.target_temperature]

        timer_body = bytearray(40)
        timer_body[0] = 0x03
        timer_body[2] = 1
        timer_body[4] = 6
        timer_status = self.device.process_message(
            _build_message(MessageType.query, timer_body),
        )

        assert status[DeviceAttributes.current_temperature.value] == current
        assert status[DeviceAttributes.target_temperature.value] == target
        assert DeviceAttributes.current_temperature.value not in timer_status
        assert DeviceAttributes.target_temperature.value not in timer_status
        assert self.device.attributes[DeviceAttributes.current_temperature] == current
        assert self.device.attributes[DeviceAttributes.target_temperature] == target

    # ------------------------------------------------------------------ #
    # process_message corner cases                                         #
    # ------------------------------------------------------------------ #

    def test_process_message_unknown_mode_is_skipped(self) -> None:
        """Unrecognised mode values do not corrupt the stored mode."""

        class FakeMessage:
            mode = 8

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")
        assert DeviceAttributes.mode.value not in status
        assert self.device.attributes[DeviceAttributes.mode] is None

    def test_process_message_bad_temperature_keeps_existing(self) -> None:
        """Unparsable temperature values preserve the existing reading."""
        self.device.set_customize('{"lua_protocol": "new"}')

        class FakeMessage:
            max_temperature = "bad"

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")
        assert status[DeviceAttributes.max_temperature.value] == 65.0
        assert self.device.attributes[DeviceAttributes.max_temperature] == 65.0

    def test_process_message_zero_temperature_without_existing(self) -> None:
        """Zero temperatures are stored when no previous reading exists."""
        self.device.set_customize('{"lua_protocol": "new"}')
        assert self.device.attributes[DeviceAttributes.current_temperature] is None

        class FakeMessage:
            current_temperature = 0.0

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")
        assert status[DeviceAttributes.current_temperature.value] == 0.0
        assert self.device.attributes[DeviceAttributes.current_temperature] == 0.0

    def test_process_message_disinfection_temperature_none_skipped(self) -> None:
        """None disinfection temperature preserves the previous reading."""
        self.device._attributes[DeviceAttributes.disinfection_temperature] = 67.0

        class FakeMessage:
            disinfection_temperature = None

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")
        assert DeviceAttributes.disinfection_temperature.value not in status
        assert self.device.attributes[DeviceAttributes.disinfection_temperature] == 67.0

    def test_process_message_empty_sterilize_schedule_fields_are_skipped(self) -> None:
        """None sterilize schedule values do not publish updates."""
        self.device._attributes[DeviceAttributes.auto_sterilize_week] = 4
        self.device._attributes[DeviceAttributes.auto_sterilize_hour] = 8
        self.device._attributes[DeviceAttributes.auto_sterilize_minute] = 15

        class FakeMessage:
            auto_sterilize_week = None
            auto_sterilize_hour = None
            auto_sterilize_minute = None

        with patch(
            "midealan.devices.cd.MessageCDResponse",
            return_value=FakeMessage(),
        ):
            status = self.device.process_message(b"")
        assert DeviceAttributes.auto_sterilize_week.value not in status
        assert DeviceAttributes.auto_sterilize_hour.value not in status
        assert DeviceAttributes.auto_sterilize_minute.value not in status
        assert self.device.attributes[DeviceAttributes.auto_sterilize_week] == 4
        assert self.device.attributes[DeviceAttributes.auto_sterilize_hour] == 8
        assert self.device.attributes[DeviceAttributes.auto_sterilize_minute] == 15

    @pytest.mark.parametrize(
        "model",
        ["RSJRAC06", "RSJRAC07", "RSJRAC08", "2530001N"],
    )
    @pytest.mark.parametrize(
        ("fahrenheit", "raw_current"),
        [(False, 110), (True, 104)],
    )
    def test_process_message_forced_conversions(
        self,
        model: str,
        *,
        fahrenheit: bool,
        raw_current: int,
    ) -> None:
        """Mixed-protocol models retain their sensor decoding exceptions."""
        device = _make_device(model=model)
        assert device._lua_protocol == LuaProtocol.new
        body = _general_body()
        body[35] = 0x80 if fahrenheit else 0x00
        body[8] = 68
        body[4] = raw_current
        signed = model in {"2530001N", "RSJRAC08"}
        if signed:
            body[55] = 1
        status = device.process_message(_build_message(MessageType.query, body))
        expected_outdoor = 19.0 if signed else 20.0
        expected_current = (40.0, 37.0)[fahrenheit] if signed else 40.0
        assert status[DeviceAttributes.outdoor_temperature.value] == expected_outdoor
        assert status[DeviceAttributes.current_temperature.value] == expected_current

    def test_process_message_rsjrac08_real_status_frame(self) -> None:
        """Decode a real RSJRAC08 status frame (Midea MCHW-50VN3A).

        Device protocol V3, message protocol 8, minus_support (body[55]) = 1.
        Setpoint, limits, tank and coil temperatures are raw degrees C (new
        protocol); current and outdoor use the capability-gated half-degree
        decoding verified for 2530001N: 148 -> 59 C (agreeing with the 58/57 C
        top/bottom sensors) and 78 -> 24 C.
        """
        device = _make_device(model="RSJRAC08")
        assert device._lua_protocol == LuaProtocol.new
        frame = bytes.fromhex(
            "aa4bcd000000000008030101113c943a39164e23412b0600160016000600003c"
            "00000000000003090000000000000000413f3f3f3f3f3f01170000000000040100"
            "01024641463c41000000ef",
        )
        status = device.process_message(frame)
        assert status[DeviceAttributes.target_temperature.value] == 60.0
        assert status[DeviceAttributes.min_temperature.value] == 43.0
        assert status[DeviceAttributes.max_temperature.value] == 65.0
        assert status[DeviceAttributes.current_temperature.value] == 59.0
        assert status[DeviceAttributes.top_temperature.value] == 58.0
        assert status[DeviceAttributes.bottom_temperature.value] == 57.0
        assert status[DeviceAttributes.condenser_temperature.value] == 22.0
        assert status[DeviceAttributes.compressor_temperature.value] == 35.0
        assert status[DeviceAttributes.outdoor_temperature.value] == 24.0
        assert status[DeviceAttributes.support_negative_temperature.value] is True

    def test_rsjrac08_power_write_preserves_target_and_max(self) -> None:
        """A write after decoding the real frame sends 60/65 C, not garbage (#1015)."""
        device = _make_device(model="RSJRAC08")
        frame = bytes.fromhex(
            "aa4bcd000000000008030101113c943a39164e23412b0600160016000600003c"
            "00000000000003090000000000000000413f3f3f3f3f3f01170000000000040100"
            "01024641463c41000000ef",
        )
        device.process_message(frame)

        with patch.object(device, "build_send") as mock_send:
            device.set_attribute(DeviceAttributes.power.value, False)

        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert message.use_old_protocol is False
        assert message.body[4] == 60
        assert message.body[23] == 65

    def test_2530001n_power_write_preserves_new_protocol_temperatures(self) -> None:
        """A power write keeps the model's correctly decoded target and maximum."""
        device = _make_device(model="2530001N")
        body = _general_body()
        body[3] = 50
        body[4] = 128
        body[8] = 68
        body[55] = 1
        body[10] = 65
        body[11] = 35

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.target_temperature.value] == 50
        assert status[DeviceAttributes.current_temperature.value] == 49
        assert status[DeviceAttributes.outdoor_temperature.value] == 19
        assert status[DeviceAttributes.max_temperature.value] == 65
        assert status[DeviceAttributes.min_temperature.value] == 35

        with patch.object(device, "build_send") as mock_send:
            device.set_attribute(DeviceAttributes.power.value, False)

        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert message.use_old_protocol is False
        assert message.body[4] == 50
        assert message.body[23] == 65

    @pytest.mark.parametrize("model", ["2530001N", "RSJRAC08"])
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (128, 49.0),
            (129, 49.5),
            (189, 79.5),
            (190, -48.0),
            (254, -16.0),
            (255, 112.5),
        ],
    )
    def test_2530001n_negative_temperature_sensor_decoding(
        self,
        model: str,
        raw: int,
        expected: float,
    ) -> None:
        """Decode signed-model tank values as the official plugin does."""
        device = _make_device(model=model)
        body = _general_body()
        body[4] = raw
        body[55] = 1

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == expected

    def test_2530001n_current_temperature_is_raw_without_negative_support(self) -> None:
        """The official plugin displays raw tank values without the flag."""
        device = _make_device(model="2530001N")
        body = _general_body()
        body[4] = 128
        body[55] = 0

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 128.0

    def test_negative_temperature_model_registry_applies_decoder(self) -> None:
        """Models added to the registry reuse the signed decoder."""
        device = _make_device(model="verified_signed_model")
        body = _general_body()
        body[4] = 129
        body[55] = 1

        with patch.object(
            MideaCDDevice,
            "_negative_temperature_models",
            frozenset({"verified_signed_model"}),
        ):
            status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 49.5

    def test_2530001n_initial_zero_current_temperature_is_stored(self) -> None:
        """An initial uninitialized tank reading remains zero."""
        device = _make_device(model="2530001N")
        body = _general_body()
        body[4] = 0
        body[55] = 1

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 0.0
        assert device.attributes[DeviceAttributes.current_temperature] == 0.0

    def test_2530001n_short_status_preserves_positive_current_temperature(
        self,
    ) -> None:
        """Fallback decoding does not replace a known tank reading."""
        device = _make_device(model="2530001N")
        device._attributes[DeviceAttributes.current_temperature] = 49.0
        body = _general_body()[:55]
        body[4] = 0

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 49.0
        assert device.attributes[DeviceAttributes.current_temperature] == 49.0

    def test_2530001n_short_status_preserves_value_on_invalid_conversion(
        self,
    ) -> None:
        """A nonpositive fallback conversion preserves a known reading."""
        device = _make_device(model="2530001N")
        device._attributes[DeviceAttributes.current_temperature] = 49.0
        body = _general_body()[:55]
        body[4] = 10

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 49.0
        assert device.attributes[DeviceAttributes.current_temperature] == 49.0

    def test_2530001n_zero_current_temperature_preserves_positive_value(self) -> None:
        """An uninitialized tank reading does not replace a known value."""
        device = _make_device(model="2530001N")
        body = _general_body()
        body[4] = 128
        body[55] = 1
        device.process_message(_build_message(MessageType.query, body))

        body[4] = 0
        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == 49.0
        assert device.attributes[DeviceAttributes.current_temperature] == 49.0

    def test_2530001n_zero_current_temperature_preserves_negative_value(self) -> None:
        """An uninitialized tank reading preserves a signed value."""
        device = _make_device(model="2530001N")
        body = _general_body()
        body[4] = 190
        body[55] = 1
        device.process_message(_build_message(MessageType.query, body))

        body[4] = 0
        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.current_temperature.value] == -48.0
        assert device.attributes[DeviceAttributes.current_temperature] == -48.0

    @pytest.mark.parametrize("model", ["2530001N", "RSJRAC08"])
    @pytest.mark.parametrize(
        ("negative_support", "raw", "expected"),
        [
            (True, 68, 19.0),
            (True, 189, 79.5),
            (True, 190, -48.0),
            (True, 254, -16.0),
            (True, 255, 112.5),
            (False, 68, 9.0),
        ],
    )
    def test_2530001n_outdoor_temperature_uses_capability_encoding(
        self,
        model: str,
        negative_support: bool,
        raw: int,
        expected: float,
    ) -> None:
        """Decode signed-model outdoor values using the reported capability."""
        device = _make_device(model=model)
        body = _general_body()
        body[8] = raw
        body[55] = int(negative_support)

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.outdoor_temperature.value] == expected

    def test_2530001n_unknown_negative_support_keeps_verified_fallback(self) -> None:
        """Keep PR #225 decoding when a short status omits the capability."""
        device = _make_device(model="2530001N")
        body = _general_body()[:55]
        body[8] = 68

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.outdoor_temperature.value] == 20.0

    def test_2530001n_active_mode_powers_on_and_updates_cached_state(self) -> None:
        """Selecting an active mode starts the heater and prevents stale writes."""
        device = _make_device(model="2530001N")
        device._attributes[DeviceAttributes.max_temperature_lower_limit] = 38.0
        device._attributes[DeviceAttributes.max_temperature_upper_limit] = 70.0
        device._attributes[DeviceAttributes.power] = False
        device._attributes[DeviceAttributes.mode] = "economy"
        device._attributes[DeviceAttributes.target_temperature] = 50.0
        device._attributes[DeviceAttributes.max_temperature] = 65.0

        with patch.object(device, "build_send") as mock_send:
            device.set_attribute(DeviceAttributes.mode.value, "hybrid")
            device.set_attribute(DeviceAttributes.target_temperature.value, 60.0)

        assert mock_send.call_count == 2
        mode_message = mock_send.call_args_list[0].args[0]
        assert mode_message.body[2] == 0x01
        assert mode_message.body[3] == 0x02
        assert mode_message.body[4] == 50
        assert mode_message.body[23] == 65
        assert device.attributes[DeviceAttributes.power] is True
        assert device.attributes[DeviceAttributes.mode] == "hybrid"

        temperature_message = mock_send.call_args_list[1].args[0]
        assert temperature_message.body[2] == 0x01
        assert temperature_message.body[3] == 0x02
        assert temperature_message.body[4] == 60

    @pytest.mark.parametrize("message_type", [MessageType.query, MessageType.notify2])
    @pytest.mark.parametrize(
        ("body_hex", "current", "top", "bottom", "outdoor", "condenser", "compressor"),
        [
            # Key 0xCD status bytes for RSJ000CB validation:
            # body[5]=T5U/top, body[6]=T5L/bottom, body[7]=T3/condenser,
            # body[8]=T4/outdoor, body[9]=TP/compressor.
            pytest.param(
                "01011531348773495f19462609001100110508000031000000000000"
                "070300000000030000000000000000000000060b0000000000",
                52.0,
                52.5,
                42.5,
                22.5,
                21.5,
                25.0,
                id="first-log",
            ),
            pytest.param(
                "01019531348787345c50462609001100110508000031000000000000"
                "870300000000040000000000000000000000060b0000000000",
                52.0,
                52.5,
                52.5,
                21.0,
                11.0,
                80.0,
                id="log2",
            ),
            pytest.param(
                "01019531358887345c50462609001100110508000031000000000000"
                "870300000000040000000000000000000000060b0000000000",
                53.0,
                53.0,
                52.5,
                21.0,
                11.0,
                80.0,
                id="log2-tank-change",
            ),
        ],
    )
    def test_process_message_mixed_temperatures_rsj000cb(
        self,
        message_type: MessageType,
        body_hex: str,
        current: float,
        top: float,
        bottom: float,
        outdoor: float,
        condenser: float,
        compressor: float,
    ) -> None:
        """Recorded RSJ000CB frames decode validated mixed sensor fields."""
        device = _make_device(model="RSJ000CB")
        assert device._lua_protocol == LuaProtocol.new
        body = bytearray.fromhex(body_hex)
        status = device.process_message(_build_message(message_type, body))

        assert status[DeviceAttributes.target_temperature.value] == 49.0
        assert status[DeviceAttributes.current_temperature.value] == current
        assert status[DeviceAttributes.max_temperature.value] == 70.0
        assert status[DeviceAttributes.min_temperature.value] == 38.0
        assert status[DeviceAttributes.top_temperature.value] == top
        assert status[DeviceAttributes.bottom_temperature.value] == bottom
        assert status[DeviceAttributes.outdoor_temperature.value] == outdoor
        assert status[DeviceAttributes.condenser_temperature.value] == condenser
        assert status[DeviceAttributes.compressor_temperature.value] == compressor
        assert status[DeviceAttributes.compressor_status.value] is False
        assert status[DeviceAttributes.water_level.value] == body[34]
        assert status[DeviceAttributes.fahrenheit.value] is False

    def test_process_message_mixed_sensors_ignore_fahrenheit_flag(
        self,
    ) -> None:
        """RSJ000CB mixed sensors ignore the message display-unit flag."""
        device = _make_device(model="RSJ000CB")
        body = _general_body()
        body[3] = 104
        body[4] = 104
        body[5] = 135
        body[6] = 115
        body[7] = 73
        body[8] = 92
        body[9] = 23
        body[10] = 149
        body[11] = 95
        body[35] = 0x80
        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.fahrenheit.value] is True
        assert status[DeviceAttributes.target_temperature.value] == 40.0
        assert status[DeviceAttributes.current_temperature.value] == 40.0
        assert status[DeviceAttributes.max_temperature.value] == 65.0
        assert status[DeviceAttributes.min_temperature.value] == 35.0
        assert status[DeviceAttributes.top_temperature.value] == 52.5
        assert status[DeviceAttributes.bottom_temperature.value] == 42.5
        assert status[DeviceAttributes.condenser_temperature.value] == 21.5
        assert status[DeviceAttributes.outdoor_temperature.value] == 21.0
        assert status[DeviceAttributes.compressor_temperature.value] == -5.0

    def test_process_message_mixed_condenser_latest_review_value(
        self,
    ) -> None:
        """PR #197 real-device review: T3 raw 66 decodes to 18 C."""
        device = _make_device(model="RSJ000CB")
        body = _general_body()
        body[7] = 66
        body[8] = 83
        status = device.process_message(_build_message(MessageType.query, body))
        assert status[DeviceAttributes.condenser_temperature.value] == 18.0
        assert status[DeviceAttributes.outdoor_temperature.value] == 16.5

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(40, -5.0), (50, 0.0), (60, 5.0), (61, 5.5), (89, 19.5)],
    )
    def test_process_message_mixed_outdoor_has_no_raw_threshold(
        self,
        raw: int,
        expected: float,
    ) -> None:
        """The outdoor candidate preserves half degrees and negative values."""
        device = _make_device(model="RSJ000CB")
        body = _general_body()
        body[8] = raw
        status = device.process_message(_build_message(MessageType.query, body))
        assert status[DeviceAttributes.outdoor_temperature.value] == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(20, -5.0), (30, 0.0), (40, 5.0), (60, 15.0), (61, 15.5)],
    )
    def test_process_message_mixed_sensor_has_no_raw_threshold(
        self,
        raw: int,
        expected: float,
    ) -> None:
        """T5U/T5L/T3 decode values at or below the bridge cutoff."""
        device = _make_device(model="RSJ000CB")
        body = _general_body()
        body[5] = raw
        body[6] = raw
        body[7] = raw
        status = device.process_message(_build_message(MessageType.query, body))
        assert status[DeviceAttributes.top_temperature.value] == expected
        assert status[DeviceAttributes.bottom_temperature.value] == expected
        assert status[DeviceAttributes.condenser_temperature.value] == expected

    @pytest.mark.parametrize(
        "model",
        ["test_model", "RSJ18RD2", "RSJRAC01", "RSJRAC06", "RSJRAC07", "RSJRAC08"],
    )
    @pytest.mark.parametrize("fahrenheit", [False, True])
    def test_process_message_other_models_keep_raw_tank_temperatures(
        self,
        model: str,
        *,
        fahrenheit: bool,
    ) -> None:
        """Only RSJ000CB gets the mixed-encoding tank correction."""
        device = _make_device(model=model)
        body = _general_body()
        body[5] = 135
        body[6] = 115
        body[35] = 0x80 if fahrenheit else 0x00
        status = device.process_message(_build_message(MessageType.query, body))
        assert status[DeviceAttributes.top_temperature.value] == 135.0
        assert status[DeviceAttributes.bottom_temperature.value] == 115.0

    def test_process_message_other_new_models_keep_condenser_generic(self) -> None:
        """The PR #197 T3 scaling remains scoped to RSJ000CB only."""
        device = _make_device(model="RSJRAC01")
        body = _general_body()
        body[7] = 66
        status = device.process_message(_build_message(MessageType.query, body))
        assert status[DeviceAttributes.condenser_temperature.value] == 66.0

    def test_rsj000cb_target_write_keeps_new_protocol_encoding(self) -> None:
        """Mixed sensor offsets never affect the target-temperature write."""
        device = _make_device(model="RSJ000CB")
        body = _general_body()
        body[3] = 49
        body[4] = 52
        body[10] = 70
        body[11] = 38
        device.process_message(_build_message(MessageType.query, body))
        with patch.object(device, "build_send") as mock_send:
            device.set_attribute(DeviceAttributes.target_temperature.value, 50.0)
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert message.use_old_protocol is False
            assert message.body[4] == 50
            assert message.body[23] == 70

    # ------------------------------------------------------------------ #
    # set_attribute branches                                               #
    # ------------------------------------------------------------------ #

    def test_set_power_target_temperature_fallback_to_min(self) -> None:
        """Invalid stored target temperature falls back to min_temperature."""
        self.device._attributes[DeviceAttributes.target_temperature] = None
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.target_temperature == 35.0

    def test_set_power_target_temperature_fallback_default(self) -> None:
        """Invalid target and min temperatures fall back to 40.0."""
        self.device._attributes[DeviceAttributes.target_temperature] = None
        self.device._attributes[DeviceAttributes.min_temperature] = None
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.target_temperature == 40.0

    def test_set_power_with_vacation_mode_state(self) -> None:
        """Stored Vacation mode is never sent as a modeValue."""
        self.device._attributes[DeviceAttributes.mode] = "vacation"
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.mode == 0x00

    def test_set_power_with_known_mode_state(self) -> None:
        """Stored Standard mode maps back to its key."""
        self.device._attributes[DeviceAttributes.mode] = "standard"
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.mode == 0x02

    def test_set_power_with_none_string_mode_state(self) -> None:
        """Stored "none" mode maps to 0x00."""
        self.device._attributes[DeviceAttributes.mode] = "none"
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.mode == 0x00

    def test_set_mode_invalid_value_not_sent(self) -> None:
        """Invalid mode values do not send a command."""
        with (
            patch.object(self.device, "build_send") as mock_send,
            patch("midealan.devices.cd._LOGGER.warning") as mock_warning,
        ):
            self.device.set_attribute(DeviceAttributes.mode.value, "Bogus")
            mock_send.assert_not_called()
            mock_warning.assert_called_once_with(
                "[%s] Invalid mode value: %s, not sending command",
                self.device.device_id,
                "Bogus",
            )

    def test_set_mode_standard(self) -> None:
        """A valid mode value is mapped, starts the heater, and is cached."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "standard")
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.mode == 0x02
            assert msg.power is True
            assert self.device.attributes[DeviceAttributes.power] is True
            assert self.device.attributes[DeviceAttributes.mode] == "standard"

    def test_set_mode_send_failure_preserves_cached_state(self) -> None:
        """A failed active-mode send does not optimistically change the cache."""
        self.device._attributes[DeviceAttributes.power] = False
        self.device._attributes[DeviceAttributes.mode] = "energy_save"

        with (
            patch.object(self.device, "build_send", side_effect=SocketException),
            pytest.raises(SocketException),
        ):
            self.device.set_attribute(DeviceAttributes.mode.value, "standard")

        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.mode] == "energy_save"

    def test_set_mode_none_does_not_change_power(self) -> None:
        """Protocol mode None remains distinct from the power control."""
        self.device._attributes[DeviceAttributes.power] = True
        self.device._attributes[DeviceAttributes.mode] = "standard"
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "none")
            self.device.set_attribute(DeviceAttributes.target_temperature.value, 42.0)

        assert mock_send.call_count == 2
        mode_message = mock_send.call_args_list[0].args[0]
        assert mode_message.mode == 0x00
        assert mode_message.power is True
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.mode] == "none"

        temperature_message = mock_send.call_args_list[1].args[0]
        assert temperature_message.mode == 0x00
        assert temperature_message.power is True

    def test_set_target_temperature_attribute(self) -> None:
        """Setting the target temperature places the value in the message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(
                DeviceAttributes.target_temperature.value,
                42.0,
            )
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.target_temperature == 42.0

    def test_enable_vacation_uses_current_days(self) -> None:
        """Enabling vacation reuses the stored vacation days."""
        self.device._attributes[DeviceAttributes.vacation_days] = 30
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.vacation_mode.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.vacation_flag is True
            assert msg.vacation_days == 30

    def test_enable_vacation_default_days(self) -> None:
        """Enabling vacation without stored days uses the default."""
        self.device._attributes[DeviceAttributes.vacation_days] = 0
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.vacation_mode.value, True)
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert msg.vacation_flag is True
            assert msg.vacation_days == 100

    # ------------------------------------------------------------------ #
    # set_customize                                                        #
    # ------------------------------------------------------------------ #

    def test_set_customize_temperature_step(self) -> None:
        """Customize can override the temperature step."""
        self.device.set_customize('{"temperature_step": 0.5}')
        assert self.device.temperature_step == 0.5

    def test_set_customize_lua_protocol_new(self) -> None:
        """Customize can force the new lua protocol."""
        self.device.set_customize('{"lua_protocol": "new"}')
        assert self.device._lua_protocol == LuaProtocol.new

    def test_set_customize_lua_protocol_bool_true(self) -> None:
        """Boolean lua_protocol true maps to new."""
        self.device.set_customize('{"lua_protocol": true}')
        assert self.device._lua_protocol == LuaProtocol.new

    def test_set_customize_lua_protocol_bool_false(self) -> None:
        """Boolean lua_protocol false maps to old."""
        self.device.set_customize('{"lua_protocol": false}')
        assert self.device._lua_protocol == LuaProtocol.old

    def test_set_customize_invalid_json(self) -> None:
        """Invalid customize JSON keeps the defaults."""
        self.device.set_customize("{bad json")
        assert self.device.temperature_step == 1.0
        assert self.device._lua_protocol == LuaProtocol.old

    @pytest.mark.parametrize(
        "model",
        ["RSJ000CB", "RSJRAC01", "RSJRAC06", "RSJRAC07", "RSJRAC08", "2530001N"],
    )
    def test_auto_lua_protocol_resolves_new(self, model: str) -> None:
        """Known new-protocol models resolve the auto Lua protocol to new."""
        device = _make_device(model=model)
        assert device._lua_protocol == LuaProtocol.new


class TestMideaCDExtendedDevice:
    """Extended controls are enabled by reported protocol capabilities."""

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Create a generic CD and mark it extended through reported limits."""
        self.device = _make_device()
        self.device._attributes[DeviceAttributes.max_temperature_lower_limit] = 35.0
        self.device._attributes[DeviceAttributes.max_temperature_upper_limit] = 70.0

    def test_official_mode_names_and_b1_query(self) -> None:
        """Capabilities expose NetHome mode labels and the B1 query."""
        assert self.device.preset_modes == [
            "economy",
            "hybrid",
            "e_heater",
            "smart",
        ]
        queries = self.device.build_query()
        assert len(queries) == 4
        assert isinstance(queries[-1], MessageQueryB1)

    def test_false_capabilities_do_not_enable_extended_protocol(self) -> None:
        """Only positive capability evidence enables extended semantics."""
        device = _make_device()
        device._attributes[DeviceAttributes.support_boost_mode] = False
        device._attributes[DeviceAttributes.support_silent_mode] = False

        assert device._is_extended_water_heater() is False
        device._attributes[DeviceAttributes.new_version_water_heater] = True
        assert device._is_extended_water_heater() is True

    def test_optional_modes_follow_reported_capabilities(self) -> None:
        """Optional modes appear only after their capability is reported."""
        self.device._attributes[DeviceAttributes.support_heat_pump_mode] = True
        self.device._attributes[DeviceAttributes.support_boost_mode] = True
        self.device._attributes[DeviceAttributes.support_silent_mode] = True
        assert self.device.preset_modes == [
            "economy",
            "hybrid",
            "e_heater",
            "smart",
            "heat_pump",
            "boost",
            "silent",
        ]

    def test_baseline_modes_follow_explicit_capabilities(self) -> None:
        """Explicitly unsupported baseline modes are not advertised."""
        self.device._attributes[DeviceAttributes.support_electric_mode] = False
        self.device._attributes[DeviceAttributes.support_smart_mode] = False

        assert self.device.preset_modes == ["economy", "hybrid"]

    def test_disinfection_write_uses_extended_payload(self) -> None:
        """Immediate disinfection preserves schedule and setpoint."""
        self.device._attributes[DeviceAttributes.disinfection_temperature] = 67.0
        self.device._attributes[DeviceAttributes.auto_sterilize_week] = 4
        self.device._attributes[DeviceAttributes.auto_sterilize_hour] = 14
        self.device._attributes[DeviceAttributes.auto_sterilize_minute] = 5
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetSterilize)
        assert message.body == bytearray([0x06, 0x01, 0x80, 4, 14, 5, 67])

    def test_disinfection_defaults_temperature_and_rejects_mapping(self) -> None:
        """Extended disinfection has a safe default and rejects mappings."""
        self.device._attributes[DeviceAttributes.disinfection_temperature] = None
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.disinfect.value, True)
            message = mock_send.call_args.args[0]
            assert message.disinfection_temperature == 60.0
            mock_send.reset_mock()
            self.device.set_attribute(DeviceAttributes.disinfect.value, {})
            mock_send.assert_not_called()

    def test_schedule_writes_require_support_and_mapping(self) -> None:
        """Weekly and daily mappings use their dedicated message types."""
        weekly_schedule = {0: [{"opentime": "6"}]}
        daily_schedule = {"amount": "1", "timers": [{"openhour": "6"}]}
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(
                DeviceAttributes.weekly_schedule.value,
                weekly_schedule,
            )
            weekly = mock_send.call_args.args[0]
            assert isinstance(weekly, MessageSetWeekly)
            assert weekly.weekly_schedule == weekly_schedule
            self.device.set_attribute(
                DeviceAttributes.daily_timer_schedule.value,
                daily_schedule,
            )
            daily = mock_send.call_args.args[0]
            assert isinstance(daily, MessageSetDaily)
            assert daily.daily_timer_schedule == daily_schedule
            mock_send.reset_mock()
            self.device.set_attribute(DeviceAttributes.weekly_schedule.value, True)
            mock_send.assert_not_called()

    @pytest.mark.parametrize(
        ("attribute", "schedule"),
        [
            (DeviceAttributes.daily_timer_schedule, {"timers": None}),
            (DeviceAttributes.daily_timer_schedule, {"timers": [None]}),
            (DeviceAttributes.daily_timer_schedule, {"amount": None}),
            (DeviceAttributes.daily_timer_schedule, {"amount": True}),
            (DeviceAttributes.daily_timer_schedule, {"single_timer_on": 1}),
            (DeviceAttributes.daily_timer_schedule, {"single_timer_off": "false"}),
            (
                DeviceAttributes.daily_timer_schedule,
                {"timers": [{"openhour": None}]},
            ),
            (DeviceAttributes.daily_timer_schedule, {"timers": [{"effect": 1}]}),
            (DeviceAttributes.weekly_schedule, {0: None}),
            (DeviceAttributes.weekly_schedule, {0: [None]}),
            (DeviceAttributes.weekly_schedule, {"0": []}),
            (DeviceAttributes.weekly_schedule, {0: [{"opentime": None}]}),
            (DeviceAttributes.weekly_schedule, {0: [{"mode": False}]}),
            (DeviceAttributes.weekly_schedule, {0: [{"effect": "false"}]}),
        ],
    )
    def test_schedule_writes_reject_invalid_timer_data(
        self,
        attribute: DeviceAttributes,
        schedule: dict[object, object],
    ) -> None:
        """Malformed nested timer collections never build a control frame."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(attribute.value, schedule)
        mock_send.assert_not_called()

    def test_scalar_controls_reject_mappings(self) -> None:
        """Ordinary scalar controls never accept schedule-like mappings."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.power.value, {})
            self.device.set_attribute(
                DeviceAttributes.maintenance_reminder.value,
                {"enabled": True},
            )
            self.device.set_attribute(
                DeviceAttributes.maintain_warn_tag.value,
                {"enabled": True},
            )
        mock_send.assert_not_called()

    def test_max_temperature_is_clamped_to_reported_limit(self) -> None:
        """Maximum target temperature uses BasicControl byte 23."""
        self.device._attributes[DeviceAttributes.max_temperature_lower_limit] = 40.0
        self.device._attributes[DeviceAttributes.max_temperature_upper_limit] = 68.0
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.max_temperature.value, 75.0)
        message = mock_send.call_args.args[0]
        assert message.body[23] == 68

    def test_max_temperature_clamps_target_and_schedule_mode(self) -> None:
        """Reducing the maximum also clamps target; schedule mode stays 0..2."""
        self.device._attributes[DeviceAttributes.target_temperature] = 69.0
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.max_temperature.value, 65.0)
            maximum = mock_send.call_args.args[0]
            assert maximum.target_temperature == 65.0
            self.device.set_attribute(DeviceAttributes.schedule_mode.value, 9.0)
            schedule = mock_send.call_args.args[0]
            assert schedule.schedule_mode == 2

    def test_maintenance_preserves_b1_flags(self) -> None:
        """Maintenance B0 control preserves priority, warning and reserved bits."""
        self.device._attributes[DeviceAttributes.b0_reserved_flags] = 0x18
        self.device._attributes[DeviceAttributes.ac_heater_priority] = True
        self.device._attributes[DeviceAttributes.high_temp_reminder] = True
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(
                DeviceAttributes.maintenance_reminder.value,
                False,
            )
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetMaintenance)
        assert message.body[5] == 0x1B

    def test_maintenance_warning_uses_canonical_extended_flag(self) -> None:
        """Extended heaters mirror the stable canonical maintenance flag."""
        body = bytearray(69)
        body[0] = 0x01
        body[38] = 0x40  # canonical true, legacy 0x80 false
        body[57] = 70
        body[58] = 35

        status = self.device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.maintenance_reminder.value] is True
        assert status[DeviceAttributes.maintain_warn.value] is True
        assert self.device.attributes[DeviceAttributes.maintain_warn] is True

    def test_short_status_uses_persisted_extended_capabilities(self) -> None:
        """Short responses retain learned mode and maintenance semantics."""
        body = bytearray(57)
        body[0] = 0x01
        body[2] = 0x04
        body[38] = 0x40

        status = self.device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.mode.value] == "hybrid"
        assert status[DeviceAttributes.maintain_warn.value] is True

    def test_legacy_maintenance_warning_keeps_raw_bit(self) -> None:
        """Legacy heaters continue to expose the independent raw warning bit."""
        device = _make_device()
        body = bytearray(57)
        body[0] = 0x01
        body[38] = 0x40

        status = device.process_message(_build_message(MessageType.query, body))

        assert status[DeviceAttributes.maintenance_reminder.value] is True
        assert status[DeviceAttributes.maintain_warn.value] is False

    def test_auto_disinfect_remains_read_only(self) -> None:
        """Automatic disinfection status is not exposed as an invented toggle."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(DeviceAttributes.auto_disinfect.value, True)
        mock_send.assert_not_called()

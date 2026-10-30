"""Test BF Device."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.bf import DeviceAttributes, MideaBFDevice
from midealan.devices.bf.message import (
    MessageQuery,
    MessageSet,
    WorkStatus,
)
from midealan.exceptions import SocketException
from midealan.message import (
    ListTypes,
    MessageType,
    ToshibaMessageRequest,
    encode_toshiba_frame,
)

# Lua-derived fixture layout, intentionally independent of production constants.
_TOSHIBA_BASE_STATUS_LENGTH = 28
_TOSHIBA_STATUS_FLAGS_OFFSET = 19
_TOSHIBA_HIGH_TEMPERATURE_OFFSET = 20
_TOSHIBA_REMAINING_TIME_OFFSET = 22
_TOSHIBA_REMAINING_TIME_END = 24
_TOSHIBA_CHAMBER_LIGHT_OFFSET = 25


def _build_device() -> MideaBFDevice:
    """Build a Midea BF device."""
    return MideaBFDevice(
        name="Test BF Device",
        device_id=1,
        ip_address="192.168.1.1",
        port=12345,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="test_model",
        subtype=1,
        customize="",
    )


def _build_toshiba_device(manufacturer_code: str | None = "0008") -> MideaBFDevice:
    """Build a BF device with optional manufacturer identity."""
    identity = (
        {"manufacturer_code": manufacturer_code}
        if manufacturer_code is not None
        else {}
    )
    return MideaBFDevice(
        name="Toshiba BF Device",
        device_id=2,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="test_model",
        subtype=1,
        customize="",
        **identity,
    )


def _toshiba_status_body() -> bytearray:
    """Build the minimum complete Toshiba BF base-status body."""
    return bytearray(_TOSHIBA_BASE_STATUS_LENGTH)


def _build_message(message_type: MessageType, body: bytearray) -> bytes:
    """Build a full BF response message."""
    header = bytearray(
        [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
    )
    return bytes(header + body + bytearray([0x00]))


class TestMideaBFDevice:
    """Test Midea BF Device."""

    device: MideaBFDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea BF Device setup."""
        self.device = _build_device()

    def test_initial_attributes_all_none(self) -> None:
        """Test all initial attributes are None."""
        for attr in DeviceAttributes:
            assert self.device.attributes[attr] is None

    def test_build_query(self) -> None:
        """Test build query returns one MessageQuery."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_toshiba_identity_builds_common_query(self) -> None:
        """Use the one-byte Toshiba BF query for manufacturer 0008."""
        device = _build_toshiba_device()
        queries = device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], ToshibaMessageRequest)
        assert queries[0].body == b"\x00"
        assert device.build_query_fallback() == []

    @pytest.mark.parametrize("frame_type", [MessageType.query, MessageType.notify1])
    def test_toshiba_query_and_notify_base_status(
        self,
        frame_type: MessageType,
    ) -> None:
        """Decode the common Toshiba BF status from query and notify frames."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_STATUS_FLAGS_OFFSET] = 0x11
        body[_TOSHIBA_HIGH_TEMPERATURE_OFFSET] = 0x01
        body[_TOSHIBA_REMAINING_TIME_OFFSET:_TOSHIBA_REMAINING_TIME_END] = (
            0x1234
        ).to_bytes(2, "little")
        body[_TOSHIBA_CHAMBER_LIGHT_OFFSET] = 0x01

        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.BF, frame_type, body)),
        )

        assert status == {
            DeviceAttributes.door: True,
            DeviceAttributes.status: "during_process",
            DeviceAttributes.time_remaining: 0x1234,
            DeviceAttributes.high_temperature: True,
            DeviceAttributes.furnace_light: True,
        }
        assert device.attributes[DeviceAttributes.time_remaining] == 0x1234

    @pytest.mark.parametrize(
        ("raw_state", "expected"),
        [
            (0, "before_cooking"),
            (1, "finish_cooking"),
            (2, "before_cooking"),
            (3, "error_occur"),
            (4, "during_process"),
            (5, "before_cooking"),
            (6, "before_cooking"),
            (7, "finished_process"),
        ],
    )
    def test_toshiba_cooking_state_mapping(
        self,
        raw_state: int,
        expected: str,
    ) -> None:
        """Map every three-bit Toshiba cooking state deterministically."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_STATUS_FLAGS_OFFSET] = raw_state << 2
        frame = encode_toshiba_frame(DeviceType.BF, MessageType.query, body)
        assert device.process_message(bytes(frame))[DeviceAttributes.status] == expected

    @pytest.mark.parametrize("mask", [0x01, 0x02, 0x04, 0x08])
    def test_toshiba_high_temperature_masks(self, mask: int) -> None:
        """Treat each documented high-temperature bit as an active warning."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_HIGH_TEMPERATURE_OFFSET] = mask
        frame = encode_toshiba_frame(DeviceType.BF, MessageType.query, body)
        status = device.process_message(bytes(frame))
        assert status[DeviceAttributes.high_temperature] is True

    @pytest.mark.parametrize("mask", [0x01, 0x02, 0x04])
    def test_toshiba_chamber_light_masks(self, mask: int) -> None:
        """Treat each documented chamber-light bit as an active light."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_CHAMBER_LIGHT_OFFSET] = mask
        frame = encode_toshiba_frame(DeviceType.BF, MessageType.notify1, body)
        status = device.process_message(bytes(frame))
        assert status[DeviceAttributes.furnace_light] is True

    def test_toshiba_requires_complete_base_status(self) -> None:
        """Accept exactly 28 bytes and reject the 27-byte truncated body."""
        device = _build_toshiba_device()
        complete = _toshiba_status_body()
        frame = encode_toshiba_frame(DeviceType.BF, MessageType.query, complete)
        assert device.process_message(bytes(frame))[DeviceAttributes.door] is False

        truncated = complete[:-1]
        frame = encode_toshiba_frame(DeviceType.BF, MessageType.query, truncated)
        assert device.process_message(bytes(frame)) == {}

    @pytest.mark.parametrize(
        ("frame_type", "body_type"),
        [
            (MessageType.set, 0x00),
            (MessageType.query, 0x01),
            (MessageType.notify1, 0x01),
        ],
    )
    def test_toshiba_rejects_unsupported_frame_body_combinations(
        self,
        frame_type: MessageType,
        body_type: int,
    ) -> None:
        """Accept only the Lua-documented BF frame and body combinations."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[0] = body_type
        frame = encode_toshiba_frame(DeviceType.BF, frame_type, body)
        assert device.process_message(bytes(frame)) == {}

    def test_toshiba_fallback_requires_valid_supported_status(self) -> None:
        """Select fallback framing only after a complete decoded BF status."""
        device = _build_toshiba_device(None)
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, ToshibaMessageRequest)

        body = _toshiba_status_body()
        invalid = encode_toshiba_frame(DeviceType.BF, MessageType.query, body)
        invalid[-1] ^= 1
        assert device.process_message(bytes(invalid)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert device.toshiba_protocol is False

        wrong_type = encode_toshiba_frame(DeviceType.DB, MessageType.query, body)
        assert device.process_message(bytes(wrong_type)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x01
        unsupported = encode_toshiba_frame(DeviceType.BF, MessageType.query, body)
        assert device.process_message(bytes(unsupported)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x00
        valid = encode_toshiba_frame(DeviceType.BF, MessageType.query, body)
        assert device.process_message(bytes(valid))[DeviceAttributes.door] is False
        assert device._is_query_response_valid(fallback) is True
        assert device.toshiba_protocol is True

    def test_explicit_non_toshiba_identity_skips_fallback(self) -> None:
        """Do not probe Toshiba framing for a known different manufacturer."""
        device = _build_toshiba_device("1234")
        assert device.build_query_fallback() == []
        assert isinstance(device.build_query()[0], MessageQuery)

    def test_toshiba_write_is_rejected_before_send(self) -> None:
        """Keep Toshiba BF writes disabled until hardware verification."""
        device = _build_toshiba_device()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.furnace_light, True)
        send.assert_not_called()

    def test_process_message_basic(self) -> None:
        """Test process message with a basic totalState body."""
        body = bytearray(60)
        body[0] = 0x01  # body_type totalState
        body[31] = WorkStatus.standby.value
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.status] == "standby"
        assert self.device.attributes[DeviceAttributes.power] is True
        assert DeviceAttributes.status.value in new_status
        assert new_status[DeviceAttributes.status.value] == "standby"

    def test_process_message_save_power(self) -> None:
        """Test process message with save_power status -> power=False."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.save_power.value
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.status] == "save_power"

    def test_process_message_all_flags(self) -> None:
        """Test process message with all byte32/33 flags set."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[32] = 0xBF  # all byte32 flags
        body[33] = 0x7F  # all byte33 flags
        body[35] = 0x20  # hot_wind
        body[56] = 0xC0  # clean_scale + ota
        body[58] = 0x03  # clean_sink_ponding + dissipate_heat
        self.device.process_message(
            _build_message(MessageType.set, body),
        )
        assert self.device.attributes[DeviceAttributes.child_lock] is True
        assert self.device.attributes[DeviceAttributes.door] is True
        assert self.device.attributes[DeviceAttributes.tank_ejected] is True
        assert self.device.attributes[DeviceAttributes.water_shortage] is True
        assert self.device.attributes[DeviceAttributes.water_change_reminder] is True
        assert self.device.attributes[DeviceAttributes.error] is True
        assert self.device.attributes[DeviceAttributes.pre_heat] is True
        assert self.device.attributes[DeviceAttributes.flip_side] is True
        assert self.device.attributes[DeviceAttributes.reaction] is True
        assert self.device.attributes[DeviceAttributes.furnace_light] is True
        assert self.device.attributes[DeviceAttributes.hot_wind] is True
        assert self.device.attributes[DeviceAttributes.clean_scale] is True
        assert self.device.attributes[DeviceAttributes.ota] is True
        assert self.device.attributes[DeviceAttributes.clean_sink_ponding] is True
        assert self.device.attributes[DeviceAttributes.dissipate_heat] is True

    def test_process_message_temperatures(self) -> None:
        """Test process message with temperature values."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[13] = 0x00  # temp_above_high
        body[14] = 200  # temp_above_low
        body[15] = 0x00  # temp_underside_high
        body[16] = 180  # temp_underside_low
        body[25] = 0x00  # cur_temp_above_high
        body[26] = 180  # cur_temp_above_low
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.temperature] == 200
        assert self.device.attributes[DeviceAttributes.temperature_above] == 200
        assert self.device.attributes[DeviceAttributes.temperature_underside] == 180
        assert self.device.attributes[DeviceAttributes.current_temperature] == 180

    def test_process_message_time_remaining(self) -> None:
        """Test process message with work time and time_remaining."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[22] = 1  # work_hour
        body[23] = 30  # work_minute
        body[24] = 0  # work_second
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.time_remaining] == 5400

    def test_process_message_work_mode(self) -> None:
        """Test process message with work_mode."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[7] = 0x01  # microwave high
        body[8] = 0x00  # microwave low
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.work_mode] == "microwave"

    def test_process_message_fire_power(self) -> None:
        """Test process message with fire_power."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[12] = 0x05  # fire_power_5
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.fire_power] == "fire_power_5"

    def test_process_message_steam_weight(self) -> None:
        """Test process message with steam and weight."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[19] = 5  # steam_quantity
        body[20] = 50  # weight/people: 50*10=500
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.steam_quantity] == 5
        assert self.device.attributes[DeviceAttributes.weight] == 500
        assert self.device.attributes[DeviceAttributes.people_number] == 50

    def test_process_message_cbs_version(self) -> None:
        """Test process message with cbs_version."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[47] = 1
        body[48] = 2
        body[49] = 3
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.cbs_version] == "V1.2.3"

    def test_process_message_maintenance_flags(self) -> None:
        """Test process message with clean_scale, ota, etc."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[56] = 0xC0  # clean_scale + ota
        body[58] = 0x03  # clean_sink_ponding + dissipate_heat
        self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.clean_scale] is True
        assert self.device.attributes[DeviceAttributes.ota] is True
        assert self.device.attributes[DeviceAttributes.clean_sink_ponding] is True
        assert self.device.attributes[DeviceAttributes.dissipate_heat] is True

    def test_set_attribute_power(self) -> None:
        """Test set_attribute with power raises SocketException (no socket)."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.power, True)
        # set_attribute sends command but doesn't update local state
        assert self.device.attributes[DeviceAttributes.power] is None

    def test_set_attribute_child_lock(self) -> None:
        """Test set_attribute with child_lock."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.child_lock, True)
        assert self.device.attributes[DeviceAttributes.child_lock] is None

    def test_set_attribute_furnace_light(self) -> None:
        """Test set_attribute with furnace_light."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.furnace_light, True)
        assert self.device.attributes[DeviceAttributes.furnace_light] is None

    def test_set_attribute_hot_wind(self) -> None:
        """Test set_attribute with hot_wind."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.hot_wind, True)
        assert self.device.attributes[DeviceAttributes.hot_wind] is None

    def test_set_attribute_door(self) -> None:
        """Test set_attribute with door."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.door, True)
        assert self.device.attributes[DeviceAttributes.door] is None

    def test_set_attribute_work_mode(self) -> None:
        """Test set_attribute with work_mode."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.work_mode, "microwave")
        assert self.device.attributes[DeviceAttributes.work_mode] is None

    def test_set_attribute_fire_power(self) -> None:
        """Test set_attribute with fire_power routes to workModeControl.

        Even without an active work_mode, fire_power is a work-mode parameter
        field so it serializes via workModeControl and reaches build_send.
        """
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.fire_power, "fire_power_5")
        assert self.device.attributes[DeviceAttributes.fire_power] is None

    def test_set_attribute_fire_power_with_work_mode(self) -> None:
        """Test set_attribute with fire_power when work_mode is active."""
        # First set up work_mode via a processed message
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[7] = 0x01  # microwave high
        body[8] = 0x00  # microwave low
        self.device.process_message(_build_message(MessageType.query, body))
        # Now fire_power should route via make_message_set with work_mode context
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.fire_power, "fire_power_5")

    def test_set_attribute_temperature(self) -> None:
        """Test set_attribute with temperature routes to workModeControl.

        Even without an active work_mode, temperature is a work-mode parameter
        field so it serializes via workModeControl and reaches build_send.
        """
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.temperature, 200)
        assert self.device.attributes[DeviceAttributes.temperature] is None

    def test_set_attribute_temperature_with_work_mode(self) -> None:
        """Test set_attribute with temperature when work_mode is active."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[7] = 0x01  # microwave high
        body[8] = 0x00  # microwave low
        self.device.process_message(_build_message(MessageType.query, body))
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.temperature, 200)

    def test_set_attribute_status_with_string(self) -> None:
        """Test set_attribute with status (maps to work_status on message)."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.status, "standby")
        assert self.device.attributes[DeviceAttributes.status] is None

    def test_set_attribute_status_invalid_type(self) -> None:
        """Test set_attribute with status as non-string logs warning and returns."""
        # This should not crash, just log a warning and return early
        self.device.set_attribute(DeviceAttributes.status, 42)
        assert self.device.attributes[DeviceAttributes.status] is None

    def test_set_attribute_unsupported_attribute(self) -> None:
        """Test set_attribute with unsupported attribute logs warning."""
        # Attributes not in _SETTABLE_ATTRS and not status should be ignored
        self.device.set_attribute(DeviceAttributes.time_remaining, 3600)
        assert self.device.attributes[DeviceAttributes.time_remaining] is None

    def test_set_attribute_hour_set(self) -> None:
        """Test set_attribute with hour_set."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.hour_set, 1)
        assert self.device.attributes[DeviceAttributes.hour_set] is None

    def test_set_attribute_minute_set(self) -> None:
        """Test set_attribute with minute_set."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.minute_set, 30)
        assert self.device.attributes[DeviceAttributes.minute_set] is None

    def test_set_attribute_second_set(self) -> None:
        """Test set_attribute with second_set."""
        with pytest.raises(SocketException):
            self.device.set_attribute(DeviceAttributes.second_set, 0)
        assert self.device.attributes[DeviceAttributes.second_set] is None

    def test_process_message_updates_returned_dict(self) -> None:
        """Test process_message returns a dict of updated attributes."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.standby.value
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert isinstance(new_status, dict)
        # All attributes that MessageBFBody provides should be in new_status
        assert DeviceAttributes.status.value in new_status
        assert DeviceAttributes.power.value in new_status

    def test_process_message_notify_type(self) -> None:
        """Test process_message with notify1 message type."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        self.device.process_message(
            _build_message(MessageType.notify1, body),
        )
        assert self.device.attributes[DeviceAttributes.status] == "work"

    def test_process_message_non_total_state(self) -> None:
        """Test process_message with non-totalState body_type."""
        body = bytearray(10)
        body[0] = 0x02  # not totalState (0x01)
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        # No BF-specific attributes should be parsed
        assert self.device.attributes[DeviceAttributes.status] is None
        assert DeviceAttributes.status.value not in new_status

    def test_set_attribute_status_unsupported_value(self) -> None:
        """Unknown status name is rejected instead of sent as a no-op."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status, "not_a_status")
            mock_build_send.assert_not_called()

    def test_set_attribute_status_valid_value_builds_message(self) -> None:
        """A valid status name is serialized as work_status."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status, "standby")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.work_status == "standby"

    def test_set_attribute_work_mode_unsupported_value(self) -> None:
        """Unknown work_mode name is rejected instead of sent as a no-op."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.work_mode, "not_a_mode")
            mock_build_send.assert_not_called()

    def test_set_attribute_fire_power_unsupported_value(self) -> None:
        """Unknown fire_power name is rejected instead of sent as a no-op."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fire_power, "bogus")
            mock_build_send.assert_not_called()

    def test_set_attribute_float_coerced_to_int(self) -> None:
        """Numeric attributes coerce float input to int before serialization.

        A float would otherwise raise TypeError during the >> / & serialization
        in MessageSet. temperature routes via workModeControl.
        """
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.temperature, 200.0)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.temperature == 200
            assert isinstance(message.temperature, int)
            # Serialization must not raise on the coerced value.
            assert message.body[0] == ListTypes.X01

    def test_set_attribute_people_number_clears_weight(self) -> None:
        """Setting people_number clears weight so it is not preferred."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[7] = 0x01  # microwave high
        body[8] = 0x00  # microwave low
        body[20] = 50  # weight/people byte -> weight=500, people_number=50
        self.device.process_message(_build_message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.weight] == 500
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.people_number, 4)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.weight is None
            assert message.people_number == 4

    def test_set_attribute_work_mode_resend_preserves_cook_time(self) -> None:
        """make_message_set carries hour/minute/second into work time fields."""
        body = bytearray(60)
        body[0] = 0x01
        body[31] = WorkStatus.work.value
        body[7] = 0x01  # microwave high
        body[8] = 0x00  # microwave low
        body[9] = 1  # hour_set
        body[10] = 30  # minute_set
        body[11] = 15  # second_set
        self.device.process_message(_build_message(MessageType.query, body))
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fire_power, "fire_power_5")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.work_hour == 1
            assert message.work_minute == 30
            assert message.work_second == 15


class TestMakeMessageSet:
    """Test make_message_set directly."""

    def test_make_message_set_returns_message_set(self) -> None:
        """make_message_set returns a MessageSet with work-mode context."""
        device = _build_device()
        message = device.make_message_set()
        assert isinstance(message, MessageSet)

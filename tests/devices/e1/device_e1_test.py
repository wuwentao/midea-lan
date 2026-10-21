"""Test E1 device."""

from typing import cast
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.e1 import DeviceAttributes, MideaE1Device
from midealan.devices.e1.message import (
    MessageLock,
    MessageOperator,
    MessagePower,
    MessageQuery,
    MessageStorage,
    MessageWork,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType


class TestMideaE1Device:
    """Test E1 device."""

    device: MideaE1Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Set up E1 device."""
        self.device = MideaE1Device(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.100",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="test_model",
            subtype=1,
            customize="test_customize",
        )

    def test_modes(self) -> None:
        """Test work modes are exposed without allowing mutation."""
        modes = self.device.modes
        assert modes[0x04] == "eco_wash"
        modes[0x04] = "Changed"
        assert self.device.modes[0x04] == "eco_wash"

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_set_work_mode(self) -> None:
        """Test setting a supported work mode."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_work_mode(0x04)

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.mode == 0x04

    def test_set_work_mode_rejects_unknown_mode(self) -> None:
        """Test setting an unknown work mode."""
        with pytest.raises(ValueWrongType, match="Unsupported work mode"):
            self.device.set_work_mode(0x11)

    def test_start_work(self) -> None:
        """Test starting the currently selected work mode."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.start_work()

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.mode == 0x04

    def test_start_work_door_auto_open(self) -> None:
        """Test starting with door auto-open."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.start_work(door_auto_open=True)

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.door_auto_open is True

    def test_cancel_work(self) -> None:
        """Test cancelling the running program keeps the current mode."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.cancel_work()

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex("080104".ljust(76, "0"))

    def test_set_delayed_start(self) -> None:
        """Test a delayed start sends status order with the delay."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_delayed_start(0x04, 60, door_auto_open=True)

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex(
            "0802040000000001000000000001".ljust(76, "0"),
        )

    @pytest.mark.parametrize("minutes", [0, -1, 24 * 60 + 1])
    def test_set_delayed_start_rejects_delay(self, minutes: int) -> None:
        """Test a delayed start rejects out of range delays."""
        with pytest.raises(ValueWrongType, match="Delay must be"):
            self.device.set_delayed_start(0x04, minutes)

    def test_set_delayed_start_rejects_unknown_mode(self) -> None:
        """Test a delayed start rejects an unknown work mode."""
        with pytest.raises(ValueWrongType, match="Unsupported work mode"):
            self.device.set_delayed_start(0x11, 60)

    def test_set_delayed_start_rejects_neutral_mode(self) -> None:
        """Test a delayed start needs a work mode."""
        with pytest.raises(ValueWrongType, match="No work mode selected"):
            self.device.set_delayed_start(0x00, 60)

    def test_cancel_delayed_start(self) -> None:
        """Test cancelling a delayed start."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.cancel_delayed_start()

        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex("080404".ljust(76, "0"))

    def test_pause_work(self) -> None:
        """Test pausing emits the 8302 operator command."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.pause_work()
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageOperator)
        assert message.body[:2] == bytearray.fromhex("8302")

    def test_resume_work(self) -> None:
        """Test resuming emits the 8301 operator command."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.resume_work()
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageOperator)
        assert message.body[:2] == bytearray.fromhex("8301")

    def test_set_attribute_status_pause(self) -> None:
        """Test set_attribute('status', 'pause') pauses the program."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "pause")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageOperator)
        assert message.body[:2] == bytearray.fromhex("8302")

    @pytest.mark.parametrize("trigger", ["resume", "start"])
    def test_set_attribute_status_resume(self, trigger: str) -> None:
        """Test set_attribute('status', 'resume'/'start') resumes the program."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, trigger)
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageOperator)
        assert message.body[:2] == bytearray.fromhex("8301")

    @pytest.mark.parametrize("mode", [None, 0, "neutral_gear"])
    def test_start_work_requires_selected_mode(self, mode: str | int | None) -> None:
        """Test starting requires a non-neutral selected mode."""
        self.device._attributes[DeviceAttributes.mode] = mode
        with pytest.raises(ValueWrongType, match="No work mode selected"):
            self.device.start_work()

    def test_start_work_rejects_invalid_mode_type(self) -> None:
        """Test starting rejects an invalid stored mode."""
        self.device._attributes[DeviceAttributes.mode] = 4
        with pytest.raises(ValueWrongType, match="Invalid work mode"):
            self.device.start_work()

    @staticmethod
    def _message(message_type: MessageType, body: bytearray) -> bytes:
        header = bytearray(
            [0xAA, *([0x00] * 7), ProtocolVersion.V1, message_type],
        )
        crc = bytearray([0x00])
        return bytes(header + body + crc)

    def test_process_message_maps_status_progress_and_mode(self) -> None:
        """Test process message maps status, progress and mode via lookup tables."""
        body = bytearray(40)
        body[1] = 0x03  # status Running
        body[2] = 0x04  # mode ECO Wash
        body[9] = 0x03  # progress Rinse
        new_status = self.device.process_message(
            self._message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.status] == "running"
        assert self.device.attributes[DeviceAttributes.mode] == "eco_wash"
        assert self.device.attributes[DeviceAttributes.progress] == "rinse"
        assert new_status[DeviceAttributes.status.value] == "running"

    @pytest.mark.parametrize(
        ("mode_byte", "mode_name"),
        [
            (0x15, "max_rapid_wash"),
            (0x1B, "single_dry"),
            (0x1C, "single_disinfect"),
            (0x1D, "wahin_wash_dry"),
            (0x1E, "high_temp_wash"),
            (0x1F, "wash_dry"),
        ],
    )
    def test_process_message_extended_modes(
        self,
        mode_byte: int,
        mode_name: str,
    ) -> None:
        """Test the richer models' extended wash modes decode (lua 7600002B)."""
        body = bytearray(40)
        body[1] = 0x03
        body[2] = mode_byte
        self.device.process_message(self._message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.mode] == mode_name

    def test_process_message_unknown_status_mode_and_progress(self) -> None:
        """Test process message returns None for unmapped lookup values."""
        body = bytearray(40)
        body[1] = 0xFF  # unknown status
        body[2] = 0xFF  # unknown mode
        body[9] = 0xFF  # out-of-range progress
        self.device.process_message(self._message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.status] is None
        assert self.device.attributes[DeviceAttributes.mode] is None
        assert self.device.attributes[DeviceAttributes.progress] is None

    def test_process_message_unhandled_message_type(self) -> None:
        """Test process message ignores unhandled message/body type combinations."""
        body = bytearray(40)
        new_status = self.device.process_message(
            self._message(MessageType.notify2, body),
        )
        assert new_status == {}

    def test_set_attribute_rejects_non_bool(self) -> None:
        """Test set attribute rejects non-bool values."""
        with pytest.raises(ValueWrongType, match="Expected bool"):
            self.device.set_attribute(DeviceAttributes.power.value, "on")

    def test_set_attribute_power(self) -> None:
        """Test set attribute power sends a power message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessagePower)
        assert message.power is True

    def test_set_attribute_child_lock(self) -> None:
        """Test set attribute child lock sends a lock message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.child_lock.value, True)
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageLock)
        assert message.lock is True

    def test_set_attribute_storage(self) -> None:
        """Test set attribute storage sends a storage message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.storage.value, True)
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageStorage)
        assert message.storage is True

    def test_set_attribute_unknown_attribute_is_noop(self) -> None:
        """Test set attribute with an unsupported attribute sends nothing."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.uv.value, True)
        mock_build_send.assert_not_called()

    def test_set_attribute_mode_starts_program(self) -> None:
        """Test writing mode through set_attribute starts the program."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "eco_wash")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.work_status == 0x03
        assert message.mode == 0x04

    def test_set_attribute_mode_by_code(self) -> None:
        """Test writing a mode code through set_attribute."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, 0x04)
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.mode == 0x04

    def test_set_attribute_status_cancel(self) -> None:
        """Test status cancel sends cancel (0x01) when not in delay."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "cancel")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex("080104".ljust(76, "0"))

    def test_set_attribute_status_cancel_during_delay(self) -> None:
        """Test status cancel sends cancel_order (0x04) when delay is pending."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device._attributes[DeviceAttributes.status] = "delay"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "cancel")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex("080404".ljust(76, "0"))

    def test_set_attribute_status_running_starts_work(self) -> None:
        """Test status running/work starts the selected program."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "running")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.work_status == 0x03
        assert message.mode == 0x04

    def test_set_attribute_status_order_uses_stored_delay(self) -> None:
        """Test status order sends a delayed start with the stored delay."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.delay_minutes.value, 60)
            self.device.set_attribute(DeviceAttributes.door_auto_open.value, True)
            self.device.set_attribute(DeviceAttributes.status.value, "order")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex(
            "0802040000000001000000000001".ljust(76, "0"),
        )

    def test_set_attribute_status_cancel_order(self) -> None:
        """Test status cancel_order cancels a pending delayed start."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "cancel_order")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex("080404".ljust(76, "0"))

    def test_set_attribute_status_unknown(self) -> None:
        """Test an unknown status trigger is rejected."""
        with pytest.raises(ValueWrongType, match="Unsupported status"):
            self.device.set_attribute(DeviceAttributes.status.value, "spin")

    def test_set_attribute_delay_minutes_stores_value(self) -> None:
        """Test delay_minutes is stored and reused by a later order."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.delay_minutes.value, 90)
        mock_build_send.assert_not_called()
        assert self.device.attributes[DeviceAttributes.delay_minutes.value] == 90

    def test_set_attribute_delay_minutes_rejects_out_of_range(self) -> None:
        """Test delay_minutes rejects out of range values."""
        with pytest.raises(ValueWrongType, match="Delay must be"):
            self.device.set_attribute(DeviceAttributes.delay_minutes.value, 0)

    def test_set_attribute_program_selects_without_starting(self) -> None:
        """Test writing program stores the choice without sending anything."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.program.value, "glass_wash")
        mock_build_send.assert_not_called()
        assert self.device.attributes[DeviceAttributes.program.value] == "glass_wash"

    @pytest.mark.parametrize("program", [0x00, "neutral_gear", "spin", 0x11])
    def test_set_attribute_program_rejects_invalid(self, program: int | str) -> None:
        """Test program rejects the neutral mode and unknown modes."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.program.value, program)

    def test_status_work_starts_selected_program(self) -> None:
        """Test status work starts the selected program, not the reported one."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device.set_attribute(DeviceAttributes.program.value, 0x05)
        self.device.set_attribute(DeviceAttributes.door_auto_open_setting.value, True)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "work")
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(
            "0803050000000000000000000001".ljust(76, "0"),
        )

    def test_status_order_from_cancel_uses_selected_program(self) -> None:
        """Test a delayed start from idle after a cancel uses the selected program."""
        self.device._attributes[DeviceAttributes.mode] = "neutral_gear"
        self.device.set_attribute(DeviceAttributes.program.value, "eco_wash")
        self.device.set_attribute(DeviceAttributes.delay_minutes.value, 60)
        self.device.set_attribute(DeviceAttributes.door_auto_open_setting.value, True)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "order")
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(
            "0802040000000001000000000001".ljust(76, "0"),
        )

    def test_settings_are_readable_and_survive_status_reply(self) -> None:
        """Test the next-start settings are readable and not overwritten."""
        self.device.set_attribute(DeviceAttributes.door_auto_open_setting.value, True)
        self.device.set_attribute(DeviceAttributes.additional_setting.value, 2)
        body = bytearray(40)
        body[1] = 0x01  # status Cancel, door auto-open bit clear, additional 0
        self.device.process_message(self._message(MessageType.query, body))
        attributes = self.device.attributes
        assert attributes[DeviceAttributes.door_auto_open_setting.value] is True
        assert attributes[DeviceAttributes.additional_setting.value] == 2
        assert attributes[DeviceAttributes.door_auto_open.value] is False
        assert attributes[DeviceAttributes.additional.value] == 0

    def test_legacy_setting_names_update_readable_settings(self) -> None:
        """Test writing door_auto_open / additional also sets the readable settings."""
        self.device.set_attribute(DeviceAttributes.door_auto_open.value, True)
        self.device.set_attribute(DeviceAttributes.additional.value, 2)
        attributes = self.device.attributes
        assert attributes[DeviceAttributes.door_auto_open_setting.value] is True
        assert attributes[DeviceAttributes.additional_setting.value] == 2

    @pytest.mark.parametrize(
        ("status", "reported", "expected"),
        [("cancel", "running", "080104"), ("cancel", "delay", "080404")],
    )
    def test_cancel_leaves_out_next_start_settings(
        self,
        status: str,
        reported: str,
        expected: str,
    ) -> None:
        """Test cancels carry only status and mode, not the next-start settings."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device._attributes[DeviceAttributes.status] = reported
        self.device.set_attribute(DeviceAttributes.door_auto_open_setting.value, True)
        self.device.set_attribute(DeviceAttributes.additional_setting.value, 2)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, status)
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(expected.ljust(76, "0"))

    @pytest.mark.parametrize(
        ("param", "setting", "byte_index"),
        [
            ("wash_region", "wash_region_setting", 4),
            ("water_level", "water_level_setting", 11),
            ("water_strong_level", "water_strong_level_setting", 12),
        ],
    )
    def test_wash_param_settings_are_readable_and_sent(
        self,
        param: str,
        setting: str,
        byte_index: int,
    ) -> None:
        """Test wash parameter settings are readable, survive replies, and are sent."""
        self.device.set_attribute(setting, 5)
        body = bytearray(42)
        body[1] = 0x01  # status Cancel
        body[35] = 3  # reported wash_region
        self.device.process_message(self._message(MessageType.query, body))
        assert self.device.attributes[setting] == 5
        assert self.device.attributes[param] != 5
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "eco_wash")
        message = mock_build_send.call_args.args[0]
        assert message.body[byte_index] == 5

    def test_plain_wash_param_write_updates_setting(self) -> None:
        """Test writing the plain wash parameter name also sets the readable setting."""
        self.device.set_attribute(DeviceAttributes.wash_region.value, 5)
        assert self.device.attributes[DeviceAttributes.wash_region_setting.value] == 5

    def test_wash_param_setting_rejects_out_of_range(self) -> None:
        """Test the setting names keep the byte range check."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.water_level_setting.value, 256)

    def test_additional_setting_is_sent_with_the_start(self) -> None:
        """Test additional_setting rides along with the next start."""
        self.device.set_attribute(DeviceAttributes.additional_setting.value, 2)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "eco_wash")
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex("08030402".ljust(76, "0"))

    def test_set_attribute_door_auto_open_stores_value(self) -> None:
        """Test door_auto_open is stored without sending a message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.door_auto_open.value, True)
        mock_build_send.assert_not_called()

    def test_door_auto_open_setting_survives_status_reply(self) -> None:
        """Test a status reply does not clear the stored door auto-open."""
        self.device.set_attribute(DeviceAttributes.door_auto_open.value, True)
        self.device.set_attribute(DeviceAttributes.delay_minutes.value, 60)
        body = bytearray(40)
        body[1] = 0x01  # status Cancel, door auto-open bit clear
        body[2] = 0x04  # mode ECO Wash
        self.device.process_message(self._message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.door_auto_open] is False

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "order")
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(
            "0802040000000001000000000001".ljust(76, "0"),
        )

    def test_set_attribute_mode_uses_door_auto_open_setting(self) -> None:
        """Test writing mode applies the stored door auto-open setting."""
        self.device.set_attribute(DeviceAttributes.door_auto_open.value, True)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, 0x04)
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(
            "0803040000000000000000000001".ljust(76, "0"),
        )

    @pytest.mark.parametrize("value", [True, 4.9, 4.0])
    def test_set_attribute_mode_rejects_non_integer(self, value: float) -> None:
        """Test writing mode rejects booleans and floats."""
        with pytest.raises(ValueWrongType, match="Unsupported work mode"):
            self.device.set_attribute(DeviceAttributes.mode.value, value)

    def test_set_attribute_delay_minutes_accepts_whole_float(self) -> None:
        """Test delay_minutes accepts a whole float such as 90.0."""
        self.device.set_attribute(DeviceAttributes.delay_minutes.value, 90.0)
        assert self.device.attributes[DeviceAttributes.delay_minutes.value] == 90

    @pytest.mark.parametrize(
        ("minutes", "delay_hex"),
        [(1, "0001"), (24 * 60, "1800")],
    )
    def test_set_attribute_delay_minutes_boundaries(
        self,
        minutes: int,
        delay_hex: str,
    ) -> None:
        """Test the shortest and longest delays are stored and encoded."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device.set_attribute(DeviceAttributes.delay_minutes.value, minutes)
        assert self.device.attributes[DeviceAttributes.delay_minutes.value] == minutes
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.status.value, "order")
        message = mock_build_send.call_args.args[0]
        assert message.body == bytearray.fromhex(
            f"08020400000000{delay_hex}".ljust(76, "0"),
        )

    @pytest.mark.parametrize("mode", [0x00, "neutral_gear"])
    def test_set_attribute_mode_rejects_neutral(self, mode: int | str) -> None:
        """Test writing the neutral mode does not start a program."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType, match="No work mode selected"),
        ):
            self.device.set_attribute(DeviceAttributes.mode.value, mode)
        mock_build_send.assert_not_called()

    @pytest.mark.parametrize("value", [90.9, True, "90"])
    def test_set_attribute_delay_minutes_rejects_invalid(
        self,
        value: float | str,
    ) -> None:
        """Test delay_minutes rejects fractions, booleans and strings."""
        with pytest.raises(ValueWrongType, match="Delay must be"):
            self.device.set_attribute(DeviceAttributes.delay_minutes.value, value)

    def test_set_delayed_start_rejects_fractional_delay(self) -> None:
        """Test a delayed start rejects a fractional delay."""
        with pytest.raises(ValueWrongType, match="Delay must be"):
            self.device.set_delayed_start(0x04, cast("int", 60.5))

    def test_set_work_mode_by_name(self) -> None:
        """Test set_work_mode accepts a mode name."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_work_mode("eco_wash")
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.mode == 0x04

    def test_set_work_mode_rejects_unknown_name(self) -> None:
        """Test set_work_mode rejects an unknown mode name."""
        with pytest.raises(ValueWrongType, match="Unsupported work mode"):
            self.device.set_work_mode("spin")

    @pytest.mark.parametrize(
        "attr",
        [
            DeviceAttributes.additional,
            DeviceAttributes.wash_region,
            DeviceAttributes.water_level,
            DeviceAttributes.water_strong_level,
        ],
    )
    def test_set_attribute_wash_param_stores_value(
        self,
        attr: DeviceAttributes,
    ) -> None:
        """Test wash params are stored as a pending setting without sending."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(attr.value, 5)
        mock_build_send.assert_not_called()
        assert self.device._wash_param_settings[attr] == 5

    def test_set_attribute_wash_param_accepts_whole_float(self) -> None:
        """Test a wash param accepts a whole float such as 5.0."""
        self.device.set_attribute(DeviceAttributes.water_level.value, 5.0)
        assert self.device._wash_param_settings[DeviceAttributes.water_level] == 5

    @pytest.mark.parametrize("value", [256, -1, 5.5, True, "5"])
    def test_set_attribute_wash_param_rejects_invalid(
        self,
        value: float | str,
    ) -> None:
        """Test a wash param rejects out-of-range, fractional and non-numbers."""
        with pytest.raises(ValueWrongType, match="must be 0 to"):
            self.device.set_attribute(DeviceAttributes.water_level.value, value)

    def test_wash_param_setting_survives_status_reply(self) -> None:
        """Test a status reply does not clear a stored wash parameter."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device.set_attribute(DeviceAttributes.additional.value, 0x05)
        self.device.set_attribute(DeviceAttributes.wash_region.value, 0x06)
        self.device.set_attribute(DeviceAttributes.water_level.value, 0x02)
        self.device.set_attribute(DeviceAttributes.water_strong_level.value, 0x01)
        # A status reply reports its own additional/water values
        body = bytearray(42)
        body[1] = 0x01  # status Cancel
        body[2] = 0x04  # mode ECO Wash
        body[3] = 0x00  # additional reported 0
        body[30] = 0x00  # water_level reported 0
        self.device.process_message(self._message(MessageType.query, body))
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.start_work()
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex(
            "08030405060000000000000201".ljust(76, "0"),
        )

    def test_wash_params_ride_along_with_work_command(self) -> None:
        """Test stored wash params are carried by the next work command."""
        self.device._attributes[DeviceAttributes.mode] = "eco_wash"
        self.device.set_attribute(DeviceAttributes.additional.value, 0x05)
        self.device.set_attribute(DeviceAttributes.wash_region.value, 0x06)
        self.device.set_attribute(DeviceAttributes.water_level.value, 0x02)
        self.device.set_attribute(DeviceAttributes.water_strong_level.value, 0x01)
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.start_work()
        message = mock_build_send.call_args.args[0]
        assert isinstance(message, MessageWork)
        assert message.body == bytearray.fromhex(
            "08030405060000000000000201".ljust(76, "0"),
        )

    def test_process_message_maps_operator_and_sensors(self) -> None:
        """Test process message exposes the new operator and sensor fields."""
        body = bytearray(42)
        body[1] = 0x03  # status Running
        body[5] = 0x08  # operator start bit
        body[30] = 2  # water_level
        body[31] = 1  # water_strong_level
        body[35] = 6  # wash_region
        body[40] = 8  # clean_left_hour
        new_status = self.device.process_message(
            self._message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.operator] == "start"
        assert self.device.attributes[DeviceAttributes.water_level] == 2
        assert self.device.attributes[DeviceAttributes.water_strong_level] == 1
        assert self.device.attributes[DeviceAttributes.wash_region] == 6
        assert self.device.attributes[DeviceAttributes.clean_left_hour] == 8
        assert new_status[DeviceAttributes.operator.value] == "start"

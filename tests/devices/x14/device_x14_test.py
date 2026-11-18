"""Test x14 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x14 import DeviceAttributes, Midea14Device
from midealan.devices.x14.message import (
    CMD_TYPE,
    DIRECTION_REVERSE,
    STATUS_OPEN,
    STATUS_STOP,
    VALUE_INVALID,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full x14 query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0x14, 0, 0, 0, 0, 0, 3, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestMidea14Device:
    """Test Midea x14 device."""

    @pytest.fixture
    def device(self) -> Midea14Device:
        """x14 device on V3 transport."""
        return Midea14Device(
            name="x14",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="00" * 32,
            key="00" * 32,
            device_protocol=ProtocolVersion.V3,
            model="",
            subtype=0,
            customize="",
        )

    def test_initial_attributes(self, device: Midea14Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.curtain_status] is None
        assert device.attributes[DeviceAttributes.curtain_position] is None

    def test_build_query(self, device: Midea14Device) -> None:
        """Build a single status query carrying the 0x01 command byte."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x01])

    def test_process_message(self, device: Midea14Device) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(
            _report_frame([CMD_TYPE, 0x10, STATUS_OPEN, 42, 0x00, 0x00]),
        )
        assert status["curtain_status"] == "open"
        assert status["curtain_position"] == 42
        assert status["curtain_direction"] == "positive"
        assert device.attributes[DeviceAttributes.software_version] == 16

    def test_process_set_echo_no_update(self, device: Midea14Device) -> None:
        """A set echo (0x02) carries no decoded state."""
        header = bytearray([0xAA, 10 + 6 + 1, 0x14, 0, 0, 0, 0, 0, 3, 0x02])
        frame = bytes(header + bytearray([CMD_TYPE, 0x10, STATUS_OPEN, 42, 0, 0, 0]))
        assert device.process_message(frame) == {}

    def test_set_curtain_status(self, device: Midea14Device) -> None:
        """Setting status sends a set with the status byte populated."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.curtain_status, "open")
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[2] == STATUS_OPEN
        # Unchanged fields stay 0xFF.
        assert message.body[3] == VALUE_INVALID

    def test_set_curtain_status_stop(self, device: Midea14Device) -> None:
        """Stop is a valid status."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.curtain_status, "stop")
        assert build_send.call_args[0][0].body[2] == STATUS_STOP

    def test_set_position(self, device: Midea14Device) -> None:
        """Setting position sends it at body offset 3."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.curtain_position, 75)
        assert build_send.call_args[0][0].body[3] == 75

    def test_set_direction(self, device: Midea14Device) -> None:
        """Setting direction sends it at body offset 4."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.curtain_direction, "reverse")
        assert build_send.call_args[0][0].body[4] == DIRECTION_REVERSE

    def test_set_status_wrong_type(self, device: Midea14Device) -> None:
        """A non-string / unknown status is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.curtain_status, 1)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.curtain_status, "half")

    def test_set_direction_wrong_type(self, device: Midea14Device) -> None:
        """A non-string / unknown direction is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.curtain_direction, "sideways")

    def test_set_position_wrong_type(self, device: Midea14Device) -> None:
        """A bool / non-number position is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.curtain_position, True)

    @pytest.mark.parametrize("value", [-1, 101])
    def test_set_position_out_of_range(
        self,
        device: Midea14Device,
        value: int,
    ) -> None:
        """A position outside 0..100 is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(DeviceAttributes.curtain_position, value)

    def test_set_readonly_attribute_ignored(self, device: Midea14Device) -> None:
        """software_version / error_code are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: Midea14Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: Midea14Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: Midea14Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: Midea14Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: Midea14Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.curtain_status] is None

"""Test x17 device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x17 import DeviceAttributes, Midea17Device
from midealan.devices.x17.message import (
    CONTROL_COMMAND,
    SELECTOR_ANION,
    SELECTOR_BAKING,
    SELECTOR_DRY,
    SELECTOR_LIGHT,
    SELECTOR_POWER,
    SELECTOR_STERILIZE,
    SELECTOR_UPDOWN,
    UPDOWN_DOWN,
    UPDOWN_PAUSE,
    UPDOWN_UP,
    VALUE_OFF,
    VALUE_ON,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType


def _report_frame(body: bytes) -> bytes:
    """Wrap a report body in a full x17 query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0x17, 0, 0, 0, 0, 0, 3, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestMidea17Device:
    """Test Midea x17 device."""

    @pytest.fixture
    def device(self) -> Midea17Device:
        """x17 device on V3 transport."""
        return Midea17Device(
            name="x17",
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

    def test_initial_attributes(self, device: Midea17Device) -> None:
        """Every exposed attribute is seeded with a safe default."""
        assert device.attributes[DeviceAttributes.power] is False
        assert device.attributes[DeviceAttributes.updown] == "pause"
        assert device.attributes[DeviceAttributes.error_code] == 0

    def test_build_query(self, device: Midea17Device) -> None:
        """Build a single status query carrying the 0x03 command byte."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x03])

    def test_process_message(self, device: Midea17Device) -> None:
        """A query reply updates every decoded attribute."""
        # power on, motor up, flags light|dry (0x05), no error.
        frame = _report_frame([VALUE_ON, UPDOWN_UP, 0x05, 0x00])
        status = device.process_message(frame)
        assert status["power"] is True
        assert status["updown"] == "up"
        assert status["light"] is True
        assert status["dry"] is True
        assert status["sterilize"] is False
        assert device.attributes[DeviceAttributes.power] is True

    def test_process_set_echo_no_update(self, device: Midea17Device) -> None:
        """A set echo (0x02) carries no decoded state, so nothing updates."""
        header = bytearray([0xAA, 10 + 4 + 1, 0x17, 0, 0, 0, 0, 0, 3, 0x02])
        frame = bytes(header + bytearray([VALUE_ON, UPDOWN_UP, 0x1F, 0x00, 0x00]))
        status = device.process_message(frame)
        assert status == {}
        assert device.attributes[DeviceAttributes.power] is False

    @pytest.mark.parametrize(
        ("attr", "value", "selector", "wire_value"),
        [
            (DeviceAttributes.power, True, SELECTOR_POWER, VALUE_ON),
            (DeviceAttributes.power, False, SELECTOR_POWER, VALUE_OFF),
            (DeviceAttributes.light, True, SELECTOR_LIGHT, VALUE_ON),
            (DeviceAttributes.sterilize, True, SELECTOR_STERILIZE, VALUE_ON),
            (DeviceAttributes.dry, False, SELECTOR_DRY, VALUE_OFF),
            (DeviceAttributes.baking, True, SELECTOR_BAKING, VALUE_ON),
            (DeviceAttributes.anion, False, SELECTOR_ANION, VALUE_OFF),
        ],
    )
    def test_set_bool_controls(
        self,
        device: Midea17Device,
        attr: str,
        value: bool,
        selector: int,
        wire_value: int,
    ) -> None:
        """Each boolean control sends command 0x00 + its selector + on/off."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(attr, value)
        build_send.assert_called_once()
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        # Body is [command, selector, value] followed by fixed zero padding.
        assert message.body[:3] == bytearray([CONTROL_COMMAND, selector, wire_value])

    @pytest.mark.parametrize(
        ("direction", "wire_value"),
        [("up", UPDOWN_UP), ("down", UPDOWN_DOWN), ("pause", UPDOWN_PAUSE)],
    )
    def test_set_updown(
        self,
        device: Midea17Device,
        direction: str,
        wire_value: int,
    ) -> None:
        """The tri-state motor control maps each direction to its Lua byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.updown, direction)
        message = build_send.call_args[0][0]
        assert message.body[:3] == bytearray(
            [CONTROL_COMMAND, SELECTOR_UPDOWN, wire_value],
        )

    def test_set_bool_wrong_type(self, device: Midea17Device) -> None:
        """A non-bool value for a boolean control is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.power, "on")

    def test_set_updown_wrong_type(self, device: Midea17Device) -> None:
        """A non-string / unknown direction for updown is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.updown, True)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.updown, "sideways")

    def test_set_readonly_attribute_ignored(self, device: Midea17Device) -> None:
        """error_code is read-only: set_attribute sends nothing."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: Midea17Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: Midea17Device) -> None:
        """A non-numeric refresh interval is logged and left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: Midea17Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: Midea17Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.power] is False

    def test_set_customize_without_refresh_key(self, device: Midea17Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

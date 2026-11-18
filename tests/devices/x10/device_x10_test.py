"""Test x10 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x10 import DeviceAttributes, Midea10Device
from midealan.devices.x10.message import POWER_OFF, POWER_ON
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full x10 query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0x10, 0, 0, 0, 0, 0, 3, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestMidea10Device:
    """Test Midea x10 device."""

    @pytest.fixture
    def device(self) -> Midea10Device:
        """x10 device on V3 transport."""
        return Midea10Device(
            name="x10",
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

    def test_initial_attributes(self, device: Midea10Device) -> None:
        """Power defaults to off."""
        assert device.attributes[DeviceAttributes.power] is False

    def test_build_query(self, device: Midea10Device) -> None:
        """Build a single status query carrying the 0x01 command byte."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x01])

    def test_process_message(self, device: Midea10Device) -> None:
        """A query reply updates power."""
        status = device.process_message(_report_frame([0x01, POWER_ON]))
        assert status["power"] is True
        assert device.attributes[DeviceAttributes.power] is True

    def test_process_set_echo_no_update(self, device: Midea10Device) -> None:
        """A set echo (0x02) carries no decoded state, so nothing updates."""
        header = bytearray([0xAA, 10 + 2 + 1, 0x10, 0, 0, 0, 0, 0, 3, 0x02])
        frame = bytes(header + bytearray([0x01, POWER_ON, 0x00]))
        status = device.process_message(frame)
        assert status == {}
        assert device.attributes[DeviceAttributes.power] is False

    @pytest.mark.parametrize(
        ("value", "wire_value"),
        [(True, POWER_ON), (False, POWER_OFF)],
    )
    def test_set_power(
        self,
        device: Midea10Device,
        value: bool,
        wire_value: int,
    ) -> None:
        """Setting power sends a set message with the power value byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.power, value)
        build_send.assert_called_once()
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body == bytearray([wire_value])

    def test_set_power_wrong_type(self, device: Midea10Device) -> None:
        """A non-bool power value is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.power, "on")

    def test_set_unknown_attribute_ignored(self, device: Midea10Device) -> None:
        """An unknown attribute sends nothing."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute("not_an_attr", True)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: Midea10Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: Midea10Device) -> None:
        """A non-numeric refresh interval is logged and left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: Midea10Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: Midea10Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: Midea10Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.power] is False

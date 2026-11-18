"""Test x9a device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9a import DeviceAttributes, Midea9aDevice
from midealan.devices.x9a.message import (
    FORM_COOK,
    FORM_STATUS,
    POWER_OFF,
    POWER_ON,
    QUERY_CMD,
    WORK_STATUS_WORK,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _query_frame(body: Sequence[int]) -> bytes:
    """Wrap a query-reply body in a full x9a frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0x9A, 0, 0, 0, 0, 0, 3, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _query_body() -> list[int]:
    """Build a full 20-byte query-reply body."""
    body = [0] * 20
    body[0] = QUERY_CMD
    body[1] = WORK_STATUS_WORK
    body[6] = 1
    body[7] = 20
    body[9] = 0x01  # microwave
    body[11] = 50  # current_temperature
    body[14] = 80  # watt
    body[15] = 30  # weight raw -> 300
    body[19] = 180  # target temperature
    return body


class TestMidea9aDevice:
    """Test Midea x9a device."""

    @pytest.fixture
    def device(self) -> Midea9aDevice:
        """x9a device on V3 transport."""
        return Midea9aDevice(
            name="x9a",
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

    def test_initial_attributes(self, device: Midea9aDevice) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.power] is None
        assert device.attributes[DeviceAttributes.mode] is None

    def test_build_query(self, device: Midea9aDevice) -> None:
        """Build a single status query carrying the 0x31 sub-command."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([QUERY_CMD])

    def test_process_message(self, device: Midea9aDevice) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_query_frame(_query_body()))
        assert status["power"] is True
        assert status["mode"] == "microwave"
        assert status["current_temperature"] == 50
        assert status["temperature"] == 180
        assert device.attributes[DeviceAttributes.weight] == 300

    def test_process_set_echo_no_query_state(self, device: Midea9aDevice) -> None:
        """A set echo (0x02) that is too short carries no decoded state."""
        header = bytearray([0xAA, 10 + 3 + 1, 0x9A, 0, 0, 0, 0, 0, 3, 0x02])
        frame = bytes(header + bytearray([0x22, FORM_STATUS, 0x03]) + bytearray([0]))
        assert device.process_message(frame) == {}

    def test_set_power_on(self, device: Midea9aDevice) -> None:
        """Power on sends a FORM_STATUS control with work_status 0x02."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.power, True)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[1] == FORM_STATUS
        assert message.body[2] == POWER_ON

    def test_set_power_off(self, device: Midea9aDevice) -> None:
        """Power off maps to work_status 0x01."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.power, False)
        assert build_send.call_args[0][0].body[2] == POWER_OFF

    def test_set_work_status(self, device: Midea9aDevice) -> None:
        """A valid work_status label is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "pause")
        assert build_send.call_args[0][0].body[1] == FORM_STATUS

    def test_set_work_status_wrong(self, device: Midea9aDevice) -> None:
        """An unknown / non-string work_status is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, "spin")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, 1)

    def test_set_lock(self, device: Midea9aDevice) -> None:
        """Lock on lands at FORM_STATUS body offset 3."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.lock, True)
        assert build_send.call_args[0][0].body[3] == 0x01

    def test_set_furnace_light(self, device: Midea9aDevice) -> None:
        """Furnace light off lands at FORM_STATUS body offset 4."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.furnace_light, False)
        assert build_send.call_args[0][0].body[4] == 0x00

    def test_set_mode(self, device: Midea9aDevice) -> None:
        """A valid mode sends a FORM_COOK control with the mode byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.mode, "pizza")
        body = build_send.call_args[0][0].body
        assert body[1] == FORM_COOK
        assert body[10] == 0xB1

    def test_set_mode_wrong(self, device: Midea9aDevice) -> None:
        """An unknown / non-string mode is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.mode, "grill")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.mode, 5)

    def test_set_temperature(self, device: Midea9aDevice) -> None:
        """Setting temperature sends it big-endian in the cook record."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 200)
        body = build_send.call_args[0][0].body
        assert body[11] == 0
        assert body[12] == 200

    def test_set_cook_seeds_from_state(self, device: Midea9aDevice) -> None:
        """A single cook-field change keeps the other cook fields from state."""
        device._attributes[DeviceAttributes.hour] = 1
        device._attributes[DeviceAttributes.minutes] = 30
        device._attributes[DeviceAttributes.second] = 15
        device._attributes[DeviceAttributes.mode] = "microwave"
        device._attributes[DeviceAttributes.watt] = 80
        device._attributes[DeviceAttributes.weight] = 300
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 150)
        body = build_send.call_args[0][0].body
        assert body[7] == 1  # seeded hour
        assert body[8] == 30  # seeded minutes
        assert body[9] == 15  # seeded second
        assert body[10] == 0x01  # seeded mode microwave
        assert body[15] == 80  # seeded watt
        assert body[16] == 30  # seeded weight 300 / 10
        assert body[12] == 150  # overridden temperature

    def test_set_cook_ignores_unknown_seed_mode(self, device: Midea9aDevice) -> None:
        """A stored mode not in the code map is not seeded."""
        device._attributes[DeviceAttributes.mode] = "bogus"
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.hour, 2)
        assert build_send.call_args[0][0].body[10] == 0

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.hour, 24),
            (DeviceAttributes.minutes, 60),
            (DeviceAttributes.second, -1),
            (DeviceAttributes.temperature, 301),
            (DeviceAttributes.weight, 3000),
        ],
    )
    def test_set_cook_out_of_range(
        self,
        device: Midea9aDevice,
        attr: str,
        value: int,
    ) -> None:
        """A cook param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_cook_wrong_type(self, device: Midea9aDevice) -> None:
        """A bool / non-number cook param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.temperature, True)

    def test_set_readonly_attribute_ignored(self, device: Midea9aDevice) -> None:
        """current_temperature / error_code are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.current_temperature, 100)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: Midea9aDevice) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: Midea9aDevice) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: Midea9aDevice) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: Midea9aDevice) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: Midea9aDevice) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.power] is None

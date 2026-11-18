"""Test f1 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.f1 import DeviceAttributes, MideaF1Device
from midealan.devices.f1.message import INNER_HEAD, POWER_ON
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full f1 query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xF1, 0, 0, 0, 0, 0, 1, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 27-byte inner-frame status report body."""
    body = [0] * 27
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[4] = 0x04
    body[5] = 0x03
    body[6] = 0x02
    body[7] = 0x01
    body[9] = 1
    body[13] = 0
    body[14] = 1
    body[17] = 55
    body[26] = 7
    return body


class TestMideaF1Device:
    """Test Midea f1 device."""

    @pytest.fixture
    def device(self) -> MideaF1Device:
        """f1 device on V3 transport."""
        return MideaF1Device(
            name="f1",
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

    def test_initial_attributes(self, device: MideaF1Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_mode] is None
        assert device.attributes[DeviceAttributes.power] is None

    def test_build_query(self, device: MideaF1Device) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaF1Device) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_status_body()))
        assert status["work_mode"] == 0x01020304
        assert status["cup_status"] == "hot_cup"
        assert status["current_temp"] == 55
        assert device.attributes[DeviceAttributes.code_id] == 7

    def test_process_message_short_no_update(self, device: MideaF1Device) -> None:
        """A body shorter than the fixed record carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_power(self, device: MideaF1Device) -> None:
        """Setting power on sends a control with the power byte at body[9]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.power, True)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[9] == POWER_ON

    def test_set_power_off(self, device: MideaF1Device) -> None:
        """Setting power off sends 0x00 at body[9]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.power, False)
        assert build_send.call_args[0][0].body[9] == 0x00

    def test_set_work_mode(self, device: MideaF1Device) -> None:
        """Setting work_mode sends it little-endian at body[4..7]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_mode, 0x01020304)
        body = build_send.call_args[0][0].body
        assert body[4] == 0x04
        assert body[7] == 0x01

    def test_set_speed(self, device: MideaF1Device) -> None:
        """Setting speed lands at body[17]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.speed, 5)
        assert build_send.call_args[0][0].body[17] == 5

    def test_set_seeds_from_state(self, device: MideaF1Device) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.work_mode] = 0x55
        device._attributes[DeviceAttributes.power] = True
        device._attributes[DeviceAttributes.set_work_temp] = 90
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.speed, 3)
        body = build_send.call_args[0][0].body
        assert body[4] == 0x55  # seeded work_mode
        assert body[9] == POWER_ON  # seeded power
        assert body[16] == 90  # seeded set_work_temp
        assert body[17] == 3  # overridden speed

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.speed, 9),
            (DeviceAttributes.set_keep_warm_time, 60),
            (DeviceAttributes.appoint_time, 70000),
            (DeviceAttributes.set_work_temp, 256),
            (DeviceAttributes.code_id, 256),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaF1Device,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaF1Device) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.speed, True)

    @pytest.mark.parametrize(
        "value",
        [3.9, float("nan"), float("inf")],
    )
    def test_set_non_integer_float_rejected(
        self,
        device: MideaF1Device,
        value: float,
    ) -> None:
        """A fractional / non-finite float is rejected, not truncated."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.speed, value)

    def test_set_integer_float_accepted(self, device: MideaF1Device) -> None:
        """A whole-number float (e.g. 5.0) is accepted and sent as an int."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.speed, 5.0)
        assert build_send.call_args[0][0].body[17] == 5

    def test_set_readonly_ignored(self, device: MideaF1Device) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.current_temp, 50)
            device.set_attribute(DeviceAttributes.lid_status, "no_cup")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaF1Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaF1Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaF1Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaF1Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaF1Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_mode] is None

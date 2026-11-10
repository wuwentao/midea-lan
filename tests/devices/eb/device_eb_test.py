"""Test eb device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.eb import DeviceAttributes, MideaEBDevice
from midealan.devices.eb.message import INNER_HEAD
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full eb query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xEB, 0, 0, 0, 0, 0, 1, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 24-byte inner-frame status report body."""
    body = [0] * 24
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[2] = 0x02
    body[7] = 0x14
    body[8] = 0x27
    body[9] = 0x01
    body[10] = 3
    body[11] = 0x12
    body[12] = 0x34
    body[19] = 7
    body[23] = 9
    return body


class TestMideaEBDevice:
    """Test Midea eb device."""

    @pytest.fixture
    def device(self) -> MideaEBDevice:
        """Eb device on V3 transport."""
        return MideaEBDevice(
            name="eb",
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

    def test_initial_attributes(self, device: MideaEBDevice) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.function_no] is None

    def test_build_query(self, device: MideaEBDevice) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaEBDevice) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_status_body()))
        assert status["work_status"] == 3
        assert status["function_no"] == 0x1234
        assert status["fire_level"] == 7
        assert device.attributes[DeviceAttributes.error_code] == 9

    def test_process_message_short_no_update(self, device: MideaEBDevice) -> None:
        """A body shorter than the minimum carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_work_status(self, device: MideaEBDevice) -> None:
        """Setting work_status sends a control frame with it at body[11]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[11] == 1

    def test_set_function_no(self, device: MideaEBDevice) -> None:
        """Setting function_no sends it big-endian at body[9]/body[10]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.function_no, 0x1234)
        body = build_send.call_args[0][0].body
        assert body[9] == 0x12
        assert body[10] == 0x34

    def test_set_fire_level(self, device: MideaEBDevice) -> None:
        """Setting fire_level lands at body[14]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.fire_level, 5)
        assert build_send.call_args[0][0].body[14] == 5

    def test_set_seeds_from_state(self, device: MideaEBDevice) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.function_no] = 0x55
        device._attributes[DeviceAttributes.fire_level] = 3
        device._attributes[DeviceAttributes.time_reserve_hr] = 2
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        body = build_send.call_args[0][0].body
        assert body[10] == 0x55  # seeded function_no lo
        assert body[11] == 1  # overridden work_status
        assert body[12] == 2  # seeded reserve hr
        assert body[14] == 3  # seeded fire_level

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.fire_level, 22),
            (DeviceAttributes.time_reserve_hr, 24),
            (DeviceAttributes.time_reserve_min, 60),
            (DeviceAttributes.definite_time_hr, -1),
            (DeviceAttributes.function_no, 0x10000),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaEBDevice,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaEBDevice) -> None:
        """A bool / non-number param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.fire_level, True)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, "on")

    def test_set_readonly_ignored(self, device: MideaEBDevice) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.time_running_hr, 2)
            device.set_attribute(DeviceAttributes.response, "response_normal")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaEBDevice) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaEBDevice) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaEBDevice) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaEBDevice) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaEBDevice) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

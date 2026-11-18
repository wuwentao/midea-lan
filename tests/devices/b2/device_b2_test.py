"""Test b2 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.b2 import DeviceAttributes, MideaB2Device
from midealan.devices.b2.message import STATUS_STANDBY, STATUS_WORK
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full b2 query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xB2, 0, 0, 0, 0, 0, 3, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _report_body() -> list[int]:
    """Build a full 17-byte report body."""
    body = [0] * 17
    body[0] = STATUS_WORK
    body[1] = 0x71  # vegetable
    body[2] = 2
    body[3] = 45
    body[4] = 90
    body[16] = 0x01  # lock
    return body


class TestMideaB2Device:
    """Test Midea b2 device."""

    @pytest.fixture
    def device(self) -> MideaB2Device:
        """b2 device on V3 transport."""
        return MideaB2Device(
            name="b2",
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

    def test_initial_attributes(self, device: MideaB2Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.work_mode] is None

    def test_build_query(self, device: MideaB2Device) -> None:
        """Build a single status query with an empty body."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x00])

    def test_process_message(self, device: MideaB2Device) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_report_body()))
        assert status["work_status"] == "work"
        assert status["work_mode"] == "vegetable"
        assert status["temperature"] == 90
        assert device.attributes[DeviceAttributes.lock] is True

    def test_process_message_unknown_status_skipped(
        self,
        device: MideaB2Device,
    ) -> None:
        """An unknown status byte leaves work_status out of the update."""
        body = _report_body()
        body[0] = 0x55  # not a known work_status
        status = device.process_message(_report_frame(body))
        assert "work_status" not in status
        # Other decoded fields still land.
        assert status["temperature"] == 90

    def test_set_work_status(self, device: MideaB2Device) -> None:
        """Setting work_status sends it as the leading body byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "work")
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[0] == STATUS_WORK

    def test_set_work_status_wrong(self, device: MideaB2Device) -> None:
        """An unknown / non-string work_status is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, "spin")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, 1)

    def test_set_work_mode(self, device: MideaB2Device) -> None:
        """Setting work_mode sends it at body offset 1."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_mode, "fish")
        assert build_send.call_args[0][0].body[1] == 0x03

    def test_set_work_mode_wrong(self, device: MideaB2Device) -> None:
        """An unknown / non-string work_mode is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_mode, "roast")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_mode, 5)

    def test_set_temperature(self, device: MideaB2Device) -> None:
        """Setting temperature sends it at body offset 4."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 80)
        assert build_send.call_args[0][0].body[4] == 80

    def test_set_lock(self, device: MideaB2Device) -> None:
        """Setting lock sends it at the control body offset 14."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.lock, True)
        assert build_send.call_args[0][0].body[14] == 0x01

    def test_set_seeds_from_state(self, device: MideaB2Device) -> None:
        """A single-field change keeps the other fields from current state."""
        device._attributes[DeviceAttributes.work_status] = "standby"
        device._attributes[DeviceAttributes.work_mode] = "fish"
        device._attributes[DeviceAttributes.work_hour] = 1
        device._attributes[DeviceAttributes.work_minute] = 20
        device._attributes[DeviceAttributes.temperature] = 70
        device._attributes[DeviceAttributes.lock] = True
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "work")
        body = build_send.call_args[0][0].body
        assert body[0] == STATUS_WORK  # overridden
        assert body[1] == 0x03  # seeded mode fish
        assert body[2] == 1  # seeded hour
        assert body[3] == 20  # seeded minute
        assert body[4] == 70  # seeded temperature
        assert body[14] == 0x01  # seeded lock

    def test_set_ignores_unknown_seed(self, device: MideaB2Device) -> None:
        """A stored status / mode not in the code map is not seeded."""
        device._attributes[DeviceAttributes.work_status] = "bogus"
        device._attributes[DeviceAttributes.work_mode] = "bogus"
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 60)
        body = build_send.call_args[0][0].body
        assert body[0] == STATUS_STANDBY  # default work_status
        assert body[1] == 0  # default mode

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.work_hour, 10),
            (DeviceAttributes.work_minute, 60),
            (DeviceAttributes.temperature, 40),
            (DeviceAttributes.temperature, 101),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaB2Device,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaB2Device) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.temperature, True)

    def test_set_readonly_ignored(self, device: MideaB2Device) -> None:
        """door/water/box state are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.door_state, "open")
            device.set_attribute(DeviceAttributes.water_state, "empty")
            device.set_attribute(DeviceAttributes.box_state, "out")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaB2Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaB2Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaB2Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaB2Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaB2Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

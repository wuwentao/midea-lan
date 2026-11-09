"""Test e9 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.e9 import DeviceAttributes, MideaE9Device
from midealan.devices.e9.message import INNER_HEAD, REPORT_BASE_PUSH
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(
    body: Sequence[int], message_type: int = MessageType.notify1
) -> bytes:
    """Wrap a report body in a full e9 response frame."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, 0xE9, 0, 0, 0, 0, 0, 0, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _push_status_body() -> list[int]:
    """Build a control-echo / notify status body (payload base at body[6])."""
    body = [0] * (REPORT_BASE_PUSH + 16)
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[REPORT_BASE_PUSH + 0] = 0x04  # control_cmd_code lo
    body[REPORT_BASE_PUSH + 2] = 1  # response normal
    body[REPORT_BASE_PUSH + 3] = 1  # volume
    body[REPORT_BASE_PUSH + 6] = 1  # work_status
    body[REPORT_BASE_PUSH + 8] = 80  # bottom_temperature
    body[REPORT_BASE_PUSH + 15] = 7  # error_code
    return body


class TestMideaE9Device:
    """Test Midea e9 device."""

    @pytest.fixture
    def device(self) -> MideaE9Device:
        """E9 device on V3 transport."""
        return MideaE9Device(
            name="e9",
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

    def test_initial_attributes(self, device: MideaE9Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.bake_temperature] is None

    def test_build_query(self, device: MideaE9Device) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaE9Device) -> None:
        """A notify report updates every decoded attribute."""
        status = device.process_message(_report_frame(_push_status_body()))
        assert status["work_status"] == 1
        assert status["control_cmd_code"] == 0x04
        assert status["volume"] == 1
        assert device.attributes[DeviceAttributes.bottom_temperature] == 80
        assert device.attributes[DeviceAttributes.error_code] == 7

    def test_process_message_short_no_update(self, device: MideaE9Device) -> None:
        """A body shorter than the minimum record carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_work_status(self, device: MideaE9Device) -> None:
        """Setting work_status lands at body[11]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[11] == 1

    def test_set_control_cmd_code(self, device: MideaE9Device) -> None:
        """Setting control_cmd_code sends it little-endian at body[6]/body[7]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.control_cmd_code, 0x1234)
        body = build_send.call_args[0][0].body
        assert body[6] == 0x34
        assert body[7] == 0x12

    def test_set_bake_temperature(self, device: MideaE9Device) -> None:
        """Setting bake_temperature lands at body[16]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.bake_temperature, 180)
        assert build_send.call_args[0][0].body[16] == 180

    def test_set_time_cuisine(self, device: MideaE9Device) -> None:
        """Setting the write-only cuisine time lands at body[12]/body[13]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.time_cuisine_min, 45)
        assert build_send.call_args[0][0].body[12] == 45

    def test_set_seeds_from_state(self, device: MideaE9Device) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.control_cmd_code] = 0x0E
        device._attributes[DeviceAttributes.volume] = 2
        device._attributes[DeviceAttributes.bake_temperature] = 150
        device._attributes[DeviceAttributes.time_cuisine_min] = 20
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        body = build_send.call_args[0][0].body
        assert body[6] == 0x0E  # seeded control_cmd_code
        assert body[8] == 2  # seeded volume
        assert body[11] == 1  # new work_status
        assert body[12] == 20  # seeded time_cuisine_min
        assert body[16] == 150  # seeded bake_temperature

    def test_set_ignores_non_int_seed(self, device: MideaE9Device) -> None:
        """A stored non-int / bool field is not seeded into the control frame."""
        device._attributes[DeviceAttributes.volume] = True
        device._attributes[DeviceAttributes.color] = "x"
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        body = build_send.call_args[0][0].body
        assert body[8] == 0  # bool volume not seeded
        assert body[9] == 0  # str color not seeded

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.volume, 4),
            (DeviceAttributes.color, 4),
            (DeviceAttributes.dosing, 4),
            (DeviceAttributes.work_status, 5),
            (DeviceAttributes.time_cuisine_min, 60),
            (DeviceAttributes.time_reserve_hr, 24),
            (DeviceAttributes.bake_temperature, 256),
            (DeviceAttributes.control_cmd_code, 0x10000),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaE9Device,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaE9Device) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.volume, True)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.volume, "x")

    def test_set_readonly_ignored(self, device: MideaE9Device) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.bottom_temperature, 50)
            device.set_attribute(DeviceAttributes.work_stage, 2)
            device.set_attribute(DeviceAttributes.product_volume, 1)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaE9Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaE9Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaE9Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaE9Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaE9Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

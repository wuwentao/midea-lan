"""Test ef device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ef import DeviceAttributes, MideaEFDevice
from midealan.devices.ef.message import DRINK_WARM, INNER_HEAD
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full ef query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xEF, 0, 0, 0, 0, 0, 1, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 20-byte inner-frame status report body."""
    body = [0] * 20
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[4] = 0x34
    body[5] = 0x12
    body[8] = 2
    body[10] = 1
    body[12] = 0x01 | 0x04
    body[18] = 80
    body[19] = 55
    return body


class TestMideaEFDevice:
    """Test Midea ef device."""

    @pytest.fixture
    def device(self) -> MideaEFDevice:
        """Ef device on V3 transport."""
        return MideaEFDevice(
            name="ef",
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

    def test_initial_attributes(self, device: MideaEFDevice) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.drink_style] is None

    def test_build_query(self, device: MideaEFDevice) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaEFDevice) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_status_body()))
        assert status["work_status"] == 2
        assert status["cmd_code"] == 0x1234
        assert status["reserve"] is True
        assert device.attributes[DeviceAttributes.temperature_current] == 55

    def test_process_message_short_no_update(self, device: MideaEFDevice) -> None:
        """A body shorter than the fixed record carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_reserve(self, device: MideaEFDevice) -> None:
        """Setting reserve sets the reserve bit in the flag byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.reserve, True)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[9] & 0x01

    def test_set_warm(self, device: MideaEFDevice) -> None:
        """Setting warm sets the warm bit in the flag byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.warm, True)
        assert build_send.call_args[0][0].body[9] & 0x02

    def test_set_drink_style(self, device: MideaEFDevice) -> None:
        """drink_style warm_drink sets the drink-style flag bit."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.drink_style, DRINK_WARM)
        assert build_send.call_args[0][0].body[9] & 0x04

    def test_set_drink_style_wrong(self, device: MideaEFDevice) -> None:
        """An unknown / non-string drink_style is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.drink_style, "iced")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.drink_style, 1)

    def test_set_temperature_setting(self, device: MideaEFDevice) -> None:
        """Setting temperature_setting lands at body[14]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature_setting, 80)
        assert build_send.call_args[0][0].body[14] == 80

    def test_set_cmd_code(self, device: MideaEFDevice) -> None:
        """Setting cmd_code sends it little-endian at body[4]/body[5]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.cmd_code, 0x1234)
        body = build_send.call_args[0][0].body
        assert body[4] == 0x34
        assert body[5] == 0x12

    def test_set_seeds_from_state(self, device: MideaEFDevice) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.cmd_code] = 0x55
        device._attributes[DeviceAttributes.reserve] = True
        device._attributes[DeviceAttributes.drink_style] = DRINK_WARM
        device._attributes[DeviceAttributes.temperature_setting] = 70
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.warm, True)
        body = build_send.call_args[0][0].body
        assert body[4] == 0x55  # seeded cmd_code
        assert body[9] == 0x01 | 0x02 | 0x04  # seeded reserve + warm + warm_drink
        assert body[14] == 70  # seeded temperature_setting

    def test_set_ignores_unknown_seed_style(self, device: MideaEFDevice) -> None:
        """A stored drink_style not in the known set is not seeded."""
        device._attributes[DeviceAttributes.drink_style] = "bogus"
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.warm, True)
        assert build_send.call_args[0][0].body[9] & 0x04 == 0

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.temperature_setting, 99),
            (DeviceAttributes.time_reserve_hr, 24),
            (DeviceAttributes.time_warm_min, 60),
            (DeviceAttributes.cmd_id, 256),
            (DeviceAttributes.cmd_code, 0x10000),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaEFDevice,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaEFDevice) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.cmd_id, True)

    def test_set_readonly_ignored(self, device: MideaEFDevice) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.temperature_current, 50)
            device.set_attribute(DeviceAttributes.work_step, 2)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaEFDevice) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaEFDevice) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaEFDevice) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaEFDevice) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaEFDevice) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

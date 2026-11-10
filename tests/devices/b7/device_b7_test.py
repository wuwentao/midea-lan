"""Test b7 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.b7 import DeviceAttributes, MideaB7Device
from midealan.devices.b7.message import (
    BURNER_LEFT,
    BURNER_LOCK,
    BURNER_RIGHT,
    CMD_STATUS_NOTIFY,
    FUNCTION_GEAR,
    FUNCTION_POWER,
    FUNCTION_TEMP_MIN,
    LOCK_OFF,
    LOCK_ON,
    MessageB7Response,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


def _frame(msg_type: int, body: Sequence[int]) -> bytes:
    """Wrap a device body in a full b7 frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xB7, 0, 0, 0, 0, 0, 3, msg_type])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Minimal status body reaching the packed-flags byte."""
    body = [0] * 18
    body[0] = CMD_STATUS_NOTIFY
    body[1] = 2  # left_status
    body[13] = 3  # left_gear
    body[17] = 0b00000001  # lock bit
    return body


class TestMideaB7Device:
    """Test Midea b7 device."""

    @pytest.fixture
    def device(self) -> MideaB7Device:
        """b7 device on V3 transport."""
        return MideaB7Device(
            name="b7",
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

    def test_initial_attributes(self, device: MideaB7Device) -> None:
        """Every attribute starts unset."""
        for attr in DeviceAttributes:
            assert device.attributes[attr] is None

    def test_build_query(self, device: MideaB7Device) -> None:
        """Build both a status and an error query."""
        query = device.build_query()
        assert len(query) == 2

    def test_process_message(self, device: MideaB7Device) -> None:
        """A status report updates the decoded attributes."""
        status = device.process_message(
            _frame(MessageType.notify1, _status_body()),
        )
        assert status["left_status"] == 2
        assert status["left_gear"] == 3
        assert device.attributes[DeviceAttributes.lock] is True

    def test_process_error_message(self, device: MideaB7Device) -> None:
        """An error report updates error_code."""
        body = [0x32, 0x03, 0b00000001, 0, 0, 0]
        status = device.process_message(_frame(MessageType.query, body))
        assert status["error_code"] == 1

    def test_set_power(self, device: MideaB7Device) -> None:
        """Power routes to the right burner with function_control 1."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.left_power, True)
        body = build_send.call_args[0][0].body
        assert body[1] == BURNER_LEFT
        assert body[2] == FUNCTION_POWER

    def test_set_power_right(self, device: MideaB7Device) -> None:
        """Right power selects the right burner."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.right_power, True)
        assert build_send.call_args[0][0].body[1] == BURNER_RIGHT

    def test_set_gear(self, device: MideaB7Device) -> None:
        """Gear routes with function_control 3 and the gear value."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.right_gear_set, 4)
        body = build_send.call_args[0][0].body
        assert body[1] == BURNER_RIGHT
        assert body[2] == FUNCTION_GEAR
        assert body[5] == 4

    def test_set_temp(self, device: MideaB7Device) -> None:
        """Temperature routes with the temp function and a 16-bit value."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.left_temp_set, 300)
        body = build_send.call_args[0][0].body
        assert body[2] == FUNCTION_TEMP_MIN
        assert body[6] == (300 >> 8) & 0xFF
        assert body[7] == 300 & 0xFF

    def test_set_temp_right(self, device: MideaB7Device) -> None:
        """Right temperature writes the right-burner 16-bit pair."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.right_temp_set, 250)
        body = build_send.call_args[0][0].body
        assert body[8] == (250 >> 8) & 0xFF
        assert body[9] == 250 & 0xFF

    def test_set_lock(self, device: MideaB7Device) -> None:
        """Lock routes to the lock burner selector."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.lock, True)
        body = build_send.call_args[0][0].body
        assert body[1] == BURNER_LOCK
        assert body[2] == LOCK_ON

    def test_set_lock_off(self, device: MideaB7Device) -> None:
        """Lock off routes to the lock burner selector with LOCK_OFF."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.lock, False)
        body = build_send.call_args[0][0].body
        assert body[1] == BURNER_LOCK
        assert body[2] == LOCK_OFF

    def test_fail_response_decode(self) -> None:
        """A fail-response frame exposes the reason on the response object."""
        resp = MessageB7Response(_frame(MessageType.set, [0x00, 0xFE, 0x00, 7]))
        assert resp.fail_resp_reason == 7

    def test_gear_out_of_range(self, device: MideaB7Device) -> None:
        """A gear above the byte range raises ValueOutOfRange."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(DeviceAttributes.left_gear_set, 300)

    def test_temp_out_of_range(self, device: MideaB7Device) -> None:
        """A temperature above the 16-bit range raises ValueOutOfRange."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(DeviceAttributes.left_temp_set, 99999)

    def test_gear_wrong_type(self, device: MideaB7Device) -> None:
        """A non-numeric gear raises ValueWrongType."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.left_gear_set, "x")

    def test_gear_bool_rejected(self, device: MideaB7Device) -> None:
        """A bool gear value is rejected as the wrong type."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.left_gear_set, True)

    def test_gear_nan_rejected(self, device: MideaB7Device) -> None:
        """A NaN gear value is rejected (int(nan) would raise ValueError)."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.left_gear_set, float("nan"))

    def test_gear_inf_rejected(self, device: MideaB7Device) -> None:
        """An infinite gear value is rejected (int(inf) would raise OverflowError)."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.left_gear_set, float("inf"))

    def test_readonly_attrs_noop(self, device: MideaB7Device) -> None:
        """Status / error attributes are read-only and send nothing."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.left_status, 5)
            device.set_attribute(DeviceAttributes.error_code, 3)
            device.set_attribute(DeviceAttributes.gas_warn, True)
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaB7Device) -> None:
        """A valid refresh_interval customize updates the interval."""
        device.set_customize('{"refresh_interval": 30}')
        assert device._refresh_interval == 30

    def test_set_customize_invalid_type(self, device: MideaB7Device) -> None:
        """A non-numeric refresh_interval is ignored without raising."""
        device.set_customize('{"refresh_interval": "bad"}')

    def test_set_customize_bad_json(self, device: MideaB7Device) -> None:
        """Malformed customize JSON is swallowed."""
        device.set_customize("{not json")

    def test_set_customize_without_refresh_interval(
        self,
        device: MideaB7Device,
    ) -> None:
        """Customize JSON that omits refresh_interval is a harmless no-op."""
        device.set_customize('{"other": 1}')

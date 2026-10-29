"""Test x13 message."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x13.message import (
    Message13Base,
    Message13Response,
    MessageMainLightBody,
    MessageQuery,
    MessageSet,
)
from midealan.message import ListTypes, MessageType


class TestMessage13Base:
    """Test x13 Message Base."""

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = Message13Base(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X24,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test x13 Message Query."""

    def test_query_body(self) -> None:
        """Test query body."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x24, 0x00, 0x00, 0x00, 0x00])


class TestMessageSet:
    """Test x13 Message Set."""

    @pytest.mark.parametrize(
        ("attr", "value", "expected_byte", "expected_body_type"),
        [
            ("power", True, 0x01, ListTypes.X01),
            ("power", False, 0x00, ListTypes.X01),
            ("effect", 2, 0x03, ListTypes.X01),
            ("effect", 5, 0x06, ListTypes.X01),
            ("effect", 0, 0x00, ListTypes.X00),  # effect 0 is out of set range
            ("color_temperature", 128, 0x80, ListTypes.X03),
            ("brightness", 100, 0x64, ListTypes.X04),
        ],
    )
    def test_set_body(
        self,
        attr: str,
        value: bool | int,
        expected_byte: int,
        expected_body_type: ListTypes,
    ) -> None:
        """Test set body for each settable attribute."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1)
        setattr(msg, attr, value)
        assert msg._body == bytearray([expected_byte, 0x00, 0x00, 0x00])
        assert msg.body_type == expected_body_type

    def test_set_body_default(self) -> None:
        """Test set body with no attribute set is empty."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1)
        assert msg._body == bytearray([0x00, 0x00, 0x00, 0x00])
        assert msg.body_type == ListTypes.X00


class TestMessageSetFanLight:
    """Test x13 Message Set for fan-light models."""

    @pytest.mark.parametrize(
        ("attr", "value", "expected_byte", "expected_body_type"),
        [
            ("power", True, 0x01, ListTypes.X01),
            ("power", False, 0x00, ListTypes.X01),
            ("brightness", 100, 0x64, ListTypes.X04),
            ("color_temperature", 128, 0x80, ListTypes.X03),
            ("fan_power", True, 0x01, ListTypes.X31),
            ("fan_power", False, 0x00, ListTypes.X31),
            ("fan_speed", 41, 0x29, ListTypes.X34),
        ],
    )
    def test_set_body(
        self,
        attr: str,
        value: bool | int,
        expected_byte: int,
        expected_body_type: ListTypes,
    ) -> None:
        """Test the six-byte payload used by fan-light models."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1, fan_light=True)
        setattr(msg, attr, value)
        assert msg._body == bytearray([expected_byte, 0x00, 0x00, 0x00, 0x00, 0x00])
        assert msg.body_type == expected_body_type

    def test_set_body_default(self) -> None:
        """Test the default fan-light payload is six bytes long."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1, fan_light=True)
        assert msg._body == bytearray(6)
        assert msg.body_type == ListTypes.X00


def _build_status_body(fan_light: bool) -> bytearray:
    """Build an A4 status body in either layout."""
    body = bytearray(11)
    body[0] = 0xA4  # main light body type
    body[1] = 100  # brightness
    body[2] = 255  # color temperature
    body[3] = 3  # effect raw value
    body[5] = 1 if fan_light else 0  # light power on fan-light models
    body[6] = 41  # fan speed raw value
    body[8] = 0 if fan_light else 1  # light power on legacy models
    body[10] = 1  # fan power

    return body


class TestMessageMainLightBody:
    """Test x13 main light body parsing."""

    def test_legacy_layout(self) -> None:
        """Test the legacy layout reads light power from byte 8."""
        parsed = MessageMainLightBody(_build_status_body(fan_light=False))
        assert parsed.power is True
        assert parsed.fan_speed is None
        assert parsed.fan_power is False
        assert parsed.fan_state_valid is False

    @pytest.mark.parametrize(("power_byte", "expected"), [(1, True), (0, False)])
    def test_fan_light_layout(self, power_byte: int, expected: bool) -> None:
        """Test the fan-light layout reads power, speed and fan state."""
        body = _build_status_body(fan_light=True)
        body[5] = power_byte
        parsed = MessageMainLightBody(body, fan_light=True)
        assert parsed.power is expected
        assert parsed.fan_speed == 41
        assert parsed.fan_power is True
        assert parsed.fan_state_valid is True

    def test_fan_light_truncated_body(self) -> None:
        """Test a truncated fan-light body does not expose the fan state."""
        body = _build_status_body(fan_light=True)[:10]
        parsed = MessageMainLightBody(body, fan_light=True)
        assert parsed.fan_state_valid is False
        assert parsed.fan_speed is None
        assert parsed.fan_power is False

    def test_response_propagates_fan_light(self) -> None:
        """Test Message13Response parses the fan-light layout when asked."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = _build_status_body(fan_light=True)
        response = Message13Response(
            bytes(header + body + bytearray([0x00])),
            fan_light=True,
        )
        assert response.power is True
        assert response.fan_speed == 41
        assert response.fan_power is True

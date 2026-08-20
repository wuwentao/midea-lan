"""Test AD message."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ad.message import (
    Message21Query,
    Message31Query,
    MessageADBase,
    MessageADResponse,
)
from midealan.message import ListTypes, MessageType


class TestMessageADBase:
    """Test AD Message Base."""

    def test_message_id_increment(self) -> None:
        """Test message Id Increment."""
        msg = MessageADBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X21,
        )
        msg2 = MessageADBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X21,
        )
        assert msg2._message_id == msg._message_id + 1
        # test reset
        for _ in range(254 - msg2._message_id):
            msg = MessageADBase(
                protocol_version=ProtocolVersion.V1,
                message_type=MessageType.query,
                body_type=ListTypes.X21,
            )
        assert msg._message_id == 1

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = MessageADBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X21,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessage21Query:
    """Test Message21Query."""

    def test_query_body(self) -> None:
        """Test query body: body type, payload, message id and CRC."""
        msg = Message21Query(protocol_version=ProtocolVersion.V1)
        body = msg.body
        assert body[:2] == bytearray([0x21, 0x01])
        assert body[2] == msg._message_id
        assert len(body) == 4


class TestMessage31Query:
    """Test Message31Query."""

    def test_query_body(self) -> None:
        """Test query body: body type, payload, message id and CRC."""
        msg = Message31Query(protocol_version=ProtocolVersion.V1)
        body = msg.body
        assert body[:2] == bytearray([0x31, 0x01])
        assert body[2] == msg._message_id
        assert len(body) == 4


class TestMessageADResponse:
    """Test AD response parsing."""

    def test_notify_presets_function(self) -> None:
        """Test notify body parses the presets_function sub message."""
        header = bytearray([0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, 0x03])
        body = bytearray(18)
        body[0] = ListTypes.X11
        body[1] = ListTypes.X04
        body[3] = ListTypes.X01
        body[4] = 0x01
        response = MessageADResponse(bytes(header + body + bytearray([0x00])))
        assert getattr(response, "presets_function", None) is True
        assert not hasattr(response, "fall_asleep_status")

    def test_notify_fall_asleep_status(self) -> None:
        """Test notify body parses the fall_asleep_status sub message."""
        header = bytearray([0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, 0x03])
        body = bytearray(18)
        body[0] = ListTypes.X11
        body[1] = ListTypes.X04
        body[3] = ListTypes.X02
        body[4] = 0x01
        response = MessageADResponse(bytes(header + body + bytearray([0x00])))
        assert getattr(response, "fall_asleep_status", None) is True
        assert not hasattr(response, "presets_function")

    def test_notify_unhandled_x04_sub_message(self) -> None:
        """Test notify body ignores unhandled X04 sub messages."""
        header = bytearray([0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, 0x03])
        body = bytearray(18)
        body[0] = ListTypes.X11
        body[1] = ListTypes.X04
        body[3] = ListTypes.X03
        response = MessageADResponse(bytes(header + body + bytearray([0x00])))
        assert not hasattr(response, "presets_function")
        assert not hasattr(response, "fall_asleep_status")

    def test_notify_unhandled_sub_body(self) -> None:
        """Test notify body ignores unhandled sub body types."""
        header = bytearray([0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, 0x03])
        body = bytearray(18)
        body[0] = ListTypes.X11
        body[1] = ListTypes.X02
        response = MessageADResponse(bytes(header + body + bytearray([0x00])))
        assert not hasattr(response, "presets_function")
        assert not hasattr(response, "fall_asleep_status")

"""Test x10 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.x10.message import (
    POWER_OFF,
    POWER_ON,
    QUERY_PAYLOAD,
    Message10Response,
    MessagePower,
    MessageQuery,
    X10GeneralMessageBody,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full x10 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.X10, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestX10GeneralMessageBody:
    """Test x10 general message body (report decode)."""

    def test_power_on(self) -> None:
        """Power byte at body[1] reads on."""
        assert X10GeneralMessageBody(bytearray([0x01, POWER_ON])).power is True

    def test_power_off(self) -> None:
        """Power byte at body[1] reads off."""
        assert X10GeneralMessageBody(bytearray([0x01, POWER_OFF])).power is False


class TestMessageQuery:
    """Test x10 query message."""

    def test_query_body(self) -> None:
        """Query body is the single command byte 0x01."""
        query = MessageQuery(3)
        assert query.body == bytearray([QUERY_PAYLOAD])
        frame = query.serialize()
        assert frame[2] == DeviceType.X10
        assert frame[9] == MessageType.query
        assert frame[10] == QUERY_PAYLOAD


class TestMessagePower:
    """Test x10 power control message."""

    def test_power_on_body(self) -> None:
        """Power-on carries the value in the body_type byte (Lua layout)."""
        message = MessagePower(3)
        message.power = True
        assert message.body == bytearray([POWER_ON])
        frame = message.serialize()
        assert frame[9] == MessageType.set
        assert frame[10] == POWER_ON

    def test_power_off_body(self) -> None:
        """Power-off carries 0x00 in the body_type byte."""
        message = MessagePower(3)
        message.power = False
        assert message.body == bytearray([POWER_OFF])

    def test_power_getter_roundtrips(self) -> None:
        """The power property reflects the last set value."""
        message = MessagePower(3)
        assert message.power is False
        message.power = True
        assert message.power is True


class TestMessage10Response:
    """Test x10 response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates power."""
        response = Message10Response(_report_frame([0x01, POWER_ON]))
        assert getattr(response, "power") is True  # noqa: B009

    def test_notify_decodes(self) -> None:
        """A notify (0x04) is decoded the same as a query reply."""
        response = Message10Response(
            _report_frame([0x01, POWER_OFF], MessageType.notify1),
        )
        assert getattr(response, "power") is False  # noqa: B009

    def test_set_echo_not_decoded(self) -> None:
        """The set echo (0x02) is ignored."""
        response = Message10Response(_report_frame([0x01, POWER_ON], MessageType.set))
        assert not hasattr(response, "power")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the power offset decodes to nothing."""
        response = Message10Response(_report_frame([0x01]))
        assert not hasattr(response, "power")

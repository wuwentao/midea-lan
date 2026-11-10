"""Test x14 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.x14.message import (
    CMD_TYPE,
    DIRECTION_POSITIVE,
    DIRECTION_REVERSE,
    QUERY_PAYLOAD,
    STATUS_CLOSE,
    STATUS_OPEN,
    STATUS_STOP,
    VALUE_INVALID,
    Message14Response,
    MessageQuery,
    MessageSet,
    X14GeneralMessageBody,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full x14 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.X14, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestX14GeneralMessageBody:
    """Test x14 general message body (report decode)."""

    def test_full_record(self) -> None:
        """All fields present (no 0xFF sentinels)."""
        body = bytearray([CMD_TYPE, 0x10, STATUS_OPEN, 42, DIRECTION_POSITIVE, 0x00])
        msg = X14GeneralMessageBody(body)
        assert msg.software_version == 16
        assert msg.curtain_status == "open"
        assert msg.curtain_position == 42
        assert msg.curtain_direction == "positive"
        assert msg.error_code == 0

    def test_status_close_and_reverse(self) -> None:
        """Close status + reverse direction decode to their labels."""
        body = bytearray([CMD_TYPE, 0x01, STATUS_CLOSE, 0, DIRECTION_REVERSE, 0x00])
        msg = X14GeneralMessageBody(body)
        assert msg.curtain_status == "close"
        assert msg.curtain_direction == "reverse"

    def test_status_stop(self) -> None:
        """Stop status decodes to its label."""
        body = bytearray([CMD_TYPE, 0x01, STATUS_STOP, 0, DIRECTION_POSITIVE, 0x00])
        assert X14GeneralMessageBody(body).curtain_status == "stop"

    def test_invalid_sentinels_omitted(self) -> None:
        """Fields set to 0xFF are not exposed at all."""
        body = bytearray(
            [CMD_TYPE, VALUE_INVALID, STATUS_STOP, VALUE_INVALID, 0xFF, VALUE_INVALID],
        )
        msg = X14GeneralMessageBody(body)
        assert msg.curtain_status == "stop"
        assert not hasattr(msg, "software_version")
        assert not hasattr(msg, "curtain_position")
        assert not hasattr(msg, "curtain_direction")
        assert not hasattr(msg, "error_code")

    def test_invalid_status_omitted(self) -> None:
        """An unknown/0xFF status byte leaves curtain_status unset."""
        body = bytearray(
            [CMD_TYPE, 0x10, VALUE_INVALID, 42, DIRECTION_POSITIVE, 0x00],
        )
        msg = X14GeneralMessageBody(body)
        assert not hasattr(msg, "curtain_status")
        # Surrounding fields still decode.
        assert msg.curtain_position == 42


class TestMessageQuery:
    """Test x14 query message."""

    def test_query_body(self) -> None:
        """Query body is the single command byte 0x01."""
        query = MessageQuery(3)
        assert query.body == bytearray([QUERY_PAYLOAD])
        frame = query.serialize()
        assert frame[2] == DeviceType.X14
        assert frame[9] == MessageType.query


class TestMessageSet:
    """Test x14 control message."""

    def test_default_all_invalid(self) -> None:
        """An untouched set message sends 0xFF for every field (no change)."""
        message = MessageSet(3)
        assert message.body == bytearray([CMD_TYPE, *([VALUE_INVALID] * 5)])

    def test_set_status_open(self) -> None:
        """Only the status field is populated; the rest stay 0xFF."""
        message = MessageSet(3)
        message.status = STATUS_OPEN
        assert message.body == bytearray(
            [CMD_TYPE, VALUE_INVALID, STATUS_OPEN, VALUE_INVALID, 0xFF, VALUE_INVALID],
        )
        frame = message.serialize()
        assert frame[9] == MessageType.set

    def test_set_position(self) -> None:
        """The position field lands at body offset 3."""
        message = MessageSet(3)
        message.position = 50
        assert message.body[3] == 50


class TestMessage14Response:
    """Test x14 response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = Message14Response(
            _report_frame([CMD_TYPE, 0x10, STATUS_OPEN, 42, DIRECTION_POSITIVE, 0x00]),
        )
        assert getattr(response, "curtain_status") == "open"  # noqa: B009
        assert getattr(response, "curtain_position") == 42  # noqa: B009

    def test_report_ack_decodes(self) -> None:
        """A report (0x05 notify2) is decoded like a query reply."""
        response = Message14Response(
            _report_frame(
                [CMD_TYPE, 0x10, STATUS_STOP, 0, DIRECTION_REVERSE, 0x00],
                MessageType.notify2,
            ),
        )
        assert getattr(response, "curtain_status") == "stop"  # noqa: B009

    def test_set_echo_not_decoded(self) -> None:
        """The set echo (0x02) is ignored."""
        response = Message14Response(
            _report_frame(
                [CMD_TYPE, 0x10, STATUS_OPEN, 42, DIRECTION_POSITIVE, 0x00],
                MessageType.set,
            ),
        )
        assert not hasattr(response, "curtain_status")

    def test_wrong_cmd_type_not_decoded(self) -> None:
        """A record whose cmdType is not 0x01 is ignored."""
        response = Message14Response(
            _report_frame([0x02, 0x10, STATUS_OPEN, 42, DIRECTION_POSITIVE, 0x00]),
        )
        assert not hasattr(response, "curtain_status")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the fixed record decodes to nothing."""
        response = Message14Response(_report_frame([CMD_TYPE, 0x10, STATUS_OPEN]))
        assert not hasattr(response, "curtain_status")

"""Test b2 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.b2.message import (
    STATUS_NONE,
    STATUS_STANDBY,
    STATUS_WORK,
    B2GeneralMessageBody,
    MessageB2Response,
    MessageQuery,
    MessageSet,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full b2 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.B2, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _report_body() -> list[int]:
    """Build a full 17-byte report body with every field populated."""
    body = [0] * 17
    body[0] = STATUS_WORK  # work_status
    body[1] = 0x71  # work_mode vegetable
    body[2] = 2  # work_hour
    body[3] = 45  # work_minute
    body[4] = 90  # temperature
    body[6] = 0x00  # box in / water full / door close
    body[16] = 0x01  # lock on
    return body


class TestB2GeneralMessageBody:
    """Test b2 status body (report decode)."""

    def test_full_record(self) -> None:
        """Every field decodes from a full report."""
        msg = B2GeneralMessageBody(bytearray(_report_body()))
        assert msg.work_status == "work"
        assert msg.work_mode == "vegetable"
        assert msg.work_hour == 2
        assert msg.work_minute == 45
        assert msg.temperature == 90
        assert msg.door_state == "close"
        assert msg.water_state == "full"
        assert msg.box_state == "in"
        assert msg.lock is True

    def test_state_bits_set(self) -> None:
        """The packed state byte decodes open / empty / out when bits are set."""
        body = _report_body()
        body[6] = 0x07
        body[16] = 0x00
        msg = B2GeneralMessageBody(bytearray(body))
        assert msg.door_state == "open"
        assert msg.water_state == "empty"
        assert msg.box_state == "out"
        assert msg.lock is False

    def test_none_status(self) -> None:
        """work_status 0xFF decodes to the 'none' label."""
        body = _report_body()
        body[0] = STATUS_NONE
        assert B2GeneralMessageBody(bytearray(body)).work_status == "none"

    def test_unknown_status_and_mode_omitted(self) -> None:
        """An unrecognized status / mode byte leaves those fields unset."""
        body = _report_body()
        body[0] = 0x55
        body[1] = 0x55
        msg = B2GeneralMessageBody(bytearray(body))
        assert not hasattr(msg, "work_status")
        assert not hasattr(msg, "work_mode")
        # Surrounding fields still decode.
        assert msg.work_hour == 2


class TestMessageQuery:
    """Test b2 query message."""

    def test_query_body(self) -> None:
        """Query body is empty (leading 0x00 body_type)."""
        query = MessageQuery(3)
        assert query.body == bytearray([0x00])
        frame = query.serialize()
        assert frame[2] == DeviceType.B2
        assert frame[9] == MessageType.query


class TestMessageSet:
    """Test b2 control message."""

    def test_default_body(self) -> None:
        """An untouched set message carries the 15-byte standby record."""
        message = MessageSet(3)
        body = message.body
        assert body[0] == STATUS_STANDBY  # work_status via body_type
        assert len(body) == 15
        assert message.serialize()[9] == MessageType.set

    def test_work_status_getter(self) -> None:
        """The work_status property reflects the set value."""
        message = MessageSet(3)
        message.work_status = STATUS_WORK
        assert message.work_status == STATUS_WORK

    def test_set_fields(self) -> None:
        """Each field lands at its control body offset; lock at body[14]."""
        message = MessageSet(3)
        message.work_status = STATUS_WORK
        message.work_mode = 0x03
        message.work_hour = 1
        message.work_minute = 20
        message.temperature = 80
        message.lock = 0x01
        body = message.body
        assert body[0] == STATUS_WORK
        assert body[1] == 0x03
        assert body[2] == 1
        assert body[3] == 20
        assert body[4] == 80
        assert body[14] == 0x01


class TestMessageB2Response:
    """Test b2 response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = MessageB2Response(_report_frame(_report_body()))
        assert getattr(response, "work_status") == "work"  # noqa: B009
        assert getattr(response, "work_mode") == "vegetable"  # noqa: B009

    def test_notify1_decodes(self) -> None:
        """A notify1 (0x04) report is decoded like a query reply."""
        response = MessageB2Response(
            _report_frame(_report_body(), MessageType.notify1),
        )
        assert getattr(response, "lock") is True  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded."""
        response = MessageB2Response(_report_frame(_report_body(), MessageType.set))
        assert getattr(response, "temperature") == 90  # noqa: B009

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the fixed record decodes to nothing."""
        response = MessageB2Response(_report_frame([STATUS_WORK, 0x03, 0x01]))
        assert not hasattr(response, "work_status")

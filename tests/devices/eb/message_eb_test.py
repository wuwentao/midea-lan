"""Test eb message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.eb.message import (
    CMD_CONTROL_HIGH,
    CMD_CONTROL_LOW,
    CMD_QUERY_HIGH,
    CMD_QUERY_LOW,
    INNER_HEAD,
    EBErrorMessageBody,
    EBGeneralMessageBody,
    MessageEBResponse,
    MessageQuery,
    MessageSet,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full eb response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.EB, 0, 0, 0, 0, 0, 1, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 24-byte inner-frame status report body."""
    body = [0] * 24
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[2] = 0x02
    body[7] = 0x14  # cmd code low (report status)
    body[8] = 0x27  # cmd code high
    body[9] = 0x01  # response normal
    body[10] = 3  # work_status
    body[11] = 0x12  # function_no hi
    body[12] = 0x34  # function_no lo
    body[13] = 1  # running hr
    body[14] = 20  # running min
    body[15] = 0  # surplus hr
    body[16] = 40  # surplus min
    body[17] = 2  # reserve hr
    body[18] = 30  # reserve min
    body[19] = 7  # fire_level
    body[20] = 1  # definite hr
    body[21] = 10  # definite min
    body[22] = 2  # work_stage
    body[23] = 9  # error_code
    return body


class TestEBGeneralMessageBody:
    """Test eb status body decode."""

    def test_full_record(self) -> None:
        """Every field decodes from a full status record."""
        msg = EBGeneralMessageBody(bytearray(_status_body()))
        assert msg.response == "response_normal"
        assert msg.work_status == 3
        assert msg.function_no == 0x1234
        assert msg.time_running_hr == 1
        assert msg.time_running_min == 20
        assert msg.time_surplus_min == 40
        assert msg.time_reserve_hr == 2
        assert msg.fire_level == 7
        assert msg.definite_time_min == 10
        assert msg.work_stage == 2
        assert msg.error_code == 9

    def test_response_error(self) -> None:
        """Response byte 0x00 decodes to the error label."""
        body = _status_body()
        body[9] = 0x00
        assert EBGeneralMessageBody(bytearray(body)).response == "response_error"

    def test_unknown_response_omitted(self) -> None:
        """An out-of-range response byte leaves response unset."""
        body = _status_body()
        body[9] = 0x05
        assert not hasattr(EBGeneralMessageBody(bytearray(body)), "response")


class TestEBErrorMessageBody:
    """Test eb error-only notify body decode."""

    def test_error_only(self) -> None:
        """The error-only notify decodes error_code from body[10]."""
        body = [0] * 11
        body[0] = INNER_HEAD
        body[10] = 5
        msg = EBErrorMessageBody(bytearray(body))
        assert msg.error_code == 5
        assert not hasattr(msg, "work_status")


class TestMessageQuery:
    """Test eb query message."""

    def test_query_body(self) -> None:
        """Query body is the inner frame carrying the 0xC353 query code."""
        query = MessageQuery(3)
        body = query.body
        assert body[0] == INNER_HEAD
        assert body[7] == CMD_QUERY_LOW
        assert body[8] == CMD_QUERY_HIGH
        frame = query.serialize()
        assert frame[2] == DeviceType.EB
        assert frame[9] == MessageType.query


class TestMessageSet:
    """Test eb control message."""

    def test_control_frame(self) -> None:
        """Control fields land in the inner frame at their Lua offsets."""
        message = MessageSet(3)
        message.function_no = 0x1234
        message.work_status = 1
        message.time_reserve_hr = 2
        message.time_reserve_min = 30
        message.fire_level = 5
        message.definite_time_hr = 1
        message.definite_time_min = 15
        body = message.body
        assert body[0] == INNER_HEAD
        assert body[7] == CMD_CONTROL_LOW
        assert body[8] == CMD_CONTROL_HIGH
        assert body[9] == 0x12  # function_no hi
        assert body[10] == 0x34  # function_no lo
        assert body[11] == 1  # work_status
        assert body[12] == 2  # reserve hr
        assert body[13] == 30  # reserve min
        assert body[14] == 5  # fire_level
        assert body[15] == 1  # definite hr
        assert body[16] == 15  # definite min
        assert message.serialize()[9] == MessageType.set


class TestMessageEBResponse:
    """Test eb response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = MessageEBResponse(_report_frame(_status_body()))
        assert getattr(response, "work_status") == 3  # noqa: B009
        assert getattr(response, "function_no") == 0x1234  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded as a status record."""
        response = MessageEBResponse(
            _report_frame(_status_body(), MessageType.set),
        )
        assert getattr(response, "fire_level") == 7  # noqa: B009

    def test_notify_status_decodes(self) -> None:
        """A notify1 (0x04) with cmd 0x2714 decodes the status record."""
        response = MessageEBResponse(
            _report_frame(_status_body(), MessageType.notify1),
        )
        assert getattr(response, "work_stage") == 2  # noqa: B009

    def test_notify_error_only_decodes(self) -> None:
        """A notify1 (0x04) with cmd 0x2716 decodes only error_code."""
        body = [0] * 11
        body[0] = INNER_HEAD
        body[7] = 0x16
        body[8] = 0x27
        body[10] = 5
        response = MessageEBResponse(_report_frame(body, MessageType.notify1))
        assert getattr(response, "error_code") == 5  # noqa: B009
        assert not hasattr(response, "work_status")

    def test_notify_unknown_cmd_not_decoded(self) -> None:
        """A notify1 with an unrecognized cmd code decodes nothing."""
        body = _status_body()
        body[7] = 0x99  # unknown cmd low
        response = MessageEBResponse(_report_frame(body, MessageType.notify1))
        assert not hasattr(response, "work_status")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the minimum decodes to nothing."""
        response = MessageEBResponse(_report_frame([INNER_HEAD, 0x55, 0x02]))
        assert not hasattr(response, "work_status")

    def test_set_echo_short_status_not_decoded(self) -> None:
        """A 0x02 frame too short for the full status record is skipped."""
        body = [0] * 15  # >= REPORT_MIN_LEN(11) but < STATUS_REPORT_MIN_LEN(24)
        body[0] = INNER_HEAD
        response = MessageEBResponse(_report_frame(body, MessageType.set))
        assert not hasattr(response, "work_status")

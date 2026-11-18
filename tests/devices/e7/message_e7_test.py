"""Test e7 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.e7.message import (
    CMD_CONTROL_HIGH,
    CMD_CONTROL_LOW,
    CMD_QUERY_HIGH,
    CMD_QUERY_LOW,
    INNER_HEAD,
    SOFT_VERSION_V1,
    SOFT_VERSION_V3,
    SOFT_VERSION_V4,
    E7ErrorMessageBody,
    E7GeneralMessageBody,
    MessageE7Response,
    MessageQuery,
    MessageSet,
    is_32bit_layout,
    soft_version_for_subtype,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full e7 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.E7, 0, 0, 0, 0, 0, 0, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body_16() -> list[int]:
    """Build a full v1 (16-bit function_no) status body."""
    body = [0] * 24
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[7] = 0x14  # cmd low (status)
    body[8] = 0x27  # cmd high
    body[9] = 1  # response normal
    body[10] = 1  # work_status
    body[11] = 0x12  # function_no hi
    body[12] = 0x34  # function_no lo
    body[13] = 0  # running hr
    body[14] = 30  # running min
    body[15] = 0  # surplus hr
    body[16] = 15  # surplus min
    body[17] = 2  # reserve hr
    body[18] = 10  # reserve min
    body[19] = 5  # fire level
    body[20] = 1  # definite hr
    body[21] = 20  # definite min
    body[22] = 3  # work stage
    body[23] = 7  # error code
    return body


def _status_body_32() -> list[int]:
    """Build a full v3/v4 (32-bit function_no) status body."""
    body = [0] * 26
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[7] = 0x14
    body[8] = 0x27
    body[9] = 1  # response normal
    body[10] = 2  # work_status
    body[11] = 0x01  # function_no byte 3
    body[12] = 0x02  # function_no byte 2
    body[13] = 0x03  # function_no byte 1
    body[14] = 0x04  # function_no byte 0
    body[15] = 1  # running hr
    body[16] = 5  # running min
    body[17] = 0  # surplus hr
    body[18] = 45  # surplus min
    body[19] = 3  # reserve hr
    body[20] = 25  # reserve min
    body[21] = 7  # fire level
    body[22] = 2  # definite hr
    body[23] = 30  # definite min
    body[24] = 4  # work stage
    body[25] = 9  # error code
    return body


class TestSoftVersionMapping:
    """Test subtype -> soft version mapping (Lua getSoftVersion)."""

    def test_known_subtypes(self) -> None:
        """Documented subtypes map to their soft version."""
        assert soft_version_for_subtype(6) == SOFT_VERSION_V1
        assert soft_version_for_subtype(10) == SOFT_VERSION_V3
        assert soft_version_for_subtype(8) == SOFT_VERSION_V4
        assert soft_version_for_subtype(9) == SOFT_VERSION_V4

    def test_unknown_subtype_defaults_to_v3(self) -> None:
        """An unmapped subtype defaults to the modern 32-bit layout."""
        assert soft_version_for_subtype(99) == SOFT_VERSION_V3

    def test_layout_classification(self) -> None:
        """Only v3 / v4 are 32-bit layouts."""
        assert not is_32bit_layout(SOFT_VERSION_V1)
        assert is_32bit_layout(SOFT_VERSION_V3)
        assert is_32bit_layout(SOFT_VERSION_V4)


class TestE7GeneralMessageBody:
    """Test e7 status body decode for both layouts."""

    def test_full_record_16bit(self) -> None:
        """Every field decodes from a v1 status record."""
        msg = E7GeneralMessageBody(bytearray(_status_body_16()), is_32bit=False)
        assert msg.response == "response_normal"
        assert msg.work_status == 1
        assert msg.function_no == 0x1234
        assert msg.time_running_min == 30
        assert msg.time_surplus_min == 15
        assert msg.time_reserve_hr == 2
        assert msg.fire_level == 5
        assert msg.definite_time_min == 20
        assert msg.work_stage == 3
        assert msg.error_code == 7

    def test_full_record_32bit(self) -> None:
        """Every field decodes from a v3/v4 status record."""
        msg = E7GeneralMessageBody(bytearray(_status_body_32()), is_32bit=True)
        assert msg.response == "response_normal"
        assert msg.work_status == 2
        assert msg.function_no == 0x01020304
        assert msg.time_running_hr == 1
        assert msg.time_surplus_min == 45
        assert msg.time_reserve_min == 25
        assert msg.fire_level == 7
        assert msg.definite_time_min == 30
        assert msg.work_stage == 4
        assert msg.error_code == 9

    def test_response_error(self) -> None:
        """Response byte 0x00 decodes to the error label."""
        body = _status_body_32()
        body[9] = 0x00
        msg = E7GeneralMessageBody(bytearray(body), is_32bit=True)
        assert msg.response == "response_error"

    def test_unknown_response_omitted(self) -> None:
        """An out-of-range response byte leaves response unset."""
        body = _status_body_32()
        body[9] = 0x05
        msg = E7GeneralMessageBody(bytearray(body), is_32bit=True)
        assert not hasattr(msg, "response")


class TestE7ErrorMessageBody:
    """Test e7 error-only notify body."""

    def test_error_body(self) -> None:
        """Error-only body decodes error_code at body[10]."""
        body = [0] * 11
        body[10] = 42
        assert E7ErrorMessageBody(bytearray(body)).error_code == 42


class TestMessageQuery:
    """Test e7 query message."""

    def test_query_body(self) -> None:
        """Query body carries the status cmd code (same across versions)."""
        query = MessageQuery(SOFT_VERSION_V3)
        body = query.body
        assert body[0] == INNER_HEAD
        assert body[7] == CMD_QUERY_LOW
        assert body[8] == CMD_QUERY_HIGH
        serialized = query.serialize()
        assert serialized[2] == DeviceType.E7
        assert serialized[9] == MessageType.query
        # The soft version is written into the device-protocol-version byte.
        assert serialized[8] == SOFT_VERSION_V3


class TestMessageSet:
    """Test e7 control message for both layouts."""

    def test_control_frame_16bit(self) -> None:
        """A v1 control frame packs function_no as two big-endian bytes."""
        message = MessageSet(SOFT_VERSION_V1)
        message.function_no = 0x1234
        message.work_status = 1
        message.time_reserve_hr = 2
        message.time_reserve_min = 30
        message.fire_level = 5
        message.definite_time_hr = 1
        message.definite_time_min = 15
        body = message.body
        assert body[7] == CMD_CONTROL_LOW
        assert body[8] == CMD_CONTROL_HIGH
        assert body[9] == 0x12  # function_no hi
        assert body[10] == 0x34  # function_no lo
        assert body[11] == 1  # work_status
        assert body[12] == 2  # reserve hr
        assert body[13] == 30  # reserve min
        assert body[14] == 5  # fire level
        assert body[15] == 1  # definite hr
        assert body[16] == 15  # definite min
        assert message.serialize()[9] == MessageType.set
        assert message.serialize()[8] == SOFT_VERSION_V1

    def test_control_frame_32bit(self) -> None:
        """A v3/v4 control frame packs function_no as four big-endian bytes."""
        message = MessageSet(SOFT_VERSION_V4)
        message.function_no = 0x01020304
        message.work_status = 2
        message.time_reserve_hr = 3
        message.time_reserve_min = 20
        message.fire_level = 7
        message.definite_time_hr = 2
        message.definite_time_min = 10
        body = message.body
        assert body[9] == 0x01
        assert body[10] == 0x02
        assert body[11] == 0x03
        assert body[12] == 0x04
        assert body[13] == 2  # work_status
        assert body[14] == 3  # reserve hr
        assert body[15] == 20  # reserve min
        assert body[16] == 7  # fire level
        assert body[17] == 2  # definite hr
        assert body[18] == 10  # definite min
        assert message.serialize()[8] == SOFT_VERSION_V4


class TestMessageE7Response:
    """Test e7 response wrapper for both layouts."""

    def test_query_reply_16bit(self) -> None:
        """A v1 query reply (0x03) populates the state attributes."""
        response = MessageE7Response(
            _report_frame(_status_body_16()),
            SOFT_VERSION_V1,
        )
        assert getattr(response, "work_status") == 1  # noqa: B009
        assert getattr(response, "function_no") == 0x1234  # noqa: B009

    def test_query_reply_32bit(self) -> None:
        """A v3 query reply (0x03) uses the 32-bit layout."""
        response = MessageE7Response(
            _report_frame(_status_body_32()),
            SOFT_VERSION_V3,
        )
        assert getattr(response, "function_no") == 0x01020304  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded."""
        response = MessageE7Response(
            _report_frame(_status_body_32(), MessageType.set),
            SOFT_VERSION_V4,
        )
        assert getattr(response, "error_code") == 9  # noqa: B009

    def test_notify_status_decodes(self) -> None:
        """A notify1 (0x04) status report (cmd 0x2714) is decoded."""
        response = MessageE7Response(
            _report_frame(_status_body_16(), MessageType.notify1),
            SOFT_VERSION_V1,
        )
        assert getattr(response, "work_stage") == 3  # noqa: B009

    def test_notify_error_only_v1(self) -> None:
        """A v1 notify1 error frame (cmd 0x2716) decodes only error_code."""
        body = [0] * 11
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[7] = 0x16  # cmd low (error)
        body[8] = 0x27
        body[10] = 42
        response = MessageE7Response(
            _report_frame(body, MessageType.notify1),
            SOFT_VERSION_V1,
        )
        assert getattr(response, "error_code") == 42  # noqa: B009
        assert not hasattr(response, "work_status")

    def test_notify_error_only_ignored_32bit(self) -> None:
        """The error-only notify is undefined for 32-bit layouts."""
        body = [0] * 11
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[7] = 0x16
        body[8] = 0x27
        body[10] = 42
        response = MessageE7Response(
            _report_frame(body, MessageType.notify1),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "error_code")

    def test_notify_unknown_cmd_not_decoded(self) -> None:
        """A notify1 with an unknown cmd code leaves state unset."""
        body = _status_body_32()
        body[7] = 0x99  # unknown cmd low
        response = MessageE7Response(
            _report_frame(body, MessageType.notify1),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "work_status")

    def test_set_echo_too_short_for_record(self) -> None:
        """A set echo past the gate but short of the record stays undecoded."""
        body = [0] * 20  # >= REPORT_MIN_LEN but < 32-bit record length
        body[0] = INNER_HEAD
        body[1] = 0x55
        response = MessageE7Response(
            _report_frame(body, MessageType.set),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "work_status")

    def test_notify_status_too_short_for_record(self) -> None:
        """A notify status past the gate but short of the record stays undecoded."""
        body = [0] * 20
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[7] = 0x14
        body[8] = 0x27
        response = MessageE7Response(
            _report_frame(body, MessageType.notify1),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "work_status")

    def test_other_message_type_not_decoded(self) -> None:
        """A message type other than set / query / notify1 is not decoded."""
        response = MessageE7Response(
            _report_frame(_status_body_32(), MessageType.notify2),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "work_status")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the minimum record decodes to nothing."""
        response = MessageE7Response(
            _report_frame([INNER_HEAD, 0x55, 0x02]),
            SOFT_VERSION_V3,
        )
        assert not hasattr(response, "work_status")

"""Test ef message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.ef.message import (
    DRINK_HOT,
    DRINK_WARM,
    INNER_HEAD,
    SELECTOR_CONTROL,
    SELECTOR_QUERY,
    EFGeneralMessageBody,
    MessageEFResponse,
    MessageQuery,
    MessageSet,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full ef response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.EF, 0, 0, 0, 0, 0, 1, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 20-byte inner-frame status report body."""
    body = [0] * 20
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[4] = 0x34  # cmd_code lo
    body[5] = 0x12  # cmd_code hi
    body[8] = 2  # work_status
    body[9] = 3  # error_code
    body[10] = 1  # response normal
    body[11] = 7  # cmd_id
    body[12] = 0x01 | 0x04  # reserve on, warm off, warm_drink
    body[13] = 5  # work_step
    body[14] = 1  # process_status
    body[15] = 0  # work hr
    body[16] = 30  # work min
    body[17] = 60  # time_max
    body[18] = 80  # temperature_setting
    body[19] = 55  # temperature_current
    return body


class TestEFGeneralMessageBody:
    """Test ef status body decode."""

    def test_full_record(self) -> None:
        """Every field decodes from a full status record."""
        msg = EFGeneralMessageBody(bytearray(_status_body()))
        assert msg.cmd_code == 0x1234
        assert msg.work_status == 2
        assert msg.error_code == 3
        assert msg.response_type == "response_normal"
        assert msg.cmd_id == 7
        assert msg.reserve is True
        assert msg.warm is False
        assert msg.drink_style == DRINK_WARM
        assert msg.work_step == 5
        assert msg.process_status == 1
        assert msg.time_work_min == 30
        assert msg.time_max == 60
        assert msg.temperature_setting == 80
        assert msg.temperature_current == 55

    def test_flags_warm_and_hot(self) -> None:
        """Warm bit set + no drink-style bit decodes warm on / hot_drink."""
        body = _status_body()
        body[12] = 0x02  # warm on, reserve off, hot drink
        msg = EFGeneralMessageBody(bytearray(body))
        assert msg.reserve is False
        assert msg.warm is True
        assert msg.drink_style == DRINK_HOT

    def test_response_error(self) -> None:
        """Response byte 0x00 decodes to the error label."""
        body = _status_body()
        body[10] = 0x00
        assert EFGeneralMessageBody(bytearray(body)).response_type == "response_error"

    def test_unknown_response_omitted(self) -> None:
        """An out-of-range response byte leaves response_type unset."""
        body = _status_body()
        body[10] = 0x05
        assert not hasattr(EFGeneralMessageBody(bytearray(body)), "response_type")


class TestMessageQuery:
    """Test ef query message."""

    def test_query_body(self) -> None:
        """Query body is the inner frame with the 0x31 selector."""
        query = MessageQuery(3)
        body = query.body
        assert body[0] == INNER_HEAD
        assert body[3] == SELECTOR_QUERY
        frame = query.serialize()
        assert frame[2] == DeviceType.EF
        assert frame[9] == MessageType.query


class TestMessageSet:
    """Test ef control message."""

    def test_control_frame(self) -> None:
        """Control fields land in the inner frame at their Lua offsets."""
        message = MessageSet(3)
        message.cmd_code = 0x1234
        message.cmd_id = 7
        message.reserve = True
        message.warm = True
        message.drink_style = DRINK_WARM
        message.time_reserve_hr = 2
        message.time_reserve_min = 30
        message.time_warm_hr = 1
        message.time_warm_min = 15
        message.temperature_setting = 80
        body = message.body
        assert body[0] == INNER_HEAD
        assert body[3] == SELECTOR_CONTROL
        assert body[4] == 0x34  # cmd_code lo
        assert body[5] == 0x12  # cmd_code hi
        assert body[8] == 7  # cmd_id
        assert body[9] == 0x01 | 0x02 | 0x04  # reserve + warm + warm_drink
        assert body[10] == 2
        assert body[11] == 30
        assert body[12] == 1
        assert body[13] == 15
        assert body[14] == 80
        assert message.serialize()[9] == MessageType.set

    def test_control_hot_drink_no_flag(self) -> None:
        """hot_drink leaves the drink-style flag bit clear."""
        message = MessageSet(3)
        message.drink_style = DRINK_HOT
        assert message.body[9] & 0x04 == 0


class TestMessageEFResponse:
    """Test ef response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = MessageEFResponse(_report_frame(_status_body()))
        assert getattr(response, "work_status") == 2  # noqa: B009
        assert getattr(response, "cmd_code") == 0x1234  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded."""
        response = MessageEFResponse(_report_frame(_status_body(), MessageType.set))
        assert getattr(response, "temperature_current") == 55  # noqa: B009

    def test_notify1_decodes(self) -> None:
        """A notify1 (0x04) report is decoded."""
        response = MessageEFResponse(
            _report_frame(_status_body(), MessageType.notify1),
        )
        assert getattr(response, "reserve") is True  # noqa: B009

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the fixed record decodes to nothing."""
        response = MessageEFResponse(_report_frame([INNER_HEAD, 0x55, 0x00, 0x31]))
        assert not hasattr(response, "work_status")

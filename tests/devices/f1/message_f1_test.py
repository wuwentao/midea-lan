"""Test f1 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.f1.message import (
    INNER_HEAD,
    POWER_ON,
    SELECTOR_CONTROL,
    SELECTOR_QUERY,
    F1GeneralMessageBody,
    MessageF1Response,
    MessageQuery,
    MessageSet,
)
from midealan.message import MessageType


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full f1 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.F1, 0, 0, 0, 0, 0, 1, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 27-byte inner-frame status report body."""
    body = [0] * 27
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[4] = 0x04  # work_mode LE32 = 0x01020304
    body[5] = 0x03
    body[6] = 0x02
    body[7] = 0x01
    body[8] = 9  # error_code
    body[9] = 1  # response success
    body[10] = 2  # work_status
    body[11] = 3  # step_status
    body[12] = 4  # work_stage
    body[13] = 0  # lid have_cup
    body[14] = 1  # cup hot_cup
    body[15] = 10  # current_time lo
    body[16] = 0  # current_time hi
    body[17] = 55  # current_temp
    body[18] = 5  # speed
    body[19] = 90  # set_work_temp
    body[20] = 60  # set_keep_warm_temp
    body[21] = 0x34  # appoint_time lo
    body[22] = 0x12  # appoint_time hi
    body[23] = 0x02  # set_work_time lo
    body[24] = 0x01  # set_work_time hi
    body[25] = 30  # set_keep_warm_time
    body[26] = 7  # code_id
    return body


class TestF1GeneralMessageBody:
    """Test f1 status body decode."""

    def test_full_record(self) -> None:
        """Every field decodes from a full status record."""
        msg = F1GeneralMessageBody(bytearray(_status_body()))
        assert msg.work_mode == 0x01020304
        assert msg.error_code == 9
        assert msg.response_type == "success"
        assert msg.work_status == 2
        assert msg.step_status == 3
        assert msg.work_stage == 4
        assert msg.lid_status == "have_cup"
        assert msg.cup_status == "hot_cup"
        assert msg.current_time == 10
        assert msg.current_temp == 55
        assert msg.speed == 5
        assert msg.set_work_temp == 90
        assert msg.set_keep_warm_temp == 60
        assert msg.appoint_time == 0x1234
        assert msg.set_work_time == 0x0102
        assert msg.set_keep_warm_time == 30
        assert msg.code_id == 7

    def test_response_fail(self) -> None:
        """Response byte 0x00 decodes to the fail label."""
        body = _status_body()
        body[9] = 0x00
        assert F1GeneralMessageBody(bytearray(body)).response_type == "fail"

    def test_unknown_response_omitted(self) -> None:
        """An out-of-range response byte leaves response_type unset."""
        body = _status_body()
        body[9] = 0x05
        assert not hasattr(F1GeneralMessageBody(bytearray(body)), "response_type")

    def test_unknown_lid_and_cup_omitted(self) -> None:
        """Unknown lid / cup bytes leave those fields unset."""
        body = _status_body()
        body[13] = 5
        body[14] = 9
        msg = F1GeneralMessageBody(bytearray(body))
        assert not hasattr(msg, "lid_status")
        assert not hasattr(msg, "cup_status")

    def test_cold_cup_and_no_cup(self) -> None:
        """cold_cup / no_cup labels decode from their bytes."""
        body = _status_body()
        body[13] = 1  # no_cup
        body[14] = 2  # cold_cup
        msg = F1GeneralMessageBody(bytearray(body))
        assert msg.lid_status == "no_cup"
        assert msg.cup_status == "cold_cup"


class TestMessageQuery:
    """Test f1 query message."""

    def test_query_body(self) -> None:
        """Query body is the inner frame with the 0x31 selector."""
        query = MessageQuery(3)
        body = query.body
        assert body[0] == INNER_HEAD
        assert body[3] == SELECTOR_QUERY
        frame = query.serialize()
        assert frame[2] == DeviceType.F1
        assert frame[9] == MessageType.query


class TestMessageSet:
    """Test f1 control message."""

    def test_control_frame(self) -> None:
        """Control fields land in the inner frame at their Lua offsets."""
        message = MessageSet(3)
        message.work_mode = 0x01020304
        message.code_id = 7
        message.power = True
        message.appoint_time = 0x1234
        message.set_work_time = 0x0102
        message.set_keep_warm_time = 30
        message.set_keep_warm_temp = 60
        message.set_work_temp = 90
        message.speed = 5
        body = message.body
        assert body[0] == INNER_HEAD
        assert body[3] == SELECTOR_CONTROL
        assert body[4] == 0x04  # work_mode LE32
        assert body[5] == 0x03
        assert body[6] == 0x02
        assert body[7] == 0x01
        assert body[8] == 7  # code_id
        assert body[9] == POWER_ON
        assert body[10] == 0x34  # appoint_time lo
        assert body[11] == 0x12  # appoint_time hi
        assert body[12] == 0x02  # set_work_time lo
        assert body[13] == 0x01  # set_work_time hi
        assert body[14] == 30
        assert body[15] == 60
        assert body[16] == 90
        assert body[17] == 5
        assert message.serialize()[9] == MessageType.set

    def test_control_power_off(self) -> None:
        """Power off sends 0x00 in the power byte."""
        message = MessageSet(3)
        message.power = False
        assert message.body[9] == 0x00


class TestMessageF1Response:
    """Test f1 response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = MessageF1Response(_report_frame(_status_body()))
        assert getattr(response, "work_mode") == 0x01020304  # noqa: B009
        assert getattr(response, "cup_status") == "hot_cup"  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded."""
        response = MessageF1Response(_report_frame(_status_body(), MessageType.set))
        assert getattr(response, "current_temp") == 55  # noqa: B009

    def test_notify1_decodes(self) -> None:
        """A notify1 (0x04) report is decoded."""
        response = MessageF1Response(
            _report_frame(_status_body(), MessageType.notify1),
        )
        assert getattr(response, "code_id") == 7  # noqa: B009

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the fixed record decodes to nothing."""
        response = MessageF1Response(_report_frame([INNER_HEAD, 0x55, 0x00, 0x31]))
        assert not hasattr(response, "work_mode")

    def test_wrong_inner_markers_not_decoded(self) -> None:
        """A long body without the 0xAA 0x55 inner markers is not decoded."""
        body = _status_body()
        body[0] = 0x00  # not INNER_HEAD
        body[1] = 0x00  # not INNER_HEAD2
        response = MessageF1Response(_report_frame(body))
        assert not hasattr(response, "work_mode")

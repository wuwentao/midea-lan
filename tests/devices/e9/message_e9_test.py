"""Test e9 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.e9.message import (
    INNER_HEAD,
    QUERY_CMD_STATUS,
    REPORT_BASE_PUSH,
    REPORT_BASE_QUERY,
    TASK_TYPE_SETTING,
    E9ErrorMessageBody,
    E9GeneralMessageBody,
    E9InfoMessageBody,
    MessageE9Response,
    MessageQuery,
    MessageSet,
    _inner_checksum,
)
from midealan.message import MessageType


def _report_frame(
    body: Sequence[int], message_type: int = MessageType.notify1
) -> bytes:
    """Wrap a report body in a full e9 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.E9, 0, 0, 0, 0, 0, 0, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _push_status_body() -> list[int]:
    """Build a control-echo / notify status body (payload base at body[6])."""
    body = [0] * (REPORT_BASE_PUSH + 16)
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[REPORT_BASE_PUSH + 0] = 0x04  # control_cmd_code lo
    body[REPORT_BASE_PUSH + 1] = 0x00  # control_cmd_code hi
    body[REPORT_BASE_PUSH + 2] = 1  # response normal
    body[REPORT_BASE_PUSH + 3] = 1  # volume
    body[REPORT_BASE_PUSH + 4] = 2  # color
    body[REPORT_BASE_PUSH + 5] = 3  # dosing
    body[REPORT_BASE_PUSH + 6] = 1  # work_status
    body[REPORT_BASE_PUSH + 7] = 5  # work_stage
    body[REPORT_BASE_PUSH + 8] = 80  # bottom_temperature
    body[REPORT_BASE_PUSH + 9] = 10  # time_reserve_min
    body[REPORT_BASE_PUSH + 10] = 1  # time_reserve_hr
    body[REPORT_BASE_PUSH + 11] = 30  # time_work_min
    body[REPORT_BASE_PUSH + 12] = 2  # time_work_hr
    body[REPORT_BASE_PUSH + 13] = 3  # time_warm_min
    body[REPORT_BASE_PUSH + 14] = 4  # time_warm_hr
    body[REPORT_BASE_PUSH + 15] = 7  # error_code
    return body


def _query_status_body() -> list[int]:
    """Build a query-status response body (payload base at body[8])."""
    body = [0] * (REPORT_BASE_QUERY + 16)
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[6] = QUERY_CMD_STATUS  # cmd low
    body[7] = 0xC3  # cmd high
    body[REPORT_BASE_QUERY + 0] = 0x04  # control_cmd_code lo
    body[REPORT_BASE_QUERY + 2] = 1  # response normal
    body[REPORT_BASE_QUERY + 3] = 1  # volume
    body[REPORT_BASE_QUERY + 6] = 2  # work_status
    body[REPORT_BASE_QUERY + 15] = 8  # error_code
    return body


class TestE9GeneralMessageBody:
    """Test e9 status body decode."""

    def test_full_push_record(self) -> None:
        """Every field decodes from a control-echo status record."""
        msg = E9GeneralMessageBody(bytearray(_push_status_body()), REPORT_BASE_PUSH)
        assert msg.control_cmd_code == 0x04
        assert msg.response_type == "response_normal"
        assert msg.volume == 1
        assert msg.color == 2
        assert msg.dosing == 3
        assert msg.work_status == 1
        assert msg.work_stage == 5
        assert msg.bottom_temperature == 80
        assert msg.time_reserve_min == 10
        assert msg.time_reserve_hr == 1
        assert msg.time_work_min == 30
        assert msg.time_work_hr == 2
        assert msg.time_warm_min == 3
        assert msg.time_warm_hr == 4
        assert msg.error_code == 7

    def test_response_error(self) -> None:
        """Response byte 0x0A decodes to the E2 error label."""
        body = _push_status_body()
        body[REPORT_BASE_PUSH + 2] = 0x0A
        msg = E9GeneralMessageBody(bytearray(body), REPORT_BASE_PUSH)
        assert msg.response_type == "response_error_e2"

    def test_unknown_response_omitted(self) -> None:
        """An out-of-range response byte leaves response_type unset."""
        body = _push_status_body()
        body[REPORT_BASE_PUSH + 2] = 0x05
        msg = E9GeneralMessageBody(bytearray(body), REPORT_BASE_PUSH)
        assert not hasattr(msg, "response_type")


class TestE9ErrorAndInfoBody:
    """Test e9 query error / info bodies."""

    def test_error_body(self) -> None:
        """Query error body decodes response + error code."""
        body = [0] * 11
        body[8] = 0x0A
        body[9] = 9
        msg = E9ErrorMessageBody(bytearray(body))
        assert msg.response_type == "response_error_e2"
        assert msg.error_code == 9

    def test_error_body_unknown_response(self) -> None:
        """An out-of-range response byte leaves response_type unset."""
        body = [0] * 11
        body[8] = 0x05
        assert not hasattr(E9ErrorMessageBody(bytearray(body)), "response_type")

    def test_info_body(self) -> None:
        """Query info body decodes response + product volume."""
        body = [0] * 16
        body[8] = 0x01
        body[15] = 2
        msg = E9InfoMessageBody(bytearray(body))
        assert msg.response_type == "response_normal"
        assert msg.product_volume == 2

    def test_info_body_unknown_response(self) -> None:
        """An out-of-range response byte leaves response_type unset."""
        body = [0] * 16
        body[8] = 0x05
        assert not hasattr(E9InfoMessageBody(bytearray(body)), "response_type")


class TestMessageQuery:
    """Test e9 query message."""

    def test_query_body(self) -> None:
        """Query body carries the status cmd code and a valid inner checksum."""
        query = MessageQuery(3)
        body = query.body
        assert body[0] == INNER_HEAD
        assert body[6] == QUERY_CMD_STATUS
        assert body[7] == 0xC3
        # body[0] is the 0xAA head, so the checksum covers body[:-1] directly.
        assert body[-1] == _inner_checksum(list(body[:-1]))
        serialized = query.serialize()
        assert serialized[2] == DeviceType.E9
        assert serialized[9] == MessageType.query


class TestMessageSet:
    """Test e9 control message."""

    def test_control_frame(self) -> None:
        """Control fields land in the inner frame at their Lua offsets."""
        message = MessageSet(3)
        message.control_cmd_code = 0x0004
        message.volume = 1
        message.color = 2
        message.dosing = 3
        message.work_status = 1
        message.time_cuisine_min = 30
        message.time_cuisine_hr = 2
        message.time_reserve_min = 15
        message.time_reserve_hr = 1
        message.bake_temperature = 180
        body = message.body
        assert body[0] == INNER_HEAD
        assert body[5] == TASK_TYPE_SETTING
        assert body[6] == 0x04  # control_cmd_code lo
        assert body[7] == 0x00  # control_cmd_code hi
        assert body[8] == 1  # volume
        assert body[9] == 2  # color
        assert body[10] == 3  # dosing
        assert body[11] == 1  # work_status
        assert body[12] == 30  # time_cuisine_min
        assert body[13] == 2  # time_cuisine_hr
        assert body[14] == 15  # time_reserve_min
        assert body[15] == 1  # time_reserve_hr
        assert body[16] == 180  # bake_temperature
        # body[0] is the 0xAA head, so the checksum covers body[:-1] directly.
        assert body[-1] == _inner_checksum(list(body[:-1]))
        assert message.serialize()[9] == MessageType.set

    def test_control_cmd_code_high_byte(self) -> None:
        """A 16-bit control_cmd_code splits little-endian across body[6]/body[7]."""
        message = MessageSet(3)
        message.control_cmd_code = 0x1234
        body = message.body
        assert body[6] == 0x34
        assert body[7] == 0x12


class TestMessageE9Response:
    """Test e9 response wrapper."""

    def test_notify_decodes(self) -> None:
        """A notify1 (0x04) report populates the state attributes."""
        response = MessageE9Response(_report_frame(_push_status_body()))
        assert getattr(response, "work_status") == 1  # noqa: B009
        assert getattr(response, "control_cmd_code") == 0x04  # noqa: B009

    def test_set_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded with the push base."""
        response = MessageE9Response(
            _report_frame(_push_status_body(), MessageType.set),
        )
        assert getattr(response, "bottom_temperature") == 80  # noqa: B009

    def test_query_status_decodes(self) -> None:
        """A query-status reply (0x03, cmd 0x52) uses the shifted base."""
        response = MessageE9Response(
            _report_frame(_query_status_body(), MessageType.query),
        )
        assert getattr(response, "work_status") == 2  # noqa: B009
        assert getattr(response, "error_code") == 8  # noqa: B009
        assert getattr(response, "volume") == 1  # noqa: B009

    def test_query_error_decodes(self) -> None:
        """A query reply with cmd low 0x50 decodes the error-only body."""
        body = [0] * 11
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[6] = 0x50  # cmd low error
        body[7] = 0xC3
        body[8] = 0x0A  # response error
        body[9] = 9  # error code
        response = MessageE9Response(_report_frame(body, MessageType.query))
        assert getattr(response, "response_type") == "response_error_e2"  # noqa: B009
        assert getattr(response, "error_code") == 9  # noqa: B009
        assert not hasattr(response, "work_status")

    def test_query_info_decodes(self) -> None:
        """A query reply with cmd low 0x51 decodes the info body."""
        body = [0] * 16
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[6] = 0x51  # cmd low info
        body[7] = 0xC3
        body[8] = 0x01  # response normal
        body[15] = 2  # product volume
        response = MessageE9Response(_report_frame(body, MessageType.query))
        assert getattr(response, "product_volume") == 2  # noqa: B009

    def test_query_unknown_cmd_not_decoded(self) -> None:
        """A query reply with an unknown cmd low leaves state unset."""
        body = [0] * 16
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[6] = 0x5F  # unknown cmd low
        body[7] = 0xC3
        response = MessageE9Response(_report_frame(body, MessageType.query))
        assert not hasattr(response, "work_status")
        assert not hasattr(response, "product_volume")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the minimum record decodes to nothing."""
        response = MessageE9Response(_report_frame([INNER_HEAD, 0x55, 0x04]))
        assert not hasattr(response, "work_status")

    def test_notify_too_short_for_full_record(self) -> None:
        """A notify body past the gate but short of the record stays undecoded."""
        body = [0] * 15  # >= REPORT_MIN_LEN but < PUSH_REPORT_MIN_LEN
        body[0] = INNER_HEAD
        body[1] = 0x55
        response = MessageE9Response(_report_frame(body, MessageType.notify1))
        assert not hasattr(response, "work_status")

    def test_other_message_type_not_decoded(self) -> None:
        """A message type other than set / notify1 / query is not decoded."""
        response = MessageE9Response(
            _report_frame(_push_status_body(), MessageType.notify2),
        )
        assert not hasattr(response, "work_status")

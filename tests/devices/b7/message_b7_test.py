"""Test b7 message encode / decode."""

from collections.abc import Sequence
from typing import Any

from midealan.const import ProtocolVersion
from midealan.devices.b7.message import (
    BURNER_LEFT,
    BURNER_LOCK,
    BURNER_RIGHT,
    CMD_ERROR,
    CMD_STATUS_NOTIFY,
    CMD_STATUS_QUERY,
    CONTROL_OPCODE,
    FUNCTION_GEAR,
    FUNCTION_POWER,
    FUNCTION_SURPLUS,
    FUNCTION_TEMP_MIN,
    LOCK_OFF,
    LOCK_ON,
    MessageB7Response,
    MessageQueryError,
    MessageQueryStatus,
    MessageSet,
    MessageSetLock,
)
from midealan.message import MessageType

# Device-body offsets used when crafting report bodies (body[0] = command).
_HEADER_MSG_TYPE_INDEX = 9


def _frame(msg_type: int, body: Sequence[int]) -> bytes:
    """Wrap a device body in a full b7 frame (10-byte header + trailer byte)."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xB7, 0, 0, 0, 0, 0, 3, msg_type])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _attr(response: MessageB7Response, name: str) -> Any:  # noqa: ANN401
    """Read a response attribute set dynamically by ``MessageResponse.set_attr``."""
    return getattr(response, name)


def _status_body() -> list[int]:
    """Long status body (0x41) exercising both burners and the temps."""
    body = [0] * 41
    body[0] = CMD_STATUS_NOTIFY
    body[1] = 2  # left_status
    body[2] = 1  # right_status
    body[3] = 0  # left_surplus_hours
    body[4] = 30  # left_surplus_minutes
    body[5] = 1  # left_work_hours
    body[6] = 20  # left_work_minutes
    body[7] = 5  # left_work_seconds
    body[8] = 0  # right_surplus_hours
    body[9] = 10  # right_surplus_minutes
    body[10] = 0  # right_work_hours
    body[11] = 45  # right_work_minutes
    body[12] = 9  # right_work_seconds
    body[13] = 3  # left_gear
    body[14] = 2  # right_gear
    body[15] = 11  # left_work_mode
    body[16] = 12  # right_work_mode
    # lock(0), menu_mark(1), gas_warn(3), right_smart_bl(4): 0b0001_1011 = 0x1B
    body[17] = 0b00011011
    body[37] = 0x00
    body[38] = 180  # left_temp
    body[39] = 0x01
    body[40] = 0x2C  # right_temp = 300
    return body


class TestB7Query:
    """Test b7 query frames."""

    def test_status_query(self) -> None:
        """Status query carries command 0x31 and an empty inner payload."""
        query = MessageQueryStatus(ProtocolVersion.V3)
        assert query.message_type == MessageType.query
        assert query.body == bytearray([CMD_STATUS_QUERY])

    def test_error_query(self) -> None:
        """Error query carries command 0x32 and the 0x03 sub-type byte."""
        query = MessageQueryError(ProtocolVersion.V3)
        assert query.body == bytearray([CMD_ERROR, 0x03])


class TestB7StatusDecode:
    """Test b7 status report decode."""

    def test_full_status(self) -> None:
        """A long 0x41 frame populates every status field incl. temps."""
        resp = MessageB7Response(_frame(MessageType.notify1, _status_body()))
        assert _attr(resp, "left_status") == 2
        assert _attr(resp, "right_status") == 1
        assert _attr(resp, "left_surplus_minutes") == 30
        assert _attr(resp, "left_work_hours") == 1
        assert _attr(resp, "left_work_minutes") == 20
        assert _attr(resp, "left_work_seconds") == 5
        assert _attr(resp, "right_work_minutes") == 45
        assert _attr(resp, "left_gear") == 3
        assert _attr(resp, "right_gear") == 2
        assert _attr(resp, "left_work_mode") == 11
        assert _attr(resp, "right_work_mode") == 12
        assert _attr(resp, "lock") is True
        assert _attr(resp, "menu_mark") is True
        assert _attr(resp, "gas_warn") is True
        assert _attr(resp, "right_smart_bl") is True
        assert _attr(resp, "left_smart_bl") is False
        assert _attr(resp, "left_temp") == 180
        assert _attr(resp, "right_temp") == 300

    def test_status_query_echo_command(self) -> None:
        """The 0x31 query-echo command is decoded the same as 0x41 notify."""
        body = _status_body()
        body[0] = CMD_STATUS_QUERY
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "left_status") == 2

    def test_short_status_has_no_temp(self) -> None:
        """A short status frame decodes flags but leaves temps unset."""
        body = _status_body()[:18]  # through the packed-flags byte only
        resp = MessageB7Response(_frame(MessageType.notify1, body))
        assert _attr(resp, "left_gear") == 3
        assert not hasattr(resp, "left_temp")

    def test_too_short_status_skipped(self) -> None:
        """A status frame shorter than the minimum is not decoded."""
        body = [CMD_STATUS_NOTIFY, 2, 1]  # below STATUS_MIN_LEN
        resp = MessageB7Response(_frame(MessageType.notify1, body))
        assert not hasattr(resp, "left_gear")


class TestB7ErrorDecode:
    """Test b7 error / tips report decode."""

    def test_error_code(self) -> None:
        """First set bit in the error groups wins (bit 2 -> code 3)."""
        body = [CMD_ERROR, 0x03, 0b00000100, 0, 0, 0]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "error_code") == 3
        assert _attr(resp, "tips_code") == 0

    def test_error_code_second_group(self) -> None:
        """A bit in the second error byte maps to codes 9..16."""
        body = [CMD_ERROR, 0x03, 0x00, 0b00000001, 0, 0]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "error_code") == 9

    def test_tips_code(self) -> None:
        """Tips bits map after the error groups (first tips byte -> 1..6)."""
        body = [CMD_ERROR, 0x03, 0x00, 0x00, 0b00000010, 0]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "error_code") == 0
        assert _attr(resp, "tips_code") == 2

    def test_tips_code_second_group(self) -> None:
        """The second tips byte maps to tips 7..8."""
        body = [CMD_ERROR, 0x03, 0x00, 0x00, 0x00, 0b00000010]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "tips_code") == 8

    def test_error_wrong_subtype(self) -> None:
        """A non-0x03 error sub-type leaves error_code/tips_code at zero."""
        body = [CMD_ERROR, 0x01, 0xFF, 0xFF, 0xFF, 0xFF]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "error_code") == 0
        assert _attr(resp, "tips_code") == 0

    def test_error_subtype_no_bits(self) -> None:
        """A 0x03 error sub-type with no bits set leaves both codes zero."""
        body = [CMD_ERROR, 0x03, 0x00, 0x00, 0x00, 0x00]
        resp = MessageB7Response(_frame(MessageType.query, body))
        assert _attr(resp, "error_code") == 0
        assert _attr(resp, "tips_code") == 0


class TestB7FailDecode:
    """Test b7 fail-response decode (Lua bytecmd[9] == 0x02 branch)."""

    def test_fail_reason(self) -> None:
        """A set-type frame with body[1] == 0xFE exposes the fail reason."""
        body = [0x00, 0xFE, 0x00, 7]
        resp = MessageB7Response(_frame(MessageType.set, body))
        assert _attr(resp, "fail_resp_reason") == 7

    def test_non_fail_set_frame(self) -> None:
        """A set-type frame without the 0xFE marker exposes no reason."""
        body = [0x00, 0x00, 0x00, 0x00]
        resp = MessageB7Response(_frame(MessageType.set, body))
        assert not hasattr(resp, "fail_resp_reason")


class TestB7Control:
    """Test b7 control frame encode."""

    def test_power(self) -> None:
        """Power sends burner selector + function_control 1 (momentary)."""
        message = MessageSet(ProtocolVersion.V3)
        message.burner = BURNER_LEFT
        message.function_control = FUNCTION_POWER
        body = message.body
        assert body[0] == CONTROL_OPCODE
        assert body[1] == BURNER_LEFT
        assert body[2] == FUNCTION_POWER

    def test_gear(self) -> None:
        """Gear control writes the gear byte at body[5]."""
        message = MessageSet(ProtocolVersion.V3)
        message.burner = BURNER_RIGHT
        message.function_control = FUNCTION_GEAR
        message.gear = 4
        body = message.body
        assert body[1] == BURNER_RIGHT
        assert body[2] == FUNCTION_GEAR
        assert body[5] == 4

    def test_surplus(self) -> None:
        """Surplus timer writes hours/minutes at body[3]/body[4]."""
        message = MessageSet(ProtocolVersion.V3)
        message.burner = BURNER_LEFT
        message.function_control = FUNCTION_SURPLUS
        message.surplus_hours = 1
        message.surplus_minutes = 15
        body = message.body
        assert body[3] == 1
        assert body[4] == 15

    def test_left_temp(self) -> None:
        """Left temperature is a 16-bit pair at body[6]/body[7]."""
        message = MessageSet(ProtocolVersion.V3)
        message.burner = BURNER_LEFT
        message.function_control = FUNCTION_TEMP_MIN
        message.left_temp = 300
        body = message.body
        assert body[6] == (300 >> 8) & 0xFF
        assert body[7] == 300 & 0xFF

    def test_right_temp(self) -> None:
        """Right temperature is a 16-bit pair at body[8]/body[9]."""
        message = MessageSet(ProtocolVersion.V3)
        message.burner = BURNER_RIGHT
        message.function_control = FUNCTION_TEMP_MIN
        message.right_temp = 250
        body = message.body
        assert body[8] == (250 >> 8) & 0xFF
        assert body[9] == 250 & 0xFF

    def test_lock_on(self) -> None:
        """Lock on uses the lock burner selector and LOCK_ON value."""
        message = MessageSetLock(ProtocolVersion.V3)
        message.lock = True
        body = message.body
        assert body[1] == BURNER_LOCK
        assert body[2] == LOCK_ON

    def test_lock_off(self) -> None:
        """Lock off uses the LOCK_OFF value."""
        message = MessageSetLock(ProtocolVersion.V3)
        message.lock = False
        assert message.body[2] == LOCK_OFF

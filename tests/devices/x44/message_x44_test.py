"""Test x44 messages."""

import pytest

from midealan.devices.x44.message import (
    BUTTON_BYTE,
    FUNC_BYTE,
    LEFT_BUTTON,
    SCREEN_FUNC,
    SCREEN_PAYLOAD_LENGTH,
    UNCHANGED,
    VOICE_VOLUME,
    VOICE_VOLUME_BYTE,
    MessageQuery,
    MessageSetScreen,
    MessageX44Base,
    MessageX44Response,
    parse_screen,
)
from midealan.message import ListTypes, MessageLenError, MessageType

SCREEN_REPORT = bytes.fromhex(
    "aa1f4400000000000003080201ff000101000000321700080015010004000023",
)
QUERY_FRAME = bytes.fromhex("aa0c44000000000000030802a3")


def _frame(message_type: int, body: bytes) -> bytearray:
    header = bytearray(
        [0xAA, 0x00, 0x44, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, message_type],
    )
    return bytearray(header + body + b"\x00")


class TestMessageX44Base:
    """Test x44 message base."""

    def test_body_not_implemented(self) -> None:
        """Test the base body is abstract."""
        message = MessageX44Base(0, MessageType.query, ListTypes.X08)
        with pytest.raises(NotImplementedError):
            _ = message.body


class TestMessageQuery:
    """Test the screen query frame."""

    def test_serialize_matches_panel(self) -> None:
        """Test the query matches the frame accepted by the panel."""
        assert MessageQuery(0).serialize() == bytearray(QUERY_FRAME)


class TestMessageSetScreen:
    """Test screen set encoding."""

    def test_unset_fields_stay_unchanged(self) -> None:
        """Test a set with no fields keeps the ignore bytes."""
        payload = MessageSetScreen(0)._body
        assert len(payload) == SCREEN_PAYLOAD_LENGTH
        assert payload[FUNC_BYTE - 1] == SCREEN_FUNC
        assert payload[1:] == bytearray([UNCHANGED] * (SCREEN_PAYLOAD_LENGTH - 1))

    def test_voice_volume(self) -> None:
        """Test one numeric field is written and the rest stay unchanged."""
        message = MessageSetScreen(0)
        message.values[VOICE_VOLUME] = 50
        payload = message._body
        assert payload[VOICE_VOLUME_BYTE - 1] == 50
        assert payload[BUTTON_BYTE - 1] == UNCHANGED

    def test_left_button_on(self) -> None:
        """Test one flag is encoded and the other pairs stay ignored."""
        message = MessageSetScreen(0)
        message.values[LEFT_BUTTON] = 1
        assert message._body[BUTTON_BYTE - 1] == 0xFD


class TestParseScreen:
    """Test screen body parsing."""

    def test_live_report(self) -> None:
        """Test the report captured from 192.168.30.23."""
        body = bytearray(SCREEN_REPORT[10:-1])
        assert parse_screen(body) == {
            "has_token": 1,
            "error_code": 0,
            "left_button": 1,
            "middle_button": 0,
            "right_button": 0,
            "show_button_name": 1,
            "close_screen_bright": 0,
            "sleep_mode_switch": 0,
            "sleep_mode_mute": 0,
            "auto_off_screen_type": 0,
            "theme": 0,
            "night_volume": 0,
            "voice_volume": 50,
            "sleep_start_hour": 23,
            "sleep_start_minute": 0,
            "sleep_duration_hour": 8,
            "sleep_duration_minute": 0,
            "left_button_keep": 1,
            "middle_button_keep": 1,
            "right_button_keep": 1,
            "voice_control": 1,
            "sleep_mode": 0,
            "screen_state": 0,
            "brightness": 0,
            "left_button_work_mode": 4,
            "middle_button_work_mode": 0,
            "right_button_work_mode": 0,
        }

    def test_other_bit_pattern(self) -> None:
        """Test the middle bit pattern decodes to 2 and a full mask is skipped."""
        body = bytearray([0x08, 0x02, 0xFF, 0xFF, 0xFF, 0x08, 0x0C])
        parsed = parse_screen(body)
        assert parsed["middle_button"] == 2
        assert parsed["show_button_name"] == 0
        assert "close_screen_bright" not in parsed

    def test_short_body(self) -> None:
        """Test a body without the function byte parses empty."""
        assert parse_screen(bytearray([0x08])) == {}

    def test_ignored_low_bits(self) -> None:
        """Test a 0x03 low pair is omitted rather than stored."""
        body = bytearray([0x08, 0x02, 0xFF, 0xFF, 0xFF, 0x03])
        assert "left_button" not in parse_screen(body)

    def test_flag_off_keeps_other_pairs_ignored(self) -> None:
        """Test encoding 0 does not set the on bit."""
        message = MessageSetScreen(0)
        message.values[LEFT_BUTTON] = 0
        assert message._body[BUTTON_BYTE - 1] == 0xFC


class TestMessageX44Response:
    """Test response gating."""

    def test_query_report(self) -> None:
        """Test a query report exposes screen attributes."""
        message = MessageX44Response(bytearray(SCREEN_REPORT))
        assert message.message_type == MessageType.query
        assert message.attributes["voice_volume"] == 50
        assert "panel_status" not in message.attributes

    def test_other_function_is_ignored(self) -> None:
        """Test function 0x01 is not decoded as a screen record."""
        body = bytes(SCREEN_REPORT[10:-1])
        framed = _frame(0x03, b"\x08\x01" + body[2:])
        message = MessageX44Response(framed)
        assert message.attributes == {}

    def test_other_body_type_is_ignored(self) -> None:
        """Test a non-screen body type is ignored."""
        message = MessageX44Response(_frame(0x03, b"\x01\x02\x03"))
        assert message.attributes == {}

    def test_notify_is_parsed(self) -> None:
        """Test a notify uses the same screen layout."""
        body = SCREEN_REPORT[10:-1]
        message = MessageX44Response(_frame(0x04, body))
        assert message.attributes["voice_volume"] == 50

    def test_unrelated_message_type_is_ignored(self) -> None:
        """Test an appliance response is not parsed as screen status."""
        message = MessageX44Response(_frame(0xA0, b"\x00\x44"))
        assert message.attributes == {}

    def test_short_message_raises(self) -> None:
        """Test a truncated frame is rejected."""
        with pytest.raises(MessageLenError):
            MessageX44Response(bytearray([0xAA]))

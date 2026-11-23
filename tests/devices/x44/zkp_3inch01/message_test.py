"""Test ZKP-3INCH01 screen requests and reports."""

import pytest

from midealan.devices.x44.zkp_3inch01.message import (
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
    ScreenRequest,
    ScreenResponse,
    decode_capture,
    parse_screen,
)
from midealan.message import ListTypes, MessageBase, MessageLenError, MessageType
from tests.devices.x44 import AC_REPORT_VIA_90S, ZKP_QUERY, ZKP_REPORT, frame


class TestScreenRequest:
    """Test the screen request base."""

    def test_body_not_implemented(self) -> None:
        """Test the base body is abstract."""
        message = ScreenRequest(0, MessageType.query, ListTypes.X08)
        with pytest.raises(NotImplementedError):
            _ = message.body


class TestMessageQuery:
    """Test the screen query frame."""

    def test_serialize_matches_panel(self) -> None:
        """Test the query matches the frame accepted by the panel."""
        assert MessageQuery(0).serialize() == bytearray(ZKP_QUERY)


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
        """Decode the status report captured from a ZKP-3INCH01 panel."""
        body = bytearray(ZKP_REPORT[10:-1])
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


class TestScreenResponse:
    """Test response gating."""

    def test_query_report(self) -> None:
        """Test a query report exposes screen attributes."""
        message = ScreenResponse(bytearray(ZKP_REPORT))
        assert message.message_type == MessageType.query
        assert message.attributes["voice_volume"] == 50
        assert "panel_status" not in message.attributes

    def test_other_function_is_ignored(self) -> None:
        """Test function 0x01 is not decoded as a screen record."""
        body = bytes(ZKP_REPORT[10:-1])
        framed = frame(0x03, b"\x08\x01" + body[2:])
        message = ScreenResponse(framed)
        assert message.attributes == {}

    def test_other_body_type_is_ignored(self) -> None:
        """Test a non-screen body type is ignored."""
        message = ScreenResponse(frame(0x03, b"\x01\x02\x03"))
        assert message.attributes == {}

    def test_notify_is_parsed(self) -> None:
        """Test a notify uses the same screen layout."""
        body = ZKP_REPORT[10:-1]
        message = ScreenResponse(frame(0x04, body))
        assert message.attributes["voice_volume"] == 50

    def test_unrelated_message_type_is_ignored(self) -> None:
        """Test an appliance response is not parsed as screen status."""
        message = ScreenResponse(frame(0xA0, b"\x00\x44"))
        assert message.attributes == {}

    def test_short_message_raises(self) -> None:
        """Test a truncated frame is rejected."""
        with pytest.raises(MessageLenError):
            ScreenResponse(bytearray([0xAA]))


@pytest.mark.parametrize(
    "message_type",
    [MessageType.query, MessageType.set, MessageType.notify1],
)
def test_decode_screen_capture(message_type: MessageType) -> None:
    """All screen report types use the same parser as an identified device."""
    report = frame(message_type, ZKP_REPORT[10:-1])
    assert decode_capture(report) == ScreenResponse(report).attributes
    assert decode_capture(report)["voice_volume"] == 50


@pytest.mark.parametrize(
    "report",
    [
        b"",
        ZKP_REPORT[:-1],
        ZKP_REPORT[:-1] + b"\x00",
        AC_REPORT_VIA_90S,
        ZKP_QUERY,
        frame(MessageType.query, b""),
        frame(MessageType.query, b"\x08"),
        frame(MessageType.query, b"\x08\x01\x01"),
        frame(MessageType.notify2, ZKP_REPORT[10:-1]),
        frame(0xFE, ZKP_REPORT[10:-1]),
    ],
)
def test_capture_without_screen_status(report: bytes | bytearray) -> None:
    """Truncated, damaged, unrelated and empty reports expose no screen fields."""
    assert decode_capture(report) == {}


@pytest.mark.parametrize(("offset", "value"), [(0, 0xAB), (1, 0x1E), (2, 0xAC)])
def test_capture_with_invalid_header(offset: int, value: int) -> None:
    """A valid payload and checksum alone cannot identify a screen capture."""
    report = bytearray(ZKP_REPORT)
    report[offset] = value
    report[-1] = MessageBase.checksum(report[1:-1])
    assert decode_capture(report) == {}

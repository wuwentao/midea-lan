"""Test x17 message."""

from midealan.const import DeviceType
from midealan.devices.x17.message import (
    CONTROL_COMMAND,
    QUERY_COMMAND,
    SELECTOR_ANION,
    SELECTOR_BAKING,
    SELECTOR_DRY,
    SELECTOR_LIGHT,
    SELECTOR_POWER,
    SELECTOR_STERILIZE,
    SELECTOR_UPDOWN,
    UPDOWN_DOWN,
    UPDOWN_UP,
    VALUE_OFF,
    VALUE_ON,
    Message17Response,
    MessageQuery,
    MessageSet,
    X17GeneralMessageBody,
)
from midealan.message import MessageType


def _report_frame(body: bytes, message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full x17 response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.X17, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


class TestX17GeneralMessageBody:
    """Test x17 general message body (report decode)."""

    def test_all_on_updown_up(self) -> None:
        """Power on, motor rising, every toggle set, no fault."""
        # flags byte: light|sterilize|dry|baking|anion = 0x1F
        body = bytearray([VALUE_ON, UPDOWN_UP, 0x1F, 0x00])
        msg = X17GeneralMessageBody(body)
        assert msg.power is True
        assert msg.updown == "up"
        assert msg.light is True
        assert msg.sterilize is True
        assert msg.dry is True
        assert msg.baking is True
        assert msg.anion is True
        assert msg.error_code == 0

    def test_all_off_updown_down_with_error(self) -> None:
        """Power off, motor lowering, every toggle clear, error code set."""
        body = bytearray([VALUE_OFF, UPDOWN_DOWN, 0x00, 0x07])
        msg = X17GeneralMessageBody(body)
        assert msg.power is False
        assert msg.updown == "down"
        assert msg.light is False
        assert msg.sterilize is False
        assert msg.dry is False
        assert msg.baking is False
        assert msg.anion is False
        assert msg.error_code == 7

    def test_selected_flags_only(self) -> None:
        """Only dry + anion set; others stay off (bitmask isolation)."""
        # dry (0x04) | anion (0x10) = 0x14
        body = bytearray([VALUE_ON, 0x00, 0x14, 0x00])
        msg = X17GeneralMessageBody(body)
        assert msg.updown == "pause"
        assert msg.dry is True
        assert msg.anion is True
        assert msg.light is False
        assert msg.sterilize is False
        assert msg.baking is False

    def test_unknown_updown_falls_back_to_pause(self) -> None:
        """An out-of-range updown byte decodes to the safe 'pause' label."""
        body = bytearray([VALUE_ON, 0xFF, 0x00, 0x00])
        assert X17GeneralMessageBody(body).updown == "pause"


class TestMessageQuery:
    """Test x17 query message."""

    def test_query_body(self) -> None:
        """Query body is the single command byte 0x03 (Lua query payload)."""
        query = MessageQuery(3)
        assert query.body == bytearray([QUERY_COMMAND])
        frame = query.serialize()
        assert frame[2] == DeviceType.X17
        assert frame[9] == MessageType.query
        assert frame[10] == QUERY_COMMAND
        # Lua query frame is 12 bytes (msgLen 11 + trailing checksum).
        assert len(frame) == 12


class TestMessageSet:
    """Test x17 single-function control message."""

    def test_set_power_on_body(self) -> None:
        """Set power-on serialises to command 0x00 + selector 0x05 + 0x01."""
        message = MessageSet(3)
        message.selector = SELECTOR_POWER
        message.value = VALUE_ON
        expected = bytearray([CONTROL_COMMAND, SELECTOR_POWER, VALUE_ON])
        assert message.body[:3] == expected
        frame = message.serialize()
        assert frame[9] == MessageType.set
        assert frame[10] == CONTROL_COMMAND
        assert frame[11] == SELECTOR_POWER
        assert frame[12] == VALUE_ON
        # Lua control frame is a fixed 21 bytes (10-byte body + header + checksum).
        assert len(frame) == 21

    def test_set_each_selector(self) -> None:
        """Every control routes through the same frame shape with its selector."""
        for selector in (
            SELECTOR_UPDOWN,
            SELECTOR_LIGHT,
            SELECTOR_STERILIZE,
            SELECTOR_DRY,
            SELECTOR_ANION,
            SELECTOR_BAKING,
        ):
            message = MessageSet(3)
            message.selector = selector
            message.value = VALUE_ON
            assert message.body[1] == selector
            assert message.body[2] == VALUE_ON


class TestMessage17Response:
    """Test x17 response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates the state attributes."""
        response = Message17Response(_report_frame([VALUE_ON, UPDOWN_UP, 0x01, 0x00]))
        assert response.power is True
        assert response.updown == "up"
        assert response.light is True

    def test_notify_decodes(self) -> None:
        """A notify (0x04) is decoded the same as a query reply."""
        response = Message17Response(
            _report_frame([VALUE_ON, 0x00, 0x00, 0x00], MessageType.notify1),
        )
        assert response.power is True

    def test_set_echo_not_decoded(self) -> None:
        """The set echo (0x02) is ignored, mirroring the Lua binToModel guard."""
        response = Message17Response(
            _report_frame([VALUE_ON, UPDOWN_UP, 0x01, 0x00], MessageType.set),
        )
        assert not hasattr(response, "power")

    def test_short_body_not_decoded(self) -> None:
        """A body shorter than the fixed offsets decodes to nothing."""
        response = Message17Response(_report_frame([VALUE_ON]))
        assert not hasattr(response, "power")

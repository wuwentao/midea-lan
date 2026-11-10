"""Test x9a message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.x9a.message import (
    CONTROL_CMD,
    FORM_COOK,
    FORM_STATUS,
    POWER_OFF,
    POWER_ON,
    QUERY_CMD,
    VALUE_INVALID,
    WEIGHT_UNIT,
    WORK_STATUS_WORK,
    Message9aResponse,
    MessageCookSet,
    MessageQuery,
    MessageStatusSet,
    X9aControlEchoBody,
    X9aQueryBody,
)
from midealan.message import MessageType


def _frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a body in a full x9a response frame (header + checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.X9A, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _query_body() -> list[int]:
    """Build a full 20-byte query-reply body with every field populated."""
    body = [0] * 20
    body[0] = QUERY_CMD
    body[1] = WORK_STATUS_WORK  # work_status work -> power on
    body[6] = 1  # hour
    body[7] = 20  # minutes
    body[8] = 5  # second
    body[9] = 0x01  # mode microwave
    body[10] = 0
    body[11] = 50  # current_temperature = 50
    body[14] = 80  # watt
    body[15] = 30  # weight raw -> 300 g
    body[16] = 0x01  # lock bit set
    body[17] = 0x04  # furnace_light bit set
    body[18] = 0
    body[19] = 180  # target temperature = 180
    return body


class TestX9aQueryBody:
    """Test x9a query-reply body decode."""

    def test_full_record(self) -> None:
        """Every field decodes from a full query reply."""
        msg = X9aQueryBody(bytearray(_query_body()))
        assert msg.power is True
        assert msg.work_status == "work"
        assert msg.mode == "microwave"
        assert msg.hour == 1
        assert msg.minutes == 20
        assert msg.second == 5
        assert msg.current_temperature == 50
        assert msg.temperature == 180
        assert msg.lock is True
        assert msg.furnace_light is True
        assert msg.watt == 80
        assert msg.weight == 300
        assert msg.error_code == 0

    def test_power_off_when_work_status_one(self) -> None:
        """work_status 0x01 reports power off and no work_status label."""
        body = _query_body()
        body[1] = POWER_OFF  # 0x01
        msg = X9aQueryBody(bytearray(body))
        assert msg.power is False
        assert not hasattr(msg, "work_status")

    def test_lock_and_light_clear(self) -> None:
        """Lock / furnace_light decode false when their bits are clear."""
        body = _query_body()
        body[16] = 0x00
        body[17] = 0x00
        msg = X9aQueryBody(bytearray(body))
        assert msg.lock is False
        assert msg.furnace_light is False

    def test_unknown_mode_omitted(self) -> None:
        """An unrecognized mode byte leaves mode unset."""
        body = _query_body()
        body[9] = 0x02  # not in MODE_NAMES
        msg = X9aQueryBody(bytearray(body))
        assert not hasattr(msg, "mode")


class TestX9aControlEchoBody:
    """Test x9a control-echo body decode."""

    def test_status_echo(self) -> None:
        """A FORM_STATUS echo decodes power / lock / light."""
        body = [CONTROL_CMD, FORM_STATUS, WORK_STATUS_WORK, 0x01, 0x01]
        msg = X9aControlEchoBody(bytearray(body))
        assert msg.power is True
        assert msg.work_status == "work"
        assert msg.lock is True
        assert msg.furnace_light is True

    def test_cook_echo(self) -> None:
        """A FORM_COOK echo decodes time / mode / temperature / watt / weight."""
        body = [
            CONTROL_CMD,
            FORM_COOK,
            0,
            0,
            0,
            0,
            0,
            2,
            15,
            0,
            0x47,
            0,
            200,
            0,
            0,
            80,
            25,
        ]
        msg = X9aControlEchoBody(bytearray(body))
        assert msg.hour == 2
        assert msg.minutes == 15
        assert msg.mode == "whole_baking"
        assert msg.temperature == 200
        assert msg.watt == 80
        assert msg.weight == 250

    def test_status_echo_unknown_work_status(self) -> None:
        """A status echo with an unknown work_status byte omits the label."""
        body = [CONTROL_CMD, FORM_STATUS, 0x07, 0x00, 0x00]
        msg = X9aControlEchoBody(bytearray(body))
        assert not hasattr(msg, "work_status")
        assert msg.power is True

    def test_cook_echo_unknown_mode(self) -> None:
        """A cook echo with an unknown mode byte omits the mode label."""
        body = [
            CONTROL_CMD,
            FORM_COOK,
            0,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
            0x02,
            0,
            100,
            0,
            0,
            0,
            0,
        ]
        msg = X9aControlEchoBody(bytearray(body))
        assert not hasattr(msg, "mode")
        assert msg.temperature == 100

    def test_short_status_echo_decodes_nothing(self) -> None:
        """A truncated FORM_STATUS echo exposes no fields."""
        msg = X9aControlEchoBody(bytearray([CONTROL_CMD, FORM_STATUS, 0x03]))
        assert not hasattr(msg, "lock")

    def test_short_cook_echo_decodes_nothing(self) -> None:
        """A truncated FORM_COOK echo exposes no fields."""
        msg = X9aControlEchoBody(bytearray([CONTROL_CMD, FORM_COOK, 0, 0]))
        assert not hasattr(msg, "mode")

    def test_unknown_form_decodes_nothing(self) -> None:
        """An unknown sub-form byte exposes no fields."""
        msg = X9aControlEchoBody(bytearray([CONTROL_CMD, 0x09, 0, 0, 0]))
        assert not hasattr(msg, "lock")
        assert not hasattr(msg, "mode")


class TestMessageQuery:
    """Test x9a query message."""

    def test_query_body(self) -> None:
        """Query body is the single sub-command byte 0x31."""
        query = MessageQuery(3)
        assert query.body == bytearray([QUERY_CMD])
        frame = query.serialize()
        assert frame[2] == DeviceType.X9A
        assert frame[9] == MessageType.query


class TestMessageStatusSet:
    """Test x9a FORM_STATUS control."""

    def test_default_all_invalid(self) -> None:
        """An untouched status set sends 0xFF for each field."""
        message = MessageStatusSet(3)
        assert message.body == bytearray(
            [CONTROL_CMD, FORM_STATUS, VALUE_INVALID, VALUE_INVALID, VALUE_INVALID],
        )

    def test_power_on(self) -> None:
        """Power on maps to work_status byte 0x02."""
        message = MessageStatusSet(3)
        message.work_status = POWER_ON
        assert message.body[2] == POWER_ON
        frame = message.serialize()
        assert frame[9] == MessageType.set

    def test_lock_and_light(self) -> None:
        """Lock / furnace_light land at body offsets 3 and 4."""
        message = MessageStatusSet(3)
        message.lock = 0x01
        message.furnace_light = 0x00
        assert message.body[3] == 0x01
        assert message.body[4] == 0x00


class TestMessageCookSet:
    """Test x9a FORM_COOK control."""

    def test_cook_body_layout(self) -> None:
        """Cook fields land at their Lua body offsets; weight scaled by 10."""
        message = MessageCookSet(3)
        message.hour = 1
        message.minutes = 30
        message.second = 10
        message.mode = 0x01
        message.temperature = 200
        message.watt = 80
        message.weight = 300
        body = message.body
        assert body[0] == CONTROL_CMD
        assert body[1] == FORM_COOK
        assert body[7] == 1
        assert body[8] == 30
        assert body[9] == 10
        assert body[10] == 0x01
        assert body[11] == 0  # temp hi
        assert body[12] == 200  # temp lo
        assert body[15] == 80
        assert body[16] == 300 // WEIGHT_UNIT

    def test_cook_temperature_big_endian(self) -> None:
        """A temperature above 255 splits across the hi/lo bytes."""
        message = MessageCookSet(3)
        message.temperature = 0x0123
        assert message.body[11] == 0x01
        assert message.body[12] == 0x23

    def test_cook_weight_invalid_passthrough(self) -> None:
        """An untouched weight stays the 0xFF sentinel (not divided)."""
        message = MessageCookSet(3)
        assert message.body[16] == VALUE_INVALID

    def test_cook_weight_255_not_dropped(self) -> None:
        """A real 255 g weight serializes to 25, not the 0xFF 'unchanged' byte."""
        message = MessageCookSet(3)
        message.weight = 255
        assert message.body[16] == 255 // WEIGHT_UNIT


class TestMessage9aResponse:
    """Test x9a response wrapper."""

    def test_query_reply_decodes(self) -> None:
        """A query reply (0x03) populates state attributes."""
        response = Message9aResponse(_frame(_query_body()))
        assert getattr(response, "mode") == "microwave"  # noqa: B009
        assert getattr(response, "temperature") == 180  # noqa: B009

    def test_notify1_decodes_like_query(self) -> None:
        """A notify1 (0x04) query report is decoded too."""
        response = Message9aResponse(_frame(_query_body(), MessageType.notify1))
        assert getattr(response, "power") is True  # noqa: B009

    def test_control_echo_decodes(self) -> None:
        """A control echo (0x02) is decoded."""
        body = [CONTROL_CMD, FORM_STATUS, WORK_STATUS_WORK, 0x01, 0x01]
        response = Message9aResponse(_frame(body, MessageType.set))
        assert getattr(response, "lock") is True  # noqa: B009

    def test_notify2_control_echo_decodes(self) -> None:
        """A notify2 (0x05) control report is decoded."""
        body = [CONTROL_CMD, FORM_STATUS, WORK_STATUS_WORK, 0x00, 0x00]
        response = Message9aResponse(_frame(body, MessageType.notify2))
        assert getattr(response, "furnace_light") is False  # noqa: B009

    def test_wrong_query_cmd_not_decoded(self) -> None:
        """A query reply whose body[0] is not 0x31 is ignored."""
        body = _query_body()
        body[0] = 0x30
        response = Message9aResponse(_frame(body))
        assert not hasattr(response, "mode")

    def test_short_query_not_decoded(self) -> None:
        """A query body shorter than the fixed record is ignored."""
        response = Message9aResponse(_frame([QUERY_CMD, 0x03, 0x00]))
        assert not hasattr(response, "mode")

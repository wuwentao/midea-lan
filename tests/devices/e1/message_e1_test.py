"""Test E1 messages."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.e1.message import (
    E1GeneralMessageBody,
    MessageE1Base,
    MessageE1Response,
    MessageLock,
    MessageOperator,
    MessagePower,
    MessageQuery,
    MessageStorage,
    MessageWork,
)
from midealan.message import ListTypes, MessageType


def _hex_body(prefix: str) -> bytearray:
    """Return a 38-byte body from a hex prefix, zero-padded."""
    return bytearray.fromhex(prefix.ljust(76, "0"))


def test_work_message_body() -> None:
    """Test work message body."""
    message = MessageWork(ProtocolVersion.V1)
    assert message.body == _hex_body("0803")

    message.mode = 0x04
    assert message.body == _hex_body("080304")


# Bodies verified on a 76000228 dishwasher (E1, protocol 3).
@pytest.mark.parametrize(
    ("work_status", "delay_minutes", "door_auto_open", "expected"),
    [
        (0x03, 0, True, "0803040000000000000000000001"),
        (0x01, 0, False, "080104"),
        (0x02, 60, True, "0802040000000001000000000001"),
        (0x02, 3 * 60 + 34, False, "0802040000000003220000000000"),
        (0x04, 0, False, "080404"),
    ],
)
def test_work_message_verified_bodies(
    work_status: int,
    delay_minutes: int,
    door_auto_open: bool,
    expected: str,
) -> None:
    """Test work message bodies for cancel, delayed start and door auto-open."""
    message = MessageWork(ProtocolVersion.V1)
    message.work_status = work_status
    message.mode = 0x04
    message.delay_minutes = delay_minutes
    message.door_auto_open = door_auto_open
    assert message.body == _hex_body(expected)


def test_work_message_ignores_delay_unless_ordering() -> None:
    """Test the delay bytes are only sent with a delayed start."""
    message = MessageWork(ProtocolVersion.V1)
    message.mode = 0x04
    message.delay_minutes = 60
    assert message.body == _hex_body("080304")


def test_work_message_wash_params() -> None:
    """Test the wash parameters are placed at the lua work-command offsets."""
    message = MessageWork(ProtocolVersion.V1)
    message.mode = 0x04
    message.additional = 0x05  # body index 3
    message.wash_region = 0x06  # body index 4
    message.water_level = 0x02  # body index 11
    message.water_strong_level = 0x01  # body index 12
    # 0x08 type, work 0x03, mode 0x04, additional 0x05, wash_region 0x06,
    # ... water_level at index 11, water_strong_level at index 12
    assert message.body == _hex_body("08030405060000000000000201")


class TestMessageE1Base:
    """Test E1 message base."""

    def test_body_not_implemented(self) -> None:
        """Test base body raises NotImplementedError."""
        message = MessageE1Base(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X00,
        )
        with pytest.raises(NotImplementedError):
            _ = message.body


class TestMessagePower:
    """Test E1 message power."""

    @pytest.mark.parametrize(("power", "expected"), [(True, 0x01), (False, 0x00)])
    def test_power_body(self, power: bool, expected: int) -> None:
        """Test power body reflects the requested state."""
        message = MessagePower(ProtocolVersion.V1)
        message.power = power
        assert message.body == bytearray([0x08, expected, 0x00, 0x00, 0x00])


class TestMessageLock:
    """Test E1 message lock."""

    @pytest.mark.parametrize(("lock", "expected"), [(True, 0x03), (False, 0x04)])
    def test_lock_body(self, lock: bool, expected: int) -> None:
        """Test lock body reflects the requested state."""
        message = MessageLock(ProtocolVersion.V1)
        message.lock = lock
        assert message.body == bytearray([0x83, expected, *([0x00] * 36)])


class TestMessageOperator:
    """Test E1 message operator (pause/resume)."""

    @pytest.mark.parametrize(("pause", "expected"), [(True, 0x02), (False, 0x01)])
    def test_operator_body(self, pause: bool, expected: int) -> None:
        """Test operator body matches the device-confirmed 8302/8301 commands."""
        message = MessageOperator(ProtocolVersion.V1)
        message.pause = pause
        assert message.body == bytearray([0x83, expected, *([0x00] * 36)])


class TestMessageStorage:
    """Test E1 message storage."""

    @pytest.mark.parametrize(("storage", "expected"), [(True, 0x01), (False, 0x00)])
    def test_storage_body(self, storage: bool, expected: int) -> None:
        """Test storage body reflects the requested state."""
        message = MessageStorage(ProtocolVersion.V1)
        message.storage = storage
        assert message.body == bytearray(
            [0x81, 0x00, 0x00, 0x00, expected, *([0xFF] * 6), *([0x00] * 27)],
        )


class TestMessageQuery:
    """Test E1 message query."""

    def test_query_body(self) -> None:
        """Test query body only contains the body type byte."""
        message = MessageQuery(ProtocolVersion.V1)
        assert message.body == bytearray([0x00])


class TestE1GeneralMessageBody:
    """Test E1 general message body."""

    def test_full_body(self) -> None:
        """Test parsing a full-length body sets every attribute."""
        body = bytearray(42)
        body[1] = 0x03  # power on, status Running
        body[2] = 0x04  # mode
        body[3] = 0x05  # additional
        body[4] = 0x7F  # diyflag, uv/uv_switch, dry, door_auto_open, ...
        body[5] = 0xFE  # door closed + all other switch/status bits set
        body[6] = 45  # time_remaining (low byte)
        body[9] = 0x03  # progress
        body[10] = 7  # error_code
        body[11] = 55  # temperature
        body[13] = 2  # softwater
        body[16] = 1  # wrong_operation
        body[17] = 4  # storage_set_time
        body[18] = 5  # storage_remaining
        body[24] = 9  # bright
        body[28] = 3  # device_version
        body[30] = 2  # water_level
        body[31] = 1  # water_strong_level
        body[32] = 1  # left_time_high
        body[33] = 60  # humidity
        body[34] = 50  # dry_set_min
        body[35] = 6  # wash_region
        body[37] = 0xFC  # all status flags except wifi_unabled off
        body[40] = 8  # clean_left_hour
        body[41] = 9  # kitchenware_left_hour

        result = E1GeneralMessageBody(body)

        assert result.power is True
        assert result.status == 0x03
        assert result.mode == 0x04
        assert result.additional == 0x05
        assert result.door is True
        assert result.doorswitch is False
        assert result.rinse_aid is True
        assert result.lack_bright is True
        assert result.salt is True
        assert result.lack_softwater is True
        assert result.start is True
        assert result.child_lock is True
        assert result.dryswitch is True
        assert result.storage is True
        assert result.drystatus is True
        assert result.storage_status is True
        assert result.water_lack is True
        assert result.diyflag is True
        assert result.uv is True
        assert result.uv_switch is True
        assert result.dry is True
        assert result.dry_status is True
        assert result.waterswitch is True
        assert result.dry_step_switch is True
        assert result.door_auto_open is True
        assert result.delay_remaining == 0  # only set in status Delay
        assert result.time_remaining == 1 * 256 + 45
        assert result.progress == 0x03
        assert result.storage_set_time == 4
        assert result.storage_remaining == 5
        assert result.temperature == 55
        assert result.humidity == 60
        assert result.error_code == 7
        assert result.softwater == 2
        assert result.wrong_operation == 1
        assert result.bright == 9
        assert result.operator == "start"
        assert result.device_version == 3
        assert result.water_level == 2
        assert result.water_strong_level == 1
        assert result.dry_set_min == 50
        assert result.wash_region == 6
        assert result.clean_left_hour == 8
        assert result.kitchenware_left_hour == 9
        # body[37] = 0xFC -> auto_throw, throw_percent empty, lock_power,
        # beep_control, light_btn_on, light_strip_on set; wifi_unabled clear
        assert result.wifi_unabled is False
        assert result.auto_throw is True
        assert result.throw_percent == 0
        assert result.lock_power is True
        assert result.beep_control is True
        assert result.light_btn_on is True
        assert result.light_strip_on is True

    def test_short_body_defaults(self) -> None:
        """Test parsing a short body falls back to default values."""
        body = bytearray(18)
        body[1] = 0x00
        body[6] = 30  # time_remaining, no high byte available

        result = E1GeneralMessageBody(body)

        assert result.time_remaining == 30
        assert result.storage_set_time is False
        assert result.storage_remaining is False
        assert result.humidity is None
        assert result.bright is None
        assert result.device_version is None
        assert result.water_level is None
        assert result.water_strong_level is None
        assert result.dry_set_min is None
        assert result.wash_region is None
        assert result.clean_left_hour is None
        assert result.kitchenware_left_hour is None
        # body[37] flags not present on a short body
        assert not hasattr(result, "auto_throw")
        assert result.operator == ""

    def test_operator_pause_in_work_status(self) -> None:
        """Test operator reads pause when running without the start bit."""
        body = bytearray(40)
        body[1] = 0x03  # status Running
        body[5] = 0x00  # start/pause bit unset

        result = E1GeneralMessageBody(body)

        assert result.operator == "pause"

    def test_throw_percent_full_when_flag_clear(self) -> None:
        """Test throw_percent reads full when its flag bit is clear."""
        body = bytearray(42)
        body[37] = 0x00  # throw percent flag clear -> full

        result = E1GeneralMessageBody(body)

        assert result.throw_percent == 100
        assert result.auto_throw is False

    def test_start_false_when_paused_without_start_bit(self) -> None:
        """Test start is False when status is paused and start bit is unset."""
        body = bytearray(40)
        body[1] = 0x02  # status Delay
        body[5] = 0x00  # start_pause bit unset

        result = E1GeneralMessageBody(body)

        assert result.start is False

    def test_delay_remaining_in_status_delay(self) -> None:
        """Test the delay left is parsed from bytes 7-8 in status Delay."""
        body = bytearray(40)
        body[1] = 0x02  # status Delay
        body[4] = 0x40  # door auto-open set
        body[7] = 0  # hours left
        body[8] = 59  # minutes left

        result = E1GeneralMessageBody(body)

        assert result.delay_remaining == 59
        assert result.door_auto_open is True


class TestMessageE1Response:
    """Test E1 message response."""

    @staticmethod
    def _message(message_type: MessageType, body_type: int) -> bytes:
        header = bytearray(
            [0xAA, *([0x00] * 7), ProtocolVersion.V1, message_type],
        )
        body = bytearray(40)
        body[0] = body_type
        crc = bytearray([0x00])
        return bytes(header + body + crc)

    @pytest.mark.parametrize(
        ("message_type", "body_type"),
        [
            (MessageType.set, 0x00),
            (MessageType.set, 0x07),
            (MessageType.query, 0x00),
            (MessageType.notify1, 0x00),
        ],
    )
    def test_handled_combinations_parse_body(
        self,
        message_type: MessageType,
        body_type: int,
    ) -> None:
        """Test handled message/body type combinations parse the general body."""
        message = MessageE1Response(self._message(message_type, body_type))
        assert hasattr(message, "power")
        assert hasattr(message, "temperature")

    @pytest.mark.parametrize(
        ("message_type", "body_type"),
        [
            (MessageType.set, 0x08),
            (MessageType.notify2, 0x00),
        ],
    )
    def test_unhandled_combinations_skip_body(
        self,
        message_type: MessageType,
        body_type: int,
    ) -> None:
        """Test unhandled message/body type combinations skip parsing."""
        message = MessageE1Response(self._message(message_type, body_type))
        assert not hasattr(message, "power")

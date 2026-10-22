"""Midea lan E1 message."""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

BRIGTH_BYTE = 24
STORAGE_REMAINING_BYTE = 18
HUMIDITY_BYTE = 33
CONTROL_BODY_LENGTH = 37  # 38 bytes with the body type, as in Midea's Lua

WORK_STATUS_POWER_OFF = 0x00
WORK_STATUS_CANCEL = 0x01
WORK_STATUS_ORDER = 0x02
WORK_STATUS_WORK = 0x03
WORK_STATUS_CANCEL_ORDER = 0x04

# Operator command (body type 0x83), value at body[1]
OPERATOR_START = 0x01
OPERATOR_PAUSE = 0x02
LOCK_ON = 0x03
LOCK_OFF = 0x04

# Work command offsets, after the body type byte
WORK_ADDITIONAL_INDEX = 2
WORK_WASH_REGION_INDEX = 3
WORK_DELAY_HOURS_INDEX = 6
WORK_DELAY_MINUTES_INDEX = 7
WORK_WATER_LEVEL_INDEX = 10
WORK_WATER_STRONG_LEVEL_INDEX = 11
WORK_DOOR_AUTO_OPEN_INDEX = 12

# Status reply offsets and flags
DOOR_AUTO_OPEN_FLAG = 0x40
OPERATOR_BYTE = 5
OPERATOR_FLAG = 0x08
DELAY_HOURS_BYTE = 7
DELAY_MINUTES_BYTE = 8
DEVICE_VERSION_BYTE = 28
WATER_LEVEL_BYTE = 30
WATER_STRONG_LEVEL_BYTE = 31
DRY_SET_MIN_BYTE = 34
WASH_REGION_BYTE = 35
STATUS_FLAGS_BYTE = 37
CLEAN_LEFT_HOUR_BYTE = 40
KITCHENWARE_LEFT_HOUR_BYTE = 41

# body[37] status flag bits
WIFI_UNABLED_FLAG = 0x02
AUTO_THROW_FLAG = 0x04
THROW_PERCENT_FLAG = 0x08
LOCK_POWER_FLAG = 0x10
BEEP_CONTROL_FLAG = 0x20
LIGHT_BTN_ON_FLAG = 0x40
LIGHT_STRIP_ON_FLAG = 0x80

THROW_PERCENT_EMPTY = 0
THROW_PERCENT_FULL = 100


class MessageE1Base(MessageRequest):
    """E1 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize E1 message base."""
        super().__init__(
            device_type=DeviceType.E1,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessagePower(MessageE1Base):
    """E1 message power."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message power."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X08,
        )
        self.power = False

    @property
    def _body(self) -> bytearray:
        power = 0x01 if self.power else 0x00
        return bytearray([power, 0x00, 0x00, 0x00])


class MessageWork(MessageE1Base):
    """E1 message work.

    Layout from Midea's T_0000_E1_7600002B_2024042301.lua: byte 1 work status,
    byte 2 mode, bytes 7-8 delay (hours, minutes) when ordering, byte 13 door
    auto-open.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message work."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X08,
        )
        self.work_status = WORK_STATUS_WORK
        self.mode = 0
        self.additional = 0
        self.wash_region = 0
        self.water_level = 0
        self.water_strong_level = 0
        self.delay_minutes = 0
        self.door_auto_open = False

    @property
    def _body(self) -> bytearray:
        body = bytearray(CONTROL_BODY_LENGTH)
        body[0] = self.work_status
        body[1] = self.mode
        body[WORK_ADDITIONAL_INDEX] = self.additional
        body[WORK_WASH_REGION_INDEX] = self.wash_region
        body[WORK_WATER_LEVEL_INDEX] = self.water_level
        body[WORK_WATER_STRONG_LEVEL_INDEX] = self.water_strong_level
        if self.work_status == WORK_STATUS_ORDER:
            (
                body[WORK_DELAY_HOURS_INDEX],
                body[WORK_DELAY_MINUTES_INDEX],
            ) = divmod(self.delay_minutes, 60)
        body[WORK_DOOR_AUTO_OPEN_INDEX] = 0x01 if self.door_auto_open else 0x00
        return body


class MessageLock(MessageE1Base):
    """E1 message lock."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message lock."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X83,
        )
        self.lock = False

    @property
    def _body(self) -> bytearray:
        lock = LOCK_ON if self.lock else LOCK_OFF
        return bytearray([lock]) + bytearray(CONTROL_BODY_LENGTH - 1)


class MessageOperator(MessageE1Base):
    """E1 message operator (pause/resume).

    Shares body type 0x83 with the lock command. body[1] carries the
    operator value: start/resume 0x01, pause 0x02 (Midea lua updateDataByJson).
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message operator."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X83,
        )
        self.pause = False

    @property
    def _body(self) -> bytearray:
        operator = OPERATOR_PAUSE if self.pause else OPERATOR_START
        return bytearray([operator]) + bytearray(CONTROL_BODY_LENGTH - 1)


class MessageStorage(MessageE1Base):
    """E1 message storage."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message storage."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X81,
        )
        self.storage = False

    @property
    def _body(self) -> bytearray:
        storage = 0x01 if self.storage else 0x00
        return (
            bytearray([0x00, 0x00, 0x00, storage])
            + bytearray([0xFF] * 6)
            + bytearray([0x00] * 27)
        )


class MessageQuery(MessageE1Base):
    """E1 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize E1 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X00,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class E1GeneralMessageBody(MessageBody):
    """E1 message general body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize E1 message general body."""
        super().__init__(body)
        self.power = body[1] > 0
        self.status = body[1]
        self.mode = body[2]
        self.additional = body[3]
        self.door = (body[5] & 0x01) == 0  # 0 - open, 1 - close
        self.rinse_aid = (body[5] & 0x02) > 0  # 0 - enough, 1 - shortage
        self.salt = (body[5] & 0x04) > 0  # 0 - enough, 1 - shortage
        start_pause = (body[OPERATOR_BYTE] & OPERATOR_FLAG) > 0  # operator
        if start_pause:
            self.start = True
        elif self.status in [2, 3]:
            self.start = False
        self.lack_bright = (body[5] & 0x02) > 0
        self.lack_softwater = (body[5] & 0x04) > 0
        self.diyflag = (body[4] & 0x08) > 0
        self.child_lock = (body[5] & 0x10) > 0
        self.uv = (body[4] & 0x2) > 0
        self.door_auto_open = (body[4] & DOOR_AUTO_OPEN_FLAG) > 0
        # Delay left until a delayed start, only meaningful in status Delay
        self.delay_remaining = (
            body[DELAY_HOURS_BYTE] * 60 + body[DELAY_MINUTES_BYTE]
            if self.status == WORK_STATUS_ORDER
            else 0
        )
        self.dry = (body[4] & 0x10) > 0
        self.dry_status = (body[4] & 0x20) > 0
        self.storage = (body[5] & 0x20) > 0  # airswitch
        self.storage_status = (body[5] & 0x40) > 0  # airstatus
        self.time_remaining = body[6]
        if len(body) > HUMIDITY_BYTE:
            _left_time_high = body[32]
            if _left_time_high:
                self.time_remaining = _left_time_high * 256 + self.time_remaining
        self.progress = body[9]  # washStage
        self.storage_set_time = (  # airSetTime    Hour
            body[17] if len(body) > STORAGE_REMAINING_BYTE else False
        )
        self.storage_remaining = (  # airLeftTime    Hour
            body[18] if len(body) > STORAGE_REMAINING_BYTE else False
        )
        self.temperature = body[11]
        self.humidity = body[33] if len(body) > HUMIDITY_BYTE else None
        self.doorswitch = (body[5] & 0x01) > 0
        self.dryswitch = (body[5] & 0x10) > 0
        self.drystatus = (body[5] & 0x20) > 0
        self.waterswitch = (body[4] & 0x04) > 0
        self.water_lack = (body[5] & 0x80) > 0
        self.dry_step_switch = (body[4] & 0x01) > 0
        self.uv_switch = (body[4] & 0x02) > 0
        self.error_code = body[10]
        self.softwater = body[13]
        self.wrong_operation = body[16]
        self.bright = body[24] if len(body) > BRIGTH_BYTE else None
        # operator: run/pause state (lua maps body[5] & 0x08 and work status)
        if (body[OPERATOR_BYTE] & OPERATOR_FLAG) > 0:
            self.operator = "start"
        elif self.status in (WORK_STATUS_ORDER, WORK_STATUS_WORK):
            self.operator = "pause"
        else:
            self.operator = ""
        self.device_version = (
            body[DEVICE_VERSION_BYTE] if len(body) > DEVICE_VERSION_BYTE else None
        )
        self.water_level = (
            body[WATER_LEVEL_BYTE] if len(body) > WATER_LEVEL_BYTE else None
        )
        self.water_strong_level = (
            body[WATER_STRONG_LEVEL_BYTE]
            if len(body) > WATER_STRONG_LEVEL_BYTE
            else None
        )
        self.dry_set_min = (
            body[DRY_SET_MIN_BYTE] if len(body) > DRY_SET_MIN_BYTE else None
        )
        self.wash_region = (
            body[WASH_REGION_BYTE] if len(body) > WASH_REGION_BYTE else None
        )
        if len(body) > STATUS_FLAGS_BYTE:
            flags = body[STATUS_FLAGS_BYTE]
            self.wifi_unabled = (flags & WIFI_UNABLED_FLAG) > 0
            self.auto_throw = (flags & AUTO_THROW_FLAG) > 0
            self.throw_percent = (
                THROW_PERCENT_EMPTY
                if (flags & THROW_PERCENT_FLAG) > 0
                else THROW_PERCENT_FULL
            )
            self.lock_power = (flags & LOCK_POWER_FLAG) > 0
            self.beep_control = (flags & BEEP_CONTROL_FLAG) > 0
            self.light_btn_on = (flags & LIGHT_BTN_ON_FLAG) > 0
            self.light_strip_on = (flags & LIGHT_STRIP_ON_FLAG) > 0
        self.clean_left_hour = (
            body[CLEAN_LEFT_HOUR_BYTE] if len(body) > CLEAN_LEFT_HOUR_BYTE else None
        )
        self.kitchenware_left_hour = (
            body[KITCHENWARE_LEFT_HOUR_BYTE]
            if len(body) > KITCHENWARE_LEFT_HOUR_BYTE
            else None
        )


class MessageE1Response(MessageResponse):
    """E1 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize E1 message response."""
        super().__init__(bytearray(message))
        if (
            self.message_type == MessageType.set
            and 0 <= self.body_type <= ListTypes.X07
        ) or (
            self.message_type in [MessageType.query, MessageType.notify1]
            and self.body_type == 0
        ):
            self.set_body(E1GeneralMessageBody(super().body))
        self.set_attr()

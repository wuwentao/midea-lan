"""Midea lan CE message."""

from midealan.const import MAX_BYTE_VALUE, DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Vendor protocol reference for the compact status and timer layouts:
# https://github.com/wuwentao/midea-lua/blob/main/lua/0xCE/T_0000_CE_171120H4_9.lua
CE_COMPACT_STATUS_BODY_LENGTH = 8
CE_GENERAL_STATUS_BODY_MIN_LENGTH = 25
CE_NOTIFY_STATUS_BODY_MIN_LENGTH = 13
CE_DAILY_TIMER_BODY_LENGTH = 27
CE_WEEKLY_TIMER_BODY_LENGTH = 28
CE_TIMER_COUNT = 5
CE_TIMER_FIELD_LENGTH = 5
CE_MIN_WEEKDAY = 1
CE_MAX_WEEKDAY = 7

CE_POWER_FLAG = 0x01
CE_AUTO_SET_FLAG = 0x02
CE_SILENT_MODE_FLAG = 0x04

CE_COMPACT_MODES = {
    0x01: "cool",
    0x02: "heat",
    0x03: "fan",
    0x04: "auto",
}
CE_SILENCE_LEVELS = {
    0x00: "level_1",
    0x01: "level_2",
}


class MessageCEBase(MessageRequest):
    """CE message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize CE message base."""
        super().__init__(
            device_type=DeviceType.CE,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageCEBase):
    """CE message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize CE message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X01,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageQueryDailyTimer(MessageCEBase):
    """CE daily timer query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize CE daily timer query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X02,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageQueryWeeklyTimer(MessageCEBase):
    """CE weekly timer query."""

    def __init__(self, protocol_version: int, weekday: int) -> None:
        """Initialize CE weekly timer query for weekday 1 through 7."""
        if not CE_MIN_WEEKDAY <= weekday <= CE_MAX_WEEKDAY:
            msg = f"weekday must be between {CE_MIN_WEEKDAY} and {CE_MAX_WEEKDAY}"
            raise ValueError(msg)
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X03,
        )
        self.weekday = weekday

    @property
    def _body(self) -> bytearray:
        return bytearray([1 << (self.weekday - 1)])


class MessageSet(MessageCEBase):
    """CE message set."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize CE message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )

        self.power = False
        self.fan_speed = 0
        self.link_to_ac = False
        self.sleep_mode = False
        self.eco_mode = False
        self.aux_heating = False
        self.powerful_purify = False
        self.scheduled = False
        self.child_lock = False

    @property
    def _body(self) -> bytearray:
        power = 0x80 if self.power else 0x00
        link_to_ac = 0x01 if self.link_to_ac else 0x00
        sleep_mode = 0x02 if self.sleep_mode else 0x00
        eco_mode = 0x04 if self.eco_mode else 0x00
        aux_heating = 0x08 if self.aux_heating else 0x00
        powerful_purify = 0x10 if self.powerful_purify else 0x00
        scheduled = 0x01 if self.scheduled else 0x00
        child_lock = 0x7F if self.child_lock else 0x00
        return bytearray(
            [
                power | 0x01,
                self.fan_speed,
                link_to_ac | sleep_mode | eco_mode | aux_heating | powerful_purify,
                scheduled,
                0x00,
                child_lock,
            ],
        )


class CEGeneralMessageBody(MessageBody):
    """CE message general body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize CE message general body."""
        super().__init__(body)
        self.power = (body[1] & 0x80) > 0
        self.child_lock = (body[1] & 0x20) > 0
        self.scheduled = (body[1] & 0x40) > 0
        self.fan_speed = body[2]
        self.pm25 = (body[3] << 8) + body[4]
        self.co2 = (body[5] << 8) + body[6]
        self.current_humidity: float | None = None
        self.current_temperature: float | None = None
        self.hcho: float | None = None
        self.aux_heating: bool | None = None

        if body[7] != MAX_BYTE_VALUE:
            self.current_humidity = (body[7] << 8) + body[8] / 10
        if body[9] != MAX_BYTE_VALUE:
            self.current_temperature = (body[9] << 8) + (body[10] - 60) / 2
        if body[11] != MAX_BYTE_VALUE:
            self.hcho = (body[11] << 8) + body[12] / 1000
        self.link_to_ac = (body[17] & 0x01) > 0
        self.sleep_mode = (body[17] & 0x02) > 0
        self.eco_mode = (body[17] & 0x04) > 0
        if (body[19] & 0x02) > 0:
            self.aux_heating = (body[17] & 0x08) > 0
        self.powerful_purify = (body[17] & 0x10) > 0
        self.filter_cleaning_reminder = (body[18] & 0x01) > 0
        self.filter_change_reminder = (body[18] & 0x02) > 0
        self.error_code = body[24]


class CENotifyMessageBody(MessageBody):
    """CE message notify body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize CE message notify body."""
        super().__init__(body)
        self.current_humidity: float | None = None
        self.current_temperature: float | None = None
        self.hcho: float | None = None

        self.pm25 = (body[1] << 8) + body[2]
        self.co2 = (body[3] << 8) + body[4]
        if body[5] != MAX_BYTE_VALUE:
            self.current_humidity = (body[5] << 8) + body[6] / 10
        if body[7] != MAX_BYTE_VALUE:
            self.current_temperature = (body[7] << 8) + (body[8] - 60) / 2
        if body[9] != MAX_BYTE_VALUE:
            self.hcho = (body[9] << 8) + body[10] / 1000
        self.error_code = body[12]


class CECompactStatusMessageBody(MessageBody):
    """CE compact status body used by the 171120H4 Lua protocol family."""

    def __init__(self, body: bytearray) -> None:
        """Initialize CE compact status body."""
        super().__init__(body)
        flags = body[1]
        self.power = (flags & CE_POWER_FLAG) > 0
        self.auto_set = (flags & CE_AUTO_SET_FLAG) > 0
        self.silent_mode = (flags & CE_SILENT_MODE_FLAG) > 0
        self.mode_raw = body[2]
        self.mode = CE_COMPACT_MODES.get(self.mode_raw)
        self.silence_level_raw = body[3]
        self.silence_level = CE_SILENCE_LEVELS.get(self.silence_level_raw)
        self.target_temperature = body[4]
        self.current_temperature = int.from_bytes(body[5:6], signed=True)
        self.error_code = body[6]
        self.automatic_run_mode = body[7]


class CETimerMessageBody(MessageBody):
    """CE timer body base."""

    def _set_timers(
        self,
        body: bytearray,
        *,
        prefix: str,
        enabled_offset: int,
        first_timer_offset: int,
    ) -> None:
        """Decode the five timer slots shared by daily and weekly replies."""
        enabled_flags = body[enabled_offset]
        for timer_index in range(CE_TIMER_COUNT):
            timer_number = timer_index + 1
            field_offset = first_timer_offset + timer_index * CE_TIMER_FIELD_LENGTH
            attribute_prefix = f"{prefix}_timer_{timer_number}"
            setattr(
                self,
                f"{attribute_prefix}_enabled",
                (enabled_flags & (1 << timer_index)) > 0,
            )
            setattr(self, f"{attribute_prefix}_temperature", body[field_offset])
            setattr(self, f"{attribute_prefix}_start_hour", body[field_offset + 1])
            setattr(self, f"{attribute_prefix}_start_minute", body[field_offset + 2])
            setattr(self, f"{attribute_prefix}_end_hour", body[field_offset + 3])
            setattr(self, f"{attribute_prefix}_end_minute", body[field_offset + 4])


class CEDailyTimerMessageBody(CETimerMessageBody):
    """CE daily timer body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize CE daily timer body."""
        super().__init__(body)
        self._set_timers(
            body,
            prefix="daily",
            enabled_offset=1,
            first_timer_offset=2,
        )


class CEWeeklyTimerMessageBody(CETimerMessageBody):
    """CE weekly timer body for one queried weekday."""

    def __init__(self, body: bytearray) -> None:
        """Initialize CE weekly timer body."""
        super().__init__(body)
        # X03 returns one weekday per frame. Keep the weekday beside the common
        # timer fields so every process-message debug entry is self-describing.
        # The device intentionally exposes the most recently received weekday;
        # a future writable schedule API can aggregate all seven replies once the
        # vendor weekday semantics and live-device behaviour are validated.
        weekday_flags = body[1]
        self.weekly_timer_weekday = next(
            (
                weekday
                for weekday in range(CE_MIN_WEEKDAY, CE_MAX_WEEKDAY + 1)
                if weekday_flags & (1 << (weekday - 1))
            ),
            None,
        )
        self._set_timers(
            body,
            prefix="weekly",
            enabled_offset=2,
            first_timer_offset=3,
        )


class MessageCEResponse(MessageResponse):
    """CE message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize CE message response."""
        super().__init__(bytearray(message))
        body = super().body
        self.compact_protocol: bool | None = None
        self.is_generic_status = False
        self.is_compact_status = False

        # CE is a device category, not one wire protocol. The established air-quality
        # layout and the compact ventilation layout even share X01 and the same frame
        # types, so model/subtype metadata is neither necessary nor always available.
        # The exact eight-byte body is the only confirmed discriminator in the
        # captured protocol: legacy query/set status needs at least 25 bytes and its
        # X01 notification needs at least 13. Keep the compact match exact and guard
        # every legacy parser by its minimum length. A future CE variant with another
        # layout should add a separate structural/length branch here; unknown short
        # layouts must remain unparsed instead of falling through to a known decoder.
        if self.body_type == ListTypes.X01 and self.message_type in {
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        }:
            if len(body) == CE_COMPACT_STATUS_BODY_LENGTH:
                self.set_body(CECompactStatusMessageBody(body))
                self.compact_protocol = True
                self.is_compact_status = True
            elif (
                self.message_type in {MessageType.query, MessageType.set}
                and len(body) >= CE_GENERAL_STATUS_BODY_MIN_LENGTH
            ):
                self.set_body(CEGeneralMessageBody(body))
                self.compact_protocol = False
                self.is_generic_status = True
            elif (
                self.message_type == MessageType.notify1
                and len(body) >= CE_NOTIFY_STATUS_BODY_MIN_LENGTH
            ):
                self.set_body(CENotifyMessageBody(body))
                self.compact_protocol = False
                self.is_generic_status = True
        elif (
            self.message_type == MessageType.notify1
            and self.body_type == ListTypes.X02
            and len(body) >= CE_GENERAL_STATUS_BODY_MIN_LENGTH
        ):
            self.set_body(CEGeneralMessageBody(body))
            self.compact_protocol = False
            self.is_generic_status = True
        elif (
            self.message_type in {MessageType.query, MessageType.set}
            and self.body_type == ListTypes.X02
            and len(body) == CE_DAILY_TIMER_BODY_LENGTH
        ):
            self.set_body(CEDailyTimerMessageBody(body))
            self.compact_protocol = True
        elif (
            self.message_type in {MessageType.query, MessageType.set}
            and self.body_type == ListTypes.X03
            and len(body) == CE_WEEKLY_TIMER_BODY_LENGTH
        ):
            self.set_body(CEWeeklyTimerMessageBody(body))
            self.compact_protocol = True
        self.set_attr()

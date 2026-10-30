"""Midea lan EA message."""

from enum import IntEnum

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
    ToshibaFrame,
)

TOSHIBA_EA_BASE_BODY_TYPE = 0x00
TOSHIBA_EA_BASE_STATUS_LENGTH = 25
TOSHIBA_EA_LEGACY_QUERY_FRAME_TYPE = 0x0003
TOSHIBA_EA_QUERY_FRAME_TYPE = 0x8003
TOSHIBA_EA_NOTIFY_FRAME_TYPE = 0x0004
TOSHIBA_EA_BASE_FRAME_TYPES = frozenset(
    (
        TOSHIBA_EA_LEGACY_QUERY_FRAME_TYPE,
        TOSHIBA_EA_QUERY_FRAME_TYPE,
        TOSHIBA_EA_NOTIFY_FRAME_TYPE,
    ),
)
TOSHIBA_EA_COURSE_OFFSET = 16
TOSHIBA_EA_REMAINING_MINUTES_OFFSET = 21
TOSHIBA_EA_REMAINING_HOURS_OFFSET = 22
TOSHIBA_EA_COOKING_STATE_OFFSET = 23
TOSHIBA_EA_COOKING_STATE = 0x0A
TOSHIBA_EA_KEEP_WARM_STATE = 0x07
MINUTES_PER_HOUR = 60

TOSHIBA_EA_PROGRESS = {
    0x01: "stop",
    0x02: "error",
    0x03: "reserved",
    0x04: "soak",
    0x05: "rice_cooking",
    0x06: "steam",
    0x07: "keep_warm",
    0x08: "heat_cleaning",
    0x0A: "cooking",
}

ToshibaEAStatus = dict[str, bool | int | str]


def _decode_bcd(value: int) -> int:
    """Decode a packed-decimal Toshiba time field."""
    return value - (value // 0x10) * 6


def decode_toshiba_ea_status(frame: ToshibaFrame) -> ToshibaEAStatus | None:
    """Decode a complete Toshiba EA rice-cooker base status."""
    body = frame.body
    if (
        frame.frame_type not in TOSHIBA_EA_BASE_FRAME_TYPES
        or len(body) < TOSHIBA_EA_BASE_STATUS_LENGTH
        or body[0] != TOSHIBA_EA_BASE_BODY_TYPE
    ):
        return None

    cooking_state = body[TOSHIBA_EA_COOKING_STATE_OFFSET]
    remaining_hours = _decode_bcd(body[TOSHIBA_EA_REMAINING_HOURS_OFFSET])
    remaining_minutes = _decode_bcd(body[TOSHIBA_EA_REMAINING_MINUTES_OFFSET])
    return {
        "cooking": cooking_state == TOSHIBA_EA_COOKING_STATE,
        "keep_warm": cooking_state == TOSHIBA_EA_KEEP_WARM_STATE,
        "mode": body[TOSHIBA_EA_COURSE_OFFSET],
        "time_remaining": remaining_hours * MINUTES_PER_HOUR + remaining_minutes,
        "progress": TOSHIBA_EA_PROGRESS.get(cooking_state, "stop"),
    }


class Progress(IntEnum):
    """Progress."""

    COOKING = 2
    KEEP_WARM = 3


class MessageEABase(MessageRequest):
    """EA message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes = ListTypes.X00,
    ) -> None:
        """Initialize EA message base."""
        super().__init__(
            device_type=DeviceType.EA,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageEABase):
    """EA message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize EA message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
        )

    @property
    def body(self) -> bytearray:
        """EA message query body."""
        return bytearray([0xAA, 0x55, 0x01, 0x03, 0x00])

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class EABody1(MessageBody):
    """EA message body 1."""

    def __init__(self, body: bytearray) -> None:
        """Initialize EA message body 1."""
        super().__init__(body)
        self.mode = body[6] + (body[7] << 8)
        self.progress = body[14]
        self.cooking = self.progress == Progress.COOKING
        self.keep_warm = self.progress == Progress.KEEP_WARM
        self.top_temperature = body[18]
        self.bottom_temperature = body[19]
        self.time_remaining = body[22] * 60 + body[23]
        self.keep_warm_time = body[26] * 60 + body[27]


class EABody2(MessageBody):
    """EA message body 2."""

    def __init__(self, body: bytearray) -> None:
        """Initialize EA message body 2."""
        super().__init__(body)
        self.progress = body[9]
        self.cooking = self.progress == Progress.COOKING
        self.keep_warm = self.progress == Progress.KEEP_WARM
        self.mode = body[58] + (body[59] << 8)
        self.time_remaining = body[50] * 60 + body[51]
        self.keep_warm_time = body[54] * 60 + body[55]
        self.top_temperature = body[21]
        self.bottom_temperature = body[20]


class EABody3(MessageBody):
    """EA message body 3."""

    def __init__(self, body: bytearray) -> None:
        """Initialize EA message body 3."""
        super().__init__(body)
        self.mode = body[4] + (body[5] << 8)
        self.progress = body[8]
        self.cooking = self.progress == Progress.COOKING
        self.keep_warm = self.progress == Progress.KEEP_WARM
        self.time_remaining = body[12] * 60 + body[13]
        self.top_temperature = body[20]
        self.bottom_temperature = body[21]
        self.keep_warm_time = body[22] * 60 + body[23]


class EABodyNew(MessageBody):
    """EA message body new."""

    def __init__(self, body: bytearray) -> None:
        """Initialize EA message body new."""
        super().__init__(body)
        if body[6] in [2, 4, 6, 8, 10, 0x62]:
            self.mode = body[7] + (body[8] << 8)
            self.progress = body[11]
            self.cooking = self.progress == Progress.COOKING
            self.keep_warm = self.progress == Progress.KEEP_WARM
            self.time_remaining = body[16] * 60 + body[17]
            self.top_temperature = body[60]
            self.bottom_temperature = body[61]
            self.keep_warm_time = body[19] * 60 + body[20]


class MessageEAResponse(MessageResponse):
    """EA message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize EA message response."""
        super().__init__(bytearray(message))
        if (
            self.message_type == MessageType.notify1
            and super().body[3] == ListTypes.X01
        ):
            self.set_body(EABodyNew(super().body))
        elif self.protocol_version == 0:
            if (
                self.message_type == MessageType.set
                and super().body[5] == ListTypes.X16
            ):  # 381
                self.set_body(EABody1(super().body))
            elif self.message_type == MessageType.query:
                if (
                    super().body[6] == ListTypes.X52 and super().body[7] == ListTypes.C3
                ):  # 404
                    self.set_body(EABody2(super().body))
                elif super().body[5] == ListTypes.X3D:  # 420
                    self.set_body(EABody1(super().body))
            elif (
                self.message_type == MessageType.notify1
                and super().body[5] == ListTypes.X3D
            ):  # 463
                self.set_body(EABody1(super().body))
        elif (
            (self.message_type == MessageType.set and super().body[3] == ListTypes.X02)
            or (
                self.message_type == MessageType.query
                and super().body[3] == ListTypes.X03
            )
            or (
                self.message_type == MessageType.notify1
                and super().body[3] == ListTypes.X04
            )
        ):  # 351
            self.set_body(EABody3(super().body))
        elif (
            self.message_type == MessageType.notify1
            and super().body[3] == ListTypes.X06
        ):
            self.mode = super().body[4] + (super().body[5] << 8)
        self.set_attr()

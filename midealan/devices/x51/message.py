"""Toshiba 0x51 device messages."""

from midealan.const import DeviceType
from midealan.message import MessageType, ToshibaFrame, ToshibaMessageRequest

TOSHIBA_X51_FUNCTION_BASE = 0x00
TOSHIBA_X51_FUNCTION_PHOTO = 0x01
TOSHIBA_X51_FUNCTION_PHOTO_MODE = 0x02
TOSHIBA_X51_FUNCTION_ERROR = 0xFE
TOSHIBA_X51_BASE_STATUS_LENGTH = 12
TOSHIBA_X51_PHOTO_MODE_BASE_LENGTH = 3
TOSHIBA_X51_PHOTO_MODE_STATUS_LENGTH = 7
TOSHIBA_X51_ERROR_STATUS_LENGTH = 3
TOSHIBA_X51_STATUS_FRAME_TYPES = frozenset(
    (MessageType.set, MessageType.query, MessageType.notify1),
)

TOSHIBA_X51_TIME_MINUTE_OFFSET = 1
TOSHIBA_X51_TIME_HOUR_OFFSET = 2
TOSHIBA_X51_TIME_DAY_OFFSET = 3
TOSHIBA_X51_TIME_MONTH_OFFSET = 4
TOSHIBA_X51_TIME_YEAR_OFFSET = 5
TOSHIBA_X51_TEMPERATURE_OFFSET = 7
TOSHIBA_X51_LIGHT_OFFSET = 9
TOSHIBA_X51_BATTERY_OFFSET = 11
TOSHIBA_X51_SHOOT_OFFSET = 1
TOSHIBA_X51_MODE_OFFSET = 2
TOSHIBA_X51_FIRST_SCHEDULE_HOUR_OFFSET = 3
TOSHIBA_X51_FIRST_SCHEDULE_MINUTE_OFFSET = 4
TOSHIBA_X51_SECOND_SCHEDULE_HOUR_OFFSET = 5
TOSHIBA_X51_SECOND_SCHEDULE_MINUTE_OFFSET = 6
TOSHIBA_X51_ERROR_CODE_OFFSET = 1
TOSHIBA_X51_DOUBLE_BYTE_WIDTH = 2

TOSHIBA_X51_SHOOT_MASK = 0x01
TOSHIBA_X51_PERIODICAL_MODE_MASK = 0x01
TOSHIBA_X51_REQUEST_MODE_MASK = 0x02
TOSHIBA_X51_AUTO_MODE_MASK = 0x04
TOSHIBA_X51_DIRECT_MODE_MASK = 0x08

TOSHIBA_X51_BATTERY_STATUS = {
    0x01: "normal",
    0x02: "low",
    0x04: "replace",
    0x08: "high",
    0x10: "high_exception",
    0x20: "low_exception",
}

ToshibaX51Status = dict[str, bool | int | str]


def decode_toshiba_x51_status(frame: ToshibaFrame) -> ToshibaX51Status | None:
    """Decode a documented Toshiba 0x51 function group."""
    body = frame.body
    if not body:
        return None

    function_type = body[0]
    status: ToshibaX51Status | None = None
    if frame.frame_type in TOSHIBA_X51_STATUS_FRAME_TYPES:
        if function_type == TOSHIBA_X51_FUNCTION_BASE:
            if len(body) < TOSHIBA_X51_BASE_STATUS_LENGTH:
                return None
            status = {
                "time_minute": body[TOSHIBA_X51_TIME_MINUTE_OFFSET],
                "time_hour": body[TOSHIBA_X51_TIME_HOUR_OFFSET],
                "time_day": body[TOSHIBA_X51_TIME_DAY_OFFSET],
                "time_month": body[TOSHIBA_X51_TIME_MONTH_OFFSET],
                "time_year": int.from_bytes(
                    body[
                        TOSHIBA_X51_TIME_YEAR_OFFSET : TOSHIBA_X51_TIME_YEAR_OFFSET
                        + TOSHIBA_X51_DOUBLE_BYTE_WIDTH
                    ],
                    "little",
                ),
                "temperature": int.from_bytes(
                    body[
                        TOSHIBA_X51_TEMPERATURE_OFFSET : TOSHIBA_X51_TEMPERATURE_OFFSET
                        + TOSHIBA_X51_DOUBLE_BYTE_WIDTH
                    ],
                    "little",
                ),
                "light": int.from_bytes(
                    body[
                        TOSHIBA_X51_LIGHT_OFFSET : TOSHIBA_X51_LIGHT_OFFSET
                        + TOSHIBA_X51_DOUBLE_BYTE_WIDTH
                    ],
                    "little",
                ),
                "battery_status": TOSHIBA_X51_BATTERY_STATUS.get(
                    body[TOSHIBA_X51_BATTERY_OFFSET],
                    body[TOSHIBA_X51_BATTERY_OFFSET],
                ),
            }
        if function_type == TOSHIBA_X51_FUNCTION_PHOTO:
            status = {}
        if function_type == TOSHIBA_X51_FUNCTION_PHOTO_MODE:
            minimum_length = (
                TOSHIBA_X51_PHOTO_MODE_BASE_LENGTH
                if frame.frame_type == MessageType.notify1
                else TOSHIBA_X51_PHOTO_MODE_STATUS_LENGTH
            )
            if len(body) < minimum_length:
                return None
            mode = body[TOSHIBA_X51_MODE_OFFSET]
            status = {
                "shoot": bool(
                    body[TOSHIBA_X51_SHOOT_OFFSET] & TOSHIBA_X51_SHOOT_MASK,
                ),
                "mode": mode,
                "periodical_mode": bool(mode & TOSHIBA_X51_PERIODICAL_MODE_MASK),
                "request_mode": bool(mode & TOSHIBA_X51_REQUEST_MODE_MASK),
                "auto_mode": bool(mode & TOSHIBA_X51_AUTO_MODE_MASK),
                "direct_mode": bool(mode & TOSHIBA_X51_DIRECT_MODE_MASK),
            }
            if len(body) >= TOSHIBA_X51_PHOTO_MODE_STATUS_LENGTH:
                status.update(
                    {
                        "first_schedule_hour": body[
                            TOSHIBA_X51_FIRST_SCHEDULE_HOUR_OFFSET
                        ],
                        "first_schedule_minute": body[
                            TOSHIBA_X51_FIRST_SCHEDULE_MINUTE_OFFSET
                        ],
                        "second_schedule_hour": body[
                            TOSHIBA_X51_SECOND_SCHEDULE_HOUR_OFFSET
                        ],
                        "second_schedule_minute": body[
                            TOSHIBA_X51_SECOND_SCHEDULE_MINUTE_OFFSET
                        ],
                    },
                )
        if status is not None:
            return status

    if (
        frame.frame_type in (MessageType.notify1, MessageType.exception)
        and function_type == TOSHIBA_X51_FUNCTION_ERROR
        and len(body) >= TOSHIBA_X51_ERROR_STATUS_LENGTH
    ):
        return {
            "error_code": int.from_bytes(
                body[
                    TOSHIBA_X51_ERROR_CODE_OFFSET : TOSHIBA_X51_ERROR_CODE_OFFSET
                    + TOSHIBA_X51_DOUBLE_BYTE_WIDTH
                ],
                "little",
            ),
        }
    return None


class MessageQueryBase(ToshibaMessageRequest):
    """Toshiba 0x51 base clock and sensor query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x00."""
        super().__init__(
            DeviceType.X51,
            protocol_version,
            bytes((TOSHIBA_X51_FUNCTION_BASE,)),
        )


class MessageQueryPhoto(ToshibaMessageRequest):
    """Toshiba 0x51 photo function query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x01."""
        super().__init__(
            DeviceType.X51,
            protocol_version,
            bytes((TOSHIBA_X51_FUNCTION_PHOTO,)),
        )


class MessageQueryPhotoMode(ToshibaMessageRequest):
    """Toshiba 0x51 photo-mode and schedule query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x02."""
        super().__init__(
            DeviceType.X51,
            protocol_version,
            bytes((TOSHIBA_X51_FUNCTION_PHOTO_MODE,)),
        )

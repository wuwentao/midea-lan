"""Shared Toshiba device-family decoders."""

from dataclasses import dataclass

TOSHIBA_WASHER_BASE_STATUS_LENGTH = 47
TOSHIBA_WASHER_BODY_TYPE_OFFSET = 0
TOSHIBA_WASHER_BASE_BODY_TYPE = 0x00
TOSHIBA_WASH_TIME_OFFSET = 9
TOSHIBA_DEHYDRATION_TIME_OFFSET = 11
TOSHIBA_MACHINE_STATUS_OFFSET = 22
TOSHIBA_REMAINING_TIME_START = 23
TOSHIBA_REMAINING_TIME_END = 27
TOSHIBA_WASH_HOUR_MIN = 0x81
TOSHIBA_WASH_HOUR_MAX = 0x8C
TOSHIBA_WASH_HOUR_BASE = 0x80
TOSHIBA_WASHER_STATUS_RUNNING = 2


@dataclass(frozen=True, slots=True)
class ToshibaWasherStatus:
    """Fields shared by Toshiba top-load and front-load washer statuses."""

    machine_status: int
    wash_time: int
    dehydration_time: int
    time_remaining: int


def decode_toshiba_washer_status(body: bytes) -> ToshibaWasherStatus | None:
    """Decode the common fields in a Toshiba washer status body."""
    if (
        len(body) < TOSHIBA_WASHER_BASE_STATUS_LENGTH
        or body[TOSHIBA_WASHER_BODY_TYPE_OFFSET] != TOSHIBA_WASHER_BASE_BODY_TYPE
    ):
        return None
    wash_time = body[TOSHIBA_WASH_TIME_OFFSET]
    if TOSHIBA_WASH_HOUR_MIN <= wash_time <= TOSHIBA_WASH_HOUR_MAX:
        wash_time = (wash_time - TOSHIBA_WASH_HOUR_BASE) * 60
    return ToshibaWasherStatus(
        machine_status=body[TOSHIBA_MACHINE_STATUS_OFFSET],
        wash_time=wash_time,
        dehydration_time=body[TOSHIBA_DEHYDRATION_TIME_OFFSET],
        time_remaining=int.from_bytes(
            body[TOSHIBA_REMAINING_TIME_START:TOSHIBA_REMAINING_TIME_END],
            "little",
        ),
    )

"""Shared Toshiba device-family decoders."""

from dataclasses import dataclass

TOSHIBA_WASHER_BASE_STATUS_LENGTH = 47
TOSHIBA_WASH_HOUR_MIN = 0x81
TOSHIBA_WASH_HOUR_MAX = 0x8C
TOSHIBA_WASH_HOUR_BASE = 0x80
TOSHIBA_WASHER_STATUS_RUNNING = 2


@dataclass(frozen=True, slots=True)
class ToshibaWasherStatus:
    """Fields shared by Toshiba top-load and front-load washer statuses."""

    machine_status: int
    progress: str
    wash_time: int
    dehydration_time: int
    time_remaining: int


def decode_toshiba_washer_status(body: bytes) -> ToshibaWasherStatus | None:
    """Decode the common fields in a Toshiba washer status body."""
    if len(body) < TOSHIBA_WASHER_BASE_STATUS_LENGTH or body[0] != 0x00:
        return None
    progress = "idle"
    for mask, value in (
        (0x02, "wash"),
        (0x04, "rinse"),
        (0x08, "spin"),
        (0x10, "dry"),
        (0x20, "soft_keep"),
    ):
        if body[18] & mask:
            progress = value
            break
    wash_time = body[9]
    if TOSHIBA_WASH_HOUR_MIN <= wash_time <= TOSHIBA_WASH_HOUR_MAX:
        wash_time = (wash_time - TOSHIBA_WASH_HOUR_BASE) * 60
    return ToshibaWasherStatus(
        machine_status=body[22],
        progress=progress,
        wash_time=wash_time,
        dehydration_time=body[11],
        time_remaining=int.from_bytes(body[23:27], "little"),
    )

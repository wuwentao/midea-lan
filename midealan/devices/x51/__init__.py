"""Toshiba 0x51 device."""

from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDeviceInitKwargs, ToshibaDevice
from midealan.message import MessageRequest, MessageType, ToshibaFrame

from .message import MessageQueryBase, MessageQueryReserved, MessageQuerySchedule

FUNCTION_BASE = 0x00
FUNCTION_RESERVED = 0x01
FUNCTION_SCHEDULE = 0x02
FUNCTION_ERROR = 0xFE
BASE_STATUS_LENGTH = 12
SCHEDULE_BASE_STATUS_LENGTH = 3
SCHEDULE_STATUS_LENGTH = 7
ERROR_STATUS_LENGTH = 3
TOSHIBA_STATUS_FRAME_TYPES = frozenset(
    (MessageType.set, MessageType.query, MessageType.notify1),
)
TOSHIBA_BATTERY_STATUS = {
    0x01: "normal",
    0x02: "low",
    0x04: "replace",
    0x08: "high",
    0x10: "high_exception",
    0x20: "low_exception",
}


class DeviceAttributes(StrEnum):
    """Toshiba 0x51 device attributes."""

    time_minute = "time_minute"
    time_hour = "time_hour"
    time_day = "time_day"
    time_month = "time_month"
    time_year = "time_year"
    temperature = "temperature"
    light = "light"
    battery_status = "battery_status"
    shoot = "shoot"
    mode = "mode"
    periodical_mode = "periodical_mode"
    request_mode = "request_mode"
    auto_mode = "auto_mode"
    direct_mode = "direct_mode"
    first_schedule_hour = "first_schedule_hour"
    first_schedule_minute = "first_schedule_minute"
    second_schedule_hour = "second_schedule_hour"
    second_schedule_minute = "second_schedule_minute"
    error_code = "error_code"


class MideaX51Device(ToshibaDevice):
    """Toshiba 0x51 device."""

    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        (*TOSHIBA_STATUS_FRAME_TYPES, MessageType.exception),
    )

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize the Toshiba 0x51 device."""
        super().__init__(
            device_type=DeviceType.X51,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )
        self._toshiba_protocol = True

    def build_toshiba_query(self) -> list[MessageRequest]:
        """Query every documented 0x51 function group."""
        return [
            MessageQueryBase(self._message_protocol_version),
            MessageQueryReserved(self._message_protocol_version),
            MessageQuerySchedule(self._message_protocol_version),
        ]

    def build_query(self) -> list[MessageRequest]:
        """Build the only documented 0x51 query family."""
        return self.build_toshiba_query()

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Process a Toshiba 0x51 message."""
        return self.process_toshiba_message(msg) or {}

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode a documented 0x51 function group."""
        body = frame.body
        if not body:
            return None
        values: dict[DeviceAttributes, Any]
        if (
            frame.frame_type in TOSHIBA_STATUS_FRAME_TYPES
            and body[0] == FUNCTION_BASE
            and len(body) >= BASE_STATUS_LENGTH
        ):
            values = {
                DeviceAttributes.time_minute: body[1],
                DeviceAttributes.time_hour: body[2],
                DeviceAttributes.time_day: body[3],
                DeviceAttributes.time_month: body[4],
                DeviceAttributes.time_year: int.from_bytes(body[5:7], "little"),
                DeviceAttributes.temperature: int.from_bytes(body[7:9], "little"),
                DeviceAttributes.light: int.from_bytes(body[9:11], "little"),
                DeviceAttributes.battery_status: TOSHIBA_BATTERY_STATUS.get(
                    body[11],
                    body[11],
                ),
            }
        elif (
            frame.frame_type in TOSHIBA_STATUS_FRAME_TYPES
            and body[0] == FUNCTION_RESERVED
        ):
            values = {}
        elif (
            frame.frame_type in TOSHIBA_STATUS_FRAME_TYPES
            and body[0] == FUNCTION_SCHEDULE
            and (
                (
                    frame.frame_type in (MessageType.set, MessageType.query)
                    and len(body) >= SCHEDULE_STATUS_LENGTH
                )
                or (
                    frame.frame_type == MessageType.notify1
                    and len(body) >= SCHEDULE_BASE_STATUS_LENGTH
                )
            )
        ):
            mode = body[2]
            values = {
                DeviceAttributes.shoot: bool(body[1] & 0x01),
                DeviceAttributes.mode: mode,
                DeviceAttributes.periodical_mode: bool(mode & 0x01),
                DeviceAttributes.request_mode: bool(mode & 0x02),
                DeviceAttributes.auto_mode: bool(mode & 0x04),
                DeviceAttributes.direct_mode: bool(mode & 0x08),
            }
            if len(body) >= SCHEDULE_STATUS_LENGTH:
                values.update(
                    {
                        DeviceAttributes.first_schedule_hour: body[3],
                        DeviceAttributes.first_schedule_minute: body[4],
                        DeviceAttributes.second_schedule_hour: body[5],
                        DeviceAttributes.second_schedule_minute: body[6],
                    },
                )
        elif (
            frame.frame_type in (MessageType.notify1, MessageType.exception)
            and body[0] == FUNCTION_ERROR
            and len(body) >= ERROR_STATUS_LENGTH
        ):
            values = {
                DeviceAttributes.error_code: int.from_bytes(body[1:3], "little"),
            }
        else:
            return None
        self._attributes.update(values)
        return {str(attr): value for attr, value in values.items()}

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Reject writes until captured traffic verifies the command profiles."""
        del attr, value
        self.reject_toshiba_write()


class MideaAppliance(MideaX51Device):
    """Toshiba 0x51 appliance."""

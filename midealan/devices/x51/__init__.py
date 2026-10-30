"""Midea lan 0x51 device."""

from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.message import MessageRequest, MessageType, ToshibaFrame

from .message import (
    TOSHIBA_X51_STATUS_FRAME_TYPES,
    MessageQueryBase,
    MessageQueryPhoto,
    MessageQueryPhotoMode,
    decode_toshiba_x51_status,
)


class DeviceAttributes(StrEnum):
    """Midea 0x51 device attributes."""

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


class MideaX51Device(MideaDevice):
    """Midea 0x51 device."""

    TOSHIBA_SUPPORTED = True
    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        (*TOSHIBA_X51_STATUS_FRAME_TYPES, MessageType.exception),
    )

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize the Midea 0x51 device."""
        super().__init__(
            device_type=DeviceType.X51,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )

    def build_toshiba_query(self) -> list[MessageRequest]:
        """Query every documented Toshiba 0x51 function group."""
        return [
            MessageQueryBase(self._message_protocol_version),
            MessageQueryPhoto(self._message_protocol_version),
            MessageQueryPhotoMode(self._message_protocol_version),
        ]

    def build_query(self) -> list[MessageRequest]:
        """Build the documented 0x51 query family after Toshiba selection."""
        if self.toshiba_protocol:
            return self.build_toshiba_query()
        return []

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Process a Toshiba 0x51 message."""
        return self.process_toshiba_message(msg) or {}

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode and publish a Toshiba 0x51 function group."""
        status = decode_toshiba_x51_status(frame)
        if status is None:
            return None
        self._attributes.update(status)
        return dict(status)

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Reject writes until captured traffic verifies the command profiles."""
        del attr, value
        self.reject_toshiba_write()


class MideaAppliance(MideaX51Device):
    """Midea 0x51 appliance."""

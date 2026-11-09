"""Midea lan x14 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    DIRECTION_CODES,
    POSITION_MAX,
    POSITION_MIN,
    STATUS_CODES,
    Message14Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea x14 device attributes."""

    curtain_status = "curtain_status"
    curtain_position = "curtain_position"
    curtain_direction = "curtain_direction"
    software_version = "software_version"
    error_code = "error_code"


class Midea14Device(MideaDevice):
    """Midea x14 device (electric curtain / blind motor)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x14 device."""
        super().__init__(
            device_type=DeviceType.X14,
            **kwargs,
            attributes={
                DeviceAttributes.curtain_status: None,
                DeviceAttributes.curtain_position: None,
                DeviceAttributes.curtain_direction: None,
                DeviceAttributes.software_version: None,
                DeviceAttributes.error_code: None,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea x14 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x14 device process message."""
        message = Message14Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x14 device set attribute."""
        message = MessageSet(self._message_protocol_version)
        if attr == DeviceAttributes.curtain_status:
            if not isinstance(value, str) or value not in STATUS_CODES:
                raise ValueWrongType("[x14] curtain_status expects open/close/stop")
            message.status = STATUS_CODES[value]
        elif attr == DeviceAttributes.curtain_position:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueWrongType("[x14] curtain_position expects a number")
            position = int(value)
            if not POSITION_MIN <= position <= POSITION_MAX:
                msg = (
                    f"[x14] curtain_position must be in "
                    f"[{POSITION_MIN}, {POSITION_MAX}]"
                )
                raise ValueOutOfRange(msg)
            message.position = position
        elif attr == DeviceAttributes.curtain_direction:
            if not isinstance(value, str) or value not in DIRECTION_CODES:
                raise ValueWrongType("[x14] curtain_direction expects positive/reverse")
            message.direction = DIRECTION_CODES[value]
        else:
            # software_version / error_code are read-only.
            return
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea x14 device set customize (JSON, same style as other appliances)."""
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "refresh_interval" in params:
                    interval = params.get("refresh_interval")
                    if isinstance(interval, int | float):
                        self.set_refresh_interval(int(interval))
                    else:
                        _LOGGER.error(
                            "[%s] Invalid type for refresh_interval: %s",
                            self.device_id,
                            interval,
                        )
            except Exception:
                _LOGGER.exception("[%s] Set customize error", self.device_id)
        self.update_all({"refresh_interval": self._refresh_interval})


class MideaAppliance(Midea14Device):
    """Midea x14 appliance."""

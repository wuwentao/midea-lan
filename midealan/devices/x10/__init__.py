"""Midea lan x10 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import Message10Response, MessagePower, MessageQuery

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea x10 device attributes."""

    power = "power"


class Midea10Device(MideaDevice):
    """Midea x10 device (power-only appliance)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x10 device."""
        super().__init__(
            device_type=DeviceType.X10,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea x10 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x10 device process message."""
        message = Message10Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x10 device set attribute."""
        if attr == DeviceAttributes.power:
            if not isinstance(value, bool):
                raise ValueWrongType("[x10] power expects a bool")
            message = MessagePower(self._message_protocol_version)
            message.power = value
            self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea x10 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(Midea10Device):
    """Midea x10 appliance."""

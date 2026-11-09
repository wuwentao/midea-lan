"""Midea lan x17 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import (
    SELECTOR_ANION,
    SELECTOR_BAKING,
    SELECTOR_DRY,
    SELECTOR_LIGHT,
    SELECTOR_POWER,
    SELECTOR_STERILIZE,
    SELECTOR_UPDOWN,
    UPDOWN_CODES,
    VALUE_OFF,
    VALUE_ON,
    Message17Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

# Boolean on/off controls and the selector byte each sends (Lua byte1).
_BOOL_SELECTORS: dict[str, int] = {
    "power": SELECTOR_POWER,
    "light": SELECTOR_LIGHT,
    "sterilize": SELECTOR_STERILIZE,
    "dry": SELECTOR_DRY,
    "baking": SELECTOR_BAKING,
    "anion": SELECTOR_ANION,
}


class DeviceAttributes(StrEnum):
    """Midea x17 device attributes."""

    power = "power"
    # Rack motor: "up"/"down" drive it, "pause" stops it (Lua tri-state).
    updown = "updown"
    light = "light"
    sterilize = "sterilize"
    dry = "dry"
    baking = "baking"
    anion = "anion"
    error_code = "error_code"


class Midea17Device(MideaDevice):
    """Midea x17 device (electric ceiling clothes-drying rack)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x17 device."""
        super().__init__(
            device_type=DeviceType.X17,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.updown: "pause",
                DeviceAttributes.light: False,
                DeviceAttributes.sterilize: False,
                DeviceAttributes.dry: False,
                DeviceAttributes.baking: False,
                DeviceAttributes.anion: False,
                DeviceAttributes.error_code: 0,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea x17 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x17 device process message."""
        message = Message17Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x17 device set attribute."""
        message = MessageSet(self._message_protocol_version)
        if attr in _BOOL_SELECTORS:
            if not isinstance(value, bool):
                raise ValueWrongType(f"[x17] {attr} expects a bool")
            message.selector = _BOOL_SELECTORS[attr]
            message.value = VALUE_ON if value else VALUE_OFF
        elif attr == DeviceAttributes.updown:
            # Momentary tri-state motor control; accept only known directions.
            if not isinstance(value, str) or value not in UPDOWN_CODES:
                raise ValueWrongType("[x17] updown expects 'up', 'down' or 'pause'")
            message.selector = SELECTOR_UPDOWN
            message.value = UPDOWN_CODES[value]
        else:
            # error_code is read-only; ignore anything we don't control.
            return
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea x17 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(Midea17Device):
    """Midea x17 appliance."""

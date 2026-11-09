"""Midea lan x9a device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    FLAG_OFF,
    FLAG_ON,
    MODE_CODES,
    POWER_OFF,
    POWER_ON,
    WORK_STATUS_CODES,
    Message9aResponse,
    MessageCookSet,
    MessageQuery,
    MessageStatusSet,
)

_LOGGER = logging.getLogger(__name__)

# Target-temperature range (Lua temperature is a 16-bit big-endian value; the
# oven UI caps at 300 C).
TEMPERATURE_MIN = 0
TEMPERATURE_MAX = 300
# Cook time component ranges.
HOUR_MIN = 0
HOUR_MAX = 23
MINUTE_MIN = 0
MINUTE_MAX = 59
SECOND_MIN = 0
SECOND_MAX = 59
# Microwave power (Lua watt) and food weight (grams) are passed through as-is.
WATT_MIN = 0
WATT_MAX = 0xFF
WEIGHT_MIN = 0
WEIGHT_MAX = 2550  # 0xFF * 10 g (weight is sent in units of 10 g)


class DeviceAttributes(StrEnum):
    """Midea x9a device attributes."""

    power = "power"
    work_status = "work_status"
    mode = "mode"
    hour = "hour"
    minutes = "minutes"
    second = "second"
    temperature = "temperature"
    current_temperature = "current_temperature"
    lock = "lock"
    furnace_light = "furnace_light"
    watt = "watt"
    weight = "weight"
    error_code = "error_code"


# Attributes carried by the FORM_STATUS control (power / lock / light).
_STATUS_ATTRS = frozenset(
    {
        DeviceAttributes.power,
        DeviceAttributes.work_status,
        DeviceAttributes.lock,
        DeviceAttributes.furnace_light,
    },
)
# Attributes carried by the FORM_COOK control (mode / time / temperature).
_COOK_ATTRS = frozenset(
    {
        DeviceAttributes.mode,
        DeviceAttributes.hour,
        DeviceAttributes.minutes,
        DeviceAttributes.second,
        DeviceAttributes.temperature,
        DeviceAttributes.watt,
        DeviceAttributes.weight,
    },
)
# Numeric cook params and their accepted inclusive ranges.
_COOK_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.hour: (HOUR_MIN, HOUR_MAX),
    DeviceAttributes.minutes: (MINUTE_MIN, MINUTE_MAX),
    DeviceAttributes.second: (SECOND_MIN, SECOND_MAX),
    DeviceAttributes.temperature: (TEMPERATURE_MIN, TEMPERATURE_MAX),
    DeviceAttributes.watt: (WATT_MIN, WATT_MAX),
    DeviceAttributes.weight: (WEIGHT_MIN, WEIGHT_MAX),
}


class Midea9aDevice(MideaDevice):
    """Midea x9a device (microwave / steam-bake oven)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x9a device."""
        super().__init__(
            device_type=DeviceType.X9A,
            **kwargs,
            attributes={
                DeviceAttributes.power: None,
                DeviceAttributes.work_status: None,
                DeviceAttributes.mode: None,
                DeviceAttributes.hour: None,
                DeviceAttributes.minutes: None,
                DeviceAttributes.second: None,
                DeviceAttributes.temperature: None,
                DeviceAttributes.current_temperature: None,
                DeviceAttributes.lock: None,
                DeviceAttributes.furnace_light: None,
                DeviceAttributes.watt: None,
                DeviceAttributes.weight: None,
                DeviceAttributes.error_code: None,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea x9a device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x9a device process message."""
        message = Message9aResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def _make_status_set(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageStatusSet:
        """Build a FORM_STATUS control for power / lock / furnace_light."""
        message = MessageStatusSet(self._message_protocol_version)
        if attr == DeviceAttributes.power:
            message.work_status = POWER_ON if value else POWER_OFF
        elif attr == DeviceAttributes.work_status:
            if not isinstance(value, str) or value not in WORK_STATUS_CODES:
                msg = "[x9a] work_status expects cancel/work/pause"
                raise ValueWrongType(msg)
            message.work_status = WORK_STATUS_CODES[value]
        elif attr == DeviceAttributes.lock:
            message.lock = FLAG_ON if value else FLAG_OFF
        else:  # DeviceAttributes.furnace_light
            message.furnace_light = FLAG_ON if value else FLAG_OFF
        return message

    def _make_cook_set(self, attr: str, value: bool | float | str) -> MessageCookSet:
        """Build a FORM_COOK control for mode / time / temperature.

        The cook record is a single frame, so the other cook fields are seeded
        from the current device state and only ``attr`` is overridden.
        """
        message = MessageCookSet(self._message_protocol_version)
        # Seed from current state so a single-field change keeps the rest.
        mode_name = self._attributes[DeviceAttributes.mode]
        if isinstance(mode_name, str) and mode_name in MODE_CODES:
            message.mode = MODE_CODES[mode_name]
        for key in (
            DeviceAttributes.hour,
            DeviceAttributes.minutes,
            DeviceAttributes.second,
            DeviceAttributes.temperature,
        ):
            current = self._attributes[key]
            if isinstance(current, int):
                setattr(message, str(key), current)
        for key in (DeviceAttributes.watt, DeviceAttributes.weight):
            current = self._attributes[key]
            if isinstance(current, int):
                setattr(message, str(key), current)

        if attr == DeviceAttributes.mode:
            if not isinstance(value, str) or value not in MODE_CODES:
                msg = "[x9a] mode is not a recognized oven mode"
                raise ValueWrongType(msg)
            message.mode = MODE_CODES[value]
        else:
            low, high = _COOK_RANGES[attr]
            if isinstance(value, bool) or not isinstance(value, int | float):
                msg = f"[x9a] {attr} expects a number"
                raise ValueWrongType(msg)
            number = int(value)
            if not low <= number <= high:
                msg = f"[x9a] {attr} must be in [{low}, {high}]"
                raise ValueOutOfRange(msg)
            setattr(message, str(attr), number)
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x9a device set attribute."""
        if attr in _STATUS_ATTRS:
            message: MessageStatusSet | MessageCookSet = self._make_status_set(
                attr,
                value,
            )
        elif attr in _COOK_ATTRS:
            message = self._make_cook_set(attr, value)
        else:
            # current_temperature / error_code are read-only.
            return
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea x9a device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(Midea9aDevice):
    """Midea x9a appliance."""

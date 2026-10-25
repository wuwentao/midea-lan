"""Midea lan x13 device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    MAX_FAN_SPEED,
    MIN_FAN_SPEED,
    Message13Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

#: X13 models that combine the main light with a fan (fan-light products).
#: Verified on a Light M0200008; other X13 lights keep the legacy layout
#: (light power in byte 8, four-byte set payload, no fan state).
FAN_LIGHT_MODELS = frozenset({"M0200008"})


class DeviceAttributes(StrEnum):
    """Midea x13 device attributes."""

    brightness = "brightness"
    color_temperature = "color_temperature"
    rgb_color = "rgb_color"
    effect = "effect"
    power = "power"
    fan_power = "fan_power"
    fan_speed = "fan_speed"


class Midea13Device(MideaDevice):
    """Midea x13 Device."""

    _effects: ClassVar[list[str]] = [
        "manual",
        "living",
        "reading",
        "mildly",
        "cinema",
        "night",
    ]

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x13 Device."""
        self._fan_light = kwargs["model"] in FAN_LIGHT_MODELS
        attributes: dict[DeviceAttributes, bool | int | str | None] = {
            DeviceAttributes.brightness: None,
            DeviceAttributes.color_temperature: None,
            DeviceAttributes.rgb_color: None,
            DeviceAttributes.effect: None,
            DeviceAttributes.power: False,
        }
        if self._fan_light:
            attributes[DeviceAttributes.fan_power] = False
            attributes[DeviceAttributes.fan_speed] = 0
        super().__init__(
            device_type=DeviceType.X13,
            **kwargs,
            attributes=attributes,
        )
        self._color_temp_range: list[int] = []
        self._default_color_temp_range: list[int] = [2700, 6500]
        self.set_customize(customize)

    @property
    def effects(self) -> list[str]:
        """Midea x13 Device effects."""
        return Midea13Device._effects

    @property
    def color_temp_range(self) -> list[int]:
        """Midea x13 Device color temperature range."""
        return self._color_temp_range

    def kelvin_to_midea(self, kelvin: int) -> float:
        """Midea x13 Device kelvin to midea."""
        return round(
            (kelvin - self._color_temp_range[0])
            / (self._color_temp_range[1] - self._color_temp_range[0])
            * 255,
        )

    def midea_to_kelvin(self, midea: int) -> float:
        """Midea x13 Device midea to kelvin."""
        return (
            round((self._color_temp_range[1] - self._color_temp_range[0]) / 255 * midea)
            + self._color_temp_range[0]
        )

    def build_query(self) -> list[MessageQuery]:
        """Midea x13 Device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x13 Device process message."""
        message = Message13Response(msg, self._fan_light)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        if hasattr(message, "control_success"):
            new_status = {"control_success": message.control_success}
            if message.control_success:
                self.refresh_status()
        else:
            for status in self._attributes:
                if hasattr(message, str(status)):
                    value = getattr(message, str(status))
                    if status == DeviceAttributes.effect:
                        self._attributes[status] = Midea13Device._effects[value]
                    elif status == DeviceAttributes.color_temperature:
                        self._attributes[status] = self.midea_to_kelvin(value)
                    else:
                        self._attributes[status] = value
                    new_status[str(status)] = self._attributes[status]
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x13 Device set attribute."""
        if self._fan_light and attr in (
            DeviceAttributes.fan_power,
            DeviceAttributes.fan_speed,
        ):
            self._set_fan_attribute(attr, value)
            return
        if attr in [
            DeviceAttributes.brightness,
            DeviceAttributes.color_temperature,
            DeviceAttributes.effect,
            DeviceAttributes.power,
        ]:
            message = MessageSet(self._message_protocol_version, self._fan_light)
            if attr == DeviceAttributes.effect and value in self._effects:
                setattr(message, str(attr), Midea13Device._effects.index(str(value)))
            elif attr == DeviceAttributes.color_temperature:
                setattr(message, str(attr), self.kelvin_to_midea(int(value)))
            else:
                setattr(message, str(attr), value)
            self.build_send(message)

    def _set_fan_attribute(self, attr: str, value: bool | float | str) -> None:
        """Send a fan control command to a fan-light appliance."""
        message = MessageSet(self._message_protocol_version, fan_light=True)
        if attr == DeviceAttributes.fan_power:
            if not isinstance(value, bool):
                raise ValueWrongType(f"[x13] {attr} expects a bool")
            message.fan_power = value
        else:
            message.fan_speed = self._coerce_fan_speed(attr, value)
        self.build_send(message)

    @staticmethod
    def _coerce_fan_speed(attr: str, value: bool | float | str) -> int:
        """Validate a fan speed percentage against the device's range."""
        # Reject bools and non-numbers up front; bool is an int subclass.
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueWrongType(f"[x13] {attr} expects a number")
        # Reject fractional values instead of silently truncating them.
        if isinstance(value, float) and not value.is_integer():
            raise ValueWrongType(f"[x13] {attr} must be a whole number")
        speed = int(value)
        if not MIN_FAN_SPEED <= speed <= MAX_FAN_SPEED:
            raise ValueOutOfRange(
                f"[x13] {attr} must be in [{MIN_FAN_SPEED}, {MAX_FAN_SPEED}]",
            )
        return speed

    def set_customize(self, customize: str) -> None:
        """Midea x13 Device set customize."""
        self._color_temp_range = self._default_color_temp_range
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "color_temp_range_kelvin" in params:
                    self._color_temp_range = params.get("color_temp_range_kelvin")
            except Exception:
                _LOGGER.exception("[%s] Set customize error", self.device_id)
            self.update_all({"color_temp_range": self._color_temp_range})


class MideaAppliance(Midea13Device):
    """Midea x13 appliance."""

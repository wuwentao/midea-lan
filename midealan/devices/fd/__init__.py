"""Midea lan FD device."""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs

from .message import (
    FD_LUA_25_AUTO_FAN_SPEED,
    FD_LUA_25_FAN_SPEEDS,
    FD_LUA_25_MODE_AUTO,
    FD_LUA_25_MODE_MANUAL,
    FD_LUA_25_SCREEN_DISPLAYS,
    FD_LUA_2024110101_FAN_SPEEDS,
    FD_LUA_2024110101_MODES,
    FD_LUA_2024110101_SCREEN_DISPLAYS,
    FD_LUA_PROTOCOL_25,
    FD_LUA_PROTOCOL_2024110101,
    FD_LUA_PROTOCOL_DEFAULT,
    MessageFDResponse,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

MAX_SUBTYPE_OLD_SPEEDS = 5


class DeviceAttributes(StrEnum):
    """Midea FD device attributes."""

    power = "power"
    fan_speed = "fan_speed"
    prompt_tone = "prompt_tone"
    target_humidity = "target_humidity"
    current_humidity = "current_humidity"
    current_temperature = "current_temperature"
    tank = "tank"
    mode = "mode"
    screen_display = "screen_display"
    disinfect = "disinfect"
    wet_pad_dry = "wet_pad_dry"


class MideaFDDevice(MideaDevice):
    """Midea FD device."""

    _modes: ClassVar[list[str]] = [
        "manual",
        "auto",
        "continuous",
        "living_room",
        "bed_room",
        "kitchen",
        "sleep",
    ]
    _speeds_old: ClassVar[dict[int, str]] = {
        1: "lowest",
        40: "low",
        60: "medium",
        80: "high",
        102: "auto",
        127: "off",
    }
    _speeds_new: ClassVar[dict[int, str]] = {
        1: "lowest",
        39: "low",
        59: "medium",
        80: "high",
        101: "auto",
        127: "off",
    }
    _screen_displays: ClassVar[dict[int, str]] = {0: "bright", 6: "dim", 7: "off"}
    _detect_modes: ClassVar[list[str]] = ["off", "pm_2.5", "methanal"]

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea FD device."""
        super().__init__(
            device_type=DeviceType.FD,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.fan_speed: None,
                DeviceAttributes.prompt_tone: True,
                DeviceAttributes.target_humidity: 60,
                DeviceAttributes.current_humidity: None,
                DeviceAttributes.current_temperature: None,
                DeviceAttributes.tank: 0,
                DeviceAttributes.mode: None,
                DeviceAttributes.screen_display: None,
                DeviceAttributes.disinfect: None,
                DeviceAttributes.wet_pad_dry: None,
            },
        )
        self._configure_lua_protocol(FD_LUA_PROTOCOL_DEFAULT)

    def _configure_lua_protocol(self, lua_protocol: str) -> None:
        """Configure capabilities for an FD Lua protocol."""
        self._lua_protocol = lua_protocol
        if lua_protocol == FD_LUA_PROTOCOL_25:
            self._speeds = FD_LUA_25_FAN_SPEEDS
            self._screen_display_values = FD_LUA_25_SCREEN_DISPLAYS
        elif lua_protocol == FD_LUA_PROTOCOL_2024110101:
            self._speeds = FD_LUA_2024110101_FAN_SPEEDS
            self._screen_display_values = FD_LUA_2024110101_SCREEN_DISPLAYS
        elif self.subtype > MAX_SUBTYPE_OLD_SPEEDS:
            self._speeds = MideaFDDevice._speeds_new
            self._screen_display_values = MideaFDDevice._screen_displays
        else:
            self._speeds = MideaFDDevice._speeds_old
            self._screen_display_values = MideaFDDevice._screen_displays
        self._mode_values = (
            FD_LUA_2024110101_MODES
            if lua_protocol == FD_LUA_PROTOCOL_2024110101
            else {index: mode for index, mode in enumerate(self._modes, start=1)}
        )

    @property
    def modes(self) -> list[str]:
        """Midea FD device modes."""
        return list(self._mode_values.values())

    @property
    def fan_speeds(self) -> list[str]:
        """Midea FD device fan speeds."""
        return list(self._speeds.values())

    @property
    def screen_displays(self) -> list[str]:
        """Midea FD device screen displays."""
        return list(self._screen_display_values.values())

    @property
    def detect_modes(self) -> list[str]:
        """Midea FD device detect modes."""
        return self._detect_modes

    def build_query(self) -> list[MessageQuery]:
        """Midea FD device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea FD device process message."""
        message = MessageFDResponse(msg, lua_protocol=self._lua_protocol)
        detected_protocol = getattr(message, "lua_protocol", self._lua_protocol)
        if detected_protocol != self._lua_protocol:
            _LOGGER.debug(
                "[%s] Detected FD Lua protocol: %s",
                self.device_id,
                detected_protocol,
            )
            self._configure_lua_protocol(detected_protocol)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                if status == DeviceAttributes.mode:
                    self._attributes[status] = self._mode_values.get(value)
                elif status == DeviceAttributes.fan_speed:
                    if value in self._speeds:
                        self._attributes[status] = self._speeds.get(value)
                    else:
                        self._attributes[status] = None
                elif status == DeviceAttributes.screen_display:
                    if value in self._screen_display_values:
                        self._attributes[status] = self._screen_display_values.get(
                            value,
                        )
                    else:
                        self._attributes[status] = None
                else:
                    self._attributes[status] = value
                new_status[str(status)] = self._attributes[status]
        return new_status

    def make_message_set(self) -> MessageSet:
        """Midea FD device make message set."""
        message = MessageSet(
            self._message_protocol_version,
            lua_protocol=self._lua_protocol,
        )
        message.power = self._attributes[DeviceAttributes.power]
        message.prompt_tone = self._attributes[DeviceAttributes.prompt_tone]
        message.disinfect = self._attributes[DeviceAttributes.disinfect]
        message.wet_pad_dry = self._attributes[DeviceAttributes.wet_pad_dry]
        message.target_humidity = self._attributes[DeviceAttributes.target_humidity]
        if self._attributes[DeviceAttributes.mode] in self._mode_values.values():
            message.mode = list(self._mode_values.keys())[
                list(self._mode_values.values()).index(
                    self._attributes[DeviceAttributes.mode],
                )
            ]
        else:
            message.mode = 1
        default_fan_speed = (
            39 if self._lua_protocol == FD_LUA_PROTOCOL_2024110101 else 40
        )
        message.fan_speed = (
            default_fan_speed
            if self._attributes[DeviceAttributes.fan_speed] is None
            else list(self._speeds.keys())[
                list(self._speeds.values()).index(
                    self._attributes[DeviceAttributes.fan_speed],
                )
            ]
        )
        message.screen_display = (
            None
            if self._lua_protocol == FD_LUA_PROTOCOL_25
            else 0
            if self._attributes[DeviceAttributes.screen_display] is None
            else list(self._screen_display_values.keys())[
                list(self._screen_display_values.values()).index(
                    self._attributes[DeviceAttributes.screen_display],
                )
            ]
        )
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea FD device set attribute."""
        if (
            attr == DeviceAttributes.prompt_tone
            and self._lua_protocol != FD_LUA_PROTOCOL_2024110101
        ):
            self._attributes[DeviceAttributes.prompt_tone] = value
            self.update_all({DeviceAttributes.prompt_tone.value: value})
        else:
            message = self.make_message_set()
            if attr == DeviceAttributes.mode:
                if value in self._mode_values.values():
                    message.mode = list(self._mode_values.keys())[
                        list(self._mode_values.values()).index(str(value))
                    ]
            elif attr == DeviceAttributes.fan_speed:
                if value in self._speeds.values():
                    message.fan_speed = list(self._speeds.keys())[
                        list(self._speeds.values()).index(str(value))
                    ]
                    if self._lua_protocol == FD_LUA_PROTOCOL_25:
                        message.mode = (
                            FD_LUA_25_MODE_AUTO
                            if message.fan_speed == FD_LUA_25_AUTO_FAN_SPEED
                            else FD_LUA_25_MODE_MANUAL
                        )
            elif attr == DeviceAttributes.screen_display:
                if value in self._screen_display_values.values():
                    message.screen_display = list(
                        self._screen_display_values.keys(),
                    )[list(self._screen_display_values.values()).index(str(value))]
                elif not value:
                    message.screen_display = 7
            else:
                setattr(message, str(attr), value)
            self.build_send(message)


class MideaAppliance(MideaFDDevice):
    """Midea FD appliance."""

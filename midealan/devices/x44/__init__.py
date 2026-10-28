"""Midea lan x44 device.

The 0x44 appliance behind this package is the Midea smart panel
(ZKP-3INCH01 / sn8 404M0001). Status comes from the Lua screen query.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    AUTO_OFF_SCREEN_TYPE,
    BRIGHTNESS,
    CLOSE_SCREEN_BRIGHT,
    ERROR_CODE,
    HAS_TOKEN,
    LEFT_BUTTON,
    LEFT_BUTTON_KEEP,
    LEFT_WORK_MODE,
    MIDDLE_BUTTON,
    MIDDLE_BUTTON_KEEP,
    MIDDLE_WORK_MODE,
    NIGHT_VOLUME,
    PANEL_STATUS,
    RIGHT_BUTTON,
    RIGHT_BUTTON_KEEP,
    RIGHT_WORK_MODE,
    SCREEN_STATE,
    SHOW_BUTTON_NAME,
    SLEEP_DURATION_HOUR,
    SLEEP_DURATION_MINUTE,
    SLEEP_MODE,
    SLEEP_MODE_MUTE,
    SLEEP_MODE_SWITCH,
    SLEEP_START_HOUR,
    SLEEP_START_MINUTE,
    THEME,
    UNCHANGED,
    VOICE_CONTROL,
    VOICE_VOLUME,
    MessageQuery,
    MessageSetScreen,
    MessageX44Response,
)

HOUR_MAX = 23
MINUTE_MAX = 59
FLAG_ON = 1
FLAG_OFF = 0


class DeviceAttributes(StrEnum):
    """Midea x44 device attributes."""

    has_token = HAS_TOKEN
    panel_status = PANEL_STATUS
    error_code = ERROR_CODE
    left_button = LEFT_BUTTON
    middle_button = MIDDLE_BUTTON
    right_button = RIGHT_BUTTON
    show_button_name = SHOW_BUTTON_NAME
    close_screen_bright = CLOSE_SCREEN_BRIGHT
    sleep_mode_switch = SLEEP_MODE_SWITCH
    sleep_mode_mute = SLEEP_MODE_MUTE
    auto_off_screen_type = AUTO_OFF_SCREEN_TYPE
    theme = THEME
    night_volume = NIGHT_VOLUME
    voice_volume = VOICE_VOLUME
    sleep_start_hour = SLEEP_START_HOUR
    sleep_start_minute = SLEEP_START_MINUTE
    sleep_duration_hour = SLEEP_DURATION_HOUR
    sleep_duration_minute = SLEEP_DURATION_MINUTE
    left_button_keep = LEFT_BUTTON_KEEP
    middle_button_keep = MIDDLE_BUTTON_KEEP
    right_button_keep = RIGHT_BUTTON_KEEP
    voice_control = VOICE_CONTROL
    sleep_mode = SLEEP_MODE
    screen_state = SCREEN_STATE
    brightness = BRIGHTNESS
    left_button_work_mode = LEFT_WORK_MODE
    middle_button_work_mode = MIDDLE_WORK_MODE
    right_button_work_mode = RIGHT_WORK_MODE


_FLAG_ATTRIBUTES = {
    DeviceAttributes.left_button,
    DeviceAttributes.middle_button,
    DeviceAttributes.right_button,
    DeviceAttributes.show_button_name,
    DeviceAttributes.close_screen_bright,
    DeviceAttributes.sleep_mode_switch,
    DeviceAttributes.sleep_mode_mute,
    DeviceAttributes.left_button_keep,
    DeviceAttributes.middle_button_keep,
    DeviceAttributes.right_button_keep,
    DeviceAttributes.voice_control,
    DeviceAttributes.sleep_mode,
    DeviceAttributes.screen_state,
}
_NUMBER_RANGES: dict[DeviceAttributes, tuple[int, int]] = {
    DeviceAttributes.auto_off_screen_type: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.theme: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.night_volume: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.voice_volume: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.sleep_start_hour: (FLAG_OFF, HOUR_MAX),
    DeviceAttributes.sleep_start_minute: (FLAG_OFF, MINUTE_MAX),
    DeviceAttributes.sleep_duration_hour: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.sleep_duration_minute: (FLAG_OFF, MINUTE_MAX),
    DeviceAttributes.brightness: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.left_button_work_mode: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.middle_button_work_mode: (FLAG_OFF, UNCHANGED - 1),
    DeviceAttributes.right_button_work_mode: (FLAG_OFF, UNCHANGED - 1),
}


class MideaX44Device(MideaDevice):
    """Midea x44 smart panel."""

    _writable: ClassVar[set[str]] = {item.value for item in _FLAG_ATTRIBUTES} | {
        item.value for item in _NUMBER_RANGES
    }

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x44 device."""
        super().__init__(
            device_type=DeviceType.X44,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )

    def build_query(self) -> list[MessageQuery]:
        """Query the screen-status record."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Store the fields carried by one screen report."""
        message = MessageX44Response(bytearray(msg))
        new_status: dict[str, Any] = {}
        for name, value in message.attributes.items():
            if name not in self._attributes:
                continue
            self._attributes[name] = value
            new_status[name] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Set one screen attribute. Other fields are left unchanged."""
        if attr not in self._writable:
            return
        encoded = self._encode_attribute(attr, value)
        message = MessageSetScreen(self._message_protocol_version)
        message.values[attr] = encoded
        self.build_send(message)

    def _encode_attribute(self, attr: str, value: bool | float | str) -> int:
        if attr in _FLAG_ATTRIBUTES:
            return self._encode_flag(value)
        return self._encode_number(attr, value)

    @staticmethod
    def _encode_flag(value: object) -> int:
        message = "[x44] Expected bool or 0/1"
        if isinstance(value, bool):
            return FLAG_ON if value else FLAG_OFF
        if isinstance(value, int) and value in {FLAG_OFF, FLAG_ON}:
            return value
        raise ValueWrongType(message)

    @staticmethod
    def _encode_number(attr: str, value: object) -> int:
        """Accept an int, or a float that is a whole number, inside the field range."""
        type_message = f"[x44] {attr} expects a number"
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueWrongType(type_message)
        # Home Assistant number entities send floats. 50.0 is the caller's 50;
        # 50.7 would be a different command, so it is rejected.
        if isinstance(value, float) and not value.is_integer():
            whole_message = f"[x44] {attr} must be a whole number"
            raise ValueWrongType(whole_message)
        coerced = int(value)
        lower, upper = _NUMBER_RANGES[DeviceAttributes(attr)]
        if not lower <= coerced <= upper:
            range_message = f"[x44] {attr} must be in [{lower}, {upper}]"
            raise ValueOutOfRange(range_message)
        return coerced


class MideaAppliance(MideaX44Device):
    """Midea x44 appliance."""

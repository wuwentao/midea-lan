"""Midea local FA device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.message import MessageType

from .message import (
    FA_MESSAGE_PROTOCOL_V6,
    FA_MESSAGE_PROTOCOLS,
    HUMIDIFY_CODES,
    SCENE_CODES,
    SWING_DIRECTION_CODES,
    TILTING_ANGLE_CODES,
    V6_DEFAULT_SWING_ANGLE,
    V6_DEFAULT_SWING_ANGLE_CODE,
    FAValue,
    MessageFAResponse,
    MessageNewSet,
    MessageQuery,
    MessageSet,
    MessageV6Set,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_NEW_SWING_ANGLE = 1275
MAX_LEGACY_SWING_MODE = 6


def _status_code(value: FAValue) -> int:
    """Convert a decoded protocol value to an integer code."""
    return int(value) if isinstance(value, (bool, float, int)) else 0


class DeviceAttributes(StrEnum):
    """Midea FA device attributes."""

    power = "power"
    child_lock = "child_lock"
    mode = "mode"
    fan_speed = "fan_speed"
    oscillate = "oscillate"
    oscillation_angle = "oscillation_angle"
    tilting_angle = "tilting_angle"
    oscillation_mode = "oscillation_mode"
    humidify = "humidify"
    waterions = "waterions"
    display_on_off = "display_on_off"
    voice = "voice"
    error_code = "error_code"
    scene = "scene"
    auto_power_off = "auto_power_off"
    target_temperature = "target_temperature"
    humidity = "humidity"
    humidify_mode = "humidify_mode"
    anophelifuge = "anophelifuge"
    anion = "anion"
    humidify_feedback = "humidify_feedback"
    temperature_feedback = "temperature_feedback"
    body_feeling_scan = "body_feeling_scan"


class MideaFADevice(MideaDevice):
    """Midea FA device."""

    _oscillation_angles: ClassVar[dict[int, str]] = {
        0x00: "Off",
        0x01: "30",
        0x02: "60",
        0x03: "90",
        0x04: "120",
        0x05: "180",
        0x06: "360",
    }
    _tilting_angles: ClassVar[dict[int, str]] = TILTING_ANGLE_CODES
    _oscillation_modes: ClassVar[dict[int, str]] = {
        key: value
        for key, value in SWING_DIRECTION_CODES.items()
        if key <= MAX_LEGACY_SWING_MODE
    }
    _new_oscillation_modes: ClassVar[dict[int, str]] = SWING_DIRECTION_CODES
    _modes: ClassVar[dict[int, str]] = {
        0x00: "Invalid",
        0x01: "Normal",
        0x02: "Natural",
        0x03: "Sleep",
        0x04: "Comfort",
        0x05: "Mute",
        0x06: "Baby",
        0x07: "Feel",
        0x08: "Storm",
        0x09: "Strong",
        0x0A: "Soft",
        0x0B: "Customize",
        0x0C: "Warm",
        0x0D: "Smart",
        0x0E: "Ionic",
        0x0F: "AI_Smart",
        0x10: "Double_Area",
        0x11: "Purified_Wind",
        0x12: "Sleeping_Wind",
        0x13: "Purify_Only",
        0x14: "Self_Selection",
    }
    _voice: ClassVar[dict[int, str]] = {
        0x00: "invalid",
        0x01: "open_gps",
        0x02: "close_gps",
        0x04: "open_buzzer",
        0x05: "open_tip",
        0x08: "close_buzzer",
        0x0A: "mute",
    }
    _humidify: ClassVar[dict[int, str]] = HUMIDIFY_CODES
    _scene: ClassVar[dict[int, str]] = SCENE_CODES

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea FA device."""
        super().__init__(
            device_type=DeviceType.FA,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.child_lock: False,
                DeviceAttributes.mode: 0,
                DeviceAttributes.fan_speed: 0,
                DeviceAttributes.oscillate: False,
                DeviceAttributes.oscillation_angle: None,
                DeviceAttributes.tilting_angle: None,
                DeviceAttributes.humidify: False,
                DeviceAttributes.waterions: False,
                DeviceAttributes.display_on_off: False,
                DeviceAttributes.oscillation_mode: None,
                DeviceAttributes.voice: None,
                DeviceAttributes.error_code: None,
                DeviceAttributes.scene: None,
                DeviceAttributes.auto_power_off: None,
                DeviceAttributes.target_temperature: None,
                DeviceAttributes.humidity: None,
                DeviceAttributes.humidify_mode: None,
                DeviceAttributes.anophelifuge: None,
                DeviceAttributes.anion: None,
                DeviceAttributes.humidify_feedback: None,
                DeviceAttributes.temperature_feedback: None,
                DeviceAttributes.body_feeling_scan: None,
            },
        )
        self._default_speed_count = 3
        self._speed_count: int = self._default_speed_count
        self.fa_protocol = 0
        self.set_customize(customize)

    @property
    def speed_count(self) -> int:
        """Return the device speed count."""
        return self._speed_count

    @property
    def oscillation_angles(self) -> list[str]:
        """Return the list of legacy oscillation angles."""
        return list(self._oscillation_angles.values())

    @property
    def tilting_angles(self) -> list[str]:
        """Return the list of tilting angles."""
        return list(self._tilting_angles.values())

    @property
    def oscillation_modes(self) -> list[str]:
        """Return the list of supported oscillation modes."""
        return list(self._oscillation_modes.values())

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of preset modes."""
        return list(self._modes.values())

    def build_query(self) -> list[MessageQuery]:
        """Build the FA query."""
        return [MessageQuery(self._message_protocol_version)]

    def _set_status_value(
        self,
        attr: DeviceAttributes,
        value: FAValue,
    ) -> FAValue:
        """Convert a decoded wire value to the public FA attribute value."""
        result = value
        if attr == DeviceAttributes.oscillation_angle:
            if self.fa_protocol in FA_MESSAGE_PROTOCOLS:
                code = _status_code(value)
                result = (
                    V6_DEFAULT_SWING_ANGLE
                    if self.fa_protocol == FA_MESSAGE_PROTOCOL_V6
                    and code == V6_DEFAULT_SWING_ANGLE_CODE
                    else code * 5
                )
            else:
                result = self._oscillation_angles.get(_status_code(value))
        elif attr == DeviceAttributes.tilting_angle:
            if self.fa_protocol in FA_MESSAGE_PROTOCOLS:
                code = _status_code(value)
                result = (
                    V6_DEFAULT_SWING_ANGLE
                    if self.fa_protocol == FA_MESSAGE_PROTOCOL_V6
                    and code == V6_DEFAULT_SWING_ANGLE_CODE
                    else code * 5
                )
            else:
                result = self._tilting_angles.get(_status_code(value))
        elif attr == DeviceAttributes.oscillation_mode:
            modes = (
                self._new_oscillation_modes
                if self.fa_protocol in FA_MESSAGE_PROTOCOLS
                else self._oscillation_modes
            )
            result = modes.get(_status_code(value))
        elif attr == DeviceAttributes.mode:
            result = self._modes.get(_status_code(value))
        elif attr == DeviceAttributes.voice:
            result = (
                value
                if isinstance(value, str)
                else self._voice.get(_status_code(value))
            )
        elif attr == DeviceAttributes.scene:
            result = (
                value
                if isinstance(value, str)
                else self._scene.get(_status_code(value))
            )
        return result

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Process an FA response."""
        message = MessageFAResponse(msg)
        if message.message_type not in {
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        }:
            return {}
        self.fa_protocol = (
            getattr(message, "protocol_version", 0)
            if getattr(message, "is_new_protocol", False)
            else 0
        )
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for attr in self._attributes:
            if not hasattr(message, str(attr)):
                continue
            value = getattr(message, str(attr))
            value = self._set_status_value(attr, value)
            if attr == DeviceAttributes.power:
                self._attributes[attr] = value
                if not value:
                    self._attributes[DeviceAttributes.fan_speed] = 0
            elif (
                attr == DeviceAttributes.fan_speed
                and not self._attributes[DeviceAttributes.power]
            ):
                self._attributes[attr] = 0
            else:
                self._attributes[attr] = value
            new_status[str(attr)] = self._attributes[attr]
        return new_status

    def _legacy_angle_code(self, value: str, values: dict[int, str]) -> int | None:
        """Convert a legacy public angle to its protocol code."""
        for key, item in values.items():
            if item == value:
                return key
        return None

    def _legacy_angle_or_default(
        self,
        value: FAValue,
        values: dict[int, str],
    ) -> int:
        """Use 90 degrees when a legacy angle is unset or Off."""
        if value in {None, "", "Off"}:
            value = "90"
        return self._legacy_angle_code(str(value), values) or 0

    def _set_oscillation_mode(self, message: MessageSet, value: str) -> None:
        """Build a legacy oscillation-mode command."""
        if value == "Off" or not value:
            message.oscillate = False
            return
        message.oscillate = True
        message.oscillation_mode = self._legacy_angle_code(
            value,
            self._oscillation_modes,
        )
        if value == "Oscillation":
            message.oscillation_angle = self._legacy_angle_or_default(
                self._attributes[DeviceAttributes.oscillation_angle],
                self._oscillation_angles,
            )
        elif value == "Tilting":
            message.tilting_angle = self._legacy_angle_or_default(
                self._attributes[DeviceAttributes.tilting_angle],
                self._tilting_angles,
            )
        else:
            message.oscillation_angle = self._legacy_angle_or_default(
                self._attributes[DeviceAttributes.oscillation_angle],
                self._oscillation_angles,
            )
            message.tilting_angle = self._legacy_angle_or_default(
                self._attributes[DeviceAttributes.tilting_angle],
                self._tilting_angles,
            )

    def _set_oscillation_angle(self, message: MessageSet, value: str) -> None:
        """Build a legacy horizontal-angle command."""
        if value == "Off" or not value:
            tilting = self._attributes[DeviceAttributes.tilting_angle]
            if tilting in {None, "Off"}:
                message.oscillate = False
            else:
                message.oscillate = True
                message.oscillation_mode = 2
                message.tilting_angle = self._legacy_angle_code(
                    str(tilting),
                    self._tilting_angles,
                )
            return
        message.oscillation_angle = self._legacy_angle_code(
            value,
            self._oscillation_angles,
        )
        message.oscillate = True
        tilting = self._attributes[DeviceAttributes.tilting_angle]
        if tilting in {None, "Off"}:
            message.oscillation_mode = 1
        elif self._attributes[DeviceAttributes.oscillation_mode] == "Tilting":
            message.oscillation_mode = 6
            message.tilting_angle = self._legacy_angle_code(
                str(tilting),
                self._tilting_angles,
            )

    def _set_tilting_angle(self, message: MessageSet, value: str) -> None:
        """Build a legacy vertical-angle command."""
        if value == "Off" or not value:
            oscillation = self._attributes[DeviceAttributes.oscillation_angle]
            if oscillation in {None, "Off"}:
                message.oscillate = False
            else:
                message.oscillate = True
                message.oscillation_mode = 1
                message.oscillation_angle = self._legacy_angle_code(
                    str(oscillation),
                    self._oscillation_angles,
                )
            return
        message.tilting_angle = self._legacy_angle_code(value, self._tilting_angles)
        message.oscillate = True
        oscillation = self._attributes[DeviceAttributes.oscillation_angle]
        if oscillation in {None, "Off"}:
            message.oscillation_mode = 2
        elif self._attributes[DeviceAttributes.oscillation_mode] == "Oscillation":
            message.oscillation_mode = 6
            message.oscillation_angle = self._legacy_angle_code(
                str(oscillation),
                self._oscillation_angles,
            )

    def set_oscillation(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageSet | None:
        """Build a legacy oscillation command."""
        message: MessageSet | None = None
        if self._attributes[attr] == value:
            return None
        if attr == DeviceAttributes.oscillate:
            message = MessageSet(self._message_protocol_version, self.subtype)
            message.oscillate = bool(value)
            if value:
                message.oscillation_angle = 3
                message.oscillation_mode = 1
        elif attr == DeviceAttributes.oscillation_mode and (
            value in self._oscillation_modes.values() or not value
        ):
            message = MessageSet(self._message_protocol_version, self.subtype)
            self._set_oscillation_mode(message, str(value))
        elif attr == DeviceAttributes.oscillation_angle and (
            value in self._oscillation_angles.values() or not value
        ):
            message = MessageSet(self._message_protocol_version, self.subtype)
            self._set_oscillation_angle(message, str(value))
        elif attr == DeviceAttributes.tilting_angle and (
            value in self._tilting_angles.values() or not value
        ):
            message = MessageSet(self._message_protocol_version, self.subtype)
            self._set_tilting_angle(message, str(value))
        return message

    def set_new_oscillation(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageNewSet | MessageV6Set | None:
        """Build a protocol v5/v6 oscillation command."""
        if self._attributes[attr] == value:
            return None
        message = self._new_message()
        valid = True
        if attr == DeviceAttributes.oscillate:
            message.oscillate = bool(value)
            if value:
                message.oscillation_angle = (
                    V6_DEFAULT_SWING_ANGLE
                    if self.fa_protocol == FA_MESSAGE_PROTOCOL_V6
                    else DEFAULT_NEW_SWING_ANGLE
                )
                message.oscillation_mode = "Oscillation"
            else:
                message.oscillation_angle = 0
                message.oscillation_mode = "Oscillation"
        elif attr == DeviceAttributes.oscillation_mode:
            if value in {"Off", "", None}:
                message.oscillate = False
                message.oscillation_angle = 0
                message.oscillation_mode = "Oscillation"
            elif value in self._new_oscillation_modes.values():
                message.oscillation_mode = str(value)
                message.oscillate = True
                current_angle = self._attributes[DeviceAttributes.oscillation_angle]
                message.oscillation_angle = (
                    current_angle
                    if isinstance(current_angle, (int, float)) and current_angle > 0
                    else (
                        V6_DEFAULT_SWING_ANGLE
                        if self.fa_protocol == FA_MESSAGE_PROTOCOL_V6
                        else DEFAULT_NEW_SWING_ANGLE
                    )
                )
            else:
                valid = False
        elif attr == DeviceAttributes.oscillation_angle:
            if value in {"Off", "", None}:
                message.oscillate = False
                message.oscillation_angle = 0
                message.oscillation_mode = "Oscillation"
            else:
                message.oscillate = True
                message.oscillation_angle = value
                message.oscillation_mode = "Oscillation"
        elif attr == DeviceAttributes.tilting_angle:
            message.oscillate = True
            message.tilting_angle = value
            message.oscillation_mode = "Tilting"
        else:
            valid = False
        return message if valid else None

    def _new_message(self) -> MessageNewSet | MessageV6Set:
        """Create a protocol v5/v6 set message."""
        message_type = (
            MessageV6Set
            if self.fa_protocol == FA_MESSAGE_PROTOCOL_V6
            else MessageNewSet
        )
        return message_type(self._message_protocol_version, self.subtype)

    def _legacy_message(self) -> MessageSet:
        """Create a legacy set message."""
        return MessageSet(self._message_protocol_version, self.subtype)

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Set an FA device attribute."""
        if attr in {
            DeviceAttributes.oscillate,
            DeviceAttributes.oscillation_mode,
            DeviceAttributes.oscillation_angle,
            DeviceAttributes.tilting_angle,
        }:
            message = (
                self.set_new_oscillation(attr, value)
                if self.fa_protocol in FA_MESSAGE_PROTOCOLS
                else self.set_oscillation(attr, value)
            )
        elif (
            attr == DeviceAttributes.fan_speed
            and int(value) > 0
            and not self._attributes[DeviceAttributes.power]
        ):
            message = (
                self._new_message() if self.fa_protocol else self._legacy_message()
            )
            message.fan_speed = int(value)
            message.power = True
        elif attr == DeviceAttributes.mode:
            message = None
            if value in self._modes.values():
                message = (
                    self._new_message() if self.fa_protocol else self._legacy_message()
                )
                message.mode = self.get_dict_key_by_value("_modes", str(value))
        elif attr == DeviceAttributes.fan_speed and int(value) == 0:
            message = None
        else:
            message = (
                self._new_message() if self.fa_protocol else self._legacy_message()
            )
            setattr(message, str(attr), value)
        if message is not None:
            self.build_send(message)

    def turn_on(self, fan_speed: int | None = None, mode: str | None = None) -> None:
        """Turn on the device."""
        message = self._new_message() if self.fa_protocol else self._legacy_message()
        message.power = True
        if fan_speed is not None:
            message.fan_speed = fan_speed
        if mode in self._modes.values():
            message.mode = self.get_dict_key_by_value("_modes", str(mode))
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Set device customization."""
        self._speed_count = self._default_speed_count
        if customize:
            try:
                params = json.loads(customize)
                if params and "speed_count" in params:
                    self._speed_count = params["speed_count"]
            except Exception:
                _LOGGER.exception("[%s] Set customize error", self.device_id)
        self.update_all({"speed_count": self._speed_count})


class MideaAppliance(MideaFADevice):
    """Midea appliance device."""

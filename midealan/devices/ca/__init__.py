"""Midea lan CA device."""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDeviceInitKwargs, ToshibaDevice
from midealan.message import (
    MessageRequest,
    MessageType,
    ToshibaFrame,
    ToshibaMessageRequest,
)

from .message import MessageCAResponse, MessageQuery

_LOGGER = logging.getLogger(__name__)

SUBTYPE_310A2111 = 56
TOSHIBA_BASE_STATUS_LENGTH = 13
TOSHIBA_SHIFTED_MODEL = "0000000D"
TOSHIBA_SHIFTED_BASE_STATUS_LENGTH = 16
FLEX_ZONE_MODE_BY_TEMPERATURE: dict[float, str] = {
    6.0: "baby",
    2.0: "treasure",
    0.0: "zero",
}


class ToshibaCAQuery(ToshibaMessageRequest):
    """Toshiba CA base-status query."""


class DeviceAttributes(StrEnum):
    """Midea CA device attributes."""

    mode = "mode"
    code_mode = "code_mode"
    freezing_mode = "freezing_mode"
    smart_mode = "smart_mode"
    energy_saving_mode = "energy_saving_mode"
    holiday_mode = "holiday_mode"
    moisturize_mode = "moisturize_mode"
    preservation_mode = "preservation_mode"
    acme_freezing_mode = "acme_freezing_mode"
    flood_light = "flood_light"
    freezing_ice_machine_power = "freezing_ice_machine_power"
    energy_consumption = "energy_consumption"
    refrigerator_actual_temp = "refrigerator_actual_temp"
    freezer_actual_temp = "freezer_actual_temp"
    flex_zone_actual_temp = "flex_zone_actual_temp"
    right_flex_zone_actual_temp = "right_flex_zone_actual_temp"
    refrigerator_setting_temp = "refrigerator_setting_temp"
    freezer_setting_temp = "freezer_setting_temp"
    flex_zone_setting_temp = "flex_zone_setting_temp"
    right_flex_zone_setting_temp = "right_flex_zone_setting_temp"
    refrigerator_door_overtime = "refrigerator_door_overtime"
    freezer_door_overtime = "freezer_door_overtime"
    bar_door_overtime = "bar_door_overtime"
    flex_zone_door_overtime = "flex_zone_door_overtime"
    refrigerator_door = "refrigerator_door"
    freezer_door = "freezer_door"
    bar_door = "bar_door"
    flex_zone_door = "flex_zone_door"
    microcrystal_fresh = "microcrystal_fresh"
    electronic_smell = "electronic_smell"
    humidity = "humidity"
    variable_mode = "variable_mode"


class MideaCADevice(ToshibaDevice):
    """Midea CA device."""

    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        (MessageType.query, MessageType.notify1),
    )

    _variable_mode: ClassVar[dict[int, str]] = {
        0x00: "none",
        0x01: "soft_freezing",
        0x02: "zero_fresh",
        0x03: "cold_drink",
        0x04: "fresh_product",
        0x05: "partial_freezing",
        0x06: "dry_zone",
        0x07: "freeze_warm",
        0x08: "partial_freezing",
    }

    _humidity: ClassVar[dict[int, str]] = {
        0x10: "high",
        0x20: "low",
    }

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea CA device."""
        super().__init__(
            device_type=DeviceType.CA,
            **kwargs,
            attributes={
                # Read-only parser values; None means no general status received.
                DeviceAttributes.mode: None,
                DeviceAttributes.code_mode: None,
                DeviceAttributes.freezing_mode: None,
                DeviceAttributes.smart_mode: None,
                DeviceAttributes.energy_saving_mode: None,
                DeviceAttributes.holiday_mode: None,
                DeviceAttributes.moisturize_mode: None,
                DeviceAttributes.preservation_mode: None,
                DeviceAttributes.acme_freezing_mode: None,
                DeviceAttributes.flood_light: None,
                DeviceAttributes.freezing_ice_machine_power: None,
                DeviceAttributes.energy_consumption: None,
                DeviceAttributes.refrigerator_actual_temp: None,
                DeviceAttributes.freezer_actual_temp: None,
                DeviceAttributes.flex_zone_actual_temp: None,
                DeviceAttributes.right_flex_zone_actual_temp: None,
                DeviceAttributes.refrigerator_setting_temp: None,
                DeviceAttributes.freezer_setting_temp: None,
                DeviceAttributes.flex_zone_setting_temp: None,
                DeviceAttributes.right_flex_zone_setting_temp: None,
                DeviceAttributes.refrigerator_door_overtime: False,
                DeviceAttributes.freezer_door_overtime: False,
                DeviceAttributes.bar_door_overtime: False,
                DeviceAttributes.flex_zone_door_overtime: False,
                DeviceAttributes.refrigerator_door: False,
                DeviceAttributes.freezer_door: False,
                DeviceAttributes.bar_door: False,
                DeviceAttributes.flex_zone_door: False,
                DeviceAttributes.microcrystal_fresh: False,
                DeviceAttributes.electronic_smell: False,
                DeviceAttributes.humidity: None,
                DeviceAttributes.variable_mode: None,
            },
        )
        self._modes = [""]

    def build_toshiba_query(self) -> list[MessageRequest]:
        """Query the base group supported by every documented CA profile."""
        return [
            ToshibaCAQuery(DeviceType.CA, self._message_protocol_version, b"\x00"),
        ]

    def build_query(self) -> list[MessageRequest]:
        """Midea CA device build query."""
        if self.toshiba_protocol:
            return self.build_toshiba_query()
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea CA device process message."""
        status = self.process_toshiba_message(msg)
        if status is not None:
            return status
        message = MessageCAResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        for attr in self._attributes:
            if hasattr(message, str(attr)):
                value = getattr(message, str(attr))
                # variable_mode
                if attr == DeviceAttributes.variable_mode:
                    self._attributes[attr] = MideaCADevice._variable_mode.get(value)
                # humidity
                elif attr == DeviceAttributes.humidity:
                    self._attributes[attr] = MideaCADevice._humidity.get(value)
                else:
                    self._attributes[attr] = value
                new_status[str(attr)] = self._attributes[attr]
        if (
            self.model == "310A2111"
            and self.subtype == SUBTYPE_310A2111
            and (
                DeviceAttributes.flex_zone_setting_temp in new_status
                or DeviceAttributes.variable_mode in new_status
            )
        ):
            # This model reports its preset through the setting temperature,
            # not the generic variable-mode byte. Emit the derived attribute
            # as well so consumers refresh on temperature-only updates.
            temperature = self._attributes[DeviceAttributes.flex_zone_setting_temp]
            mode = (
                FLEX_ZONE_MODE_BY_TEMPERATURE.get(temperature)
                if isinstance(temperature, (int, float))
                and not isinstance(temperature, bool)
                else None
            )
            self._attributes[DeviceAttributes.variable_mode] = mode
            new_status[DeviceAttributes.variable_mode] = mode
        return new_status

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode a complete Toshiba refrigerator base status."""
        body = frame.body
        shifted = self.model == TOSHIBA_SHIFTED_MODEL
        minimum_length = (
            TOSHIBA_SHIFTED_BASE_STATUS_LENGTH
            if shifted
            else TOSHIBA_BASE_STATUS_LENGTH
        )
        if len(body) < minimum_length or body[0] != 0x00:
            return None
        mode_index = 4 if shifted else 2
        door_index = 11 if shifted else 8
        energy_start = 14 if shifted else 11
        values: dict[DeviceAttributes, Any] = {
            DeviceAttributes.mode: body[mode_index],
            DeviceAttributes.energy_saving_mode: bool(body[1] & 0x01),
            DeviceAttributes.refrigerator_actual_temp: body[mode_index + 1],
            DeviceAttributes.freezer_actual_temp: body[mode_index + 2],
            DeviceAttributes.refrigerator_door: bool(body[door_index] & 0x01),
            DeviceAttributes.freezer_door: bool(body[door_index] & 0x02),
            DeviceAttributes.bar_door: bool(body[door_index] & 0x04),
            DeviceAttributes.flex_zone_door: bool(body[door_index] & 0x08),
            DeviceAttributes.energy_consumption: int.from_bytes(
                body[energy_start : energy_start + 2],
                "little",
            ),
        }
        self._attributes.update(values)
        return {str(attr): value for attr, value in values.items()}

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea CA device set attribute."""
        del attr, value
        self.reject_toshiba_write()


class MideaAppliance(MideaCADevice):
    """Midea CA appliance."""

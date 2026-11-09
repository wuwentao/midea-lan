"""Midea lan ef device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    CMD_CODE_HIGH,
    CMD_CODE_LOW,
    CMD_ID_HIGH,
    CMD_ID_LOW,
    DRINK_HOT,
    DRINK_WARM,
    TEMPERATURE_HIGH,
    TEMPERATURE_LOW,
    TIME_HR_HIGH,
    TIME_HR_LOW,
    TIME_MIN_HIGH,
    TIME_MIN_LOW,
    MessageEFResponse,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

_DRINK_STYLES = (DRINK_HOT, DRINK_WARM)


class DeviceAttributes(StrEnum):
    """Midea ef device attributes."""

    cmd_code = "cmd_code"
    work_status = "work_status"
    error_code = "error_code"
    response_type = "response_type"
    cmd_id = "cmd_id"
    reserve = "reserve"
    warm = "warm"
    drink_style = "drink_style"
    work_step = "work_step"
    process_status = "process_status"
    time_work_hr = "time_work_hr"
    time_work_min = "time_work_min"
    time_max = "time_max"
    time_reserve_hr = "time_reserve_hr"
    time_reserve_min = "time_reserve_min"
    time_warm_hr = "time_warm_hr"
    time_warm_min = "time_warm_min"
    temperature_setting = "temperature_setting"
    temperature_current = "temperature_current"


# Bool control params carried in the packed flag byte.
_BOOL_ATTRS = frozenset(
    {DeviceAttributes.reserve, DeviceAttributes.warm},
)
# Numeric control params and their accepted inclusive ranges (Lua bounds).
_NUMERIC_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.cmd_code: (CMD_CODE_LOW, CMD_CODE_HIGH),
    DeviceAttributes.cmd_id: (CMD_ID_LOW, CMD_ID_HIGH),
    DeviceAttributes.time_reserve_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.time_reserve_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.time_warm_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.time_warm_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.temperature_setting: (TEMPERATURE_LOW, TEMPERATURE_HIGH),
}
# All writable control params (bool + drink_style + numeric).
_SETTABLE = _BOOL_ATTRS | {DeviceAttributes.drink_style} | set(_NUMERIC_RANGES)
# Control-frame fields seeded from current state (name -> message attribute).
_SEED_BOOL = (DeviceAttributes.reserve, DeviceAttributes.warm)
_SEED_NUMERIC = (
    DeviceAttributes.cmd_code,
    DeviceAttributes.cmd_id,
    DeviceAttributes.time_reserve_hr,
    DeviceAttributes.time_reserve_min,
    DeviceAttributes.time_warm_hr,
    DeviceAttributes.time_warm_min,
    DeviceAttributes.temperature_setting,
)


class MideaEFDevice(MideaDevice):
    """Midea ef device (beverage / drink maker)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea ef device."""
        super().__init__(
            device_type=DeviceType.EF,
            **kwargs,
            attributes={
                DeviceAttributes.cmd_code: None,
                DeviceAttributes.work_status: None,
                DeviceAttributes.error_code: None,
                DeviceAttributes.response_type: None,
                DeviceAttributes.cmd_id: None,
                DeviceAttributes.reserve: None,
                DeviceAttributes.warm: None,
                DeviceAttributes.drink_style: None,
                DeviceAttributes.work_step: None,
                DeviceAttributes.process_status: None,
                DeviceAttributes.time_work_hr: None,
                DeviceAttributes.time_work_min: None,
                DeviceAttributes.time_max: None,
                DeviceAttributes.time_reserve_hr: None,
                DeviceAttributes.time_reserve_min: None,
                DeviceAttributes.time_warm_hr: None,
                DeviceAttributes.time_warm_min: None,
                DeviceAttributes.temperature_setting: None,
                DeviceAttributes.temperature_current: None,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea ef device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea ef device process message."""
        message = MessageEFResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def _make_message_set(self) -> MessageSet:
        """Build a control message seeded from the current device state."""
        message = MessageSet(self._message_protocol_version)
        for key in _SEED_BOOL:
            current = self._attributes[key]
            if isinstance(current, bool):
                setattr(message, str(key), current)
        for key in _SEED_NUMERIC:
            current = self._attributes[key]
            if isinstance(current, int):
                setattr(message, str(key), current)
        style = self._attributes[DeviceAttributes.drink_style]
        if isinstance(style, str) and style in _DRINK_STYLES:
            message.drink_style = style
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea ef device set attribute."""
        if attr not in _SETTABLE:
            # work_status / error_code / response_type / work_step /
            # process_status / work time / time_max / temperature_current are
            # read-only report fields.
            return
        message = self._make_message_set()
        if attr in _BOOL_ATTRS:
            setattr(message, str(attr), bool(value))
        elif attr == DeviceAttributes.drink_style:
            if not isinstance(value, str) or value not in _DRINK_STYLES:
                msg = "[ef] drink_style expects warm_drink/hot_drink"
                raise ValueWrongType(msg)
            message.drink_style = value
        else:
            low, high = _NUMERIC_RANGES[attr]
            if isinstance(value, bool) or not isinstance(value, int | float):
                msg = f"[ef] {attr} expects a number"
                raise ValueWrongType(msg)
            number = int(value)
            if not low <= number <= high:
                msg = f"[ef] {attr} must be in [{low}, {high}]"
                raise ValueOutOfRange(msg)
            setattr(message, str(attr), number)
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea ef device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaEFDevice):
    """Midea ef appliance."""

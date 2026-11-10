"""Midea lan e9 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    BAKE_TEMPERATURE_HIGH,
    BAKE_TEMPERATURE_LOW,
    CMD_CODE_HIGH,
    CMD_CODE_LOW,
    COLOR_HIGH,
    COLOR_LOW,
    DOSING_HIGH,
    DOSING_LOW,
    TIME_HR_HIGH,
    TIME_HR_LOW,
    TIME_MIN_HIGH,
    TIME_MIN_LOW,
    VOLUME_HIGH,
    VOLUME_LOW,
    WORK_STATUS_HIGH,
    WORK_STATUS_LOW,
    MessageE9Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea e9 device attributes."""

    control_cmd_code = "control_cmd_code"
    response_type = "response_type"
    volume = "volume"
    color = "color"
    dosing = "dosing"
    work_status = "work_status"
    work_stage = "work_stage"
    bottom_temperature = "bottom_temperature"
    time_cuisine_min = "time_cuisine_min"
    time_cuisine_hr = "time_cuisine_hr"
    time_reserve_min = "time_reserve_min"
    time_reserve_hr = "time_reserve_hr"
    time_work_min = "time_work_min"
    time_work_hr = "time_work_hr"
    time_warm_min = "time_warm_min"
    time_warm_hr = "time_warm_hr"
    bake_temperature = "bake_temperature"
    product_volume = "product_volume"
    error_code = "error_code"


# Numeric control params and their accepted inclusive ranges (Lua bounds).
_NUMERIC_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.control_cmd_code: (CMD_CODE_LOW, CMD_CODE_HIGH),
    DeviceAttributes.volume: (VOLUME_LOW, VOLUME_HIGH),
    DeviceAttributes.color: (COLOR_LOW, COLOR_HIGH),
    DeviceAttributes.dosing: (DOSING_LOW, DOSING_HIGH),
    DeviceAttributes.work_status: (WORK_STATUS_LOW, WORK_STATUS_HIGH),
    DeviceAttributes.time_cuisine_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.time_cuisine_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.time_reserve_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.time_reserve_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.bake_temperature: (BAKE_TEMPERATURE_LOW, BAKE_TEMPERATURE_HIGH),
}
# All writable control params.
_SETTABLE = set(_NUMERIC_RANGES)
# Write-only control fields: the device never reports these back (the status /
# echo body decodes neither cuisine time nor bake temperature), so a set must
# store the written value on the device state itself, otherwise the next set
# re-seeds them from None and silently resets them to 0.
_WRITE_ONLY = (
    DeviceAttributes.time_cuisine_min,
    DeviceAttributes.time_cuisine_hr,
    DeviceAttributes.bake_temperature,
)
# Control-frame fields seeded from current state (shared attribute names). The
# write-only fields above are seeded from the value the previous set stored.
_SEED_NUMERIC = (
    DeviceAttributes.control_cmd_code,
    DeviceAttributes.volume,
    DeviceAttributes.color,
    DeviceAttributes.dosing,
    DeviceAttributes.work_status,
    DeviceAttributes.time_cuisine_min,
    DeviceAttributes.time_cuisine_hr,
    DeviceAttributes.time_reserve_min,
    DeviceAttributes.time_reserve_hr,
    DeviceAttributes.bake_temperature,
)


class MideaE9Device(MideaDevice):
    """Midea e9 device (bread / baking machine)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea e9 device."""
        super().__init__(
            device_type=DeviceType.E9,
            **kwargs,
            attributes={
                DeviceAttributes.control_cmd_code: None,
                DeviceAttributes.response_type: None,
                DeviceAttributes.volume: None,
                DeviceAttributes.color: None,
                DeviceAttributes.dosing: None,
                DeviceAttributes.work_status: None,
                DeviceAttributes.work_stage: None,
                DeviceAttributes.bottom_temperature: None,
                DeviceAttributes.time_cuisine_min: None,
                DeviceAttributes.time_cuisine_hr: None,
                DeviceAttributes.time_reserve_min: None,
                DeviceAttributes.time_reserve_hr: None,
                DeviceAttributes.time_work_min: None,
                DeviceAttributes.time_work_hr: None,
                DeviceAttributes.time_warm_min: None,
                DeviceAttributes.time_warm_hr: None,
                DeviceAttributes.bake_temperature: None,
                DeviceAttributes.product_volume: None,
                DeviceAttributes.error_code: None,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea e9 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea e9 device process message."""
        message = MessageE9Response(msg)
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
        for key in _SEED_NUMERIC:
            current = self._attributes[key]
            if isinstance(current, int) and not isinstance(current, bool):
                setattr(message, str(key), current)
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea e9 device set attribute."""
        if attr not in _SETTABLE:
            # response_type / work_stage / bottom_temperature / work time /
            # warm time / product_volume / error_code are read-only report
            # fields.
            return
        message = self._make_message_set()
        low, high = _NUMERIC_RANGES[attr]
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"[e9] {attr} expects a number"
            raise ValueWrongType(msg)
        number = int(value)
        if not low <= number <= high:
            msg = f"[e9] {attr} must be in [{low}, {high}]"
            raise ValueOutOfRange(msg)
        setattr(message, str(attr), number)
        # Persist write-only fields so a later set re-seeds them from state
        # instead of resetting them to 0 (the device never reports them back).
        if attr in _WRITE_ONLY:
            self._attributes[attr] = number
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea e9 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaE9Device):
    """Midea e9 appliance."""

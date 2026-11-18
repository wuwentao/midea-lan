"""Midea lan e7 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    FIRE_LEVEL_HIGH,
    FIRE_LEVEL_LOW,
    FUNCTION_NO_HIGH_16,
    FUNCTION_NO_HIGH_32,
    FUNCTION_NO_LOW,
    TIME_HR_HIGH,
    TIME_HR_LOW,
    TIME_MIN_HIGH,
    TIME_MIN_LOW,
    WORK_STATUS_HIGH,
    WORK_STATUS_LOW,
    MessageE7Response,
    MessageQuery,
    MessageSet,
    is_32bit_layout,
    soft_version_for_subtype,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea e7 device attributes."""

    response = "response"
    work_status = "work_status"
    function_no = "function_no"
    time_running_hr = "time_running_hr"
    time_running_min = "time_running_min"
    time_surplus_hr = "time_surplus_hr"
    time_surplus_min = "time_surplus_min"
    time_reserve_hr = "time_reserve_hr"
    time_reserve_min = "time_reserve_min"
    fire_level = "fire_level"
    definite_time_hr = "definite_time_hr"
    definite_time_min = "definite_time_min"
    work_stage = "work_stage"
    error_code = "error_code"


# Writable control params that share one fixed range across layouts (Lua bounds).
_FIXED_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.work_status: (WORK_STATUS_LOW, WORK_STATUS_HIGH),
    DeviceAttributes.time_reserve_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.time_reserve_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.fire_level: (FIRE_LEVEL_LOW, FIRE_LEVEL_HIGH),
    DeviceAttributes.definite_time_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.definite_time_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
}
# function_no range depends on the frame width (16-bit vs 32-bit layout).
_SEED_ATTRS = (DeviceAttributes.function_no, *_FIXED_RANGES)


class MideaE7Device(MideaDevice):
    """Midea e7 device (steam / warming cooking appliance)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea e7 device."""
        super().__init__(
            device_type=DeviceType.E7,
            **kwargs,
            attributes={
                DeviceAttributes.response: None,
                DeviceAttributes.work_status: None,
                DeviceAttributes.function_no: None,
                DeviceAttributes.time_running_hr: None,
                DeviceAttributes.time_running_min: None,
                DeviceAttributes.time_surplus_hr: None,
                DeviceAttributes.time_surplus_min: None,
                DeviceAttributes.time_reserve_hr: None,
                DeviceAttributes.time_reserve_min: None,
                DeviceAttributes.fire_level: None,
                DeviceAttributes.definite_time_hr: None,
                DeviceAttributes.definite_time_min: None,
                DeviceAttributes.work_stage: None,
                DeviceAttributes.error_code: None,
            },
        )
        # The frame layout (16-bit vs 32-bit function_no) is keyed off the
        # device subtype, mirroring the Lua getSoftVersion mapping.
        self._soft_version = soft_version_for_subtype(self.subtype)
        self.set_customize(customize)

    @property
    def _function_no_high(self) -> int:
        """Upper bound for function_no in the active layout."""
        if is_32bit_layout(self._soft_version):
            return FUNCTION_NO_HIGH_32
        return FUNCTION_NO_HIGH_16

    def _range_for(self, attr: str) -> tuple[int, int]:
        """Return the accepted inclusive range for a writable attribute."""
        if attr == DeviceAttributes.function_no:
            return (FUNCTION_NO_LOW, self._function_no_high)
        return _FIXED_RANGES[attr]

    def build_query(self) -> list[MessageQuery]:
        """Midea e7 device build query."""
        return [MessageQuery(self._soft_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea e7 device process message."""
        message = MessageE7Response(msg, self._soft_version)
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
        message = MessageSet(self._soft_version)
        for key in _SEED_ATTRS:
            current = self._attributes[key]
            if isinstance(current, int) and not isinstance(current, bool):
                setattr(message, str(key), current)
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea e7 device set attribute."""
        if attr != DeviceAttributes.function_no and attr not in _FIXED_RANGES:
            # response / running / surplus time / work_stage / error_code are
            # read-only report fields.
            return
        low, high = self._range_for(attr)
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"[e7] {attr} expects a number"
            raise ValueWrongType(msg)
        number = int(value)
        if not low <= number <= high:
            msg = f"[e7] {attr} must be in [{low}, {high}]"
            raise ValueOutOfRange(msg)
        message = self._make_message_set()
        setattr(message, str(attr), number)
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea e7 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaE7Device):
    """Midea e7 appliance."""

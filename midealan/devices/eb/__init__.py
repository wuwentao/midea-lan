"""Midea lan eb device."""

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
    TIME_HR_HIGH,
    TIME_HR_LOW,
    TIME_MIN_HIGH,
    TIME_MIN_LOW,
    MessageEBResponse,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

# function_no is a 16-bit menu/function identifier (Lua bit-packed 2 bytes).
FUNCTION_NO_MIN = 0
FUNCTION_NO_MAX = 0xFFFF
# work_status is a single status byte (Lua BYTE_STATUS_* 0..9).
WORK_STATUS_MIN = 0
WORK_STATUS_MAX = 0xFF


class DeviceAttributes(StrEnum):
    """Midea eb device attributes."""

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


# Writable control params and their accepted inclusive ranges (Lua bounds).
_SETTABLE_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.function_no: (FUNCTION_NO_MIN, FUNCTION_NO_MAX),
    DeviceAttributes.work_status: (WORK_STATUS_MIN, WORK_STATUS_MAX),
    DeviceAttributes.time_reserve_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.time_reserve_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
    DeviceAttributes.fire_level: (FIRE_LEVEL_LOW, FIRE_LEVEL_HIGH),
    DeviceAttributes.definite_time_hr: (TIME_HR_LOW, TIME_HR_HIGH),
    DeviceAttributes.definite_time_min: (TIME_MIN_LOW, TIME_MIN_HIGH),
}


class MideaEBDevice(MideaDevice):
    """Midea eb device (steam / warming cooking appliance)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea eb device."""
        super().__init__(
            device_type=DeviceType.EB,
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
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea eb device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea eb device process message."""
        message = MessageEBResponse(msg)
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
        for key in _SETTABLE_RANGES:
            current = self._attributes[key]
            if isinstance(current, int):
                setattr(message, str(key), current)
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea eb device set attribute."""
        if attr not in _SETTABLE_RANGES:
            # response / running / surplus time / work_stage / error_code are
            # read-only report fields.
            return
        low, high = _SETTABLE_RANGES[attr]
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"[eb] {attr} expects a number"
            raise ValueWrongType(msg)
        number = int(value)
        if not low <= number <= high:
            msg = f"[eb] {attr} must be in [{low}, {high}]"
            raise ValueOutOfRange(msg)
        message = self._make_message_set()
        setattr(message, str(attr), number)
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea eb device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaEBDevice):
    """Midea eb appliance."""

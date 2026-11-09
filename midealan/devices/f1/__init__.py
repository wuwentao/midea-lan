"""Midea lan f1 device."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    CODE_ID_HIGH,
    CODE_ID_LOW,
    MODE_HIGH,
    MODE_LOW,
    SPEED_HIGH,
    SPEED_LOW,
    TEMP_HIGH,
    TEMP_LOW,
    TIME_16_HIGH,
    TIME_16_LOW,
    WARM_TIME_HIGH,
    WARM_TIME_LOW,
    MessageF1Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea f1 device attributes."""

    work_mode = "work_mode"
    code_id = "code_id"
    power = "power"
    error_code = "error_code"
    response_type = "response_type"
    work_status = "work_status"
    step_status = "step_status"
    work_stage = "work_stage"
    lid_status = "lid_status"
    cup_status = "cup_status"
    current_time = "current_time"
    current_temp = "current_temp"
    speed = "speed"
    set_work_temp = "set_work_temp"
    set_keep_warm_temp = "set_keep_warm_temp"
    appoint_time = "appoint_time"
    set_work_time = "set_work_time"
    set_keep_warm_time = "set_keep_warm_time"


# Numeric control params and their accepted inclusive ranges (Lua bounds).
_NUMERIC_RANGES: dict[str, tuple[int, int]] = {
    DeviceAttributes.work_mode: (MODE_LOW, MODE_HIGH),
    DeviceAttributes.code_id: (CODE_ID_LOW, CODE_ID_HIGH),
    DeviceAttributes.appoint_time: (TIME_16_LOW, TIME_16_HIGH),
    DeviceAttributes.set_work_time: (TIME_16_LOW, TIME_16_HIGH),
    DeviceAttributes.set_keep_warm_time: (WARM_TIME_LOW, WARM_TIME_HIGH),
    DeviceAttributes.set_keep_warm_temp: (TEMP_LOW, TEMP_HIGH),
    DeviceAttributes.set_work_temp: (TEMP_LOW, TEMP_HIGH),
    DeviceAttributes.speed: (SPEED_LOW, SPEED_HIGH),
}
# All writable control params (power + numeric).
_SETTABLE = {DeviceAttributes.power} | set(_NUMERIC_RANGES)


class MideaF1Device(MideaDevice):
    """Midea f1 device (tea / beverage brewer)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea f1 device."""
        super().__init__(
            device_type=DeviceType.F1,
            **kwargs,
            attributes={
                DeviceAttributes.work_mode: None,
                DeviceAttributes.code_id: None,
                DeviceAttributes.power: None,
                DeviceAttributes.error_code: None,
                DeviceAttributes.response_type: None,
                DeviceAttributes.work_status: None,
                DeviceAttributes.step_status: None,
                DeviceAttributes.work_stage: None,
                DeviceAttributes.lid_status: None,
                DeviceAttributes.cup_status: None,
                DeviceAttributes.current_time: None,
                DeviceAttributes.current_temp: None,
                DeviceAttributes.speed: None,
                DeviceAttributes.set_work_temp: None,
                DeviceAttributes.set_keep_warm_temp: None,
                DeviceAttributes.appoint_time: None,
                DeviceAttributes.set_work_time: None,
                DeviceAttributes.set_keep_warm_time: None,
            },
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea f1 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea f1 device process message."""
        message = MessageF1Response(msg)
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
        for key in _NUMERIC_RANGES:
            current = self._attributes[key]
            if isinstance(current, int):
                setattr(message, str(key), current)
        power = self._attributes[DeviceAttributes.power]
        if isinstance(power, bool):
            message.power = power
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea f1 device set attribute."""
        if attr not in _SETTABLE:
            # error_code / response_type / work_status / step_status /
            # work_stage / lid_status / cup_status / current_* are read-only.
            return
        message = self._make_message_set()
        if attr == DeviceAttributes.power:
            message.power = bool(value)
        else:
            low, high = _NUMERIC_RANGES[attr]
            if isinstance(value, bool) or not isinstance(value, int | float):
                msg = f"[f1] {attr} expects a number"
                raise ValueWrongType(msg)
            number = int(value)
            if not low <= number <= high:
                msg = f"[f1] {attr} must be in [{low}, {high}]"
                raise ValueOutOfRange(msg)
            setattr(message, str(attr), number)
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea f1 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaF1Device):
    """Midea f1 appliance."""

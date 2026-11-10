"""Midea lan b7 device.

0xB7 智能燃气灶 (dual-burner smart gas stove / cooktop). This package implements a
read-only status subset plus the simple per-burner controls, per the reviewed
scope decision. The following Lua features are intentionally NOT implemented and
are left as FUTURE work (they are cloud-only or need a product decision on entity
shape):

- the variable-length ``pots[]`` bound-induction-pot array in the status report;
- Bluetooth device enumeration (query/report 0x37 / 0x47);
- recipe/menu download (command 0xCA, cloud-only: carries an md5 + URL);
- MAC binding (command 0x27);
- ``work_burner_control`` 4/5/6 (pot menu step / menu download / pot binding).
"""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    BURNER_LEFT,
    BURNER_RIGHT,
    FUNCTION_GEAR,
    FUNCTION_POWER,
    FUNCTION_TEMP_MIN,
    GEAR_MAX,
    GEAR_MIN,
    TEMP_MAX,
    TEMP_MIN,
    MessageB7Response,
    MessageQueryError,
    MessageQueryStatus,
    MessageSet,
    MessageSetLock,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea b7 device attributes."""

    # --- read-only status (query 0x31 / notify 0x41) ---
    left_status = "left_status"
    right_status = "right_status"
    left_gear = "left_gear"
    right_gear = "right_gear"
    left_surplus_hours = "left_surplus_hours"
    left_surplus_minutes = "left_surplus_minutes"
    right_surplus_hours = "right_surplus_hours"
    right_surplus_minutes = "right_surplus_minutes"
    left_work_hours = "left_work_hours"
    left_work_minutes = "left_work_minutes"
    left_work_seconds = "left_work_seconds"
    right_work_hours = "right_work_hours"
    right_work_minutes = "right_work_minutes"
    right_work_seconds = "right_work_seconds"
    left_work_mode = "left_work_mode"
    right_work_mode = "right_work_mode"
    left_temp = "left_temp"
    right_temp = "right_temp"
    left_smart_bl = "left_smart_bl"
    right_smart_bl = "right_smart_bl"
    gas_warn = "gas_warn"
    menu_mark = "menu_mark"
    # --- read-only error / tips (query 0x32) ---
    error_code = "error_code"
    tips_code = "tips_code"
    # --- writable controls (flat per-burner, one HA entity each) ---
    lock = "lock"
    left_power = "left_power"
    right_power = "right_power"
    left_gear_set = "left_gear_set"
    right_gear_set = "right_gear_set"
    left_temp_set = "left_temp_set"
    right_temp_set = "right_temp_set"


# Writable control attributes and their burner selector.
_POWER_ATTRS = {
    DeviceAttributes.left_power: BURNER_LEFT,
    DeviceAttributes.right_power: BURNER_RIGHT,
}
_GEAR_ATTRS = {
    DeviceAttributes.left_gear_set: BURNER_LEFT,
    DeviceAttributes.right_gear_set: BURNER_RIGHT,
}
_TEMP_ATTRS = {
    DeviceAttributes.left_temp_set: BURNER_LEFT,
    DeviceAttributes.right_temp_set: BURNER_RIGHT,
}
# Every attribute the user may write; anything else is a read-only sensor.
_WRITABLE = (
    {DeviceAttributes.lock}
    | set(_POWER_ATTRS)
    | set(_GEAR_ATTRS)
    | set(_TEMP_ATTRS)
)


class MideaB7Device(MideaDevice):
    """Midea b7 device (smart gas stove)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea b7 device."""
        super().__init__(
            device_type=DeviceType.B7,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQueryStatus | MessageQueryError]:
        """Midea b7 device build query (status + error)."""
        return [
            MessageQueryStatus(self._message_protocol_version),
            MessageQueryError(self._message_protocol_version),
        ]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea b7 device process message."""
        message = MessageB7Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def _set_power(self, burner: int) -> None:
        # The Lua power path writes burner selector + function_control = 1 only;
        # there is no separate on/off value, so this is a momentary action
        # (ignite / toggle) rather than a stateful switch.
        message = MessageSet(self._message_protocol_version)
        message.burner = burner
        message.function_control = FUNCTION_POWER
        self.build_send(message)

    def _set_gear(self, burner: int, value: int) -> None:
        if not GEAR_MIN <= value <= GEAR_MAX:
            msg = f"[b7] gear must be in [{GEAR_MIN}, {GEAR_MAX}]"
            raise ValueOutOfRange(msg)
        message = MessageSet(self._message_protocol_version)
        message.burner = burner
        message.function_control = FUNCTION_GEAR
        message.gear = value
        self.build_send(message)

    def _set_temp(self, burner: int, value: int) -> None:
        if not TEMP_MIN <= value <= TEMP_MAX:
            msg = f"[b7] temperature must be in [{TEMP_MIN}, {TEMP_MAX}]"
            raise ValueOutOfRange(msg)
        message = MessageSet(self._message_protocol_version)
        message.burner = burner
        message.function_control = FUNCTION_TEMP_MIN  # temp-set function (11)
        if burner == BURNER_LEFT:
            message.left_temp = value
        else:
            message.right_temp = value
        self.build_send(message)

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea b7 device set attribute."""
        if attr not in _WRITABLE:
            # All status / error attributes are read-only sensors.
            return
        if attr == DeviceAttributes.lock:
            message = MessageSetLock(self._message_protocol_version)
            message.lock = bool(value)
            self.build_send(message)
        elif attr in _POWER_ATTRS:
            # Momentary ignite/toggle: value is ignored (no on/off in protocol).
            self._set_power(_POWER_ATTRS[DeviceAttributes(attr)])
        elif attr in _GEAR_ATTRS:
            number = self._as_int(attr, value)
            self._set_gear(_GEAR_ATTRS[DeviceAttributes(attr)], number)
        else:  # temperature set
            number = self._as_int(attr, value)
            self._set_temp(_TEMP_ATTRS[DeviceAttributes(attr)], number)

    @staticmethod
    def _as_int(attr: str, value: bool | float | str) -> int:
        """Coerce a numeric control value to int, rejecting bool/str."""
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"[b7] {attr} expects a number"
            raise ValueWrongType(msg)
        return int(value)

    def set_customize(self, customize: str) -> None:
        """Midea b7 device set customize."""
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


class MideaAppliance(MideaB7Device):
    """Midea b7 appliance."""

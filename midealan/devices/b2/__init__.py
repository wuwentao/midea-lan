"""Midea lan b2 device."""

import json
import logging
import threading
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    LOCK_OFF,
    LOCK_ON,
    MODE_CODES,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WORK_HOUR_MAX,
    WORK_HOUR_MIN,
    WORK_MINUTE_MAX,
    WORK_MINUTE_MIN,
    WORK_STATUS_CODES,
    MessageB2Response,
    MessageQuery,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)

# Numeric cook params and their accepted inclusive ranges (Lua checkBoundary).
_PARAM_RANGES: dict[str, tuple[int, int]] = {
    "work_hour": (WORK_HOUR_MIN, WORK_HOUR_MAX),
    "work_minute": (WORK_MINUTE_MIN, WORK_MINUTE_MAX),
    "temperature": (TEMPERATURE_MIN, TEMPERATURE_MAX),
}


class DeviceAttributes(StrEnum):
    """Midea b2 device attributes."""

    work_status = "work_status"
    work_mode = "work_mode"
    work_hour = "work_hour"
    work_minute = "work_minute"
    temperature = "temperature"
    door_state = "door_state"
    water_state = "water_state"
    box_state = "box_state"
    lock = "lock"


_WRITABLE_ATTRS = (
    DeviceAttributes.work_status,
    DeviceAttributes.work_mode,
    DeviceAttributes.work_hour,
    DeviceAttributes.work_minute,
    DeviceAttributes.temperature,
    DeviceAttributes.lock,
)


class MideaB2Device(MideaDevice):
    """Midea b2 device (steam box / steam oven)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea b2 device."""
        super().__init__(
            device_type=DeviceType.B2,
            **kwargs,
            attributes={
                DeviceAttributes.work_status: None,
                DeviceAttributes.work_mode: None,
                DeviceAttributes.work_hour: None,
                DeviceAttributes.work_minute: None,
                DeviceAttributes.temperature: None,
                DeviceAttributes.door_state: None,
                DeviceAttributes.water_state: None,
                DeviceAttributes.box_state: None,
                DeviceAttributes.lock: None,
            },
        )
        # A B2 control frame carries every writable field. Keep successful
        # writes pending until a report confirms them so a rapid follow-up
        # write does not rebuild the frame from stale reported state.
        self._pending_controls: dict[str, bool | int | str] = {}
        self._pending_controls_lock = threading.RLock()
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea b2 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea b2 device process message."""
        message = MessageB2Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                status_key = str(status)
                with self._pending_controls_lock:
                    if self._pending_controls.get(status_key) == value:
                        del self._pending_controls[status_key]
                new_status[status_key] = value
        return new_status

    def _make_message_set(self) -> MessageSet:
        """Build a control message seeded from the current device state."""
        message = MessageSet(self._message_protocol_version)
        with self._pending_controls_lock:
            controls = {
                key: self._pending_controls.get(str(key), self._attributes[key])
                for key in _WRITABLE_ATTRS
            }
            status = controls[DeviceAttributes.work_status]
            if isinstance(status, str) and status in WORK_STATUS_CODES:
                message.work_status = WORK_STATUS_CODES[status]
            mode = controls[DeviceAttributes.work_mode]
            if isinstance(mode, str) and mode in MODE_CODES:
                message.work_mode = MODE_CODES[mode]
            for key in (
                DeviceAttributes.work_hour,
                DeviceAttributes.work_minute,
                DeviceAttributes.temperature,
            ):
                current = controls[key]
                if isinstance(current, int) and not isinstance(current, bool):
                    setattr(message, str(key), current)
            lock = controls[DeviceAttributes.lock]
            message.lock = LOCK_ON if lock else LOCK_OFF
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea b2 device set attribute."""
        # door_state / water_state / box_state are read-only sensors.
        if attr in (
            DeviceAttributes.door_state,
            DeviceAttributes.water_state,
            DeviceAttributes.box_state,
        ):
            return
        if attr == DeviceAttributes.work_status:
            if not isinstance(value, str) or value not in WORK_STATUS_CODES:
                msg = "[b2] work_status is not a recognized value"
                raise ValueWrongType(msg)
        elif attr == DeviceAttributes.work_mode:
            if not isinstance(value, str) or value not in MODE_CODES:
                msg = "[b2] work_mode is not a recognized value"
                raise ValueWrongType(msg)
        elif attr == DeviceAttributes.lock:
            value = bool(value)
        else:  # work_hour / work_minute / temperature
            low, high = _PARAM_RANGES[attr]
            if isinstance(value, bool) or not isinstance(value, int | float):
                msg = f"[b2] {attr} expects a number"
                raise ValueWrongType(msg)
            number = int(value)
            if not low <= number <= high:
                msg = f"[b2] {attr} must be in [{low}, {high}]"
                raise ValueOutOfRange(msg)
            value = number
        attr_key = str(attr)
        with self._pending_controls_lock:
            previous_pending = self._pending_controls.copy()
            self._pending_controls[attr_key] = value
            message = self._make_message_set()
            try:
                self.build_send(message)
            except Exception:
                if attr_key in previous_pending:
                    self._pending_controls[attr_key] = previous_pending[attr_key]
                else:
                    del self._pending_controls[attr_key]
                raise

    def set_customize(self, customize: str) -> None:
        """Midea b2 device set customize (JSON, same style as other appliances)."""
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


class MideaAppliance(MideaB2Device):
    """Midea b2 appliance."""

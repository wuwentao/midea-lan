"""Midea lan b2 device."""

import json
import logging
from collections import deque
from enum import StrEnum
from threading import RLock
from typing import Any, NamedTuple, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType

from .message import (
    CONTROL_BODY_LEN,
    LOCK_BYTE,
    LOCK_OFF,
    LOCK_ON,
    MODE_CODES,
    REPORT_MIN_LEN,
    TEMPERATURE_BYTE,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WORK_HOUR_BYTE,
    WORK_HOUR_MAX,
    WORK_HOUR_MIN,
    WORK_MINUTE_BYTE,
    WORK_MINUTE_MAX,
    WORK_MINUTE_MIN,
    WORK_MODE_BYTE,
    WORK_STATUS_BYTE,
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

type _ControlValue = bool | int | str
type _ControlSnapshot = tuple[int, int, int, int, int, int]


class _PendingControlFrame(NamedTuple):
    """One transmitted full-control frame awaiting its ordered echo."""

    snapshot: _ControlSnapshot
    attr: str
    value: _ControlValue


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
        self._pending_controls: dict[str, deque[_ControlValue]] = {}
        self._pending_control_frames: deque[_PendingControlFrame] = deque()
        # Reports run on the asyncio stream loop, while synchronous setters may
        # run in an executor thread. asyncio.Lock cannot protect both call paths;
        # this lock covers only state/frame construction, never awaited I/O.
        self._pending_controls_lock = RLock()
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea b2 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def reset_init_query(self) -> None:
        """Discard controls that belonged to the invalidated connection."""
        super().reset_init_query()
        with self._pending_controls_lock:
            self._pending_controls.clear()
            self._pending_control_frames.clear()

    @staticmethod
    def _control_snapshot(message: MessageSet) -> _ControlSnapshot:
        """Return the writable wire fields from a transmitted control."""
        body = message.body
        return (
            body[WORK_STATUS_BYTE],
            body[WORK_MODE_BYTE],
            body[WORK_HOUR_BYTE],
            body[WORK_MINUTE_BYTE],
            body[TEMPERATURE_BYTE],
            body[CONTROL_BODY_LEN - 1],
        )

    @staticmethod
    def _echo_snapshot(message: MessageB2Response) -> _ControlSnapshot:
        """Return the writable wire fields from a full control echo."""
        body = message.body
        return (
            body[WORK_STATUS_BYTE],
            body[WORK_MODE_BYTE],
            body[WORK_HOUR_BYTE],
            body[WORK_MINUTE_BYTE],
            body[TEMPERATURE_BYTE],
            body[LOCK_BYTE],
        )

    def _confirm_control_frame(self, snapshot: _ControlSnapshot) -> None:
        """Confirm writes through the first transmitted frame matching an echo."""
        confirmed_count = 0
        for index, pending_frame in enumerate(self._pending_control_frames):
            if pending_frame.snapshot == snapshot:
                confirmed_count = index + 1
                break
        for _ in range(confirmed_count):
            confirmed_frame = self._pending_control_frames.popleft()
            pending = self._pending_controls[confirmed_frame.attr]
            pending.popleft()
            if not pending:
                del self._pending_controls[confirmed_frame.attr]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea b2 device process message."""
        message = MessageB2Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        with self._pending_controls_lock:
            for status in self._attributes:
                if hasattr(message, str(status)):
                    value = getattr(message, str(status))
                    self._attributes[status] = value
                    status_key = str(status)
                    new_status[status_key] = value
            if (
                message.message_type == MessageType.set
                and len(message.body) >= REPORT_MIN_LEN
            ):
                self._confirm_control_frame(self._echo_snapshot(message))
        return new_status

    def _make_message_set(self) -> MessageSet:
        """Build a control message seeded from the current device state."""
        message = MessageSet(self._message_protocol_version)
        with self._pending_controls_lock:
            controls = {
                key: pending[-1]
                if (pending := self._pending_controls.get(str(key)))
                else self._attributes[key]
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
            pending = self._pending_controls.setdefault(attr_key, deque())
            pending.append(value)
            message = self._make_message_set()
            pending_frame = _PendingControlFrame(
                snapshot=self._control_snapshot(message),
                attr=attr_key,
                value=value,
            )
            self._pending_control_frames.append(pending_frame)
            try:
                self.build_send(message)
            except Exception:
                self._pending_control_frames.pop()
                pending.pop()
                if not pending:
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

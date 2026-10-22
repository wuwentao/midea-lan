"""Midea lan E1 device."""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Unpack, cast

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

if TYPE_CHECKING:
    from collections.abc import Callable

from .message import (
    WORK_STATUS_CANCEL,
    WORK_STATUS_CANCEL_ORDER,
    WORK_STATUS_ORDER,
    WORK_STATUS_WORK,
    MessageE1Response,
    MessageLock,
    MessageOperator,
    MessagePower,
    MessageQuery,
    MessageStorage,
    MessageWork,
)

_LOGGER = logging.getLogger(__name__)

MAX_DELAY_MINUTES = 24 * 60


class DeviceAttributes(StrEnum):
    """Midea E1 device attributes."""

    power = "power"
    status = "status"
    mode = "mode"
    additional = "additional"
    door = "door"
    rinse_aid = "rinse_aid"
    salt = "salt"
    child_lock = "child_lock"
    uv = "uv"
    dry = "dry"
    dry_status = "dry_status"
    storage = "storage"
    storage_status = "storage_status"
    time_remaining = "time_remaining"
    progress = "progress"
    storage_remaining = "storage_remaining"
    temperature = "temperature"
    humidity = "humidity"
    waterswitch = "waterswitch"
    water_lack = "water_lack"
    error_code = "error_code"
    softwater = "softwater"
    wrong_operation = "wrong_operation"
    bright = "bright"
    door_auto_open = "door_auto_open"
    delay_remaining = "delay_remaining"
    delay_minutes = "delay_minutes"
    # Settings for the next start, kept apart from the reported state
    program = "program"
    door_auto_open_setting = "door_auto_open_setting"
    additional_setting = "additional_setting"
    wash_region_setting = "wash_region_setting"
    water_level_setting = "water_level_setting"
    water_strong_level_setting = "water_strong_level_setting"
    # Sensors (read-only), decoded from the status reply
    operator = "operator"
    wash_region = "wash_region"
    water_level = "water_level"
    water_strong_level = "water_strong_level"
    dry_set_min = "dry_set_min"
    clean_left_hour = "clean_left_hour"
    kitchenware_left_hour = "kitchenware_left_hour"
    device_version = "device_version"
    wifi_unabled = "wifi_unabled"
    auto_throw = "auto_throw"
    throw_percent = "throw_percent"
    lock_power = "lock_power"
    beep_control = "beep_control"
    light_btn_on = "light_btn_on"
    light_strip_on = "light_strip_on"


# Work-command triggers accepted through set_attribute("status", ...). The keys
# mirror the names exposed in the "status" attribute (see self._status) plus the
# plain "work"/"order" aliases.
STATUS_WORK = "work"
STATUS_RUNNING = "running"
STATUS_CANCEL = "cancel"
STATUS_ORDER = "order"
STATUS_DELAY = "delay"
STATUS_CANCEL_ORDER = "cancel_order"
# Operator triggers accepted through set_attribute("status", ...) / "operator".
STATUS_PAUSE = "pause"
STATUS_RESUME = "resume"
STATUS_START = "start"

# Single-byte wash parameters stored and sent with the next work command.
MAX_BYTE_VALUE = 0xFF
# Each maps to the readable setting for the next start, kept apart from the
# value the device reports.
_WASH_PARAM_SETTINGS = {
    DeviceAttributes.additional: DeviceAttributes.additional_setting,
    DeviceAttributes.wash_region: DeviceAttributes.wash_region_setting,
    DeviceAttributes.water_level: DeviceAttributes.water_level_setting,
    DeviceAttributes.water_strong_level: DeviceAttributes.water_strong_level_setting,
}
_WASH_PARAM_ATTRS = frozenset(_WASH_PARAM_SETTINGS)
_SETTING_TO_WASH_PARAM = {v: k for k, v in _WASH_PARAM_SETTINGS.items()}


class MideaE1Device(MideaDevice):
    """Midea E1 device."""

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea E1 device."""
        super().__init__(
            device_type=DeviceType.E1,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.status: None,
                DeviceAttributes.mode: 0,
                DeviceAttributes.additional: 0,
                DeviceAttributes.uv: False,
                DeviceAttributes.dry: False,
                DeviceAttributes.dry_status: False,
                DeviceAttributes.door: False,
                DeviceAttributes.rinse_aid: False,
                DeviceAttributes.salt: False,
                DeviceAttributes.child_lock: False,
                DeviceAttributes.storage: False,
                DeviceAttributes.storage_status: False,
                DeviceAttributes.time_remaining: None,
                DeviceAttributes.progress: None,
                DeviceAttributes.storage_remaining: None,
                DeviceAttributes.temperature: None,
                DeviceAttributes.humidity: None,
                DeviceAttributes.waterswitch: False,
                DeviceAttributes.water_lack: False,
                DeviceAttributes.error_code: None,
                DeviceAttributes.softwater: 0,
                DeviceAttributes.wrong_operation: None,
                DeviceAttributes.bright: 0,
                DeviceAttributes.door_auto_open: False,
                DeviceAttributes.delay_remaining: 0,
                DeviceAttributes.delay_minutes: 0,
                DeviceAttributes.program: None,
                DeviceAttributes.door_auto_open_setting: False,
                DeviceAttributes.additional_setting: 0,
                DeviceAttributes.wash_region_setting: 0,
                DeviceAttributes.water_level_setting: 0,
                DeviceAttributes.water_strong_level_setting: 0,
                DeviceAttributes.operator: None,
                DeviceAttributes.wash_region: 0,
                DeviceAttributes.water_level: None,
                DeviceAttributes.water_strong_level: None,
                DeviceAttributes.dry_set_min: None,
                DeviceAttributes.clean_left_hour: None,
                DeviceAttributes.kitchenware_left_hour: None,
                DeviceAttributes.device_version: None,
                DeviceAttributes.wifi_unabled: None,
                DeviceAttributes.auto_throw: None,
                DeviceAttributes.throw_percent: None,
                DeviceAttributes.lock_power: None,
                DeviceAttributes.beep_control: None,
                DeviceAttributes.light_btn_on: None,
                DeviceAttributes.light_strip_on: None,
            },
        )
        self._modes = {
            0x00: "neutral_gear",  # BYTE_MODE_NEUTRAL_GEAR
            0x01: "auto_wash",  # BYTE_MODE_AUTO_WASH
            0x02: "strong_wash",  # BYTE_MODE_STRONG_WASH
            0x03: "standard_wash",  # BYTE_MODE_STANDARD_WASH
            0x04: "eco_wash",  # BYTE_MODE_ECO_WASH
            0x05: "glass_wash",  # BYTE_MODE_GLASS_WASH
            0x06: "hour_wash",  # BYTE_MODE_HOUR_WASH
            0x07: "fast_wash",  # BYTE_MODE_FAST_WASH
            0x08: "soak_wash",  # BYTE_MODE_SOAK_WASH
            0x09: "90min",  # BYTE_MODE_90MIN_WASH
            0x0A: "self_clean",  # BYTE_MODE_SELF_CLEAN
            0x0B: "fruit_wash",  # BYTE_MODE_FRUIT_WASH
            0x0C: "self_define",  # BYTE_MODE_SELF_DEFINE
            0x0D: "germ",  # BYTE_MODE_GERM ???
            0x0E: "bowl_wash",  # BYTE_MODE_BOWL_WASH
            0x0F: "kill_germ",  # BYTE_MODE_KILL_GERM
            0x10: "sea_food_wash",  # BYTE_MODE_SEA_FOOD_WASH
            0x12: "hot_pot_wash",  # BYTE_MODE_HOT_POT_WASH
            0x13: "quiet_night_wash",  # BYTE_MODE_QUIET_NIGHT_WASH
            0x14: "less_wash",  # BYTE_MODE_LESS_WASH
            0x15: "max_rapid_wash",  # BYTE_MODE_MAX_RAPID_WASH
            0x16: "oil_net_wash",  # BYTE_MODE_OIL_NET_WASH
            0x19: "cloud_wash",  # BYTE_MODE_CLOUD_WASH
            0x1B: "single_dry",  # BYTE_MODE_SINGLE_DRY
            0x1C: "single_disinfect",  # BYTE_MODE_SINGLE_DISINFECT
            0x1D: "wahin_wash_dry",  # BYTE_MODE_WAHIN_WASH_DRY
            0x1E: "high_temp_wash",  # BYTE_MODE_HIGH_TEMP_WASH
            0x1F: "wash_dry",  # BYTE_MODE_WASH_DRY
        }
        self._status = {
            0x00: "power_off",
            0x01: "cancel",
            0x02: "delay",
            0x03: "running",
            0x04: "error",
            0x05: "soft_gear",
        }
        self._progress = {
            0x00: "idle",
            0x01: "pre_wash",
            0x02: "wash",
            0x03: "rinse",
            0x04: "dry",
            0x05: "complete",
        }
        # Door auto-open to send with the next work/order command. Kept apart
        # from the door_auto_open attribute, which status replies overwrite.
        self._door_auto_open_setting = False
        # Wash parameters to send with the next work/order command. Kept apart
        # from their reported attributes, which status replies overwrite.
        self._wash_param_settings: dict[DeviceAttributes, int] = dict.fromkeys(
            _WASH_PARAM_ATTRS,
            0,
        )

    @property
    def modes(self) -> dict[int, str]:
        """Return supported work modes.

        Returns
        -------
        Mapping of mode codes to names.

        """
        return self._modes.copy()

    def build_query(self) -> list[MessageQuery]:
        """Midea E1 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def _check_mode(self, mode: int) -> None:
        if mode not in self._modes:
            msg = f"[e1] Unsupported work mode: {mode}"
            raise ValueWrongType(msg)

    def _current_mode(self) -> int:
        """Return the code of the current work mode, 0 if unknown."""
        mode_name = self.get_attribute(DeviceAttributes.mode)
        return next(
            (code for code, name in self._modes.items() if name == mode_name),
            0,
        )

    def _resolve_mode(self, mode: object) -> int:
        """Return the mode code for a code or name, validated."""
        if isinstance(mode, str):
            mode = next(
                (code for code, name in self._modes.items() if name == mode),
                -1,
            )
        if isinstance(mode, bool) or not isinstance(mode, int):
            msg = f"[e1] Unsupported work mode: {mode}"
            raise ValueWrongType(msg)
        self._check_mode(mode)
        return mode

    def _check_delay(self, minutes: object) -> None:
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, int)
            or not 0 < minutes <= MAX_DELAY_MINUTES
        ):
            msg = f"[e1] Delay must be 1 to {MAX_DELAY_MINUTES} minutes: {minutes}"
            raise ValueWrongType(msg)

    def _check_byte(self, attr: str, value: object) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= MAX_BYTE_VALUE
        ):
            msg = f"[e1] {attr} must be 0 to {MAX_BYTE_VALUE}: {value}"
            raise ValueWrongType(msg)
        return value

    def make_message_set(
        self,
        work_status: int,
        *,
        mode: int | None = None,
        delay_minutes: int | None = None,
        door_auto_open: bool | None = None,
    ) -> MessageWork:
        """Build the E1 work command from the current state.

        Explicit callers may override ``mode``, ``delay_minutes`` and
        ``door_auto_open``; anything left as ``None`` falls back to the stored
        attribute, so a plain ``set_attribute`` write reuses the device state.
        The wash parameters (additional, wash_region, water_level,
        water_strong_level) always ride along from their stored values.
        """
        message = MessageWork(self._message_protocol_version)
        message.work_status = work_status
        message.mode = self._current_mode() if mode is None else mode
        message.delay_minutes = (
            self._stored_delay_minutes() if delay_minutes is None else delay_minutes
        )
        message.door_auto_open = (
            self._stored_door_auto_open() if door_auto_open is None else door_auto_open
        )
        message.additional = self._wash_param_settings[DeviceAttributes.additional]
        message.wash_region = self._wash_param_settings[DeviceAttributes.wash_region]
        message.water_level = self._wash_param_settings[DeviceAttributes.water_level]
        message.water_strong_level = self._wash_param_settings[
            DeviceAttributes.water_strong_level
        ]
        return message

    def set_work_mode(self, mode: int | str, *, door_auto_open: bool = False) -> None:
        """Set the dishwasher work mode and start the selected program.

        ``mode`` may be a numeric code or a mode name.

        Raises
        ------
        ValueWrongType
            If the mode code is not supported.

        """
        resolved = self._resolve_mode(mode)
        if resolved == 0:
            msg = "[e1] No work mode selected"
            raise ValueWrongType(msg)
        self.build_send(
            self.make_message_set(
                WORK_STATUS_WORK,
                mode=resolved,
                door_auto_open=door_auto_open,
            ),
        )

    def start_work(self, *, door_auto_open: bool = False) -> None:
        """Start the dishwasher using its currently selected work mode.

        Raises
        ------
        ValueWrongType
            If there is no selected work mode, or the stored work mode is
            not a valid name.

        """
        mode_name = self.get_attribute(DeviceAttributes.mode)
        if mode_name is None or mode_name == 0:
            msg = "[e1] No work mode selected"
            raise ValueWrongType(msg)
        if not isinstance(mode_name, str):
            msg = "[e1] Invalid work mode"
            raise ValueWrongType(msg)

        mode = self._current_mode()
        if mode == 0:
            msg = "[e1] No work mode selected"
            raise ValueWrongType(msg)
        self.set_work_mode(mode, door_auto_open=door_auto_open)

    def cancel_work(self) -> None:
        """Cancel the running program, leaving the dishwasher on.

        A plain power off is ignored by some models while a program runs.
        """
        self.build_send(self._make_cancel(WORK_STATUS_CANCEL))

    def _cancel(self) -> None:
        """Cancel the current activity, matching the command to the state.

        A pending delayed start is cancelled with cancel_order (work_status
        0x04); a running or otherwise active program is cancelled with cancel
        (0x01). The device ignores the command that does not fit its state, so
        a plain cancel (0x01) leaves a delayed start untouched. Dispatch on the
        reported ``status`` so one "cancel" write does the right thing.
        """
        if self.get_attribute(DeviceAttributes.status) == STATUS_DELAY:
            self.cancel_delayed_start()
        else:
            self.cancel_work()

    def set_delayed_start(
        self,
        mode: int,
        minutes: int,
        *,
        door_auto_open: bool = False,
    ) -> None:
        """Start the given work mode after a delay in minutes.

        Raises
        ------
        ValueWrongType
            If the mode code is not supported or the delay is out of range.

        """
        mode = self._resolve_mode(mode)
        if mode == 0:
            msg = "[e1] No work mode selected"
            raise ValueWrongType(msg)
        self._check_delay(minutes)
        self.build_send(
            self.make_message_set(
                WORK_STATUS_ORDER,
                mode=mode,
                delay_minutes=minutes,
                door_auto_open=door_auto_open,
            ),
        )

    def cancel_delayed_start(self) -> None:
        """Cancel a pending delayed start."""
        self.build_send(self._make_cancel(WORK_STATUS_CANCEL_ORDER))

    def _make_cancel(self, work_status: int) -> MessageWork:
        """Build a cancel command with only work status and mode.

        The next-start settings (door auto-open, wash parameters) are left at
        zero, matching the cancel bodies verified on model 76000228.
        """
        message = MessageWork(self._message_protocol_version)
        message.work_status = work_status
        message.mode = self._current_mode()
        return message

    def pause_work(self) -> None:
        """Pause the running program (operator command, body type 0x83)."""
        message = MessageOperator(self._message_protocol_version)
        message.pause = True
        self.build_send(message)

    def resume_work(self) -> None:
        """Resume a paused program (operator command, body type 0x83)."""
        message = MessageOperator(self._message_protocol_version)
        message.pause = False
        self.build_send(message)

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea E1 device process message."""
        message = MessageE1Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                if status == DeviceAttributes.status:
                    self._attributes[status] = self._status.get(value)
                elif status == DeviceAttributes.progress:
                    self._attributes[status] = self._progress.get(value)
                elif status == DeviceAttributes.mode:
                    self._attributes[status] = self._modes.get(value)
                else:
                    self._attributes[status] = getattr(message, str(status))
                new_status[str(status)] = self._attributes[status]
        return new_status

    def _stored_int(self, attr: DeviceAttributes) -> int:
        """Return a stored numeric attribute as int, 0 if unset."""
        value = self.get_attribute(attr)
        return int(value) if isinstance(value, (int, bool)) else 0

    def _stored_delay_minutes(self) -> int:
        """Return the stored delay in minutes, 0 if unset."""
        return self._stored_int(DeviceAttributes.delay_minutes)

    def _stored_door_auto_open(self) -> bool:
        """Return the door auto-open setting for the next command."""
        return self._door_auto_open_setting

    def _selected_mode(self) -> int:
        """Return the program to start: the selected one, else the reported mode."""
        program = self.get_attribute(DeviceAttributes.program)
        if isinstance(program, str):
            return self._resolve_mode(program)
        return self._current_mode()

    def _start_selected(self) -> None:
        """Start the selected program, or the reported one if none is selected."""
        if self.get_attribute(DeviceAttributes.program) is None:
            self.start_work(door_auto_open=self._stored_door_auto_open())
            return
        self.set_work_mode(
            self._selected_mode(),
            door_auto_open=self._stored_door_auto_open(),
        )

    def _start_delayed(self) -> None:
        """Start a delayed program from the selected mode and stored delay."""
        self.set_delayed_start(
            self._selected_mode(),
            self._stored_delay_minutes(),
            door_auto_open=self._stored_door_auto_open(),
        )

    def _set_status(self, value: str) -> None:
        """Issue a work command from a status trigger write."""
        actions: dict[str, Callable[[], None]] = {
            STATUS_WORK: self._start_selected,
            STATUS_RUNNING: self._start_selected,
            STATUS_CANCEL: self._cancel,
            STATUS_ORDER: self._start_delayed,
            STATUS_DELAY: self._start_delayed,
            STATUS_CANCEL_ORDER: self.cancel_delayed_start,
            STATUS_PAUSE: self.pause_work,
            STATUS_RESUME: self.resume_work,
            STATUS_START: self.resume_work,
        }
        action = actions.get(value)
        if action is None:
            msg = f"[e1] Unsupported status: {value}"
            raise ValueWrongType(msg)
        action()

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea E1 device set attribute.

        Boolean toggles (power, child_lock, storage, door_auto_open) and the
        delay_minutes value are applied directly. Writing ``mode`` starts the
        selected program and ``status`` issues the matching work command
        (work/cancel/order/cancel_order), so the whole device can be driven
        through set_attribute, like e2/e6.

        ``program`` selects a program without starting it; ``status`` work and
        order then use it instead of the reported mode. ``door_auto_open_setting``
        and the ``*_setting`` wash parameters (``additional``, ``wash_region``,
        ``water_level``, ``water_strong_level``) are the readable settings for the
        next start (writing the plain names sets them too), while the plain names
        report what the device last sent.
        """
        if attr == DeviceAttributes.mode:
            self.set_work_mode(
                self._resolve_mode(value),
                door_auto_open=self._stored_door_auto_open(),
            )
            return
        if attr == DeviceAttributes.status:
            self._set_status(str(value))
            return
        if attr == DeviceAttributes.program:
            mode = self._resolve_mode(value)
            if mode == 0:
                msg = "[e1] No work mode selected"
                raise ValueWrongType(msg)
            self._attributes[DeviceAttributes.program] = self._modes[mode]
            return
        if attr in _SETTING_TO_WASH_PARAM:
            attr = _SETTING_TO_WASH_PARAM[DeviceAttributes(attr)]
        elif attr == DeviceAttributes.door_auto_open_setting:
            attr = DeviceAttributes.door_auto_open
        if attr == DeviceAttributes.delay_minutes:
            minutes = (
                int(value) if isinstance(value, float) and value.is_integer() else value
            )
            self._check_delay(minutes)
            self._attributes[DeviceAttributes.delay_minutes] = cast("int", minutes)
            return
        if attr in _WASH_PARAM_ATTRS:
            number = (
                int(value) if isinstance(value, float) and value.is_integer() else value
            )
            self._wash_param_settings[DeviceAttributes(attr)] = self._check_byte(
                attr,
                number,
            )
            param = DeviceAttributes(attr)
            self._attributes[_WASH_PARAM_SETTINGS[param]] = self._wash_param_settings[
                param
            ]
            return

        if not isinstance(value, bool):
            raise ValueWrongType("[e1] Expected bool")
        message: MessagePower | MessageLock | MessageStorage | None = None
        if attr == DeviceAttributes.door_auto_open:
            self._door_auto_open_setting = value
            self._attributes[DeviceAttributes.door_auto_open_setting] = value
        elif attr == DeviceAttributes.power:
            message = MessagePower(self._message_protocol_version)
            message.power = value
            self.build_send(message)
        elif attr == DeviceAttributes.child_lock:
            message = MessageLock(self._message_protocol_version)
            message.lock = value
            self.build_send(message)
        elif attr == DeviceAttributes.storage:
            message = MessageStorage(self._message_protocol_version)
            message.storage = value
            self.build_send(message)


class MideaAppliance(MideaE1Device):
    """Midea E1 appliance."""

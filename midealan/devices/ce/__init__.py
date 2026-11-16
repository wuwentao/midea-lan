"""Midea lan CE device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import (
    CE_MAX_WEEKDAY,
    CE_MIN_WEEKDAY,
    MessageCEResponse,
    MessageQuery,
    MessageQueryDailyTimer,
    MessageQueryWeeklyTimer,
    MessageSet,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea CE device attributes."""

    power = "power"
    mode = "mode"
    child_lock = "child_lock"
    scheduled = "scheduled"
    fan_speed = "fan_speed"
    pm25 = "pm25"
    co2 = "co2"
    current_humidity = "current_humidity"
    current_temperature = "current_temperature"
    hcho = "hcho"
    link_to_ac = "link_to_ac"
    sleep_mode = "sleep_mode"
    eco_mode = "eco_mode"
    aux_heating = "aux_heating"
    powerful_purify = "powerful_purify"
    filter_cleaning_reminder = "filter_cleaning_reminder"
    filter_change_reminder = "filter_change_reminder"
    error_code = "error_code"
    auto_set = "auto_set"
    silent_mode = "silent_mode"
    silence_level = "silence_level"
    silence_level_raw = "silence_level_raw"
    mode_raw = "mode_raw"
    target_temperature = "target_temperature"
    automatic_run_mode = "automatic_run_mode"
    daily_timer_1_enabled = "daily_timer_1_enabled"
    daily_timer_1_temperature = "daily_timer_1_temperature"
    daily_timer_1_start_hour = "daily_timer_1_start_hour"
    daily_timer_1_start_minute = "daily_timer_1_start_minute"
    daily_timer_1_end_hour = "daily_timer_1_end_hour"
    daily_timer_1_end_minute = "daily_timer_1_end_minute"
    daily_timer_2_enabled = "daily_timer_2_enabled"
    daily_timer_2_temperature = "daily_timer_2_temperature"
    daily_timer_2_start_hour = "daily_timer_2_start_hour"
    daily_timer_2_start_minute = "daily_timer_2_start_minute"
    daily_timer_2_end_hour = "daily_timer_2_end_hour"
    daily_timer_2_end_minute = "daily_timer_2_end_minute"
    daily_timer_3_enabled = "daily_timer_3_enabled"
    daily_timer_3_temperature = "daily_timer_3_temperature"
    daily_timer_3_start_hour = "daily_timer_3_start_hour"
    daily_timer_3_start_minute = "daily_timer_3_start_minute"
    daily_timer_3_end_hour = "daily_timer_3_end_hour"
    daily_timer_3_end_minute = "daily_timer_3_end_minute"
    daily_timer_4_enabled = "daily_timer_4_enabled"
    daily_timer_4_temperature = "daily_timer_4_temperature"
    daily_timer_4_start_hour = "daily_timer_4_start_hour"
    daily_timer_4_start_minute = "daily_timer_4_start_minute"
    daily_timer_4_end_hour = "daily_timer_4_end_hour"
    daily_timer_4_end_minute = "daily_timer_4_end_minute"
    daily_timer_5_enabled = "daily_timer_5_enabled"
    daily_timer_5_temperature = "daily_timer_5_temperature"
    daily_timer_5_start_hour = "daily_timer_5_start_hour"
    daily_timer_5_start_minute = "daily_timer_5_start_minute"
    daily_timer_5_end_hour = "daily_timer_5_end_hour"
    daily_timer_5_end_minute = "daily_timer_5_end_minute"
    weekly_timer_weekday = "weekly_timer_weekday"
    weekly_timer_1_enabled = "weekly_timer_1_enabled"
    weekly_timer_1_temperature = "weekly_timer_1_temperature"
    weekly_timer_1_start_hour = "weekly_timer_1_start_hour"
    weekly_timer_1_start_minute = "weekly_timer_1_start_minute"
    weekly_timer_1_end_hour = "weekly_timer_1_end_hour"
    weekly_timer_1_end_minute = "weekly_timer_1_end_minute"
    weekly_timer_2_enabled = "weekly_timer_2_enabled"
    weekly_timer_2_temperature = "weekly_timer_2_temperature"
    weekly_timer_2_start_hour = "weekly_timer_2_start_hour"
    weekly_timer_2_start_minute = "weekly_timer_2_start_minute"
    weekly_timer_2_end_hour = "weekly_timer_2_end_hour"
    weekly_timer_2_end_minute = "weekly_timer_2_end_minute"
    weekly_timer_3_enabled = "weekly_timer_3_enabled"
    weekly_timer_3_temperature = "weekly_timer_3_temperature"
    weekly_timer_3_start_hour = "weekly_timer_3_start_hour"
    weekly_timer_3_start_minute = "weekly_timer_3_start_minute"
    weekly_timer_3_end_hour = "weekly_timer_3_end_hour"
    weekly_timer_3_end_minute = "weekly_timer_3_end_minute"
    weekly_timer_4_enabled = "weekly_timer_4_enabled"
    weekly_timer_4_temperature = "weekly_timer_4_temperature"
    weekly_timer_4_start_hour = "weekly_timer_4_start_hour"
    weekly_timer_4_start_minute = "weekly_timer_4_start_minute"
    weekly_timer_4_end_hour = "weekly_timer_4_end_hour"
    weekly_timer_4_end_minute = "weekly_timer_4_end_minute"
    weekly_timer_5_enabled = "weekly_timer_5_enabled"
    weekly_timer_5_temperature = "weekly_timer_5_temperature"
    weekly_timer_5_start_hour = "weekly_timer_5_start_hour"
    weekly_timer_5_start_minute = "weekly_timer_5_start_minute"
    weekly_timer_5_end_hour = "weekly_timer_5_end_hour"
    weekly_timer_5_end_minute = "weekly_timer_5_end_minute"


COMPACT_READ_ONLY_ATTRIBUTES = (
    DeviceAttributes.auto_set,
    DeviceAttributes.silent_mode,
    DeviceAttributes.silence_level,
    DeviceAttributes.silence_level_raw,
    DeviceAttributes.mode_raw,
    DeviceAttributes.target_temperature,
    DeviceAttributes.automatic_run_mode,
    DeviceAttributes.daily_timer_1_enabled,
    DeviceAttributes.daily_timer_1_temperature,
    DeviceAttributes.daily_timer_1_start_hour,
    DeviceAttributes.daily_timer_1_start_minute,
    DeviceAttributes.daily_timer_1_end_hour,
    DeviceAttributes.daily_timer_1_end_minute,
    DeviceAttributes.daily_timer_2_enabled,
    DeviceAttributes.daily_timer_2_temperature,
    DeviceAttributes.daily_timer_2_start_hour,
    DeviceAttributes.daily_timer_2_start_minute,
    DeviceAttributes.daily_timer_2_end_hour,
    DeviceAttributes.daily_timer_2_end_minute,
    DeviceAttributes.daily_timer_3_enabled,
    DeviceAttributes.daily_timer_3_temperature,
    DeviceAttributes.daily_timer_3_start_hour,
    DeviceAttributes.daily_timer_3_start_minute,
    DeviceAttributes.daily_timer_3_end_hour,
    DeviceAttributes.daily_timer_3_end_minute,
    DeviceAttributes.daily_timer_4_enabled,
    DeviceAttributes.daily_timer_4_temperature,
    DeviceAttributes.daily_timer_4_start_hour,
    DeviceAttributes.daily_timer_4_start_minute,
    DeviceAttributes.daily_timer_4_end_hour,
    DeviceAttributes.daily_timer_4_end_minute,
    DeviceAttributes.daily_timer_5_enabled,
    DeviceAttributes.daily_timer_5_temperature,
    DeviceAttributes.daily_timer_5_start_hour,
    DeviceAttributes.daily_timer_5_start_minute,
    DeviceAttributes.daily_timer_5_end_hour,
    DeviceAttributes.daily_timer_5_end_minute,
    DeviceAttributes.weekly_timer_weekday,
    DeviceAttributes.weekly_timer_1_enabled,
    DeviceAttributes.weekly_timer_1_temperature,
    DeviceAttributes.weekly_timer_1_start_hour,
    DeviceAttributes.weekly_timer_1_start_minute,
    DeviceAttributes.weekly_timer_1_end_hour,
    DeviceAttributes.weekly_timer_1_end_minute,
    DeviceAttributes.weekly_timer_2_enabled,
    DeviceAttributes.weekly_timer_2_temperature,
    DeviceAttributes.weekly_timer_2_start_hour,
    DeviceAttributes.weekly_timer_2_start_minute,
    DeviceAttributes.weekly_timer_2_end_hour,
    DeviceAttributes.weekly_timer_2_end_minute,
    DeviceAttributes.weekly_timer_3_enabled,
    DeviceAttributes.weekly_timer_3_temperature,
    DeviceAttributes.weekly_timer_3_start_hour,
    DeviceAttributes.weekly_timer_3_start_minute,
    DeviceAttributes.weekly_timer_3_end_hour,
    DeviceAttributes.weekly_timer_3_end_minute,
    DeviceAttributes.weekly_timer_4_enabled,
    DeviceAttributes.weekly_timer_4_temperature,
    DeviceAttributes.weekly_timer_4_start_hour,
    DeviceAttributes.weekly_timer_4_start_minute,
    DeviceAttributes.weekly_timer_4_end_hour,
    DeviceAttributes.weekly_timer_4_end_minute,
    DeviceAttributes.weekly_timer_5_enabled,
    DeviceAttributes.weekly_timer_5_temperature,
    DeviceAttributes.weekly_timer_5_start_hour,
    DeviceAttributes.weekly_timer_5_start_minute,
    DeviceAttributes.weekly_timer_5_end_hour,
    DeviceAttributes.weekly_timer_5_end_minute,
)


class MideaCEDevice(MideaDevice):
    """Midea CE device."""

    _modes: ClassVar[list[str]] = ["normal", "sleep_mode", "eco_mode"]
    _compact_modes: ClassVar[list[str]] = ["auto", "heat", "cool", "fan"]

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea CE device."""
        super().__init__(
            device_type=DeviceType.CE,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.mode: None,
                DeviceAttributes.child_lock: False,
                DeviceAttributes.scheduled: False,
                DeviceAttributes.fan_speed: 0,
                DeviceAttributes.pm25: None,
                DeviceAttributes.co2: None,
                DeviceAttributes.current_humidity: None,
                DeviceAttributes.current_temperature: None,
                DeviceAttributes.hcho: None,
                DeviceAttributes.link_to_ac: False,
                DeviceAttributes.sleep_mode: False,
                DeviceAttributes.eco_mode: False,
                DeviceAttributes.aux_heating: None,
                DeviceAttributes.powerful_purify: False,
                DeviceAttributes.filter_cleaning_reminder: False,
                DeviceAttributes.filter_change_reminder: False,
                DeviceAttributes.error_code: 0,
            }
            | dict.fromkeys(COMPACT_READ_ONLY_ATTRIBUTES),
        )
        self._compact_protocol: bool | None = None
        self._timer_queries_pending = False
        self._default_speed_count = 7
        self._speed_count = self._default_speed_count
        self.set_customize(customize)

    @property
    def speed_count(self) -> int:
        """Midea CE device speed count."""
        return self._speed_count

    @property
    def preset_modes(self) -> list[str]:
        """Midea CE device preset modes."""
        return self._compact_modes if self._compact_protocol else self._modes

    @property
    def compact_protocol(self) -> bool | None:
        """Return whether the compact CE wire protocol has been detected."""
        return self._compact_protocol

    def build_query(
        self,
    ) -> list[MessageQuery | MessageQueryDailyTimer | MessageQueryWeeklyTimer]:
        """Midea CE device build query."""
        queries: list[
            MessageQuery | MessageQueryDailyTimer | MessageQueryWeeklyTimer
        ] = [MessageQuery(self._message_protocol_version)]
        # X01 is safe for both known CE layouts and acts as the wire-level probe.
        # Timer queries belong to the compact layout, so send them once only after an
        # eight-byte X01 reply has selected that decoder. This prevents a new decoder
        # from changing traffic sent to legacy CE appliances. Reconnect re-arms the
        # one-shot queries so a fresh debug log captures the optional responses.
        if self._compact_protocol and self._timer_queries_pending:
            self._timer_queries_pending = False
            queries.append(MessageQueryDailyTimer(self._message_protocol_version))
            queries.extend(
                MessageQueryWeeklyTimer(self._message_protocol_version, weekday)
                for weekday in range(CE_MIN_WEEKDAY, CE_MAX_WEEKDAY + 1)
            )
        return queries

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea CE device process message."""
        message = MessageCEResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        if message.compact_protocol is True:
            if self._compact_protocol is not True:
                self._timer_queries_pending = True
            self._compact_protocol = True
        elif message.compact_protocol is False and self._compact_protocol is None:
            self._compact_protocol = False
        new_status = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = self._attributes[status]
        if message.is_generic_status:
            if self._attributes[DeviceAttributes.sleep_mode]:
                self._attributes[DeviceAttributes.mode] = "sleep_mode"
            elif self._attributes[DeviceAttributes.eco_mode]:
                self._attributes[DeviceAttributes.mode] = "eco_mode"
            else:
                self._attributes[DeviceAttributes.mode] = "none"
            new_status[DeviceAttributes.mode.value] = self._attributes[
                DeviceAttributes.mode
            ]
        return new_status

    def make_message_set(self) -> MessageSet:
        """Midea CE device make message set."""
        message = MessageSet(self._message_protocol_version)
        message.power = self._attributes[DeviceAttributes.power]
        message.fan_speed = self._attributes[DeviceAttributes.fan_speed]
        message.link_to_ac = self._attributes[DeviceAttributes.link_to_ac]
        message.sleep_mode = self._attributes[DeviceAttributes.sleep_mode]
        message.eco_mode = self._attributes[DeviceAttributes.eco_mode]
        message.aux_heating = self._attributes[DeviceAttributes.aux_heating]
        message.powerful_purify = self._attributes[DeviceAttributes.powerful_purify]
        message.scheduled = self._attributes[DeviceAttributes.scheduled]
        message.child_lock = self._attributes[DeviceAttributes.child_lock]
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea CE device set attribute."""
        if self._compact_protocol:
            msg = "[ce] compact protocol attributes are read-only"
            raise ValueWrongType(msg)
        message = self.make_message_set()
        if attr == DeviceAttributes.mode:
            message.sleep_mode = False
            message.eco_mode = False
            if value == "sleep_mode":
                message.sleep_mode = True
            elif value == "eco_mode":
                message.eco_mode = True
        else:
            setattr(message, str(attr), value)
        self.build_send(message)

    def reset_init_query(self) -> None:
        """Re-arm compact timer discovery queries after reconnect."""
        super().reset_init_query()
        self._timer_queries_pending = self._compact_protocol is True

    def set_customize(self, customize: str) -> None:
        """Midea CE device set customize."""
        self._speed_count = self._default_speed_count
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "speed_count" in params:
                    self._speed_count = params.get("speed_count")
            except Exception:
                _LOGGER.exception("[%s] Set customize error", self.device_id)
            self.update_all({"speed_count": self._speed_count})


class MideaAppliance(MideaCEDevice):
    """Midea CE appliance."""

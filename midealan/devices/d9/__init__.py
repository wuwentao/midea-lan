"""Midea local D9 device.

D9 is a combined washer/dryer that carries two independent buckets over one
LAN connection: a DB washer bucket and a DC dryer bucket. Each bucket keeps its
own power/status/program state, so attributes are prefixed ``db_``/``dc_`` and
controls are routed to the matching bucket.
"""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import MAX_BYTE_VALUE, DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType
from midealan.message import ListTypes

from .message import (
    BUCKET_DB,
    BUCKET_DC,
    MessageD9Response,
    MessagePower,
    MessageProgram,
    MessageQuery,
    MessageStart,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea D9 device attributes."""

    # DB washer bucket
    db_power = "db_power"
    db_program = "db_program"
    db_water_level = "db_water_level"
    db_dry = "db_dry"
    db_rinse_count = "db_rinse_count"
    db_temperature = "db_temperature"
    db_dehydration_speed = "db_dehydration_speed"
    db_wash_time = "db_wash_time"
    db_detergent = "db_detergent"
    db_softener = "db_softener"
    db_appointment_time = "db_appointment_time"
    db_memory = "db_memory"
    db_appointment = "db_appointment"
    db_baby_lock = "db_baby_lock"
    db_light = "db_light"
    db_sterilize = "db_sterilize"
    db_water_quality_link = "db_water_quality_link"
    db_remain_time = "db_remain_time"
    db_running_status = "db_running_status"
    db_progress = "db_progress"
    db_error_code = "db_error_code"
    db_dehydration_time = "db_dehydration_time"
    db_position = "db_position"
    db_water_consumption = "db_water_consumption"
    db_power_consumption = "db_power_consumption"
    db_clean_notification = "db_clean_notification"
    db_softener_needed = "db_softener_needed"
    db_detergent_needed = "db_detergent_needed"
    db_location = "db_location"
    db_appointment_end_time = "db_appointment_end_time"
    db_material = "db_material"
    db_ai = "db_ai"
    # DC dryer bucket
    dc_power = "dc_power"
    dc_program = "dc_program"
    dc_dry_time = "dc_dry_time"
    dc_intensity = "dc_intensity"
    dc_light = "dc_light"
    dc_baby_lock = "dc_baby_lock"
    dc_appointment = "dc_appointment"
    dc_sterilize = "dc_sterilize"
    dc_remind_sound = "dc_remind_sound"
    dc_position = "dc_position"
    dc_appointment_time = "dc_appointment_time"
    dc_steam = "dc_steam"
    dc_prevent_wrinkle = "dc_prevent_wrinkle"
    dc_running_status = "dc_running_status"
    dc_error_code = "dc_error_code"
    dc_dry_status = "dc_dry_status"
    dc_remain_time = "dc_remain_time"
    dc_water_consumption = "dc_water_consumption"
    dc_power_consumption = "dc_power_consumption"
    dc_appointment_end_time = "dc_appointment_end_time"
    dc_location = "dc_location"


class MideaD9Device(MideaDevice):
    """Midea D9 device."""

    _db_running_status: ClassVar[dict[int, str]] = {
        0: "off",
        1: "standby",
        2: "start",
        3: "pause",
        4: "end",
        5: "fault",
        6: "delay",
    }

    _dc_running_status: ClassVar[dict[int, str]] = {
        1: "standby",
        2: "start",
        3: "pause",
        4: "end",
        5: "fault",
        6: "delay",
        8: "delay",
    }

    _dc_dry_status: ClassVar[dict[int, str]] = {
        1: "heating",
        2: "ironing",
        4: "cooling",
        8: "ending",
        16: "preventwrinkling",
        32: "sterilizing",
        64: "steamironing",
    }

    _db_program: ClassVar[dict[int, str]] = {
        0x00: "cotton",
        0x01: "eco",
        0x02: "fast_wash",
        0x03: "mixed_wash",
        0x04: "fiber",
        0x05: "wool",
        0x06: "enzyme",
        0x07: "ssp",
        0x08: "sport_clothes",
        0x09: "single_dehytration",
        0x0A: "rinsing_dehydration",
        0x0B: "big",
        0x0C: "baby_clothes",
        0x0D: "underwear",
        0x0E: "outdoor",
        0x0F: "down_jacket",
        0x10: "color",
        0x11: "intelligent",
        0x12: "quick_wash",
        0x13: "kids",
        0x14: "water_baby_clothes",
        0x15: "air_wash",
        0x16: "single_drying",
        0x17: "fast_wash_30",
        0x18: "water_shirt",
        0x19: "water_intelligent",
        0x1A: "water_steep",
        0x1B: "water_fast_wash_30",
        0x1C: "shirt",
        0x1D: "steep",
        0x1E: "new_water_cotton",
        0x1F: "water_mixed_wash",
        0x20: "water_fiber",
        0x21: "water_kids",
        0x22: "water_underwear",
        0x23: "specialist",
        0x24: "water_eco",
        0x25: "wash_drying_60",
        0x26: "self_wash_5",
        0x27: "fast_wash_min",
        0x28: "mixed_wash_min",
        0x29: "dehydration_min",
        0x2A: "self_wash_min",
        0x2B: "baby_clothes_min",
        0x2C: "prevent_allergy",
        0x2D: "cold_wash",
        0x2E: "soft_wash",
        0x2F: "remove_mite_wash",
        0x30: "water_intense_wash",
        0x31: "fast_dry",
        0x32: "water_outdoor",
        0x33: "spring_autumn_wash",
        0x34: "summer_wash",
        0x35: "winter_wash",
        0x36: "jean",
        0x37: "new_clothes_wash",
        0x38: "silk",
        0x39: "insight_wash",
        0x3A: "fitness_clothes",
        0x3B: "mink",
        0x3C: "fresh_air",
        0x3D: "bucket_dry",
        0x3E: "jacket",
        0x3F: "bath_towel",
        0x40: "night_fresh_wash",
        0x60: "heart_wash",
        0x61: "water_cold_wash",
        0x62: "water_prevent_allergy",
        0x63: "water_remove_mite_wash",
        0x64: "water_ssp",
        0x65: "silk_wash",
        0x66: "standard",
        0x67: "green_wool",
        0x68: "cook_wash",
        0x69: "fresh_remove_wrinkle",
        0x6A: "steam_sterilize_wash",
        0x70: "sterilize_wash",
        0xFE: "love",
    }

    _dc_program: ClassVar[dict[int, str]] = {
        0x00: "cotton",
        0x01: "fiber",
        0x02: "mixed_wash",
        0x03: "jean",
        0x04: "bedsheet",
        0x05: "outdoor",
        0x06: "down_jacket",
        0x07: "plush",
        0x08: "wool",
        0x09: "dehumidify",
        0x0A: "cold_air_fresh_air",
        0x0B: "hot_air_dry",
        0x0C: "sport_clothes",
        0x0D: "underwear",
        0x0E: "baby_clothes",
        0x0F: "shirt",
        0x10: "standard",
        0x11: "quick_dry",
        0x12: "fresh_air",
        0x13: "low_temp_dry",
        0x14: "eco_dry",
        0x17: "intelligent_dry",
        0x18: "steam_care",
        0x19: "big",
        0x1A: "fixed_time_dry",
        0x1B: "night_dry",
        0x1C: "bracket_dry",
        0x1D: "western_trouser",
        0x1E: "dehumidification",
        0x1F: "silk",
        0x25: "air_wash",
    }

    # Report attribute -> {raw value: label} lookups applied during parsing.
    _value_maps: ClassVar[dict[str, dict[int, str]]] = {}

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea D9 device."""
        super().__init__(
            device_type=DeviceType.D9,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )
        # Populate the class-level value maps once. Kept here (rather than a
        # class attribute literal) so it can reference the program/status dicts
        # without repeating them.
        if not MideaD9Device._value_maps:
            MideaD9Device._value_maps = {
                DeviceAttributes.db_program: MideaD9Device._db_program,
                DeviceAttributes.db_running_status: (MideaD9Device._db_running_status),
                DeviceAttributes.dc_program: MideaD9Device._dc_program,
                DeviceAttributes.dc_running_status: (MideaD9Device._dc_running_status),
                DeviceAttributes.dc_dry_status: MideaD9Device._dc_dry_status,
            }

    def build_query(self) -> list[MessageQuery]:
        """Midea D9 device build query.

        Query both buckets so washer and dryer state refresh together.
        """
        return [
            MessageQuery(self._message_protocol_version, BUCKET_DB),
            MessageQuery(self._message_protocol_version, BUCKET_DC),
        ]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea D9 device process message."""
        message = MessageD9Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for name, value in message.attributes.items():
            if name not in self._attributes:
                continue
            value_map = MideaD9Device._value_maps.get(name)
            if value_map is not None:
                self._attributes[name] = value_map.get(value, value)
            else:
                self._attributes[name] = value
            new_status[name] = self._attributes[name]
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea D9 device set attribute.

        ``*_power`` and ``*_control_status`` accept a bool; ``*_program``
        accepts the program name (str) or raw value (int).
        """
        bucket = BUCKET_DC if attr.startswith("dc_") else BUCKET_DB
        message: MessagePower | MessageStart | MessageProgram | None = None
        if attr in (DeviceAttributes.db_power, DeviceAttributes.dc_power):
            if not isinstance(value, bool):
                raise ValueWrongType("[d9] Expected bool")
            message = MessagePower(self._message_protocol_version, bucket)
            message.power = value
        elif attr in (
            DeviceAttributes.db_running_status,
            DeviceAttributes.dc_running_status,
        ):
            if not isinstance(value, bool):
                raise ValueWrongType("[d9] Expected bool")
            message = MessageStart(self._message_protocol_version, bucket)
            message.start = value
        elif attr in (DeviceAttributes.db_program, DeviceAttributes.dc_program):
            program = self._resolve_program(bucket, value)
            if program is None:
                return
            message = MessageProgram(self._message_protocol_version, bucket)
            message.program = program
        if message is not None:
            self.build_send(message)

    @staticmethod
    def _resolve_program(
        bucket: ListTypes,
        value: bool | float | str,
    ) -> int | None:
        """Resolve a program name or raw value into a program byte."""
        program_map = (
            MideaD9Device._dc_program
            if bucket == BUCKET_DC
            else MideaD9Device._db_program
        )
        if isinstance(value, str):
            for raw, name in program_map.items():
                if name == value:
                    return raw
            return None
        if isinstance(value, bool):
            return None
        # Reject fractional or out-of-byte-range values so the appliance never
        # receives a silently truncated/wrapped program code.
        if not 0 <= value <= MAX_BYTE_VALUE:
            return None
        program = int(value)
        return program if value == program else None


class MideaAppliance(MideaD9Device):
    """Midea D9 appliance."""

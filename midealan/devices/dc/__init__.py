"""Midea lan DC device."""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import (
    BASIC_PARAMETER_END,
    BASIC_PARAMETER_START,
    PROFILE_MODEL,
    PROFILE_SUBTYPE,
    STATUS_DELAY,
    STATUS_OFFSET,
    STATUS_START,
    DCControls,
    MessageDCResponse,
    MessagePower,
    MessageQuery,
    MessageStart,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea DC device attributes."""

    power = "power"
    start = "start"
    status = "status"
    program = "program"
    intensity = "intensity"
    dryness_level = "dryness_level"
    dry_temperature = "dry_temperature"
    error_code = "error_code"
    door_warn = "door_warn"
    ai_switch = "ai_switch"
    material = "material"
    water_box = "water_box"
    washing_data = "washing_data"
    progress = "progress"
    time_remaining = "time_remaining"
    appointment_control_supported = "appointment_control_supported"
    appointment_controls_available = "appointment_controls_available"
    appointment = "appointment"
    appointment_finish = "appointment_finish"
    parameter_control_supported = "parameter_control_supported"
    parameter_controls_available = "parameter_controls_available"
    program_control = "program_control"
    temperature_control = "temperature_control"
    dryness_control = "dryness_control"
    sterilize = "sterilize"
    anti_wrinkle = "anti_wrinkle"
    timed_extra = "timed_extra"


class MideaDCDevice(MideaDevice):
    """Midea DC device."""

    _status: ClassVar[dict[int, str]] = {
        0: "idle",
        1: "standby",
        2: "start",
        3: "pause",
        4: "end",
        5: "prevent_wrinkle_end",
        6: "delay_choosing",
        7: "fault",
        8: "delay",
        9: "delay_pause",
    }

    _program: ClassVar[dict[int, str]] = {
        0: "cotton",
        1: "fiber",
        2: "mixed_wash",
        3: "jean",
        4: "bedsheet",
        5: "outdoor",
        6: "down_jacket",
        7: "plush",
        8: "wool",
        9: "dehumidify",
        10: "cold_air_fresh_air",
        11: "hot_air_dry",
        12: "sport_clothes",
        13: "underwear",
        14: "baby_clothes",
        15: "shirt",
        16: "standard",
        17: "quick_dry",
        18: "fresh_air",
        19: "low_temp_dry",
        20: "eco_dry",
        21: "quick_dry_30",
        22: "towel",
        23: "intelligent_dry",
        24: "steam_care",
        25: "big",
        26: "fixed_time_dry",
        27: "night_dry",
        28: "bracket_dry",
        29: "western_trouser",
        30: "dehumidification",
        31: "smart_dry",
        32: "four_piece_suit",
        33: "warm_clothes",
        34: "quick_dry_20",
        35: "steam_sterilize",
        36: "enzyme",
        37: "big_60",
        38: "steam_no_iron",
        39: "air_wash",
        40: "bed_clothes",
        41: "little_fast_dry",
        42: "small_piece_dry",
        43: "big_dry",
        44: "wool_nurse",
        45: "sun_quilt",
        46: "fresh_remove_smell",
        47: "bucket_self_clean",
        48: "silk",
        49: "sterilize",
    }

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea DC device."""
        super().__init__(
            device_type=DeviceType.DC,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.start: False,
                DeviceAttributes.status: "unknown",
                DeviceAttributes.program: "none",
                DeviceAttributes.intensity: None,
                DeviceAttributes.dryness_level: None,
                DeviceAttributes.dry_temperature: None,
                DeviceAttributes.error_code: None,
                DeviceAttributes.door_warn: None,
                DeviceAttributes.ai_switch: None,
                DeviceAttributes.material: None,
                DeviceAttributes.water_box: None,
                DeviceAttributes.washing_data: bytearray([]),
                DeviceAttributes.progress: "unknown",
                DeviceAttributes.time_remaining: None,
            },
        )

        profile = self.subtype == PROFILE_SUBTYPE and PROFILE_MODEL in (
            self.model,
            self.sn8,
        )
        # The Lua 0xDC protocol confirms generic program, feature, and
        # appointment fields; only the extended profile fields remain gated.
        self._controls = DCControls(profile=profile)
        self._attributes.update(self._controls.attributes)

    def get_parameter_options(self, attr: str) -> list[str]:
        """Return active protocol options, including profile-specific choices."""
        return self._controls.options(attr) if self._controls is not None else []

    def build_query(self) -> list[MessageQuery]:
        """Midea DC device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea DC device process message."""
        message = MessageDCResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        progress = [
            "prog0",
            "prog1",
            "prog2",
            "prog3",
            "prog4",
            "prog5",
            "prog6",
            "prog7",
        ]
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                # parse progress
                if status == DeviceAttributes.progress:
                    # 0 means no progress bit is set; prevent value out of index range
                    if 0 < value < len(progress):
                        self._attributes[DeviceAttributes.progress] = progress[value]
                    else:
                        self._attributes[DeviceAttributes.progress] = None
                # parse status
                elif status == DeviceAttributes.status:
                    self._attributes[DeviceAttributes.status] = (
                        MideaDCDevice._status.get(value, value)
                    )
                # parse program
                elif status == DeviceAttributes.program:
                    self._attributes[DeviceAttributes.program] = (
                        self._controls.programs
                        if self._controls is not None
                        else self._program
                    ).get(value, value)
                else:
                    self._attributes[status] = getattr(message, str(status))
                new_status[str(status)] = self._attributes[status]
        if self._controls is not None and hasattr(message, "washing_data"):
            controls = self._controls.update(message.body)
            if self._controls.profile:
                self._attributes[DeviceAttributes.start] = message.body[
                    STATUS_OFFSET
                ] in (STATUS_START, STATUS_DELAY)
                new_status[DeviceAttributes.start] = self._attributes[
                    DeviceAttributes.start
                ]
                self._attributes[DeviceAttributes.time_remaining] = (
                    self._controls.remaining_minutes()
                    if self._attributes[DeviceAttributes.power]
                    else None
                )
                new_status[DeviceAttributes.time_remaining] = self._attributes[
                    DeviceAttributes.time_remaining
                ]
            self._attributes.update(controls)
            new_status.update({str(attr): value for attr, value in controls.items()})
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea DC device set attribute."""
        if self._controls is not None and self._controls.supports(attr):
            message_set = self._controls.make_message(
                attr,
                value,
                self._message_protocol_version,
            )
            if attr == DeviceAttributes.appointment and value is False:
                self.build_send(MessageStart(self._message_protocol_version))
            self.build_send(message_set)
            self.build_send(MessageQuery(self._message_protocol_version))
            return
        if not isinstance(value, bool):
            raise ValueWrongType("[dc] Expected bool")
        message: MessagePower | MessageStart | None = None
        if attr == DeviceAttributes.power:
            message = MessagePower(self._message_protocol_version)
            message.power = value
            self.build_send(message)
        elif attr == DeviceAttributes.start:
            message = MessageStart(self._message_protocol_version)
            message.start = value
            message.washing_data = (
                bytearray(
                    self._controls.body[BASIC_PARAMETER_START:BASIC_PARAMETER_END],
                )
                if self._controls is not None and self._controls.body
                else self._attributes[DeviceAttributes.washing_data]
            )
            self.build_send(message)


class MideaAppliance(MideaDCDevice):
    """Midea DC appliance."""

"""Midea lan DA device."""

import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDeviceInitKwargs, ToshibaDevice
from midealan.devices.toshiba import (
    TOSHIBA_WASHER_STATUS_RUNNING,
    decode_toshiba_washer_status,
)
from midealan.exceptions import ValueWrongType
from midealan.message import (
    MessageRequest,
    MessageType,
    ToshibaFrame,
    ToshibaMessageRequest,
)

from .message import MessageDAResponse, MessagePower, MessageQuery, MessageStart

_LOGGER = logging.getLogger(__name__)

MIN_TEMP = 15


class ToshibaDAQuery(ToshibaMessageRequest):
    """Toshiba DA query using the normal DA wire type."""


class ToshibaDALegacyQuery(ToshibaMessageRequest):
    """Toshiba DA v1 query using its documented DB wire-type anomaly."""


class DeviceAttributes(StrEnum):
    """Midea DA device attributes."""

    power = "power"
    start = "start"
    washing_data = "washing_data"
    program = "program"
    progress = "progress"
    time_remaining = "time_remaining"
    wash_time = "wash_time"
    soak_time = "soak_time"
    dehydration_time = "dehydration_time"
    dehydration_speed = "dehydration_speed"
    error_code = "error_code"
    rinse_count = "rinse_count"
    rinse_level = "rinse_level"
    wash_level = "wash_level"
    wash_strength = "wash_strength"
    softener = "softener"
    detergent = "detergent"


class MideaDADevice(ToshibaDevice):
    """Midea DA device."""

    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        (MessageType.set, MessageType.query, MessageType.notify1),
    )

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea DA device."""
        super().__init__(
            device_type=DeviceType.DA,
            **kwargs,
            attributes={
                DeviceAttributes.power: False,
                DeviceAttributes.start: False,
                DeviceAttributes.error_code: None,
                DeviceAttributes.washing_data: bytearray([]),
                DeviceAttributes.program: None,
                DeviceAttributes.progress: "unknown",
                DeviceAttributes.time_remaining: None,
                DeviceAttributes.wash_time: None,
                DeviceAttributes.soak_time: None,
                DeviceAttributes.dehydration_time: None,
                DeviceAttributes.dehydration_speed: None,
                DeviceAttributes.rinse_count: None,
                DeviceAttributes.rinse_level: None,
                DeviceAttributes.wash_level: None,
                DeviceAttributes.wash_strength: None,
                DeviceAttributes.softener: None,
                DeviceAttributes.detergent: None,
            },
        )

    def toshiba_wire_device_types(self) -> tuple[DeviceType | int, ...]:
        """Accept the DA v2 wire type and the DA v1 DB compatibility type."""
        if self._selected_toshiba_wire_type is not None:
            return (self._selected_toshiba_wire_type,)
        return (DeviceType.DA, DeviceType.DB)

    def build_toshiba_query(self) -> list[MessageRequest]:
        """Probe both documented Toshiba DA wire-type profiles when unresolved."""
        if self._selected_toshiba_wire_type == DeviceType.DB:
            return [
                ToshibaDALegacyQuery(
                    DeviceType.DA,
                    self._message_protocol_version,
                    b"\x00",
                    wire_device_type=DeviceType.DB,
                ),
            ]
        queries: list[MessageRequest] = [
            ToshibaDAQuery(
                DeviceType.DA,
                self._message_protocol_version,
                b"\x00",
            ),
        ]
        if self._selected_toshiba_wire_type is None:
            queries.append(
                ToshibaDALegacyQuery(
                    DeviceType.DA,
                    self._message_protocol_version,
                    b"\x00",
                    wire_device_type=DeviceType.DB,
                ),
            )
        return queries

    def build_query(self) -> list[MessageRequest]:
        """Midea DA device build query."""
        if self.toshiba_protocol:
            return self.build_toshiba_query()
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea DA device process message."""
        status = self.process_toshiba_message(msg)
        if status is not None:
            return status
        message = MessageDAResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        progress = ["idle", "spin", "rinse", "wash", "weight", "unknown", "dry", "soak"]
        program = [
            "standard",
            "fast",
            "blanket",
            "wool",
            "embathe",
            "memory",
            "child",
            "down_jacket",
            "stir",
            "mute",
            "bucket_self_clean",
            "air_dry",
        ]
        speed = ["-", "low", "medium", "high"]
        strength = ["-", "week", "medium", "strong"]
        detergent = [
            "no",
            "less",
            "medium",
            "more",
            "4",
            "5",
            "6",
            "7",
            "8",
            "insufficient",
        ]
        softener = [
            "no",
            "intelligent",
            "programed",  # codespell:ignore
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "insufficient",
        ]
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                if status == DeviceAttributes.progress:
                    self._attributes[status] = (
                        None if value >= len(progress) else progress[value]
                    )
                elif status == DeviceAttributes.program:
                    self._attributes[status] = (
                        None if value >= len(program) else program[value]
                    )
                elif status == DeviceAttributes.rinse_level:
                    self._attributes[status] = "-" if value == MIN_TEMP else value
                elif status == DeviceAttributes.dehydration_speed:
                    self._attributes[status] = (
                        None if value >= len(speed) else speed[value]
                    )
                elif status == DeviceAttributes.detergent:
                    self._attributes[status] = (
                        None if value >= len(detergent) else detergent[value]
                    )
                elif status == DeviceAttributes.softener:
                    self._attributes[status] = (
                        None if value >= len(softener) else softener[value]
                    )
                elif status == DeviceAttributes.wash_strength:
                    self._attributes[status] = (
                        None if value >= len(strength) else strength[value]
                    )
                else:
                    self._attributes[status] = value
                new_status[str(status)] = self._attributes[status]
        return new_status

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode the common Toshiba top-load washer base status."""
        body = frame.body
        base_status = decode_toshiba_washer_status(body)
        if base_status is None:
            return None
        programs = [
            "standard",
            "fast",
            "blanket",
            "wool",
            "embathe",
            "memory",
            "child",
            "down_jacket",
            "stir",
            "mute",
            "bucket_self_clean",
            "air_dry",
        ]
        program = body[3]
        values: dict[DeviceAttributes, Any] = {
            DeviceAttributes.power: base_status.machine_status != 0,
            DeviceAttributes.start: (
                base_status.machine_status == TOSHIBA_WASHER_STATUS_RUNNING
            ),
            DeviceAttributes.washing_data: bytearray(body),
            DeviceAttributes.program: (
                programs[program] if program < len(programs) else program
            ),
            DeviceAttributes.progress: base_status.progress,
            DeviceAttributes.time_remaining: base_status.time_remaining,
            DeviceAttributes.wash_time: base_status.wash_time,
            DeviceAttributes.dehydration_time: base_status.dehydration_time,
            DeviceAttributes.error_code: int.from_bytes(body[20:22], "little"),
        }
        self._attributes.update(values)
        return {str(attr): value for attr, value in values.items()}

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea DA device set attribute."""
        self.reject_toshiba_write()
        if not isinstance(value, bool):
            raise ValueWrongType("[da] Expected bool")
        message: MessagePower | MessageStart | None = None
        if attr == DeviceAttributes.power:
            message = MessagePower(self._message_protocol_version)
            message.power = value
            self.build_send(message)
        elif attr == DeviceAttributes.start:
            message = MessageStart(self._message_protocol_version)
            message.start = value
            message.washing_data = self._attributes[DeviceAttributes.washing_data]
            self.build_send(message)


class MideaAppliance(MideaDADevice):
    """Midea DA appliance."""

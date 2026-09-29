"""Midea local D9 message.

The D9 appliance is a combined washer (DB bucket) and dryer (DC bucket). Unlike
the fixed-offset DB/DC protocols, D9 uses a type-length-value (TLV) body: the
first body byte is the bucket identifier (``0xDB``/``0xDC``) followed by a
sequence of ``<data_type><length><value...>`` records. Requests and responses
share this framing.
"""

from typing import Literal

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Bucket identifiers carried as the first body byte.
BUCKET_DB = ListTypes.DB
BUCKET_DC = ListTypes.DC

# TLV control record data types (shared by DB and DC buckets).
CONTROL_POWER = 0x01
CONTROL_STATUS = 0x02
CONTROL_PROGRAM = 0x04
CONTROL_LENGTH_ONE = 0x01

# Control record values.
VALUE_ON = 0x01
VALUE_OFF = 0x00

# TLV parsing layout.
BUCKET_OFFSET = 1  # body[0] holds the bucket byte; records start at body[1]
TLV_HEADER_LEN = 2  # one byte data type + one byte length

# Appointment-end-time is a 3-byte record: 2-byte little-endian minutes plus a
# day flag (0 today, 1 tomorrow) that shifts the value by a full day.
APPOINTMENT_END_TIME_BYTES = 3
APPOINTMENT_END_TIME_MINUTES = 2  # first two bytes are the minute-of-day value
APPOINTMENT_END_TIME_DAY_INDEX = 2  # third byte is the day flag
APPOINTMENT_END_TOMORROW = 1
MINUTES_PER_DAY = 1440
APPOINTMENT_END_TIME_NAMES = frozenset(
    {"db_appointment_end_time", "dc_appointment_end_time"},
)

# Byte order for multi-byte TLV values.
LITTLE: Literal["little"] = "little"

# DB (washer) bucket report data type -> attribute name.
DB_REPORT_MAP: dict[int, str] = {
    0x01: "db_power",
    0x04: "db_program",
    0x05: "db_water_level",
    0x06: "db_dry",
    0x07: "db_rinse_count",
    0x08: "db_temperature",
    0x09: "db_dehydration_speed",
    0x0A: "db_wash_time",
    0x0B: "db_detergent",
    0x0C: "db_softener",
    0x0D: "db_appointment_time",
    0x0E: "db_memory",
    0x0F: "db_appointment",
    0x10: "db_spray_wash",
    0x11: "db_speedy_wash",
    0x12: "db_nightly_wash",
    0x13: "db_baby_lock",
    0x14: "db_light",
    0x15: "db_easy_ironing",
    0x16: "db_appointment_wash",
    0x17: "db_super_clean_wash",
    0x18: "db_intelligent_wash",
    0x19: "db_strong_wash",
    0x1A: "db_steam_wash",
    0x1B: "db_fast_clean_wash",
    0x1C: "db_disinfectant",
    0x1D: "db_stains_wash",
    0x1E: "db_sterilize",
    0x1F: "db_soak_wash",
    0x20: "db_detergent_increment",
    0x21: "db_softener_increment",
    0x22: "db_water_quality_link",
    0x23: "db_remain_time",
    0x24: "db_running_status",
    0x25: "db_progress",
    0x26: "db_error_code",
    0x27: "db_dehydration_time",
    0x28: "db_set_dewater_time",
    0x29: "db_set_wash_time",
    0x2A: "db_position",
    0x2B: "db_project_no",
    0x2C: "db_water_consumption",
    0x2D: "db_power_consumption",
    0x2E: "db_clean_notification",
    0x2F: "db_softener_needed",
    0x30: "db_detergent_needed",
    0x32: "db_location",
    0x33: "db_water_radar_rinse",
    0x34: "db_water_radar_wash_time",
    0x35: "db_appointment_end_time",
    0x36: "db_material",
    0x3A: "db_ai",
}

# DC (dryer) bucket report data type -> attribute name.
DC_REPORT_MAP: dict[int, str] = {
    0x01: "dc_power",
    0x04: "dc_program",
    0x05: "dc_dry_time",
    0x07: "dc_intensity",
    0x08: "dc_light",
    0x09: "dc_baby_lock",
    0x0B: "dc_appointment",
    0x0D: "dc_sterilize",
    0x0E: "dc_remind_sound",
    0x0F: "dc_position",
    0x10: "dc_appointment_time",
    0x11: "dc_steam",
    0x12: "dc_prevent_wrinkle",
    0x13: "dc_running_status",
    0x14: "dc_error_code",
    0x15: "dc_dry_status",
    0x16: "dc_remain_time",
    0x2B: "dc_project_no",
    0x2C: "dc_water_consumption",
    0x2D: "dc_power_consumption",
    0x2E: "dc_appointment_end_time",
    0x32: "dc_location",
}


class MessageD9Base(MessageRequest):
    """D9 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize D9 message base."""
        super().__init__(
            device_type=DeviceType.D9,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageD9Base):
    """D9 message query.

    Queries a single bucket. The body is just the bucket byte, so build one
    query per bucket (DB washer and DC dryer) to refresh the full device state.
    """

    def __init__(
        self,
        protocol_version: int,
        bucket: ListTypes = BUCKET_DB,
    ) -> None:
        """Initialize D9 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=bucket,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessagePower(MessageD9Base):
    """D9 message power."""

    def __init__(
        self,
        protocol_version: int,
        bucket: ListTypes = BUCKET_DB,
    ) -> None:
        """Initialize D9 message power."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=bucket,
        )
        self.power = False

    @property
    def _body(self) -> bytearray:
        value = VALUE_ON if self.power else VALUE_OFF
        return bytearray([CONTROL_POWER, CONTROL_LENGTH_ONE, value])


class MessageStart(MessageD9Base):
    """D9 message start/pause."""

    def __init__(
        self,
        protocol_version: int,
        bucket: ListTypes = BUCKET_DB,
    ) -> None:
        """Initialize D9 message start."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=bucket,
        )
        self.start = False

    @property
    def _body(self) -> bytearray:
        value = VALUE_ON if self.start else VALUE_OFF
        return bytearray([CONTROL_STATUS, CONTROL_LENGTH_ONE, value])


class MessageProgram(MessageD9Base):
    """D9 message program selection."""

    def __init__(
        self,
        protocol_version: int,
        bucket: ListTypes = BUCKET_DB,
    ) -> None:
        """Initialize D9 message program."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=bucket,
        )
        self.program = 0

    @property
    def _body(self) -> bytearray:
        return bytearray([CONTROL_PROGRAM, CONTROL_LENGTH_ONE, self.program & 0xFF])


class D9GeneralMessageBody(MessageBody):
    """D9 message general body.

    Walks the TLV records and collects each recognised record into
    ``attributes``, keyed by its bucket name (``db_*`` / ``dc_*``). Only the
    bucket present in the message is populated, so a single response updates one
    bucket's attributes.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize D9 message general body."""
        super().__init__(body)
        bucket = body[0] if body else 0
        bucket_maps: dict[int, dict[int, str]] = {
            BUCKET_DB: DB_REPORT_MAP,
            BUCKET_DC: DC_REPORT_MAP,
        }
        report_map = bucket_maps.get(bucket)
        self.attributes: dict[str, int] = {}
        if report_map is not None:
            self._parse_tlv(body, report_map)

    def _parse_tlv(self, body: bytearray, report_map: dict[int, str]) -> None:
        """Parse the TLV records into ``attributes``."""
        pos = BUCKET_OFFSET
        while pos + TLV_HEADER_LEN <= len(body):
            data_type = body[pos]
            length = body[pos + 1]
            value_start = pos + TLV_HEADER_LEN
            value_end = value_start + length
            if value_end > len(body):
                break
            name = report_map.get(data_type)
            if name is not None and length > 0:
                raw = body[value_start:value_end]
                self.attributes[name] = self._decode(name, raw, length)
            pos = value_end

    @staticmethod
    def _decode(name: str, raw: bytearray, length: int) -> int:
        """Decode a single record value (little-endian, with date handling)."""
        if name in APPOINTMENT_END_TIME_NAMES and length == APPOINTMENT_END_TIME_BYTES:
            value = int.from_bytes(raw[:APPOINTMENT_END_TIME_MINUTES], LITTLE)
            if raw[APPOINTMENT_END_TIME_DAY_INDEX] == APPOINTMENT_END_TOMORROW:
                value += MINUTES_PER_DAY
            return value
        return int.from_bytes(raw, LITTLE)


class MessageD9Response(MessageResponse):
    """D9 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize D9 message response."""
        super().__init__(bytearray(message))
        # Parsed TLV records keyed by their bucket attribute name. Empty unless
        # the message carries a recognised DB/DC/DA bucket body.
        self.attributes: dict[str, int] = {}
        if self.message_type in [
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        ] and self.body_type in [
            ListTypes.DB,
            ListTypes.DC,
            ListTypes.DA,
        ]:
            body = D9GeneralMessageBody(super().body)
            self.set_body(body)
            self.attributes = body.attributes
        self.set_attr()

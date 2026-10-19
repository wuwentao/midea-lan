"""Midea DB messages and model-specific parameter encoding."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import ClassVar, NamedTuple

from midealan.const import DeviceType
from midealan.exceptions import ValueWrongType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

MINIMUM_STATUS_LENGTH = 31
UNCHANGED = 0xFF
PARAMETER_BODY_LENGTH = 22
POWER_OFFSET = 1
STATUS_OFFSET = 2
PROGRAM_OFFSET = 4
STATUS_BODY_TYPES = (0x03, 0x04)
APPOINTMENT_TIME_OFFSET = 14
APPOINTMENT_TIME_END = 16
REMAINING_TIME_OFFSET = 17
REMAINING_TIME_END = 19
MINUTES_PER_DAY = 1440
SECONDS_PER_MINUTE = 60
START_COMMAND = 1
PAUSE_COMMAND = 0

type ControlValue = bool | int | str | None


# Only the DB v33 control profile is verified for writes. DB v41 is decoded
# read-only, while Toshiba 0x0008 uses a separate 55AA/CRC16 frame below.
# Protocol reference: wuwentao/midea-lua, lua/0xDB/.
PROFILE_MODEL = "38131140"
PROFILE_SUBTYPE = 13145
PROFILE_V41_MODEL = "38132386"
PROFILE_V41_SUBTYPE = 0
TOSHIBA_MANUFACTURER_CODE = "0008"
TOSHIBA_CLOUD_NAMES = frozenset(("Toshiba Iolife", "TSmartLife"))
STATUS_IDLE = 0
STATUS_STANDBY = 1
STATUS_END = 4
TEMPERATURE_OFFSET = 7
SPIN_SPEED_OFFSET = 8
WATER_LEVEL_OFFSET = 5
DETERGENT_OFFSET = 11
MODE_OFFSET = 3
NORMAL_MODE = 0
RINSE_OFFSET = 6
NIBBLE_SHIFT = 4
KEEP_DRYER_NIBBLE = 0x0F
WASH_REQUEST_OFFSET = 9
SPIN_REQUEST_OFFSET = 10
WASH_MINUTES_OFFSET = 27
SPIN_MINUTES_OFFSET = 28
MINUTE_SENTINEL = 254
# Request codes select adjustments to the program's default, not minutes.
# Mixed wash reports 42/45/50/55/60 minutes cold, but 11/14/19/24/29 at 30 C;
# derive that default from the current request and actual-minute report.
WASH_MINUTE_OFFSETS = (0, 5, 10, 15, -3)
# Measured 8/9/10/11/12-minute spin options map to request codes 3/4/0/1/2.
SPIN_MINUTE_OFFSETS = (0, 1, 2, -2, -1)
FRESH_STATUS_LENGTH = 56
# Forget-free is fresh_anion_switch, not the legacy wind_dispel flag.
FRESH_REPORT_OFFSET = 55
FRESH_REPORT_MASK = 0x20
FRESH_BODY_LENGTH = 54
V2_CONTROL_OFFSET = 22
V2_CONTROL_VERSION = 2
FRESH_CONTROL_OFFSET = 24
FRESH_OFF = 0x3F
FRESH_ON = 0x7F
BASIC_PARAMETER_START = 3
BASIC_PARAMETER_END = 16
CLOUD_PROGRAM_START = 36
CLOUD_PROGRAM_END = 38
STATUS_DELAY = 6
STATUS_DELAY_PAUSE = 8
APPOINTMENT_REPORT_OFFSET = 13
APPOINTMENT_REPORT_MASK = 0x02
APPOINTMENT_CONTROL_OFFSET = 35
APPOINTMENT_OFF = 0xF3
APPOINTMENT_ON = 0xF7
TOSHIBA_HEADER_LENGTH = 16
TOSHIBA_TRAILER_LENGTH = 2
TOSHIBA_FRAME_MAGIC = b"\x55\xaa\xcc\x33"
TOSHIBA_MINIMUM_STATUS_LENGTH = 47
TOSHIBA_FRAME_QUERY = 0x0003
TOSHIBA_SUBTYPE_BASE = 0x00
TOSHIBA_PROGRAM_OFFSET = 3
TOSHIBA_TEMPERATURE_OFFSET = 14
TOSHIBA_STATUS_OFFSET = 22
TOSHIBA_REMAINING_TIME_OFFSET = 23
TOSHIBA_REMAINING_TIME_END = 27
TOSHIBA_STATUS_RUNNING = 2
TOSHIBA_CRC_POLYNOMIAL = 0x1021
TOSHIBA_CRC_HIGH_BIT = 0x8000
TOSHIBA_CRC_MASK = 0xFFFF
TOSHIBA_WASH_HOUR_MIN = 0x81
TOSHIBA_WASH_HOUR_MAX = 0x8C
TOSHIBA_WASH_HOUR_BASE = 0x80
MINUTES_PER_HOUR = 60


class ControlAttributes(StrEnum):
    """Additional washer controls, separate from legacy sensor keys."""

    parameter_control_supported = "parameter_control_supported"
    parameter_controls_available = "parameter_controls_available"
    program_control = "program_control"
    temperature_control = "temperature_control"
    spin_speed_control = "spin_speed_control"
    water_level_control = "water_level_control"
    detergent_control = "detergent_control"
    rinse_count = "rinse_count"
    wash_time_control = "wash_time_control"
    spin_time_control = "spin_time_control"
    forget_free = "forget_free"
    appointment_control_supported = "appointment_control_supported"
    appointment_controls_available = "appointment_controls_available"
    appointment = "appointment"
    appointment_finish = "appointment_finish"


class ParameterField(NamedTuple):
    """Body offset and the verified raw-code to option-label mapping."""

    offset: int
    options: dict[int, str]


PROGRAMS = {
    31: "water_mixed_wash",
    2: "fast_wash",
    9: "single_dehytration",
    10: "rinsing_dehydration",
    23: "fast_wash_30",
    11: "big",
    100: "tub_clean",
    163: "deep_tub_clean",
    15: "down_jacket",
    30: "new_water_cotton",
    20: "baby_clothes",
    24: "shirt",
    103: "wool",
    34: "water_underwear",
    56: "silk",
    62: "jacket",
    55: "new_clothes_wash",
    54: "jean",
    32: "water_fiber",
    36: "water_eco",
    25: "water_intelligent",
    26: "water_steep",
    97: "water_cold_wash",
    6: "sterilization_wash",
    99: "water_remove_mite_wash",
    112: "disinfection_wash",
    132: "stain_wash",
    8: "sport_clothes",
    147: "yoga",
    145: "quick_drying_clothes",
}

V41_PROGRAMS = {
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
    0x14: "water_cotton",
    0x15: "air_wash",
    0x16: "single_drying",
    0x17: "fast_wash_30",
    0x18: "fast_wash_60",
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
    0x50: "diy0",
    0x51: "diy1",
    0x52: "diy2",
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
    0x6B: "aromatherapy",
    0x6C: "eco_40_60",
    0x6D: "steam_care",
    0x6E: "allergy_care",
    0x6F: "greatwaves",
    0x70: "sterilize_wash",
    0x71: "wash45",
    0x72: "quick12",
    0x73: "bulky",
    0x74: "whites",
    0x75: "towels",
    0x76: "delicates",
    0x77: "drum_clean",
    0x80: "wash_and_dry",
    0x81: "auto_dry",
    0x82: "time_dry",
    0xFE: "love",
}

TOSHIBA_PROGRAMS = {
    0x00: "none",
    0x01: "standard",
    0x02: "tub_clean",
    0x03: "fast",
    0x04: "careful",
    0x05: "sixty_wash",
    0x06: "blanket",
    0x07: "delicate",
    0x08: "tub_clean_dry",
    0x09: "memory",
    0x0A: "sterilization",
    0x0B: "mute",
    0x0C: "soft",
    0x0D: "delicate_dryer",
    0x0E: "soak",
    0x0F: "odor_eliminating",
    0x10: "empty",
    0x11: "degerm",
    0x12: "auto_care",
    0x13: "auto_twice_wash",
    0x14: "prewash_plus",
    0x15: "uv_wash_and_dry",
    0x16: "uv_dry_with_rotation",
    0x17: "uv_dry_without_rotation",
    0x18: "forty_five_wash",
    0x1C: "fragrant_and_delicate",
    0x1D: "tick_extermination",
    0x1E: "pollen",
    0x21: "app_course_1",
    0x22: "app_course_2",
    0x23: "app_course_3",
    0x24: "app_course",
    0x25: "uv_wash",
    0x26: "uv_without_rotation",
    0x27: "uv_with_rotation",
    0x28: "uv_deodorize_without_rotation",
    0x29: "uv_deodorize_with_rotation",
    0x30: "60_tub_clean",
    0x32: "tub_clean_wash_dry",
    0x36: "tub_clean_2",
    0x37: "tub_clean_tub_dry",
    0x38: "tub_dry",
    0x3A: "wrinkle_care",
    0x3B: "60_tub_clean_2",
    0x51: "sheets",
    0x52: "lace_curtain",
    0x53: "towel",
    0x54: "fleece",
    0x55: "school_uniform_or_washable",
    0x56: "slacks_skirt",
    0x57: "jeans",
    0x58: "cap",
    0x59: "down_jacket",
    0x5A: "bet_putt",
    0x5B: "functional_underwear",
    0x5C: "reusable_bag",
    0x5D: "duvet",
    0x5E: "t_shirt_recovery",
    0x5F: "sports_wear",
    0x81: "light_dirt",
    0x82: "wash_thoroughly_and_rinse",
    0x83: "quick_wash_and_dry",
    0x84: "yellowing_off",
    0x85: "disinfection_clothing",
    0x86: "keep_water_temperature",
    0x87: "prewash",
    0x88: "tick_care",
    0x91: "super_concentrated_soak",
    0x92: "no_rinse_and_delicate",
    0x93: "t_shirt_recovery_pro",
    0xA0: "customize",
}

TIME_FIELDS = {
    ControlAttributes.wash_time_control: (
        WASH_REQUEST_OFFSET,
        WASH_MINUTES_OFFSET,
        WASH_MINUTE_OFFSETS,
    ),
    ControlAttributes.spin_time_control: (
        SPIN_REQUEST_OFFSET,
        SPIN_MINUTES_OFFSET,
        SPIN_MINUTE_OFFSETS,
    ),
}


APPOINTMENT_ATTRIBUTES = (
    ControlAttributes.appointment,
    ControlAttributes.appointment_finish,
)


def parameter_body(length: int = PARAMETER_BODY_LENGTH) -> bytearray:
    """Build a no-change body, including no change to power and start."""
    return bytearray([ListTypes.X02] + [UNCHANGED] * (length - 1))


def option_label(value: bool | float | str) -> str:
    """Normalize integer option values without accepting booleans as numbers."""
    if isinstance(value, bool):
        raise ValueWrongType("Laundry select parameters require an option, not bool")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class MessageDBBase(MessageRequest):
    """DB message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize DB message base."""
        super().__init__(
            device_type=DeviceType.DB,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageDBBase):
    """DB message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DB message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X03,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessagePower(MessageDBBase):
    """DB message power."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DB message power."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X02,
        )
        self.power = False

    @property
    def _body(self) -> bytearray:
        power = 0x01 if self.power else 0x00
        return bytearray(
            [
                power,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
                0xFF,
            ],
        )


class MessageStart(MessageDBBase):
    """DB message start."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DB message start."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X02,
        )
        self.start = False
        self.washing_data = bytearray([])

    @property
    def _body(self) -> bytearray:
        if self.start:  # Pause
            return bytearray([0xFF, 0x01]) + self.washing_data
        # Pause
        return bytearray([0xFF, 0x00])


class DBGeneralMessageBody(MessageBody):
    """DB message general body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize DB message general body."""
        super().__init__(body)
        self.power = body[1] > 0
        self.start = body[2] in [2, 6]
        self.washing_data = body[3:16]
        self.status = body[2]
        self.mode = body[3]
        self.program = body[4]
        self.water_level = body[5]
        self.temperature = body[7]
        self.dehydration_speed = body[8]
        self.wash_time = body[9]
        self.dehydration_time = body[10]
        self.detergent = body[11]
        self.softener = body[12]
        self.progress = 0
        # progress
        for i in range(7):
            if (body[16] & (1 << i)) > 0:
                self.progress = i + 1
                break
        self.stains = body[26]
        self.wash_time_value = body[27]
        self.dehydration_time_value = body[28]
        self.dirty_degree = body[30]
        self.time_remaining: float | None = None
        if self.power:
            self.time_remaining = body[17] + (body[18] << 8)


class MessageDBResponse(MessageResponse):
    """DB message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize DB message response."""
        super().__init__(bytearray(message))
        if (
            len(super().body) >= MINIMUM_STATUS_LENGTH
            and super().body[1] in (0, 1)
            and (
                self.message_type in [MessageType.query, MessageType.set]
                or (
                    self.message_type == MessageType.notify1
                    and self.body_type == ListTypes.X04
                )
            )
        ):
            self.set_body(DBGeneralMessageBody(super().body))
        self.set_attr()


class MessageParameters(MessageDBBase):
    """Frame a complete parameter body without appending a message ID."""

    def __init__(self, protocol_version: int, body: bytearray) -> None:
        """Copy the body; normal transport supplies header and checksum."""
        super().__init__(protocol_version, MessageType.set, ListTypes.X02)
        self._parameters = body[1:]

    @property
    def _body(self) -> bytearray:
        """Return parameters following the body type byte."""
        return self._parameters


def toshiba_crc16(data: bytes | bytearray) -> int:
    """Calculate the CRC16-CCITT variant used by T_0008 Lua protocols."""
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = (
                (crc << 1) ^ TOSHIBA_CRC_POLYNOMIAL
                if crc & TOSHIBA_CRC_HIGH_BIT
                else crc << 1
            ) & TOSHIBA_CRC_MASK
    return crc


def toshiba_frame(body: bytes | bytearray, frame_type: int) -> bytearray:
    """Wrap a Toshiba body in its 55AA UART header and little-endian CRC."""
    frame = bytearray(
        [
            0x55,
            0xAA,
            0xCC,
            0x33,
            0x00,
            0x00,
            0x01,
            DeviceType.DB,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            frame_type & 0xFF,
            frame_type >> 8,
        ],
    )
    frame.extend(body)
    frame[4:6] = (len(frame) + TOSHIBA_TRAILER_LENGTH - 4).to_bytes(2, "little")
    frame.extend(toshiba_crc16(frame).to_bytes(2, "little"))
    return frame


class MessageToshibaBase(MessageRequest):
    """Build a Toshiba T_0008 request without the regular Midea AA frame."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        frame_type: int,
        body: bytearray,
    ) -> None:
        """Store the UART frame type and protocol body."""
        super().__init__(
            device_type=DeviceType.DB,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=ListTypes.X00,
        )
        self._frame_type = frame_type
        self._parameters = body

    @property
    def _body(self) -> bytearray:
        return self._parameters

    @property
    def body(self) -> bytearray:
        """Return the Toshiba protocol body without a regular body-type byte."""
        return self._parameters

    def serialize(self) -> bytearray:
        """Serialize the complete Toshiba inner UART frame."""
        return toshiba_frame(self.body, self._frame_type)


class MessageToshibaQuery(MessageToshibaBase):
    """Query the common base status used by all known T_0008 DB Lua files."""

    def __init__(self, protocol_version: int) -> None:
        """Build the base subtype query."""
        super().__init__(
            protocol_version,
            MessageType.query,
            TOSHIBA_FRAME_QUERY,
            bytearray([TOSHIBA_SUBTYPE_BASE]),
        )


TOSHIBA_MODES = {
    0x00: "none",
    0x01: "wash_dry",
    0x02: "wash",
    0x03: "dry",
    0x04: "clean_care",
    0x05: "care",
}


class MessageToshibaDBResponse:
    """Decode the base status shared by Toshiba DB Lua versions 24 through 33."""

    def __init__(self, message: bytes) -> None:
        """Validate the complete UART frame and expose compatible DB attributes."""
        self.body = bytearray()
        if not self._valid_frame(message):
            return
        body = bytearray(message[TOSHIBA_HEADER_LENGTH:-TOSHIBA_TRAILER_LENGTH])
        if len(body) < TOSHIBA_MINIMUM_STATUS_LENGTH or body[0] != TOSHIBA_SUBTYPE_BASE:
            return
        self.body = body
        machine_status = body[TOSHIBA_STATUS_OFFSET]
        self.power = machine_status != 0
        self.start = machine_status == TOSHIBA_STATUS_RUNNING
        self.status = machine_status
        self.mode = TOSHIBA_MODES.get(body[2], body[2])
        self.program = TOSHIBA_PROGRAMS.get(body[TOSHIBA_PROGRAM_OFFSET], body[3])
        self.temperature = body[TOSHIBA_TEMPERATURE_OFFSET]
        self.wash_time = self._wash_minutes(body[9])
        self.dehydration_time = body[11]
        self.washing_data = body
        self.progress = self._progress(body[18])
        self.time_remaining = int.from_bytes(
            body[TOSHIBA_REMAINING_TIME_OFFSET:TOSHIBA_REMAINING_TIME_END],
            "little",
        )

    @staticmethod
    def _valid_frame(message: bytes) -> bool:
        """Reject truncated, corrupt, non-DB and non-status UART frames."""
        minimum_length = TOSHIBA_HEADER_LENGTH + TOSHIBA_TRAILER_LENGTH
        if (
            len(message) < minimum_length
            or message[: len(TOSHIBA_FRAME_MAGIC)] != TOSHIBA_FRAME_MAGIC
            or message[7] != DeviceType.DB
            or int.from_bytes(message[4:6], "little") != len(message) - 4
            or message[14] not in (0x02, 0x03)
        ):
            return False
        expected_crc = int.from_bytes(message[-TOSHIBA_TRAILER_LENGTH:], "little")
        return toshiba_crc16(message[:-TOSHIBA_TRAILER_LENGTH]) == expected_crc

    @staticmethod
    def _wash_minutes(value: int) -> int:
        """Convert the Lua protocol's encoded one-to-twelve-hour values."""
        if TOSHIBA_WASH_HOUR_MIN <= value <= TOSHIBA_WASH_HOUR_MAX:
            return (value - TOSHIBA_WASH_HOUR_BASE) * MINUTES_PER_HOUR
        return value

    @staticmethod
    def _progress(process_info: int) -> int:
        """Translate Toshiba process flags to the existing DB progress index."""
        for mask, progress in (
            (0x02, 3),
            (0x04, 2),
            (0x08, 1),
            (0x10, 5),
            (0x20, 8),
        ):
            if process_info & mask:
                return progress
        return 0


class DBControls:
    """Decode confirmed washer parameters and validate complete commands."""

    device_type = DeviceType.DB
    minimum_status_length = MINIMUM_STATUS_LENGTH
    editable_statuses = (STATUS_IDLE, STATUS_STANDBY, STATUS_END)
    appointment_statuses = (STATUS_DELAY, STATUS_DELAY_PAUSE)
    fields: ClassVar[dict[ControlAttributes, ParameterField]] = {
        ControlAttributes.program_control: ParameterField(PROGRAM_OFFSET, PROGRAMS),
        ControlAttributes.temperature_control: ParameterField(
            TEMPERATURE_OFFSET,
            {1: "cold", 2: "20", 3: "30", 4: "40", 5: "60", 6: "95"},
        ),
        ControlAttributes.spin_speed_control: ParameterField(
            SPIN_SPEED_OFFSET,
            {0: "0", 1: "400", 2: "600", 3: "800", 4: "1000", 5: "1200", 6: "1400"},
        ),
        ControlAttributes.water_level_control: ParameterField(
            WATER_LEVEL_OFFSET,
            {5: "auto", 1: "l1", 2: "l2", 3: "l3", 4: "l4"},
        ),
        ControlAttributes.detergent_control: ParameterField(
            DETERGENT_OFFSET,
            {4: "smart", 0: "off", 1: "l1", 2: "l2", 3: "l3", 5: "l4"},
        ),
        ControlAttributes.rinse_count: ParameterField(
            RINSE_OFFSET,
            {1: "1", 2: "2", 3: "3", 4: "4"},
        ),
    }
    attribute_keys = (
        *fields,
        ControlAttributes.wash_time_control,
        ControlAttributes.spin_time_control,
        ControlAttributes.forget_free,
    )

    def __init__(self) -> None:
        """Start without a fabricated parameter or operational state."""
        self.programs = PROGRAMS
        self.body = b""
        self.attributes: dict[ControlAttributes, ControlValue] = dict.fromkeys(
            self.attribute_keys,
        )
        self.attributes[ControlAttributes.parameter_control_supported] = True
        self.attributes[ControlAttributes.parameter_controls_available] = False
        self.attributes.update(dict.fromkeys(APPOINTMENT_ATTRIBUTES))
        self.attributes[ControlAttributes.appointment_control_supported] = True
        self.attributes[ControlAttributes.appointment_controls_available] = False

    def supports(self, attr: str) -> bool:
        """Return whether an attribute is a writable parameter."""
        return attr in (*self.attribute_keys, *APPOINTMENT_ATTRIBUTES)

    def update(self, body: bytearray) -> dict[ControlAttributes, ControlValue]:
        """Replace the snapshot only from complete status/query bodies."""
        if len(body) < self.minimum_status_length or body[0] not in STATUS_BODY_TYPES:
            return {}
        self.body = bytes(body)
        self.attributes.update(dict.fromkeys(self.attribute_keys))
        self.attributes.update(self.decode())
        self.attributes[ControlAttributes.parameter_controls_available] = (
            self.is_editable()
        )
        self.attributes.update(self.decode_appointment())
        self.attributes[ControlAttributes.appointment_controls_available] = (
            self.appointment_available()
        )
        return dict(self.attributes)

    def _appointment_available(self) -> bool:
        """Allow reservation changes in standby or an existing reservation only."""
        # A queued reservation blocks ordinary parameter writes, but its
        # deadline and cancellation must remain independently editable.
        return bool(
            self.body
            and self.body[POWER_OFFSET] == 1
            and (
                self.is_editable()
                or (
                    self.body[STATUS_OFFSET] in self.appointment_statuses
                    and self.appointment_enabled() is True
                )
            ),
        )

    def remaining_minutes(self) -> int:
        """Read the verified profile's little-endian program duration in minutes."""
        return int.from_bytes(
            self.body[REMAINING_TIME_OFFSET:REMAINING_TIME_END],
            "little",
        )

    def decode_appointment(self) -> dict[ControlAttributes, ControlValue]:
        """Report a completion estimate only while a valid reservation is present."""
        enabled = self.appointment_enabled()
        wait = int.from_bytes(
            self.body[APPOINTMENT_TIME_OFFSET:APPOINTMENT_TIME_END],
            "little",
        )
        finish = None
        if enabled and 0 < wait < MINUTES_PER_DAY and self.remaining_minutes() > 0:
            finish = (
                datetime.now(UTC).replace(second=0, microsecond=0)
                + timedelta(minutes=wait + self.remaining_minutes())
            ).isoformat()
        return {
            ControlAttributes.appointment: enabled,
            ControlAttributes.appointment_finish: finish,
        }

    def appointment_message(
        self,
        key: ControlAttributes,
        value: bool | float | str,
    ) -> bytearray:
        """Register a future cycle or explicitly pause and cancel a reservation."""
        if not self.appointment_available():
            raise ValueError("Keep the appliance in standby or an existing reservation")
        if key == ControlAttributes.appointment:
            if value is not False:
                raise ValueError(
                    "Use appointment_finish to reserve; appointment=false to cancel",
                )
            return self.encode_appointment(enabled=False, wait=0)
        if not isinstance(value, str):
            raise ValueWrongType(
                "Completion time requires an ISO datetime with timezone",
            )
        target = datetime.fromisoformat(value)
        if target.tzinfo is None or target.second or target.microsecond:
            raise ValueError("Completion time requires a timezone and whole minutes")
        now = datetime.now(UTC)
        if not now < target <= now + timedelta(days=1):
            raise ValueError("Completion time must be within the next 24 hours")
        duration = self.remaining_minutes()
        wait = (
            int(target.timestamp() // SECONDS_PER_MINUTE)
            - int(
                now.timestamp() // SECONDS_PER_MINUTE,
            )
            - duration
        )
        if not 0 < duration < MINUTES_PER_DAY or not 0 < wait < MINUTES_PER_DAY:
            raise ValueError(
                "Completion time must leave a positive wait before the program starts",
            )
        return self.encode_appointment(enabled=True, wait=wait)

    def _is_editable(self) -> bool:
        """Return whether the latest real status permits parameter editing."""
        return bool(
            self.body
            and self.body[POWER_OFFSET] == 1
            and self.body[STATUS_OFFSET] in self.editable_statuses,
        )

    def _decode(self) -> dict[ControlAttributes, ControlValue]:
        """Read only verified codes; unsupported fields remain absent."""
        return {
            attr: field.options.get(self.body[field.offset])
            for attr, field in self.fields.items()
        }

    def _options(self, attr: str) -> list[str]:
        """List verified options for the currently supported parameter."""
        key = ControlAttributes(attr)
        if key not in self.fields or (
            key != ControlAttributes.program_control
            and self.attributes.get(key) is None
        ):
            return []
        return list(self.fields[key].options.values())

    def make_message(
        self,
        attr: str,
        value: bool | float | str,
        protocol_version: int,
    ) -> MessageParameters:
        """Validate current state and return a frame without optimistic updates."""
        key = ControlAttributes(attr)
        if key in APPOINTMENT_ATTRIBUTES:
            return MessageParameters(
                protocol_version,
                self.appointment_message(key, value),
            )
        if not self.is_editable():
            raise ValueError("Keep the appliance powered on and in standby")
        if (
            key != ControlAttributes.program_control
            and self.attributes.get(key) is None
        ):
            raise ValueError("This parameter is unavailable in the current program")
        return MessageParameters(
            protocol_version,
            self.encode(key, value),
        )

    def _encode(self, attr: ControlAttributes, value: bool | float | str) -> bytearray:
        """Encode a verified select option, preserving all other fields."""
        label = option_label(value)
        if label not in self.options(attr):
            raise ValueError(f"Unsupported laundry option: {label}")
        field = self.fields[attr]
        code = next(code for code, option in field.options.items() if option == label)
        body = parameter_body()
        body[field.offset] = code
        return body

    def is_editable(self) -> bool:
        """Only edit a standby washer in normal operating mode."""
        return self._is_editable() and self.body[MODE_OFFSET] == NORMAL_MODE

    def appointment_enabled(self) -> bool:
        """Read the washer's single-bit reservation flag."""
        return bool(self.body[APPOINTMENT_REPORT_OFFSET] & APPOINTMENT_REPORT_MASK)

    def appointment_available(self) -> bool:
        """Require the V2 cloud-cycle fields and normal operating mode."""
        return (
            self._appointment_available()
            and len(self.body) >= CLOUD_PROGRAM_END
            and self.body[MODE_OFFSET] == NORMAL_MODE
        )

    def encode_appointment(self, *, enabled: bool, wait: int) -> bytearray:
        """Register/cancel atomically, preserving the complete cloud program."""
        # Cancellation must pause AND clear the flag/wait in the same command:
        # clearing only the wait could start the selected cycle immediately.
        # V2 needs both the legacy flag and the byte-35 control field below.
        body = parameter_body(FRESH_BODY_LENGTH)
        body[BASIC_PARAMETER_START:BASIC_PARAMETER_END] = self.body[
            BASIC_PARAMETER_START:BASIC_PARAMETER_END
        ]
        body[STATUS_OFFSET] = START_COMMAND if enabled else PAUSE_COMMAND
        body[APPOINTMENT_REPORT_OFFSET] = self.body[
            APPOINTMENT_REPORT_OFFSET
        ] & ~APPOINTMENT_REPORT_MASK | (APPOINTMENT_REPORT_MASK if enabled else 0)
        body[APPOINTMENT_TIME_OFFSET:APPOINTMENT_TIME_END] = wait.to_bytes(
            APPOINTMENT_TIME_END - APPOINTMENT_TIME_OFFSET,
            "little",
        )
        body[V2_CONTROL_OFFSET] = V2_CONTROL_VERSION
        body[APPOINTMENT_CONTROL_OFFSET] = (
            APPOINTMENT_ON if enabled else APPOINTMENT_OFF
        )
        # FF is not "unchanged" for these selectors: preserve the real report
        # to avoid resetting the selected program's temperature/time presets.
        body[CLOUD_PROGRAM_START:CLOUD_PROGRAM_END] = self.body[
            CLOUD_PROGRAM_START:CLOUD_PROGRAM_END
        ]
        return body

    def minute_codes(self, attr: ControlAttributes) -> dict[str, int]:
        """Calculate options from effective minutes and the request level."""
        if not self.body:
            return {}
        request_offset, minutes_offset, offsets = TIME_FIELDS[attr]
        request, actual = self.body[request_offset], self.body[minutes_offset]
        if request >= len(offsets) or not 0 < actual < MINUTE_SENTINEL:
            return {}
        base = actual - offsets[request]
        if base + min(offsets) <= 0:
            return {}
        return {
            str(base + offsets[code]): code
            for code in sorted(range(len(offsets)), key=lambda code: offsets[code])
            if 0 < base + offsets[code] < MINUTE_SENTINEL
        }

    def decode(self) -> dict[ControlAttributes, ControlValue]:
        """Keep unsupported fields unknown and request codes separate from minutes."""
        values = self._decode()
        values[ControlAttributes.rinse_count] = self.fields[
            ControlAttributes.rinse_count
        ].options.get(self.body[RINSE_OFFSET] >> NIBBLE_SHIFT)
        for attr, (_, minutes_offset, _) in TIME_FIELDS.items():
            values[attr] = (
                str(self.body[minutes_offset]) if self.minute_codes(attr) else None
            )
        values[ControlAttributes.forget_free] = (
            bool(self.body[FRESH_REPORT_OFFSET] & FRESH_REPORT_MASK)
            if len(self.body) >= FRESH_STATUS_LENGTH
            else None
        )
        return values

    def options(self, attr: str) -> list[str]:
        """Return dynamic actual-minute options where the report supports them."""
        key = ControlAttributes(attr)
        if key in TIME_FIELDS:
            return list(self.minute_codes(key))
        return self._options(attr)

    def encode(self, attr: ControlAttributes, value: bool | float | str) -> bytearray:
        """Write one parameter without powering or starting the appliance."""
        if attr == ControlAttributes.forget_free:
            return self.encode_fresh(value)
        if attr in TIME_FIELDS:
            codes = self.minute_codes(attr)
            label = option_label(value)
            if label not in codes:
                raise ValueError(f"Unsupported time for the current program: {label}")
            body = parameter_body()
            body[TIME_FIELDS[attr][0]] = codes[label]
            return body
        body = self._encode(attr, value)
        if attr == ControlAttributes.rinse_count:
            # Only the upper nibble is rinse count; F preserves the drying flag.
            body[RINSE_OFFSET] = body[RINSE_OFFSET] << NIBBLE_SHIFT | KEEP_DRYER_NIBBLE
        return body

    def encode_fresh(self, value: bool | float | str) -> bytearray:
        """Use fresh_anion_switch, retaining complete parameters and cloud cycle."""
        # The full V2 frame preserves basic parameters and cloud selectors.
        # On-device toggles retained both default and custom 60/12-minute
        # wash/spin selections; verification never executed a washing cycle.
        if not isinstance(value, bool):
            raise ValueWrongType("Forget-free requires bool")
        body = parameter_body(FRESH_BODY_LENGTH)
        body[BASIC_PARAMETER_START:BASIC_PARAMETER_END] = self.body[
            BASIC_PARAMETER_START:BASIC_PARAMETER_END
        ]
        body[V2_CONTROL_OFFSET] = V2_CONTROL_VERSION
        body[FRESH_CONTROL_OFFSET] = FRESH_ON if value else FRESH_OFF
        # Unlike ordinary parameter bytes, FF here changes the selected cycle
        # and resets temperature/time defaults on this model.
        body[CLOUD_PROGRAM_START:CLOUD_PROGRAM_END] = self.body[
            CLOUD_PROGRAM_START:CLOUD_PROGRAM_END
        ]
        return body

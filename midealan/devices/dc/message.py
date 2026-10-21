"""Midea DC messages and model-specific parameter encoding."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import NamedTuple

from midealan.const import DeviceType
from midealan.exceptions import ValueWrongType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

MINIMUM_STATUS_LENGTH = 30
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
STATUS_RUNNING_PAUSED = 3

type ControlValue = bool | int | str | None


PROFILE_MODEL = "38208801"
PROFILE_SUBTYPE = 13367
STATUS_IDLE = 0
STATUS_STANDBY = 1
STATUS_PAUSE = 3
STATUS_END = 4
STATUS_PREVENT_WRINKLE_END = 5
DRY_TIME_OFFSET = 5
DRY_TIME_END = 7
DRYNESS_OFFSET = 9
DRYNESS_READY_TO_WEAR = 2
DRYNESS_STORAGE = 3
STERILIZE_MODE_OFFSET = 11
ANTI_WRINKLE_OFFSET = 12
STERILIZE_FLAG_OFFSET = 13
FEATURE_SHIFT = 2
FEATURE_MASK = 0x03
FEATURE_OFF = 0xF3
FEATURE_ON = 0xF7
EXTENDED_STATUS_LENGTH = 43
TEMPERATURE_REPORT_OFFSET = 36
SEASON_REPORT_OFFSET = 42
TEMPERATURE_BODY_LENGTH = 33
TEMPERATURE_CONTROL_OFFSET = 24
RESERVED_CONTROL_OFFSET = 28
SEASON_CONTROL_OFFSET = 29
TIMED_PROGRAM = 26
TIMED_EXTRA_MAX = 170
TIMED_EXTRA_STEP = 10
UNKNOWN_CODE = 0xFF
STATUS_START = 2
STATUS_DELAY_CHOOSING = 6
STATUS_DELAY = 8
STATUS_DELAY_PAUSE = 9
APPOINTMENT_REPORT_OFFSET = 12
APPOINTMENT_MASK = 0x03
APPOINTMENT_OFF = 0xFC
APPOINTMENT_ON = 0xFD
BASIC_PARAMETER_START = 3
BASIC_PARAMETER_END = 16


class ControlAttributes(StrEnum):
    """Additional dryer controls, separate from legacy sensor keys."""

    parameter_control_supported = "parameter_control_supported"
    parameter_controls_available = "parameter_controls_available"
    program_control = "program_control"
    temperature_control = "temperature_control"
    dryness_control = "dryness_control"
    sterilize = "sterilize"
    anti_wrinkle = "anti_wrinkle"
    timed_extra = "timed_extra"
    appointment_control_supported = "appointment_control_supported"
    appointment_controls_available = "appointment_controls_available"
    appointment = "appointment"
    appointment_finish = "appointment_finish"


class ParameterField(NamedTuple):
    """Body offset and the verified raw-code to option-label mapping."""

    offset: int
    options: dict[int, str]


GENERIC_PROGRAMS = {
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
PROFILE_PROGRAMS = {
    2: "mixed_wash",
    8: "wool",
    27: "night_dry",
    43: "big_dry",
    42: "small_piece_dry",
    14: "baby_clothes",
    6: "down_jacket",
    17: "quick_dry",
    0: "cotton",
    15: "shirt",
    3: "jean",
    13: "underwear",
    64: "school_uniform",
    48: "silk",
    22: "towel",
    100: "chiffon",
    97: "polar_fleece",
    62: "hanfu",
    85: "hanfu_tang",
    86: "hanfu_song",
    88: "hanfu_ming",
    87: "hanfu_modern",
    45: "sun_quilt",
    47: "bucket_self_clean",
    24: "steam_care",
    26: "fixed_time_dry",
    33: "warm_clothes",
    10: "cold_air_fresh_air",
    83: "sterilize_mite",
    28: "bracket_dry",
    114: "pet_sterilize",
    12: "sport_clothes",
    5: "outdoor",
    98: "quick_drying_clothes",
    99: "yoga",
    39: "air_wash",
}
TEMPERATURE_OPTIONS = {1: "standard", 2: "low"}


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


class MessageDCBase(MessageRequest):
    """DC message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize DC message base."""
        super().__init__(
            device_type=DeviceType.DC,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageDCBase):
    """DC message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DC message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X03,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessagePower(MessageDCBase):
    """DC message power."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DC message power."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X02,
        )
        self.power = False

    @property
    def _body(self) -> bytearray:
        power = 0x01 if self.power else 0x00
        return bytearray([power, 0xFF])


class MessageStart(MessageDCBase):
    """DC message start."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize DC message start."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X02,
        )
        self.start = False
        self.washing_data = bytearray([])

    @property
    def _body(self) -> bytearray:
        if self.start:
            return bytearray([0xFF, 0x01]) + self.washing_data
        # Stop
        return bytearray([0xFF, 0x00])


class DCGeneralMessageBody(MessageBody):
    """DC message general body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize DC message general body."""
        super().__init__(body)
        self.power = body[1] > 0
        self.start = body[2] in [2, 6]
        self.status = body[2]
        self.program = body[4]
        self.intensity = body[9]
        self.dryness_level = body[10]
        self.dry_temperature = body[10]
        self.error_code = body[24]
        self.door_warn = body[25]
        self.ai_switch = body[27]
        self.material = body[28]
        self.water_box = body[29]
        self.washing_data = body[3:15]
        self.progress = 0
        self.time_remaining: int | None = None
        for i in range(1, 7):
            if (body[16] & (1 << i)) > 0:
                self.progress = i
                break
        if self.power:
            self.time_remaining = int.from_bytes(
                body[REMAINING_TIME_OFFSET:REMAINING_TIME_END],
                "little",
            )


class MessageDCResponse(MessageResponse):
    """DC message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize DC message response."""
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
            self.set_body(DCGeneralMessageBody(super().body))
        self.set_attr()


class MessageParameters(MessageDCBase):
    """Frame a complete parameter body without appending a message ID."""

    def __init__(self, protocol_version: int, body: bytearray) -> None:
        """Copy the body; normal transport supplies header and checksum."""
        super().__init__(protocol_version, MessageType.set, ListTypes.X02)
        self._parameters = body[1:]

    @property
    def _body(self) -> bytearray:
        """Return parameters following the body type byte."""
        return self._parameters


class DCControls:
    """Decode confirmed dryer parameters and validate complete commands."""

    device_type = DeviceType.DC
    minimum_status_length = MINIMUM_STATUS_LENGTH
    editable_statuses = (
        STATUS_IDLE,
        STATUS_STANDBY,
        STATUS_PAUSE,
        STATUS_END,
        STATUS_PREVENT_WRINKLE_END,
    )
    appointment_statuses = (STATUS_DELAY_CHOOSING, STATUS_DELAY, STATUS_DELAY_PAUSE)

    def __init__(self, *, profile: bool = False) -> None:
        """Start with generic controls and optional verified extensions."""
        self.profile = profile
        self.body = b""
        programs = PROFILE_PROGRAMS if profile else GENERIC_PROGRAMS
        self.fields: dict[ControlAttributes, ParameterField] = {
            ControlAttributes.program_control: ParameterField(PROGRAM_OFFSET, programs),
        }
        if profile:
            self.fields[ControlAttributes.dryness_control] = ParameterField(
                DRYNESS_OFFSET,
                {
                    DRYNESS_READY_TO_WEAR: "ready_to_wear",
                    DRYNESS_STORAGE: "storage",
                },
            )
        self.attribute_keys = (
            *self.fields,
            ControlAttributes.sterilize,
            ControlAttributes.anti_wrinkle,
            *(
                (
                    ControlAttributes.temperature_control,
                    ControlAttributes.timed_extra,
                )
                if profile
                else ()
            ),
        )
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

    @property
    def programs(self) -> dict[int, str]:
        """Return the active generic or verified program mapping."""
        return self.fields[ControlAttributes.program_control].options

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

    def appointment_available(self) -> bool:
        """Allow reservation changes in standby or an existing reservation only."""
        return bool(
            self.body
            and self.body[POWER_OFFSET] == 1
            and self.appointment_enabled() is not None
            and (
                (
                    self.is_editable()
                    and self.body[STATUS_OFFSET] != STATUS_RUNNING_PAUSED
                )
                or (
                    self.body[STATUS_OFFSET] in self.appointment_statuses
                    and self.appointment_enabled() is True
                )
            ),
        )

    def remaining_minutes(self) -> int:
        """Read the verified profiles' little-endian program duration in minutes."""
        return int.from_bytes(
            self.body[REMAINING_TIME_OFFSET:REMAINING_TIME_END],
            "little",
        )

    def appointment_parameters(self) -> bytes:
        """Identify selected parameters independently of reservation/status fields."""
        return (
            self.body[BASIC_PARAMETER_START:APPOINTMENT_REPORT_OFFSET]
            + bytes([self.body[APPOINTMENT_REPORT_OFFSET] & ~APPOINTMENT_MASK])
            + self.body[STERILIZE_FLAG_OFFSET:APPOINTMENT_TIME_OFFSET]
            + (
                self.body[TEMPERATURE_REPORT_OFFSET : TEMPERATURE_REPORT_OFFSET + 1]
                + self.body[SEASON_REPORT_OFFSET : SEASON_REPORT_OFFSET + 1]
                if self.profile
                else b""
            )
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

    def is_editable(self) -> bool:
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

    def appointment_enabled(self) -> bool | None:
        """Decode reservation independently of the adjacent anti-wrinkle field."""
        code = self.body[APPOINTMENT_REPORT_OFFSET] & APPOINTMENT_MASK
        return bool(code) if code in (0, 1) else None

    def encode_appointment(self, *, enabled: bool, wait: int) -> bytearray:
        """Keep all selected parameters and change only reservation and start."""
        body = parameter_body()
        body[BASIC_PARAMETER_START:BASIC_PARAMETER_END] = self.body[
            BASIC_PARAMETER_START:BASIC_PARAMETER_END
        ]
        # Active reservation cancellation first uses a separate pause command.
        # Combining pause with these fields makes the device ignore the clear.
        body[STATUS_OFFSET] = START_COMMAND if enabled else UNCHANGED
        # This verified appliance ignored the generic FD "on" selector.
        # Write an explicit packed byte preserving reported adjacent fields;
        # generic Lua devices retain their FD/FC selector masks.
        body[APPOINTMENT_REPORT_OFFSET] = (
            (self.body[APPOINTMENT_REPORT_OFFSET] & ~APPOINTMENT_MASK) | int(enabled)
            if self.profile
            else APPOINTMENT_ON
            if enabled
            else APPOINTMENT_OFF
        )
        body[APPOINTMENT_TIME_OFFSET:APPOINTMENT_TIME_END] = wait.to_bytes(
            APPOINTMENT_TIME_END - APPOINTMENT_TIME_OFFSET,
            "little",
        )
        return body

    def feature(self, offset: int) -> bool | None:
        """Decode the two-bit field without turning unavailable into off."""
        code = self.body[offset] >> FEATURE_SHIFT & FEATURE_MASK
        return bool(code) if code in (0, 1) else None

    def decode(self) -> dict[ControlAttributes, ControlValue]:
        """Read actual options, including extended temperature and season data."""
        values = self._decode()
        values[ControlAttributes.anti_wrinkle] = self.feature(ANTI_WRINKLE_OFFSET)
        flag = self.feature(STERILIZE_FLAG_OFFSET)
        mode = self.body[STERILIZE_MODE_OFFSET]
        values[ControlAttributes.sterilize] = (
            flag
            if not self.profile
            else flag
            if flag is not None and mode == int(flag)
            else None
        )
        if self.profile:
            values[ControlAttributes.temperature_control] = (
                TEMPERATURE_OPTIONS.get(self.body[TEMPERATURE_REPORT_OFFSET])
                if len(self.body) >= EXTENDED_STATUS_LENGTH
                and self.body[SEASON_REPORT_OFFSET] != UNKNOWN_CODE
                and values[ControlAttributes.anti_wrinkle] is not None
                else None
            )
            extra = int.from_bytes(self.body[DRY_TIME_OFFSET:DRY_TIME_END], "little")
            values[ControlAttributes.timed_extra] = (
                extra
                if self.body[PROGRAM_OFFSET] == TIMED_PROGRAM
                and 0 <= extra <= TIMED_EXTRA_MAX
                and extra % TIMED_EXTRA_STEP == 0
                else None
            )
        return values

    def options(self, attr: str) -> list[str]:
        """Reflect the real instant-wear constraint when sterilization is on."""
        key = ControlAttributes(attr)
        if key == ControlAttributes.temperature_control:
            if not self.profile:
                return []
            return list(TEMPERATURE_OPTIONS.values()) if self.attributes[key] else []
        if key == ControlAttributes.dryness_control:
            if self.attributes.get(key) is None:
                return []
            if self.attributes.get(ControlAttributes.sterilize):
                return ["ready_to_wear"]
        return self._options(attr)

    def encode(self, attr: ControlAttributes, value: bool | float | str) -> bytearray:
        """Use the independently verified body layout for each parameter."""
        if attr == ControlAttributes.temperature_control:
            if not self.profile:
                raise ValueError("This parameter is unavailable in the current profile")
            return self.encode_temperature(value)
        if attr in (ControlAttributes.sterilize, ControlAttributes.anti_wrinkle):
            return self.encode_feature(attr, value)
        if attr == ControlAttributes.timed_extra:
            if not self.profile:
                raise ValueError("This parameter is unavailable in the current profile")
            label = option_label(value)
            if not label.isdecimal():
                raise ValueError("Timed extra must be an integer number of minutes")
            extra = int(label)
            if not 0 <= extra <= TIMED_EXTRA_MAX or extra % TIMED_EXTRA_STEP:
                raise ValueError("Timed extra must be 0..170 minutes in steps of 10")
            body = parameter_body()
            body[DRY_TIME_OFFSET:DRY_TIME_END] = extra.to_bytes(
                DRY_TIME_END - DRY_TIME_OFFSET,
                "little",
            )
            return body
        return self._encode(attr, value)

    def encode_temperature(self, value: bool | float | str) -> bytearray:
        """Preserve anti-wrinkle and season with the complete extended command."""
        label = option_label(value)
        if label not in self.options(ControlAttributes.temperature_control):
            raise ValueError(f"Unsupported dryer temperature: {label}")
        code = next(
            code for code, option in TEMPERATURE_OPTIONS.items() if option == label
        )
        body = parameter_body(TEMPERATURE_BODY_LENGTH)
        body[ANTI_WRINKLE_OFFSET] = (
            FEATURE_ON
            if self.attributes[ControlAttributes.anti_wrinkle]
            else FEATURE_OFF
        )
        body[TEMPERATURE_CONTROL_OFFSET] = code
        body[RESERVED_CONTROL_OFFSET] = 0
        body[SEASON_CONTROL_OFFSET] = self.body[SEASON_REPORT_OFFSET]
        return body

    def encode_feature(
        self,
        attr: ControlAttributes,
        value: bool | float | str,
    ) -> bytearray:
        """Set both sterilization fields and enforce instant-wear when supported."""
        if not isinstance(value, bool):
            raise ValueWrongType("Dryer feature switches require bool")
        body = parameter_body()
        offset = (
            STERILIZE_FLAG_OFFSET
            if attr == ControlAttributes.sterilize
            else ANTI_WRINKLE_OFFSET
        )
        body[offset] = FEATURE_ON if value else FEATURE_OFF
        if attr == ControlAttributes.sterilize and self.profile:
            body[STERILIZE_MODE_OFFSET] = int(value)
            if value and self.body[DRYNESS_OFFSET] in (
                DRYNESS_READY_TO_WEAR,
                DRYNESS_STORAGE,
            ):
                body[DRYNESS_OFFSET] = DRYNESS_READY_TO_WEAR
        return body

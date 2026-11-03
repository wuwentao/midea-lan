"""Midea lan C3 message."""

from collections.abc import Mapping
from enum import IntEnum, StrEnum
from math import isfinite
from typing import ClassVar

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

BYTE_BITS = 8
ENERGY_SCALE = 100

QUINTUPLE_MODEL = "17100007"
BASIC_TABLE = 0x2010
ENERGY_TABLE = 0x2F12
ENVELOPE_LENGTH = 10
FORMAT_OFFSET = 7
TLV_FORMAT = 1
TLV_HEADER_LENGTH = 3
INVALID_BYTE = 0xFF
INVALID_TEMPERATURE = 0x7FFF
TEMPERATURE_SCALE = 10
AUTO_MODE_TAG = 28
ERROR_CODE_TAG = 42
WATTS_PER_ENERGY_UNIT = 10
ENERGY_SIZES = (1, 4, 2, 2, 2) + (4,) * 31
MIN_ENERGY_LENGTH = ENVELOPE_LENGTH + sum(ENERGY_SIZES[:12])
QUINTUPLE_ENERGY_FIELDS = {
    2: "current_unit_capacity",
    3: "instant_renew_power0",
    4: "instant_power0",
    6: "total_produced_energy",
    9: "total_energy_consumption",
}
QUINTUPLE_ENERGY_ATTRIBUTES = frozenset(QUINTUPLE_ENERGY_FIELDS.values())
WATT_TAGS = frozenset((3, 4))


class BasicTag(IntEnum):
    """Writable fields in the vendor's 0x2010 table."""

    ZONE1_POWER = 0
    ZONE2_POWER = 1
    DHW_POWER = 2
    MODE = 3
    ZONE1_TEMPERATURE = 4
    ZONE2_TEMPERATURE = 5
    ROOM_TEMPERATURE = 6
    DHW_TEMPERATURE = 7
    ZONE1_CURVE = 8
    ZONE2_CURVE = 9
    TANK_BOOSTER = 10
    FAST_DHW = 11


TEMPERATURE_TAGS = frozenset(
    (
        BasicTag.ZONE1_TEMPERATURE,
        BasicTag.ZONE2_TEMPERATURE,
        BasicTag.ROOM_TEMPERATURE,
        BasicTag.DHW_TEMPERATURE,
    ),
)
WIRE_MODES = frozenset((0, 2, 3, 5))
MODE_FROM_WIRE = {0: 0, 2: 2, 3: 3, 5: 1}
MODE_TO_WIRE = {0: 0, 1: 5, 2: 2, 3: 3}

# Sizes of every entry, including the ASCII and reserved entries needed to
# locate trailing fields in sequential responses. Indexes are vendor tags.
BASIC_SIZES = (
    1,
    1,
    1,
    1,
    2,
    2,
    2,
    2,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    5,
    12,
    4,
    2,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    2,
    1,
    1,
)
MIN_SEQUENTIAL_LENGTH = ENVELOPE_LENGTH + sum(BASIC_SIZES[:53])
BOOLEAN_FIELDS = {
    0: "zone1_power",
    1: "zone2_power",
    2: "dhw_power",
    8: "zone1_curve",
    9: "zone2_curve",
    10: "tbh",
    11: "fast_dhw",
    12: "remote_onoff",
    13: "silent_mode",
    14: "heat",
    15: "cool",
    16: "dhw",
    17: "double_zone",
    20: "room_thermal_support",
    21: "room_thermal_state",
    22: "time_set",
    24: "holiday_on",
    25: "eco_mode",
    44: "tbh_control",
    47: "sys_energy_ana_en",
    48: "hmi_energy_ana_set_en",
}
TEMPERATURE_FIELDS = {
    6: "room_target_temp",
    7: "dhw_target_temp",
    37: "room_temp_max",
    38: "room_temp_min",
    39: "dhw_temp_max",
    40: "dhw_temp_min",
    41: "tank_actual_temperature",
    52: "outdoor_temperature",
}
TEMPERATURE_LIMIT_FIELDS = frozenset(
    ("room_temp_max", "room_temp_min", "dhw_temp_max", "dhw_temp_min"),
)
ARRAY_FIELDS = {
    "zone_target_temp": (4, 5),
    "zone_heating_temp_max": (29, 33),
    "zone_heating_temp_min": (30, 34),
    "zone_cooling_temp_max": (31, 35),
    "zone_cooling_temp_min": (32, 36),
}
ZONE_TEMP_TYPE_TAGS = (18, 19)
STATUS_TEMPERATURE_ATTRIBUTES = {
    4: ("zone1_temp_set", "idu_t1s1"),
    5: ("zone2_temp_set",),
    6: ("tas",),
    7: ("t5s",),
    52: ("temp_t4",),
}


def _envelope(table: int, format_code: int) -> bytearray:
    return bytearray(
        table.to_bytes(2, "big")
        + b"\xff\xff\xff\xff"
        + bytes((format_code, INVALID_BYTE, INVALID_BYTE)),
    )


class MessageQuery2010(MessageRequest):
    """Query basic status with the exact vendor query envelope."""

    def __init__(self, protocol_version: int = 0) -> None:
        """Initialize the model-specific status request."""
        super().__init__(
            DeviceType.C3,
            protocol_version,
            MessageType.query,
            ListTypes.X00,
        )

    @property
    def _body(self) -> bytearray:
        return _envelope(BASIC_TABLE, 0)


class MessageQuery2F12(MessageQuery2010):
    """Query the vendor energy table without changing any settings."""

    @property
    def _body(self) -> bytearray:
        return _envelope(ENERGY_TABLE, 0)


class MessageSet2010(MessageRequest):
    """Write only the supplied 0x2010 properties in TLV form."""

    def __init__(
        self,
        values: dict[BasicTag, bool | float | int],
        protocol_version: int = 0,
    ) -> None:
        """Validate and encode a sparse set of control properties."""
        super().__init__(
            DeviceType.C3,
            protocol_version,
            MessageType.set,
            ListTypes.X00,
        )
        if not values:
            raise ValueError("A C3 control request must contain a property")
        self._encoded = _envelope(BASIC_TABLE, TLV_FORMAT)
        for tag, value in sorted(values.items()):
            if tag not in BasicTag:
                raise ValueError("Unsupported C3 control property")
            if tag in TEMPERATURE_TAGS:
                temperature = float(value)
                if not isfinite(temperature):
                    raise ValueError("Invalid C3 target temperature")
                scaled = round(temperature * TEMPERATURE_SCALE)
                if not 0 <= scaled < INVALID_TEMPERATURE:
                    raise ValueError("Invalid C3 target temperature")
                data = scaled.to_bytes(2, "big")
            elif tag == BasicTag.MODE:
                if value not in WIRE_MODES:
                    raise ValueError("Unsupported C3 operating mode")
                data = bytes((int(value),))
            else:
                if not isinstance(value, bool):
                    raise ValueError(
                        "C3 power and curve controls require boolean values",
                    )
                data = bytes((int(value),))
            self._encoded.extend(
                int(tag).to_bytes(2, "big") + bytes((len(data),)) + data,
            )

    @property
    def _body(self) -> bytearray:
        return self._encoded


def _read_fields(
    body: bytearray,
    sizes: tuple[int, ...] = BASIC_SIZES,
    minimum_length: int = MIN_SEQUENTIAL_LENGTH,
) -> dict[int, bytes]:
    if len(body) < ENVELOPE_LENGTH:
        return {}
    values = {}
    offset = ENVELOPE_LENGTH
    if body[FORMAT_OFFSET] == TLV_FORMAT:
        while offset < len(body):
            if offset + TLV_HEADER_LENGTH > len(body):
                return {}
            tag = int.from_bytes(body[offset : offset + 2], "big")
            size = body[offset + 2]
            offset += TLV_HEADER_LENGTH
            if offset + size > len(body):
                return {}
            if tag < len(sizes):
                if size != sizes[tag]:
                    return {}
                values[tag] = bytes(body[offset : offset + size])
            offset += size
    elif body[FORMAT_OFFSET] == 0:
        if len(body) < minimum_length:
            return {}
        for tag, size in enumerate(sizes):
            if offset + size > len(body):
                break
            values[tag] = bytes(body[offset : offset + size])
            offset += size
    return values


def _temperature(raw: bytes) -> float | None:
    if int.from_bytes(raw, "big") == INVALID_TEMPERATURE:
        return None
    return int.from_bytes(raw, "big", signed=True) / TEMPERATURE_SCALE


class C3QuintupleEnergyBody(MessageBody):
    """Decode 0x2F12 energy using the vendor's 0.01 kW/kWh scale."""

    quintuple_energy: bool
    current_unit_capacity: float | None
    instant_renew_power0: float | None
    instant_power0: float | None
    total_produced_energy: float | None
    total_energy_consumption: float | None

    def __init__(self, body: bytearray) -> None:
        """Expose complete energy fields from sequential or TLV packets."""
        super().__init__(body)
        values = _read_fields(body, ENERGY_SIZES, MIN_ENERGY_LENGTH)
        self.quintuple_energy = bool(values)
        for tag, name in QUINTUPLE_ENERGY_FIELDS.items():
            if tag in values:
                raw = values[tag]
                value = int.from_bytes(raw, "big")
                invalid = (1 << (len(raw) * BYTE_BITS)) - 1
                scaled = (
                    value * WATTS_PER_ENERGY_UNIT
                    if tag in WATT_TAGS
                    else value / ENERGY_SCALE
                )
                setattr(self, name, None if value == invalid else scaled)


class C3QuintupleBasicBody(MessageBody):
    """Decode sequential status and sparse control acknowledgements."""

    quintuple_basic: bool
    quintuple_arrays: dict[str, dict[int, float | bool | None]]
    outdoor_temperature: float

    def __init__(self, body: bytearray) -> None:
        """Expose valid fields, retaining absent array members in the device."""
        super().__init__(body)
        values = _read_fields(body)
        self.quintuple_basic = bool(values)
        self.quintuple_arrays = {}
        for tag, name in BOOLEAN_FIELDS.items():
            if tag in values:
                raw = values[tag][0]
                setattr(self, name, bool(raw) if raw in (0, 1) else None)
        for tag, name in TEMPERATURE_FIELDS.items():
            if tag in values and (
                (value := _temperature(values[tag])) is not None
                or name in TEMPERATURE_LIMIT_FIELDS
            ):
                setattr(self, name, value)
        for name, tags in ARRAY_FIELDS.items():
            changes: dict[int, float | bool | None] = {
                index: value
                for index, tag in enumerate(tags)
                if tag in values
                and (
                    (value := _temperature(values[tag])) is not None
                    or name != "zone_target_temp"
                )
            }
            if changes:
                self.quintuple_arrays[name] = changes
        types: dict[int, float | bool | None] = {
            index: values[tag][0] == 0 if values[tag][0] in (0, 1) else None
            for index, tag in enumerate(ZONE_TEMP_TYPE_TAGS)
            if tag in values
        }
        if types:
            self.quintuple_arrays["zone_temp_type"] = types
        if BasicTag.MODE in values:
            self.mode = MODE_FROM_WIRE.get(values[BasicTag.MODE][0])
        if AUTO_MODE_TAG in values:
            self.mode_auto = (
                values[AUTO_MODE_TAG][0] + 1
                if values[AUTO_MODE_TAG][0] in (1, 2)
                else None
            )
        if ERROR_CODE_TAG in values and values[ERROR_CODE_TAG][0] != INVALID_BYTE:
            self.error_code = values[ERROR_CODE_TAG][0]
        for tag, names in STATUS_TEMPERATURE_ATTRIBUTES.items():
            if tag in values and (value := _temperature(values[tag])) is not None:
                for name in names:
                    setattr(self, name, value)


SILENT_LEVELS = ("level_1", "level_2", "level_3")
ENERGY_TABLES = (0x2F11, 0x2F10, 0x2F17)
CONTROL_TABLES = (0x2050, 0x2070, 0x2090)
TABLE_SIZES: dict[int, tuple[int, ...]] = {
    0x2050: (1,) * 12,
    0x2070: (1,) * 7,
    0x2090: (1,) * 7,
    0x2F11: (1,) * 4 + (4,) * 48,
    0x2F12: (1,) + (4,) + (2,) * 3 + (4,) * 31,
    0x2F17: (1,) * 9 + (4,) * 2 + (2,) * 7 + (1,) * 49,
}
MIN_FIELDS = {0x2050: 2, 0x2070: 2, 0x2090: 5, 0x2F11: 20, 0x2F12: 12, 0x2F17: 6}
TABLE_FIELDS: dict[tuple[int, int], tuple[tuple[str, ...], str]] = {
    (0x2F11, 6): (("heating_power",), "scaled"),
    (0x2F11, 4): (("heating_heat_output",), "scaled"),
    (0x2F11, 7): (("heating_cop",), "scaled"),
    (0x2F11, 10): (("heating_total_energy",), "scaled"),
    (0x2F11, 8): (("heating_total_heat",), "scaled"),
    (0x2F11, 11): (("heating_total_cop",), "scaled"),
    (0x2F11, 22): (("heating_energy_today",), "scaled"),
    (0x2F11, 20): (("heating_heat_today",), "scaled"),
    (0x2F11, 23): (("heating_cop_today",), "scaled"),
    (0x2F11, 26): (("heating_energy_this_week",), "scaled"),
    (0x2F11, 24): (("heating_heat_this_week",), "scaled"),
    (0x2F11, 27): (("heating_cop_this_week",), "scaled"),
    (0x2F11, 30): (("heating_energy_this_month",), "scaled"),
    (0x2F11, 28): (("heating_heat_this_month",), "scaled"),
    (0x2F11, 31): (("heating_cop_this_month",), "scaled"),
    (0x2F11, 34): (("heating_energy_this_year",), "scaled"),
    (0x2F11, 32): (("heating_heat_this_year",), "scaled"),
    (0x2F11, 35): (("heating_cop_this_year",), "scaled"),
    (0x2F11, 14): (("cooling_power",), "scaled"),
    (0x2F11, 12): (("cooling_heat_output",), "scaled"),
    (0x2F11, 15): (("cooling_cop",), "scaled"),
    (0x2F11, 18): (("cooling_total_energy",), "scaled"),
    (0x2F11, 16): (("cooling_total_heat",), "scaled"),
    (0x2F11, 19): (("cooling_total_cop",), "scaled"),
    (0x2F11, 38): (("cooling_energy_today",), "scaled"),
    (0x2F11, 36): (("cooling_heat_today",), "scaled"),
    (0x2F11, 39): (("cooling_cop_today",), "scaled"),
    (0x2F11, 42): (("cooling_energy_this_week",), "scaled"),
    (0x2F11, 40): (("cooling_heat_this_week",), "scaled"),
    (0x2F11, 43): (("cooling_cop_this_week",), "scaled"),
    (0x2F11, 46): (("cooling_energy_this_month",), "scaled"),
    (0x2F11, 44): (("cooling_heat_this_month",), "scaled"),
    (0x2F11, 47): (("cooling_cop_this_month",), "scaled"),
    (0x2F11, 50): (("cooling_energy_this_year",), "scaled"),
    (0x2F11, 48): (("cooling_heat_this_year",), "scaled"),
    (0x2F11, 51): (("cooling_cop_this_year",), "scaled"),
    (0x2F12, 14): (("dhw_power_consumption",), "scaled"),
    (0x2F12, 12): (("dhw_heat_output",), "scaled"),
    (0x2F12, 15): (("dhw_cop",), "scaled"),
    (0x2F12, 18): (("dhw_total_energy",), "scaled"),
    (0x2F12, 16): (("dhw_total_heat",), "scaled"),
    (0x2F12, 19): (("dhw_total_cop",), "scaled"),
    (0x2F12, 22): (("dhw_energy_today",), "scaled"),
    (0x2F12, 20): (("dhw_heat_today",), "scaled"),
    (0x2F12, 23): (("dhw_cop_today",), "scaled"),
    (0x2F12, 26): (("dhw_energy_this_week",), "scaled"),
    (0x2F12, 24): (("dhw_heat_this_week",), "scaled"),
    (0x2F12, 27): (("dhw_cop_this_week",), "scaled"),
    (0x2F12, 30): (("dhw_energy_this_month",), "scaled"),
    (0x2F12, 28): (("dhw_heat_this_month",), "scaled"),
    (0x2F12, 31): (("dhw_cop_this_month",), "scaled"),
    (0x2F12, 34): (("dhw_energy_this_year",), "scaled"),
    (0x2F12, 32): (("dhw_heat_this_year",), "scaled"),
    (0x2F12, 35): (("dhw_cop_this_year",), "scaled"),
    (0x2F12, 2): (("heat_output",), "scaled"),
    (0x2F12, 5): (("instant_cop",), "scaled"),
    (0x2F12, 11): (("total_cop",), "scaled"),
    (0x2050, 0): (("silent_mode",), "boolean"),
    (0x2050, 1): (("_silent_level",), "level"),
    (0x2070, 0): (("eco_mode", "eco_function_state"), "boolean"),
    (0x2070, 1): (("eco_timer_state",), "boolean"),
    (0x2090, 0): (("disinfect",), "boolean"),
    (0x2090, 1): (("disinfect_run",), "boolean"),
    (0x2090, 2): (("disinfect_set_weekday",), "integer"),
    (0x2090, 3): (("disinfect_start_hour",), "integer"),
    (0x2090, 4): (("disinfect_start_minutes",), "integer"),
    (0x2F17, 1): (("status_heating", "heat_run"), "boolean"),
    (0x2F17, 2): (("status_cool", "cool_run"), "boolean"),
    (0x2F17, 3): (("status_dhw", "dhw_run"), "boolean"),
    (0x2F17, 4): (("status_tbh",), "boolean"),
    (0x2F17, 5): (("status_ibh",), "boolean"),
}
FEATURE_ENERGY_ATTRIBUTES = frozenset(
    names[0] for names, kind in TABLE_FIELDS.values() if kind == "scaled"
)


def decode_table(body: bytearray) -> dict[str, bool | float | int | str | None]:
    """Decode mapped values from complete core blocks or atomic sparse TLVs."""
    if len(body) < ENVELOPE_LENGTH:
        return {}
    table = int.from_bytes(body[1:3], "big")
    if table not in TABLE_SIZES:
        return {}
    sizes = TABLE_SIZES[table]
    minimum = ENVELOPE_LENGTH + sum(sizes[: MIN_FIELDS[table]])
    fields = _read_fields(body, sizes, minimum)
    result: dict[str, bool | float | int | str | None] = {}
    for tag, raw in fields.items():
        spec = TABLE_FIELDS.get((table, tag))
        if spec is None:
            continue
        names, kind = spec
        number = int.from_bytes(raw, "big")
        value: bool | float | int | str | None
        if number == (1 << (len(raw) * BYTE_BITS)) - 1:
            value = None
        elif kind == "boolean":
            value = bool(number) if number in (0, 1) else None
        elif kind == "level":
            value = SILENT_LEVELS[number] if number < len(SILENT_LEVELS) else None
        else:
            value = number / ENERGY_SCALE if kind == "scaled" else number
        for name in names:
            result[name] = value
    return result


class MessageQueryTable(MessageRequest):
    """Read a known table, with independent unsupported-query tracking."""

    def __init__(self, table: int, protocol_version: int = 0) -> None:
        """Reject table identifiers outside the curated protocol."""
        if table not in (*TABLE_SIZES, *ENERGY_TABLES):
            raise ValueError("Unknown C3 table")
        super().__init__(
            DeviceType.C3,
            protocol_version,
            MessageType.query,
            ListTypes.X00,
        )
        self._encoded = _envelope(table, 0)

    @property
    def _body(self) -> bytearray:
        return self._encoded


QUERY_CLASSES: dict[int, type[MessageQueryTable]] = {
    table: type(f"MessageQueryC3{table:04X}", (MessageQueryTable,), {})
    for table in (*TABLE_SIZES, *ENERGY_TABLES)
}


def query_table(table: int, protocol_version: int) -> MessageQueryTable:
    """Build a request whose class identifies its particular table."""
    return QUERY_CLASSES[table](table, protocol_version)


class FeatureSetting(StrEnum):
    """Normal user controls with a verified native encoding."""

    SILENT_POWER = "silent_mode"
    SILENT_LEVEL = "silent_level"
    ECO = "eco_mode"
    DISINFECT = "disinfect"


class MessageSetSettings(MessageRequest):
    """Write selected user settings atomically without replaying other fields."""

    _fields: ClassVar[dict[FeatureSetting, tuple[int, int]]] = {
        FeatureSetting.SILENT_POWER: (0x2050, 0),
        FeatureSetting.SILENT_LEVEL: (0x2050, 1),
        FeatureSetting.ECO: (0x2070, 0),
        FeatureSetting.DISINFECT: (0x2090, 0),
    }

    def __init__(
        self,
        values: Mapping[FeatureSetting, bool | str],
        protocol_version: int = 0,
    ) -> None:
        """Reject unknown settings, mixed tables and incorrect value types."""
        super().__init__(
            DeviceType.C3,
            protocol_version,
            MessageType.set,
            ListTypes.X00,
        )
        if not values or any(key not in self._fields for key in values):
            raise ValueError("Unknown or empty C3 setting")
        tables = {self._fields[key][0] for key in values}
        if len(tables) != 1:
            raise ValueError("C3 settings must belong to the same table")
        self._encoded = _envelope(tables.pop(), TLV_FORMAT)
        for key, value in sorted(
            values.items(),
            key=lambda item: self._fields[item[0]][1],
        ):
            if key == FeatureSetting.SILENT_LEVEL:
                if not isinstance(value, str) or value not in SILENT_LEVELS:
                    raise ValueError("Invalid C3 silent level")
                encoded = SILENT_LEVELS.index(value)
            else:
                if not isinstance(value, bool):
                    raise ValueError("C3 switches require boolean values")
                encoded = int(value)
            self._encoded.extend(
                self._fields[key][1].to_bytes(2, "big") + bytes((1, encoded)),
            )

    @property
    def _body(self) -> bytearray:
        return self._encoded


TEMP_NEG_VALUE = 127

# Sentinels for probes/curves the unit does not have installed. Confirmed
# against a Galmet Prima 06 GT: a wired-HMI reading sheet transcribed at the
# same timestamps as a LAN capture shows "-" (not installed) for every one of
# these fields exactly when the LAN byte reads the sentinel value below, so
# the byte means "not present", not a literal 127 degC or an active curve.
TEMP_PROBE_DISCONNECTED = 0x7F
CURVE_SETPOINT_INACTIVE = 0xFF

C3_SHORT_X01_BODY_LENGTH = 50
C3_SHORT_X01_POWER_OFFSET = 2
C3_SHORT_X01_SETPOINT_OFFSET = 3
C3_SHORT_X01_MODE_SENTINEL_OFFSET = 4
C3_SHORT_X01_STATUS_OFFSET = 16
C3_SHORT_X01_TBH_OFFSET = 24
C3_SHORT_SETPOINT_BIAS = 35
C3_SHORT_DHW_POWER_MASK = 0x02
C3_SHORT_DHW_RUNNING_MASK = 0x20
C3_SHORT_COMPRESSOR_RUNNING_MASK = 0x80
C3_SHORT_TBH_MASK = 0x10
C3_SHORT_DHW_TEMP_MIN = 55.0
C3_SHORT_DHW_TEMP_MAX = 70.0

C3_DIAGNOSTIC_WATER_TEMP_OFFSET = 7
C3_DIAGNOSTIC_TANK_TEMP_OFFSET = 9
C3_DIAGNOSTIC_INSTANT_POWER_OFFSET = 18
C3_DIAGNOSTIC_DHW_STATUS_OFFSET = 29
C3_DIAGNOSTIC_TOTAL_COUNTER_OFFSET = 36
C3_DIAGNOSTIC_TEMP_FACTOR = 10.0
C3_DIAGNOSTIC_BODY_MIN_LENGTH = C3_DIAGNOSTIC_TOTAL_COUNTER_OFFSET + 3


def _temp_or_none(raw: int) -> int | None:
    """Map the disconnected-probe sentinel (0x7F) to None."""
    return None if raw == TEMP_PROBE_DISCONNECTED else raw


def _setpoint_or_none(raw: int) -> int | None:
    """Map the curve-inactive sentinel (0xFF) to None."""
    return None if raw == CURVE_SETPOINT_INACTIVE else raw


def _read_be16(body: bytearray, offset: int) -> int:
    """Read an unsigned big-endian 16-bit value."""
    return (MessageBody.read_byte(body, offset) << 8) + MessageBody.read_byte(
        body,
        offset + 1,
    )


def _read_be24(body: bytearray, offset: int) -> int:
    """Read an unsigned big-endian 24-bit value."""
    return (
        (MessageBody.read_byte(body, offset) << 16)
        + (MessageBody.read_byte(body, offset + 1) << 8)
        + MessageBody.read_byte(body, offset + 2)
    )


# Serial-number blocks appended to the X10 telemetry frame. The lua splits
# the tail into three fixed 32-byte ASCII blocks (1-indexed):
#   iduSNCode = _bodyBytes[96..127]
#   oduSNCode = _bodyBytes[128..159]
#   hmiSNCode = _bodyBytes[160..191]
# Only the HMI block is decoded; on the captured 171H120F the IDU and ODU
# blocks are dash-filled. Unused positions are padded with "-", and a block
# shorter than its full width is NUL-terminated.
SN_BLOCK_LENGTH = 32
HMI_SN_BLOCK_OFFSET = 159


def _parse_sn_block(
    body: bytearray,
    data_offset: int,
    block_offset: int,
) -> str | None:
    """Decode one fixed-width, dash-padded ASCII serial-number block.

    Returns None when the frame stops before the block, when the block holds
    only padding, or when its content is not printable ASCII.
    """
    start = data_offset + block_offset
    end = start + SN_BLOCK_LENGTH
    if len(body) < end:
        return None
    block = bytes(body[start:end])
    terminator = block.find(0)
    if terminator == -1:
        # No NUL in the block: only a fully populated 32-byte value is
        # valid. A dash-padded block with no terminator is a partial or
        # corrupt record, not a short serial that happens to fill the slot.
        if block.strip(b"-") != block:
            return None
    else:
        # Bytes after the terminator must be pure dash padding. Anything
        # else (garbage, a second value) makes the record untrustworthy.
        if block[terminator + 1 :].strip(b"-"):
            return None
        block = block[:terminator]
    candidate = block.strip(b"-").strip()
    if not candidate:
        return None
    try:
        decoded = candidate.decode("ascii")
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


# Outdoor fan speed is transmitted as RPM / 10.
FAN_SPEED_FACTOR = 10

# Newer C3 controllers report state in an unsolicited X00 envelope whose
# first byte is 0x00 and whose next two bytes are the inner command.
C3_X00_COMMAND_OFFSET = 1
C3_X00_COMMAND_LENGTH = 2
C3_X00_U16_LENGTH = 2
C3_X00_U32_LENGTH = 4
C3_X00_TEMPERATURE_SCALE = 10
C3_X00_PRESSURE_SCALE = 10
C3_X00_WATER_FLOW_SCALE = 100
C3_X00_CURRENT_UNIT_CAPACITY_SCALE = 100
C3_X00_DC_CURRENT_SCALE = 100
C3_X00_SIGN_BIT = 0x8000
C3_X00_SIGN_VALUE_MASK = 0x7FFF
C3_X00_INVALID_U16 = 0xFFFF
C3_X00_TELEMETRY_MODEL = QUINTUPLE_MODEL

# Basic state command used by model 17100007. Temperatures in this frame are
# unsigned 16-bit big-endian values in tenths of a degree Celsius.
C3_2010_COMMAND = bytes((0x20, 0x10))
C3_2010_DHW_TARGET_TEMP_OFFSET = 20
C3_2010_TANK_ACTUAL_TEMP_OFFSET = 67
C3_2010_OUTDOOR_TEMP_OFFSET = 97
C3_2010_MIN_LENGTH = C3_2010_OUTDOOR_TEMP_OFFSET + C3_X00_U16_LENGTH

# Sensor telemetry commands observed on model 17100007. Offsets are zero-based
# within the X00 body, including its leading 0x00 byte.
C3_20B0_COMMAND = bytes((0x20, 0xB0))
C3_2F10_COMMAND = bytes((0x2F, 0x10))

C3_20B0_COMP_RUN_FREQ_OFFSET = 10
C3_20B0_FAN_SPEED_OFFSET = 12
C3_20B0_TEMP_T3_OFFSET = 16
C3_20B0_TEMP_T4_OFFSET = 18
C3_20B0_TEMP_TP_OFFSET = 20
C3_20B0_TEMP_TW_IN_OFFSET = 22
C3_20B0_TEMP_TW_OUT_OFFSET = 24
C3_20B0_ODU_COMP_CURRENT_OFFSET = 33
C3_20B0_ODU_VOLTAGE_OFFSET = 35
C3_20B0_EXV_CURRENT_OFFSET = 37
C3_20B0_ODU_MODEL_OFFSET = 39
C3_20B0_TEMP_T1_OFFSET = 92
C3_20B0_TEMP_T2_OFFSET = 96
C3_20B0_TEMP_T2B_OFFSET = 98
C3_20B0_TEMP_T5_OFFSET = 100
C3_20B0_PRESSURE_HIGH_OFFSET = 109
C3_20B0_TEMP_TH_OFFSET = 113
C3_20B0_TEMP_TF_OFFSET = 119
C3_20B0_IDU_T1S1_OFFSET = 121
C3_20B0_WATER_FLOW_OFFSET = 125
C3_20B0_CURRENT_UNIT_CAPACITY_OFFSET = 129
C3_20B0_PUMP_I_PWM_OFFSET = 139
C3_20B0_TOTAL_ENERGY_CONSUMPTION_OFFSET = 140
C3_20B0_MIN_LENGTH = C3_20B0_TEMP_TW_OUT_OFFSET + C3_X00_U16_LENGTH

C3_2F10_COMP_RUN_FREQ_OFFSET = 10
C3_2F10_FAN_SPEED_OFFSET = 11
C3_2F10_TEMP_T3_OFFSET = 13
C3_2F10_TEMP_T4_OFFSET = 15
C3_2F10_TEMP_TP_OFFSET = 17
C3_2F10_TEMP_TW_IN_OFFSET = 19
C3_2F10_TEMP_TW_OUT_OFFSET = 21
C3_2F10_ODU_COMP_CURRENT_OFFSET = 23
C3_2F10_ODU_VOLTAGE_OFFSET = 25
C3_2F10_TEMP_T1_OFFSET = 27
C3_2F10_TEMP_T2_OFFSET = 31
C3_2F10_TEMP_T2B_OFFSET = 33
C3_2F10_TEMP_T5_OFFSET = 35
C3_2F10_PRESSURE_HIGH_OFFSET = 39
C3_2F10_TEMP_TH_OFFSET = 43
C3_2F10_TEMP_TF_OFFSET = 46
C3_2F10_IDU_T1S1_OFFSET = 48
C3_2F10_WATER_FLOW_OFFSET = 52
C3_2F10_CURRENT_UNIT_CAPACITY_OFFSET = 54
C3_2F10_TOTAL_ENERGY_CONSUMPTION_OFFSET = 60
C3_2F10_COMP_TOTAL_RUN_TIME_OFFSET = 88
C3_2F10_PUMP_I_PWM_OFFSET = 92
C3_2F10_COMP_RUN_TIME_OFFSET = 118
C3_2F10_ODU_MODEL_OFFSET = 122
C3_2F10_EXV_CURRENT_OFFSET = 127
C3_2F10_DC_BUS_VOLTAGE_OFFSET = 141
C3_2F10_DC_CURRENT_OFFSET = 143
C3_2F10_SV1_OPEN_OFFSET = 145
C3_2F10_SV2_OPEN_OFFSET = 146
C3_2F10_PUMP_I_RUNNING_OFFSET = 148
C3_2F10_PUMP_O_RUNNING_OFFSET = 149
C3_2F10_PUMP_D_RUNNING_OFFSET = 150
C3_2F10_FAN_TOTAL_RUN_TIME_OFFSET = 157
C3_2F10_PUMP_I_TOTAL_RUN_TIME_OFFSET = 161
C3_2F10_MIN_LENGTH = C3_2F10_TEMP_TW_OUT_OFFSET + C3_X00_U16_LENGTH


def _read_u16_be(body: bytearray, offset: int) -> int:
    """Read an unsigned big-endian 16-bit value."""
    return int.from_bytes(body[offset : offset + C3_X00_U16_LENGTH], byteorder="big")


def _read_u32_be(body: bytearray, offset: int) -> int:
    """Read an unsigned big-endian 32-bit value."""
    return int.from_bytes(body[offset : offset + C3_X00_U32_LENGTH], byteorder="big")


def _parse_c3_2010_temperature(body: bytearray, offset: int) -> float:
    """Decode a C3 0x2010 temperature stored as unsigned tenths of a degree."""
    return _read_u16_be(body, offset) / C3_X00_TEMPERATURE_SCALE


def _parse_c3_x00_signed_temperature(body: bytearray, offset: int) -> float | None:
    """Decode a signed C3 X00 temperature stored as tenths of a degree."""
    raw = _read_u16_be(body, offset)
    if raw == C3_X00_INVALID_U16:
        return None
    magnitude = raw & C3_X00_SIGN_VALUE_MASK
    if raw & C3_X00_SIGN_BIT:
        magnitude = -magnitude
    return magnitude / C3_X00_TEMPERATURE_SCALE


def _c3_x00_inner_command(body: bytearray) -> bytes:
    """Return the two-byte inner command carried by a C3 X00 message."""
    return bytes(
        body[C3_X00_COMMAND_OFFSET : C3_X00_COMMAND_OFFSET + C3_X00_COMMAND_LENGTH],
    )


# Error code lookup (source: Midea Modbus documentation V4.7,
# 0052003044313 V.E, "Error code table 1", page 11).
# Format: raw_value -> (display_code, human_description).
# All entries below were cross-checked against that source; the four
# codes previously marked "unknown" (Hd, HE, L2, L9) plus L8 are now
# filled in, and three codes (E1, H9, HA) whose text had been
# shifted from neighbouring rows during transcription are corrected.
C3_ERROR_CODE_TABLE: dict[int, tuple[str, str]] = {
    1: ("E0", "Water flow fault (E8 displayed 3 times)"),
    2: (
        "E1",
        (
            "Phase loss, or neutral and live wire connected reversely "
            "(three-phase units only)"
        ),
    ),
    3: ("E2", "Communication fault between controller and hydraulic module"),
    4: ("E3", "Final outlet water temp. sensor (T1) fault"),
    5: ("E4", "Water tank temp. sensor (T5) fault"),
    6: ("E5", "Condenser outlet refrigerant temp. sensor (T3) fault"),
    7: ("E6", "Ambient temp. sensor (T4) fault"),
    8: ("E7", "Buffer tank up temp. sensor (Tbt1) fault"),
    9: ("E8", "Water flow failure"),
    10: ("E9", "Suction temp. sensor (Th) fault"),
    11: ("EA", "Discharge temp. sensor (Tp) fault"),
    12: ("Eb", "Solar temp. sensor (Tsolar) fault"),
    13: ("Ec", "Buffer tank low temp. sensor (Tbt2) fault"),
    14: ("Ed", "Inlet water temp. sensor (Tw_in) malfunction"),
    15: ("EE", "Hydraulic module EEPROM failure"),
    20: ("P0", "Low pressure switch protection"),
    21: ("P1", "High pressure switch protection"),
    23: ("P3", "Compressor overcurrent protection"),
    24: ("P4", "High discharge temperature protection"),
    25: ("P5", "|Tw_out - Tw_in| value too big protection"),
    26: ("P6", "Inverter module protection"),
    31: ("Pb", "Anti-freeze mode"),
    33: ("Pd", "High refrigerant outlet temp. protection of condenser"),
    38: ("PP", "Tw_out - Tw_in unusual protection"),
    39: ("H0", "Communication fault: hydraulic PCB B <-> main control PCB B"),
    40: ("H1", "Communication fault: inverter PCB A <-> main control PCB B"),
    41: ("H2", "Refrigerant liquid temp. sensor (T2) fault"),
    42: ("H3", "Refrigerant gas temp. sensor (T2B) fault"),
    43: ("H4", "Three times P6 (L0/L1) protection"),
    44: ("H5", "Room temp. sensor (Ta) fault"),
    45: ("H6", "DC fan motor fault"),
    46: ("H7", "Voltage protection"),
    47: ("H8", "Pressure sensor fault"),
    48: ("H9", "Outlet water temp. sensor for Zone 2 (Tw2) fault"),
    49: ("HA", "Outlet water temp. sensor (Tw_out) fault"),
    50: ("Hb", "3 times PP protection and Tw_out < 7C"),
    52: ("Hd", "Communication fault between hydraulic modules (parallel)"),
    53: ("HE", "Communication error: main board <-> thermostat transfer board"),
    54: ("HF", "Inverter module board EEPROM fault"),
    55: ("HH", "H6 displayed 10 times in 2 hours"),
    57: ("HP", "Low pressure protection (Pe<0.6) occurred 3 times in 1 hour"),
    65: ("C7", "Transducer module temperature too high protection"),
    112: ("bH", "PED PCB fault"),
    116: ("F1", "Low DC generatrix voltage protection"),
    134: ("L0", "Module protection"),
    135: ("L1", "DC generatrix low voltage protection"),
    136: ("L2", "DC generatrix high voltage protection"),
    138: ("L4", "MCE fault"),
    139: ("L5", "Zero speed protection"),
    141: ("L7", "Phase sequence fault"),
    142: ("L8", "Speed difference > 15Hz between front and back clock"),
    143: ("L9", "Speed difference > 15Hz between real and setting speed"),
}


class C3SilentLevel(IntEnum):
    """C3 Silent Level."""

    OFF = 0x0
    SILENT = 0x1
    SUPER_SILENT = 0x3


class C3DeviceMode(IntEnum):
    """C3 Device Mode."""

    COOL = 2
    HEAT = 3


class MessageC3Base(MessageRequest):
    """C3 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize C3 message base."""
        super().__init__(
            device_type=DeviceType.C3,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageC3Base):
    """C3 message query."""

    def __init__(self, protocol_version: int, body_type: ListTypes) -> None:
        """Initialize C3 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageQueryBasic(MessageQuery):
    """C3 Message query basic."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query basic."""
        super().__init__(protocol_version, ListTypes.X01)


class MessageQuerySilence(MessageQuery):
    """C3 Message query silence."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X05)


class MessageQueryECO(MessageQuery):
    """C3 Message query ECO."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X07)


class MessageQueryInstall(MessageQuery):
    """C3 Message query INSTALL."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X08)


class MessageQueryDisinfect(MessageQuery):
    """C3 Message query Disinfect."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X09)


class MessageQueryUnitPara(MessageQuery):
    """C3 Message query UNITPARA."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X10)


class MessageQueryDiagnostic(MessageQuery):
    """C3 message query diagnostic data."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query diagnostic data."""
        super().__init__(protocol_version, ListTypes.X0D)


class MessageQueryHMIPara(MessageQuery):
    """C3 Message query HMIPARA."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X0A)


class MessageSet(MessageC3Base):
    """C3 message set."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        self.zone1_power = False
        self.zone2_power = False
        self.dhw_power = False
        self.mode = 0
        self.zone_target_temp = [25.0, 25.0]
        self.dhw_target_temp = 40.0
        self.room_target_temp = 25.0
        self.zone1_curve = False
        self.zone2_curve = False
        self.fast_dhw = False
        self.tbh = False

    @property
    def _body(self) -> bytearray:
        # Byte 1
        zone1_power = 0x01 if self.zone1_power else 0x00
        zone2_power = 0x02 if self.zone2_power else 0x00
        dhw_power = 0x04 if self.dhw_power else 0x00
        # Byte 7
        zone1_curve = 0x01 if self.zone1_curve else 0x00
        zone2_curve = 0x02 if self.zone2_curve else 0x00
        tbh = 0x04 if self.tbh else 0x00
        fast_dhw = 0x08 if self.fast_dhw else 0x00
        room_target_temp = int(self.room_target_temp * 2)
        zone1_target_temp = int(self.zone_target_temp[0])
        zone2_target_temp = int(self.zone_target_temp[1])
        dhw_target_temp = int(self.dhw_target_temp)
        return bytearray(
            [
                zone1_power | zone2_power | dhw_power,
                self.mode,
                zone1_target_temp,
                zone2_target_temp,
                dhw_target_temp,
                room_target_temp,
                zone1_curve | zone2_curve | tbh | fast_dhw,
            ],
        )


class MessageSetSilent(MessageC3Base):
    """C3 message set silent."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set silent."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X05,
        )
        self.silent_mode = False
        self.silent_level = C3SilentLevel.OFF

    @property
    def _body(self) -> bytearray:
        return bytearray(
            [
                self.silent_level if self.silent_mode else C3SilentLevel.OFF,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class MessageSetECO(MessageC3Base):
    """C3 message set eco."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set eco."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X07,
        )
        self.eco_mode = False

    @property
    def _body(self) -> bytearray:
        eco_mode = 0x01 if self.eco_mode else 0

        return bytearray([eco_mode, 0x00, 0x00, 0x00, 0x00, 0x00])


class MessageSetDisinfect(MessageC3Base):
    """C3 message set Disinfect."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set eco."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X09,
        )
        self.disinfect = False

    @property
    def _body(self) -> bytearray:
        disinfect = 0x01 if self.disinfect else 0

        return bytearray([disinfect, 0x00, 0x00, 0x00])


class C3BasicBody(MessageBody):
    """C3 Basic message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 message body."""
        super().__init__(body)
        # BodyBytes 1
        self.zone1_power = body[data_offset + 0] & 0x01 > 0
        self.zone2_power = body[data_offset + 0] & 0x02 > 0
        self.dhw_power = body[data_offset + 0] & 0x04 > 0
        self.zone1_curve = body[data_offset + 0] & 0x08 > 0
        self.zone2_curve = body[data_offset + 0] & 0x10 > 0
        self.tbh = body[data_offset + 0] & 0x20 > 0
        self.fast_dhw = body[data_offset + 0] & 0x40 > 0
        self.remote_onoff = body[data_offset + 0] & 0x80 > 0
        # BodyBytes 2
        self.heat = body[data_offset + 1] & 0x01 > 0
        self.cool = body[data_offset + 1] & 0x02 > 0
        self.dhw = body[data_offset + 1] & 0x04 > 0
        self.double_zone = body[data_offset + 1] & 0x08 > 0
        self.zone_temp_type = [
            body[data_offset + 1] & 0x10 > 0,
            body[data_offset + 1] & 0x20 > 0,
        ]
        self.room_thermal_support = body[data_offset + 1] & 0x40 > 0
        self.room_thermal_state = body[data_offset + 1] & 0x80 > 0
        # BodyBytes 3
        self.time_set = body[data_offset + 2] & 0x01 > 0
        self.silent_mode = body[data_offset + 2] & 0x02 > 0
        self.holiday_on = body[data_offset + 2] & 0x04 > 0
        self.eco_mode = body[data_offset + 2] & 0x08 > 0
        self.zone_terminal_type = body[data_offset + 2]
        # BodyBytes 4
        self.mode = body[data_offset + 3]
        self.mode_auto = body[data_offset + 4]
        # zone1, zone2
        self.zone_target_temp = [
            float(body[data_offset + 5]),
            float(body[data_offset + 6]),
        ]
        self.dhw_target_temp = float(body[data_offset + 7])
        self.room_target_temp = float(body[data_offset + 8] / 2)
        # zone1, zone2
        self.zone_heating_temp_max = [
            float(body[data_offset + 9]),
            float(body[data_offset + 13]),
        ]
        self.zone_heating_temp_min = [
            float(body[data_offset + 10]),
            float(body[data_offset + 14]),
        ]
        self.zone_cooling_temp_max = [
            float(body[data_offset + 11]),
            float(body[data_offset + 15]),
        ]
        self.zone_cooling_temp_min = [
            float(body[data_offset + 12]),
            float(body[data_offset + 16]),
        ]
        self.room_temp_max = float(body[data_offset + 17] / 2)
        self.room_temp_min = float(body[data_offset + 18] / 2)
        self.dhw_temp_max = float(body[data_offset + 19])
        self.dhw_temp_min = float(body[data_offset + 20])
        self.tank_actual_temperature = float(body[data_offset + 21])
        self.error_code = body[data_offset + 22]
        if self.error_code == 0:
            self.error_code_description = "No error"
        else:
            _code_info = C3_ERROR_CODE_TABLE.get(self.error_code)
            if _code_info:
                self.error_code_description = f"{_code_info[0]}: {_code_info[1]}"
            else:
                self.error_code_description = f"Unknown code (raw={self.error_code})"
        self.tbh_control = body[data_offset + 23] & 0x80 > 0
        self.sys_energy_ana_en = body[data_offset + 23] & 0x20 > 0
        self.hmi_energy_ana_set_en = body[data_offset + 23] & 0x40 > 0


class C3ShortBasicBody(MessageBody):
    """C3 short X01 body used by 171000-series heat-pump water heaters."""

    def __init__(self, body: bytearray) -> None:
        """Initialize C3 short basic message body."""
        super().__init__(body)
        power_byte = body[C3_SHORT_X01_POWER_OFFSET]
        status_byte = body[C3_SHORT_X01_STATUS_OFFSET]
        self.zone1_power = False
        self.zone2_power = False
        self.dhw_power = bool(power_byte & C3_SHORT_DHW_POWER_MASK)
        self.zone1_curve = False
        self.zone2_curve = False
        self.fast_dhw = False
        self.remote_onoff = None
        self.heat = False
        self.cool = False
        self.dhw = True
        self.double_zone = False
        self.zone_temp_type = [True, True]
        self.room_thermal_support = False
        self.room_thermal_state = False
        self.time_set = False
        self.silent_mode = False
        self.holiday_on = False
        self.eco_mode = False
        self.mode = C3DeviceMode.HEAT
        self.mode_auto = C3DeviceMode.HEAT
        self.zone_target_temp = [50.0, 25.0]
        raw_setpoint = body[C3_SHORT_X01_SETPOINT_OFFSET]
        if raw_setpoint >= C3_SHORT_SETPOINT_BIAS:
            self.dhw_target_temp = float(raw_setpoint - C3_SHORT_SETPOINT_BIAS)
            self.current_lwt_target = self.dhw_target_temp
        self.room_target_temp = 25.0
        self.zone_heating_temp_max = [C3_SHORT_DHW_TEMP_MAX, C3_SHORT_DHW_TEMP_MAX]
        self.zone_heating_temp_min = [C3_SHORT_DHW_TEMP_MIN, C3_SHORT_DHW_TEMP_MIN]
        self.zone_cooling_temp_max = [C3_SHORT_DHW_TEMP_MAX, C3_SHORT_DHW_TEMP_MAX]
        self.zone_cooling_temp_min = [C3_SHORT_DHW_TEMP_MIN, C3_SHORT_DHW_TEMP_MIN]
        self.room_temp_max = C3_SHORT_DHW_TEMP_MAX
        self.room_temp_min = C3_SHORT_DHW_TEMP_MIN
        self.dhw_temp_max = C3_SHORT_DHW_TEMP_MAX
        self.dhw_temp_min = C3_SHORT_DHW_TEMP_MIN
        self.error_code = 0
        self.error_code_description = "No error"
        self.tbh = bool(body[C3_SHORT_X01_TBH_OFFSET] & C3_SHORT_TBH_MASK)
        self.tbh_control = False
        self.sys_energy_ana_en = False
        self.hmi_energy_ana_set_en = False
        self.status_dhw = bool(status_byte & C3_SHORT_DHW_RUNNING_MASK)
        self.status_heating = bool(status_byte & C3_SHORT_COMPRESSOR_RUNNING_MASK)
        self.status_tbh = self.tbh
        self.compressor_on = self.status_heating


class C3DiagnosticBody(MessageBody):
    """C3 X0D diagnostic body used by 171000-series devices."""

    def __init__(self, body: bytearray) -> None:
        """Initialize C3 diagnostic message body."""
        super().__init__(body)
        water_temperature = (
            _read_be16(body, C3_DIAGNOSTIC_WATER_TEMP_OFFSET)
            / C3_DIAGNOSTIC_TEMP_FACTOR
        )
        tank_temperature = (
            _read_be16(body, C3_DIAGNOSTIC_TANK_TEMP_OFFSET) / C3_DIAGNOSTIC_TEMP_FACTOR
        )
        self.temp_tw_out = water_temperature
        self.tank_actual_temperature = tank_temperature or water_temperature
        self.instant_power0 = _read_be16(body, C3_DIAGNOSTIC_INSTANT_POWER_OFFSET)
        dhw_status = MessageBody.read_byte(body, C3_DIAGNOSTIC_DHW_STATUS_OFFSET)
        if dhw_status in (0, 1):
            self.status_dhw = bool(dhw_status)
        self.total_energy_consumption = _read_be24(
            body,
            C3_DIAGNOSTIC_TOTAL_COUNTER_OFFSET,
        )


class C3Basic2010Body(MessageBody):
    """C3 basic state carried by the newer 0x2010 inner protocol."""

    def __init__(self, body: bytearray) -> None:
        """Initialize a C3 0x2010 basic-state message body."""
        super().__init__(body)
        self.dhw_target_temp = _parse_c3_2010_temperature(
            body,
            C3_2010_DHW_TARGET_TEMP_OFFSET,
        )
        self.tank_actual_temperature = _parse_c3_2010_temperature(
            body,
            C3_2010_TANK_ACTUAL_TEMP_OFFSET,
        )
        self.temp_t4 = _parse_c3_2010_temperature(
            body,
            C3_2010_OUTDOOR_TEMP_OFFSET,
        )
        self.outdoor_temperature = self.temp_t4


class C3X0020B0TelemetryBody(MessageBody):
    """C3 telemetry carried by the model 17100007 0x20B0 push."""

    def __init__(self, body: bytearray) -> None:
        """Initialize a C3 0x20B0 telemetry message body."""
        super().__init__(body)
        self.comp_run_freq = body[C3_20B0_COMP_RUN_FREQ_OFFSET]
        self.compressor_on = self.comp_run_freq > 0
        self.fan_speed = _read_u16_be(body, C3_20B0_FAN_SPEED_OFFSET)
        self.temp_t3 = _parse_c3_x00_signed_temperature(
            body,
            C3_20B0_TEMP_T3_OFFSET,
        )
        self.temp_t4 = _parse_c3_x00_signed_temperature(
            body,
            C3_20B0_TEMP_T4_OFFSET,
        )
        self.outdoor_temperature = self.temp_t4
        self.temp_tp = _parse_c3_x00_signed_temperature(
            body,
            C3_20B0_TEMP_TP_OFFSET,
        )
        self.temp_tw_in = _parse_c3_x00_signed_temperature(
            body,
            C3_20B0_TEMP_TW_IN_OFFSET,
        )
        self.temp_tw_out = _parse_c3_x00_signed_temperature(
            body,
            C3_20B0_TEMP_TW_OUT_OFFSET,
        )
        # Later telemetry is optional; never turn an incomplete value into zero.
        if len(body) >= C3_20B0_ODU_COMP_CURRENT_OFFSET + C3_X00_U16_LENGTH:
            self.odu_comp_current = _read_u16_be(body, C3_20B0_ODU_COMP_CURRENT_OFFSET)
        if len(body) >= C3_20B0_ODU_VOLTAGE_OFFSET + C3_X00_U16_LENGTH:
            self.odu_voltage = _read_u16_be(body, C3_20B0_ODU_VOLTAGE_OFFSET)
        if len(body) >= C3_20B0_EXV_CURRENT_OFFSET + C3_X00_U16_LENGTH:
            self.exv_current = _read_u16_be(body, C3_20B0_EXV_CURRENT_OFFSET)
        if len(body) > C3_20B0_ODU_MODEL_OFFSET:
            self.odu_model = body[C3_20B0_ODU_MODEL_OFFSET]
        if len(body) >= C3_20B0_TEMP_T1_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t1 = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_T1_OFFSET,
            )
        if len(body) >= C3_20B0_TEMP_T2_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t2 = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_T2_OFFSET,
            )
        if len(body) >= C3_20B0_TEMP_T2B_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t2b = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_T2B_OFFSET,
            )
        if len(body) >= C3_20B0_TEMP_T5_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t5 = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_T5_OFFSET,
            )
        if len(body) >= C3_20B0_PRESSURE_HIGH_OFFSET + C3_X00_U16_LENGTH:
            self.pressure_high = (
                _read_u16_be(body, C3_20B0_PRESSURE_HIGH_OFFSET) * C3_X00_PRESSURE_SCALE
            )
        if len(body) >= C3_20B0_TEMP_TH_OFFSET + C3_X00_U16_LENGTH:
            self.temp_th = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_TH_OFFSET,
            )
        if len(body) >= C3_20B0_TEMP_TF_OFFSET + C3_X00_U16_LENGTH:
            self.temp_tf = _parse_c3_x00_signed_temperature(
                body,
                C3_20B0_TEMP_TF_OFFSET,
            )
        if len(body) >= C3_20B0_IDU_T1S1_OFFSET + C3_X00_U16_LENGTH:
            self.idu_t1s1 = (
                _read_u16_be(body, C3_20B0_IDU_T1S1_OFFSET) / C3_X00_TEMPERATURE_SCALE
            )
        if len(body) >= C3_20B0_WATER_FLOW_OFFSET + C3_X00_U16_LENGTH:
            self.water_flower = (
                _read_u16_be(body, C3_20B0_WATER_FLOW_OFFSET) / C3_X00_WATER_FLOW_SCALE
            )
        if len(body) >= C3_20B0_CURRENT_UNIT_CAPACITY_OFFSET + C3_X00_U16_LENGTH:
            # The /100 capacity scale still needs a steady-running sample.
            self.current_unit_capacity = (
                _read_u16_be(body, C3_20B0_CURRENT_UNIT_CAPACITY_OFFSET)
                / C3_X00_CURRENT_UNIT_CAPACITY_SCALE
            )
        if len(body) > C3_20B0_PUMP_I_PWM_OFFSET:
            self.pump_i_pwm = body[C3_20B0_PUMP_I_PWM_OFFSET]
            self.pwm_pump_out = self.pump_i_pwm
        if len(body) >= C3_20B0_TOTAL_ENERGY_CONSUMPTION_OFFSET + C3_X00_U32_LENGTH:
            self.total_energy_consumption = _read_u32_be(
                body,
                C3_20B0_TOTAL_ENERGY_CONSUMPTION_OFFSET,
            )


class C3X002F10TelemetryBody(MessageBody):
    """C3 telemetry carried by the model 17100007 0x2F10 push."""

    def __init__(self, body: bytearray) -> None:
        """Initialize a C3 0x2F10 telemetry message body."""
        super().__init__(body)
        self.comp_run_freq = body[C3_2F10_COMP_RUN_FREQ_OFFSET]
        self.compressor_on = self.comp_run_freq > 0
        self.fan_speed = _read_u16_be(body, C3_2F10_FAN_SPEED_OFFSET)
        self.temp_t3 = _parse_c3_x00_signed_temperature(
            body,
            C3_2F10_TEMP_T3_OFFSET,
        )
        self.temp_t4 = _parse_c3_x00_signed_temperature(
            body,
            C3_2F10_TEMP_T4_OFFSET,
        )
        self.outdoor_temperature = self.temp_t4
        self.temp_tp = _parse_c3_x00_signed_temperature(
            body,
            C3_2F10_TEMP_TP_OFFSET,
        )
        self.temp_tw_in = _parse_c3_x00_signed_temperature(
            body,
            C3_2F10_TEMP_TW_IN_OFFSET,
        )
        self.temp_tw_out = _parse_c3_x00_signed_temperature(
            body,
            C3_2F10_TEMP_TW_OUT_OFFSET,
        )
        self._parse_optional_sensors(body)
        self._parse_operation(body)

    def _parse_optional_sensors(self, body: bytearray) -> None:
        """Decode complete trailing sensor, capacity, and energy fields."""
        if len(body) >= C3_2F10_ODU_COMP_CURRENT_OFFSET + C3_X00_U16_LENGTH:
            self.odu_comp_current = _read_u16_be(body, C3_2F10_ODU_COMP_CURRENT_OFFSET)
        if len(body) >= C3_2F10_ODU_VOLTAGE_OFFSET + C3_X00_U16_LENGTH:
            self.odu_voltage = _read_u16_be(body, C3_2F10_ODU_VOLTAGE_OFFSET)
        if len(body) >= C3_2F10_TEMP_T1_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t1 = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_T1_OFFSET,
            )
        if len(body) >= C3_2F10_TEMP_T2_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t2 = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_T2_OFFSET,
            )
        if len(body) >= C3_2F10_TEMP_T2B_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t2b = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_T2B_OFFSET,
            )
        if len(body) >= C3_2F10_TEMP_T5_OFFSET + C3_X00_U16_LENGTH:
            self.temp_t5 = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_T5_OFFSET,
            )
        if len(body) >= C3_2F10_PRESSURE_HIGH_OFFSET + C3_X00_U16_LENGTH:
            self.pressure_high = (
                _read_u16_be(body, C3_2F10_PRESSURE_HIGH_OFFSET) * C3_X00_PRESSURE_SCALE
            )
        if len(body) >= C3_2F10_TEMP_TH_OFFSET + C3_X00_U16_LENGTH:
            self.temp_th = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_TH_OFFSET,
            )
        if len(body) >= C3_2F10_TEMP_TF_OFFSET + C3_X00_U16_LENGTH:
            self.temp_tf = _parse_c3_x00_signed_temperature(
                body,
                C3_2F10_TEMP_TF_OFFSET,
            )
        if len(body) >= C3_2F10_IDU_T1S1_OFFSET + C3_X00_U16_LENGTH:
            self.idu_t1s1 = (
                _read_u16_be(body, C3_2F10_IDU_T1S1_OFFSET) / C3_X00_TEMPERATURE_SCALE
            )
        if len(body) >= C3_2F10_WATER_FLOW_OFFSET + C3_X00_U16_LENGTH:
            self.water_flower = (
                _read_u16_be(body, C3_2F10_WATER_FLOW_OFFSET) / C3_X00_WATER_FLOW_SCALE
            )
        if len(body) >= C3_2F10_CURRENT_UNIT_CAPACITY_OFFSET + C3_X00_U16_LENGTH:
            # The /100 capacity scale still needs a steady-running sample.
            self.current_unit_capacity = (
                _read_u16_be(body, C3_2F10_CURRENT_UNIT_CAPACITY_OFFSET)
                / C3_X00_CURRENT_UNIT_CAPACITY_SCALE
            )
        if len(body) >= C3_2F10_TOTAL_ENERGY_CONSUMPTION_OFFSET + C3_X00_U32_LENGTH:
            self.total_energy_consumption = _read_u32_be(
                body,
                C3_2F10_TOTAL_ENERGY_CONSUMPTION_OFFSET,
            )

    def _parse_operation(self, body: bytearray) -> None:
        """Decode complete runtime, electrical, and relay fields."""
        if len(body) >= C3_2F10_COMP_TOTAL_RUN_TIME_OFFSET + C3_X00_U32_LENGTH:
            self.comp_total_run_time = _read_u32_be(
                body,
                C3_2F10_COMP_TOTAL_RUN_TIME_OFFSET,
            )
        if len(body) > C3_2F10_PUMP_I_PWM_OFFSET:
            self.pump_i_pwm = body[C3_2F10_PUMP_I_PWM_OFFSET]
            self.pwm_pump_out = self.pump_i_pwm
        if len(body) >= C3_2F10_COMP_RUN_TIME_OFFSET + C3_X00_U16_LENGTH:
            # Minute count confirmed; the high byte awaits a >255 min capture.
            self.comp_run_time = _read_u16_be(body, C3_2F10_COMP_RUN_TIME_OFFSET)
        if len(body) > C3_2F10_ODU_MODEL_OFFSET:
            self.odu_model = body[C3_2F10_ODU_MODEL_OFFSET]
        if len(body) >= C3_2F10_EXV_CURRENT_OFFSET + C3_X00_U16_LENGTH:
            self.exv_current = _read_u16_be(body, C3_2F10_EXV_CURRENT_OFFSET)
        if len(body) >= C3_2F10_DC_BUS_VOLTAGE_OFFSET + C3_X00_U16_LENGTH:
            self.dc_bus_voltage = _read_u16_be(body, C3_2F10_DC_BUS_VOLTAGE_OFFSET)
        if len(body) >= C3_2F10_DC_CURRENT_OFFSET + C3_X00_U16_LENGTH:
            # /100 matches the only nonzero sample; request live confirmation.
            self.dc_current = (
                _read_u16_be(body, C3_2F10_DC_CURRENT_OFFSET) / C3_X00_DC_CURRENT_SCALE
            )
        if len(body) > C3_2F10_SV1_OPEN_OFFSET:
            self.sv1_open = bool(body[C3_2F10_SV1_OPEN_OFFSET])
        if len(body) > C3_2F10_SV2_OPEN_OFFSET:
            self.sv2_open = bool(body[C3_2F10_SV2_OPEN_OFFSET])
        if len(body) > C3_2F10_PUMP_I_RUNNING_OFFSET:
            self.pump_i_running = bool(body[C3_2F10_PUMP_I_RUNNING_OFFSET])
        if len(body) > C3_2F10_PUMP_O_RUNNING_OFFSET:
            self.pump_o_running = bool(body[C3_2F10_PUMP_O_RUNNING_OFFSET])
        if len(body) > C3_2F10_PUMP_D_RUNNING_OFFSET:
            self.pump_d_running = bool(body[C3_2F10_PUMP_D_RUNNING_OFFSET])
        if len(body) >= C3_2F10_FAN_TOTAL_RUN_TIME_OFFSET + C3_X00_U32_LENGTH:
            self.fan_total_run_time = _read_u32_be(
                body,
                C3_2F10_FAN_TOTAL_RUN_TIME_OFFSET,
            )
        if len(body) >= C3_2F10_PUMP_I_TOTAL_RUN_TIME_OFFSET + C3_X00_U32_LENGTH:
            self.pump_i_total_run_time = _read_u32_be(
                body,
                C3_2F10_PUMP_I_TOTAL_RUN_TIME_OFFSET,
            )


class C3EnergyBody(MessageBody):
    """C3 Energy MSG_TYPE_UP_POWER4 message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 notify1 message body."""
        super().__init__(body)
        status_byte = body[data_offset]
        # bit0
        self.status_heating = (status_byte & 0x01) > 0
        # bit1
        self.status_cool = (status_byte & 0x02) > 0
        # bit2
        self.status_dhw = (status_byte & 0x04) > 0
        # bit3
        self.status_tbh = (status_byte & 0x08) > 0
        # bit4
        self.status_ibh = (status_byte & 0x10) > 0
        # 32 bit big-endian counters: the lua multiplies the top byte by
        # 16777216 (<< 24), not 4294967296.
        # total_energy_consumption
        self.total_energy_consumption = (
            (body[data_offset + 1] << 24)
            + (body[data_offset + 2] << 16)
            + (body[data_offset + 3] << 8)
            + (body[data_offset + 4])
        )
        # total_produced_energy
        self.total_produced_energy = (
            (body[data_offset + 5] << 24)
            + (body[data_offset + 6] << 16)
            + (body[data_offset + 7] << 8)
            + (body[data_offset + 8])
        )
        base_value = body[data_offset + 9]
        self.outdoor_temperature = float(
            (base_value - 256) if base_value > TEMP_NEG_VALUE else base_value,
        )  # outdoor_temperature is t4
        self.zone1_temp_set = float(body[data_offset + 10])
        self.zone2_temp_set = float(body[data_offset + 11])
        self.t5s = body[data_offset + 12]
        self.tas = body[data_offset + 13]


class C3SilenceBody(MessageBody):
    """C3 Silence message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 query silence message body."""
        super().__init__(body)
        self.silent_mode = body[data_offset] & 0x1 > 0
        self.silent_level = C3SilentLevel(
            (body[data_offset] & 0x1) + ((body[data_offset] & 0x8) >> 2)
            if self.silent_mode
            else C3SilentLevel.OFF.value,
        ).name.lower()
        # Message protocol information:
        # silence_function_state: Byte 1, BIT 0
        # silence_timer1_state: Byte 1, BIT 1
        # silence_timer2_state: Byte 1, BIT 2
        # silence_function_level: Byte 1, BIT 3
        # silence_timer1_starthour: Byte 2
        # silence_timer1_startmin: Byte 3
        # silence_timer1_endhour: Byte 4
        # silence_timer1_endmin: Byte 5
        # silence_timer2_starthour: Byte 6
        # silence_timer2_startmin: Byte 7
        # silence_timer2_endhour: Byte 8
        # silence_timer2_endmin: Byte 9


class C3ECOBody(MessageBody):
    """C3 ECO message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 ECO message body."""
        super().__init__(body)
        self.eco_function_state = body[data_offset] & 0x01 > 0
        self.eco_timer_state = body[data_offset] & 0x02 > 0


class C3DisinfectBody(MessageBody):
    """C3 Disinfect message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 Disinfect message body."""
        super().__init__(body)
        self.disinfect = body[data_offset] & 0x01 > 0
        self.disinfect_run = body[data_offset] & 0x02 > 0
        self.disinfect_set_weekday = body[data_offset + 1]
        self.disinfect_start_hour = body[data_offset + 2]
        self.disinfect_start_minutes = body[data_offset + 3]


class C3UnitParaBody(MessageBody):
    """C3 UnitPara message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 UnitPara message body."""
        super().__init__(body)
        self.comp_run_freq = body[data_offset]
        self.compressor_on = self.comp_run_freq > 0
        self.unit_mode_run = body[data_offset + 1]
        # Outdoor fan speed, transmitted as RPM / 10 in a single byte.
        # It lives at data_offset + 2, directly after unit_mode_run; the
        # previous data_offset + 3 read a neighbouring byte that is small and
        # nearly constant while the unit runs, so fan_speed was reported as a
        # fixed low value (typically 20) regardless of the real fan command.
        self.fan_speed = body[data_offset + 2] * FAN_SPEED_FACTOR
        # lua _bodyBytes[5]; data_offset + 5 is the disabled `tempset` byte.
        self.fg_capacity_need = body[data_offset + 4]
        self.temp_t3 = body[data_offset + 6]
        self.temp_t4 = body[data_offset + 7]
        self.temp_tp = body[data_offset + 8]
        self.temp_tw_in = body[data_offset + 9]
        self.temp_tw_out = body[data_offset + 10]
        self.temp_tsolar = _temp_or_none(body[data_offset + 11])
        self.hydbox_subtype = body[data_offset + 12]
        self.fg_usb_info_connect = body[data_offset + 13]
        # self.usb_index_max  body[data_offset + 14]
        # lua _bodyBytes[17], compressor current in A. Already decoded by
        # C3UnitParaUpBody; enabled here so the polled response carries it too.
        self.odu_comp_current = body[data_offset + 16]
        self.odu_voltage = body[data_offset + 17] * 256 + body[data_offset + 18]
        self.exv_current = body[data_offset + 19] * 256 + body[data_offset + 20]
        self.odu_model = body[data_offset + 21]
        # self.unit_online_num  body[data_offset + 22]
        # self.current_code  body[data_offset + 23]
        # LOAD_OUTPUT bitmap. Authoritative source: Midea Modbus doc
        # V4.7, register 129 (Load output, 16-bit). Cross-checked
        # against the wired HMI during a pump test.
        #   BIT0 = electric heater IBH1     BIT4 = SV1
        #   BIT1 = electric heater IBH2     BIT5 = SV2
        #   BIT2 = electric heater TBH      BIT6 = external pump Pump_o
        #   BIT3 = internal pump Pump_i     BIT7 = DHW pump Pump_d
        # BIT8 (mixed water loop pump Pump_c, zone 2) lives in the
        # adjacent byte; BIT9-BIT15 are reserved per the Modbus doc.
        load_output = body[data_offset + 32]
        load_output_hi = body[data_offset + 31]
        self.ibh1_on = bool(load_output & 0x01)
        self.ibh2_on = bool(load_output & 0x02)
        self.load_output_tbh = bool(load_output & 0x04)
        self.pump_i_running = bool(load_output & 0x08)
        self.sv1_open = bool(load_output & 0x10)
        self.sv2_open = bool(load_output & 0x20)
        self.pump_o_running = bool(load_output & 0x40)
        self.pump_d_running = bool(load_output & 0x80)
        self.pump_c_running = bool(load_output_hi & 0x01)
        # Remaining bits of register 129 (Modbus doc V4.7 BIT9-BIT15).
        # BIT13 and BIT15 are documented as reserved, but the 171H120F lua
        # reads them as fgRunValveOn and fgDefValveOn and they are live on
        # real units, so both are decoded. BIT10 is "Crankcase heater" in
        # the doc and fgHeat4ValveOn in the lua; the doc name is used.
        self.sv3_open = bool(load_output_hi & 0x02)
        self.crankcase_heater_on = bool(load_output_hi & 0x04)
        self.pump_s_running = bool(load_output_hi & 0x08)
        self.alarm_on = bool(load_output_hi & 0x10)
        self.run_valve_on = bool(load_output_hi & 0x20)
        self.aux_heat_on = bool(load_output_hi & 0x40)
        self.defrost_valve_on = bool(load_output_hi & 0x80)
        # Run-state byte. Not part of the Modbus register map; the bit
        # names come from the 171H120F lua, which fills bits 1-7. Bit 0 is
        # unnamed there and is left undecoded.
        run_state = body[data_offset + 30]
        self.fact_req_solar_on = bool(run_state & 0x02)
        self.fact_req_ther_cool_on = bool(run_state & 0x04)
        self.cool_run = bool(run_state & 0x08)
        self.heat_run = bool(run_state & 0x10)
        self.dhw_run = bool(run_state & 0x20)
        self.fact_req_ther_heat_on = bool(run_state & 0x40)
        self.edge_version_type = bool(run_state & 0x80)
        self.temp_t1 = body[data_offset + 33]
        self.temp_tw2 = _temp_or_none(body[data_offset + 34])
        self.temp_t2 = body[data_offset + 35]
        self.temp_t2b = body[data_offset + 36]
        self.temp_t5 = body[data_offset + 37]
        self.temp_ta = _temp_or_none(body[data_offset + 38])
        self.temp_tb_t1 = _temp_or_none(body[data_offset + 39])
        self.temp_tb_t2 = _temp_or_none(body[data_offset + 40])
        self.hydrobox_capacity = body[data_offset + 41]
        self.pressure_high = body[data_offset + 42] * 256 + body[data_offset + 43]
        self.pressure_low = body[data_offset + 44] * 256 + body[data_offset + 45]
        self.temp_th = body[data_offset + 46]
        self.machine_type = body[data_offset + 47]
        self.odu_target_fre = body[data_offset + 48]
        self.dc_current = body[data_offset + 49]
        # Inverter DC bus voltage, single byte scaled x10 (V). Offset +50
        # sits between dc_current (+49) and temp_tf (+51) and was previously
        # unused. Correlated against wired HMI: raw 33 -> 330 V, raw 37 -> 370 V.
        self.dc_bus_voltage = body[data_offset + 50] * 10
        self.temp_tf = body[data_offset + 51]
        self.idu_t1s1 = _setpoint_or_none(body[data_offset + 52])
        self.idu_t1s2 = _setpoint_or_none(body[data_offset + 53])
        self.water_flower = _read_u16_be(body, data_offset + 54)
        self.odu_plan_vol_lmt = body[data_offset + 56]
        # lua _bodyBytes[58] * 256 + _bodyBytes[59]; the low byte was dropped.
        self.current_unit_capacity = _read_u16_be(body, data_offset + 57)
        self.sphera_ahs_voltage = body[data_offset + 59]
        self.temp_t4a_ver = body[data_offset + 60]
        self.water_pressure = body[data_offset + 61] * 256 + body[data_offset + 62]
        self.room_rel_hum = body[data_offset + 63]
        # lua _bodyBytes[65]; data_offset + 63 duplicated room_rel_hum.
        # On a 171H120F this byte reads 0 while the MSG_TYPE_UP_UNITPARA
        # notify reports pwmPumpOut = 99, so this firmware appears not to
        # populate it in the query response. _bodyBytes[66], which happens
        # to hold a constant 99, is marked reserved by the lua and is not
        # used here.
        # Keep the legacy field, but do not overwrite push-only pump_i_pwm.
        self.pwm_pump_out = body[data_offset + 64]
        self.total_electricity0 = (
            (body[data_offset + 66] << 24)
            + (body[data_offset + 67] << 16)
            + (body[data_offset + 68] << 8)
            + (body[data_offset + 69])
        )
        self.total_thermal0 = (
            (body[data_offset + 70] << 24)
            + (body[data_offset + 71] << 16)
            + (body[data_offset + 72] << 8)
            + (body[data_offset + 73])
        )
        self.heat_elec_total_consum0 = (
            (body[data_offset + 74] << 24)
            + (body[data_offset + 75] << 16)
            + (body[data_offset + 76] << 8)
            + (body[data_offset + 77])
        )
        self.heat_elec_total_capacity0 = (
            (body[data_offset + 78] << 24)
            + (body[data_offset + 79] << 16)
            + (body[data_offset + 80] << 8)
            + (body[data_offset + 81])
        )
        self.instant_power0 = (body[data_offset + 82] << 8) + (body[data_offset + 83])
        self.instant_renew_power0 = (body[data_offset + 84] << 8) + (
            body[data_offset + 85]
        )
        # lua _bodyBytes[87..90] as a 32 bit value; data_offset + 84,85
        # duplicated instant_renew_power0. Read defensively: the lua frame runs
        # to _bodyBytes[191] but this parser previously stopped at
        # data_offset + 85, so shorter bodies must not raise.
        self.total_renew_power0 = (
            (self.read_byte(body, data_offset + 86) << 24)
            + (self.read_byte(body, data_offset + 87) << 16)
            + (self.read_byte(body, data_offset + 88) << 8)
            + self.read_byte(body, data_offset + 89)
        )
        # ------------------------------------------------------------------
        # IDU / ODU software versions (Modbus reg 130 / reg 1042 mapped
        # into X10 telemetry frame). Verified against wired HMI:
        #   raw byte offset 93 = IDU sw version (HMI shows "V<n>")
        #   raw byte offset 94 = ODU sw version (HMI shows "V<n>")
        # Guard: leave version bytes unset when the frame is short. This
        # reads body[...] directly rather than going through read_byte()
        # like the rest of the method on purpose -- read_byte() defaults to
        # 0, which would surface as "V0" and be indistinguishable from a
        # unit actually reporting version 0. None says "not reported".
        self.idu_software_version: int | None = None
        self.odu_software_version: int | None = None
        if len(body) > data_offset + 94:
            self.idu_software_version = body[data_offset + 93]
            self.odu_software_version = body[data_offset + 94]
        self.idu_software_version_str = (
            f"V{self.idu_software_version}"
            if self.idu_software_version is not None
            else None
        )
        self.odu_software_version_str = (
            f"V{self.odu_software_version}"
            if self.odu_software_version is not None
            else None
        )
        # HMI serial number, read at its fixed block offset.
        self.hmi_sn_code: str | None = _parse_sn_block(
            body,
            data_offset,
            HMI_SN_BLOCK_OFFSET,
        )


class C3UnitParaUpBody(MessageBody):
    """C3 UnitPara notify (MSG_TYPE_UP_UNITPARA) message body.

    The unit pushes this unsolicited between polls. It carries the same
    quantities as the X10 query response but in its own, shorter layout, so
    the attribute names deliberately match C3UnitParaBody: whichever message
    arrives last refreshes the same device attributes.

    Layout from the official C3 lua for the 171H120F module,
    MSG_TYPE_UP_UNITPARA block. The lua is 1-indexed, so _bodyBytes[N] is
    body[data_offset + N - 1].

    Only the fields C3UnitParaBody already exposes are decoded here. The lua
    block continues with a long Sys* energy-analysis section that reuses the
    same byte ranges for several different names, so it is not parsed.
    """

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 UnitPara notify message body."""
        super().__init__(body)
        self.comp_run_freq = body[data_offset]
        self.compressor_on = self.comp_run_freq > 0
        self.fan_speed = body[data_offset + 1] * FAN_SPEED_FACTOR
        self.temp_t3 = body[data_offset + 2]
        self.temp_t4 = body[data_offset + 3]
        self.temp_tp = body[data_offset + 4]
        self.temp_tw_in = body[data_offset + 5]
        self.temp_tw_out = body[data_offset + 6]
        self.odu_comp_current = body[data_offset + 7]
        self.odu_voltage = body[data_offset + 8] * 256 + body[data_offset + 9]
        self.temp_t1 = body[data_offset + 10]
        self.temp_tw2 = _temp_or_none(body[data_offset + 11])
        self.temp_t2 = body[data_offset + 12]
        self.temp_t2b = body[data_offset + 13]
        self.temp_t5 = body[data_offset + 14]
        self.temp_ta = _temp_or_none(body[data_offset + 15])
        self.pressure_high = body[data_offset + 16] * 256 + body[data_offset + 17]
        self.pressure_low = body[data_offset + 18] * 256 + body[data_offset + 19]
        self.temp_th = body[data_offset + 20]
        self.odu_target_fre = body[data_offset + 21]
        self.temp_tf = body[data_offset + 22]
        self.idu_t1s1 = _setpoint_or_none(body[data_offset + 23])
        self.idu_t1s2 = _setpoint_or_none(body[data_offset + 24])
        self.water_flower = _read_u16_be(body, data_offset + 25)
        self.current_unit_capacity = _read_u16_be(body, data_offset + 27)
        self.water_pressure = body[data_offset + 29] * 256 + body[data_offset + 30]
        self.room_rel_hum = body[data_offset + 31]
        self.total_electricity0 = (
            (body[data_offset + 32] << 24)
            + (body[data_offset + 33] << 16)
            + (body[data_offset + 34] << 8)
            + (body[data_offset + 35])
        )
        self.total_thermal0 = (
            (body[data_offset + 36] << 24)
            + (body[data_offset + 37] << 16)
            + (body[data_offset + 38] << 8)
            + (body[data_offset + 39])
        )
        # NOTE: _bodyBytes[41..48] are given two conflicting meanings by the
        # lua (heatElecTotConsum0 / heatTotCapacity0 overlap SysHeatDay*), and
        # on a real unit heatElecTotConsum0 reads 0 here while the X10 query
        # reports 2249 at the same moment. Not decoded.
        self.instant_power0 = (body[data_offset + 48] << 8) + (body[data_offset + 49])
        self.instant_renew_power0 = (body[data_offset + 50] << 8) + (
            body[data_offset + 51]
        )
        self.total_renew_power0 = (
            (body[data_offset + 52] << 24)
            + (body[data_offset + 53] << 16)
            + (body[data_offset + 54] << 8)
            + (body[data_offset + 55])
        )
        self.unit_mode_run = body[data_offset + 59]
        # Compressor total run time in hours (u16 BE at lua bytes 57-58,
        # i.e. body[data_offset + 56 .. + 57]). The capture fixture used
        # in the tests decodes to 2964 h. Cross-checked on a second unit,
        # a Galmet Prima 06 GT, where the notify decoded 2365 h against
        # 2365 h read from the wired HMI at the same time. The X10 query
        # response does not carry this counter, so this notify is the
        # only source for it.
        self.comp_total_run_time = body[data_offset + 56] * 256 + body[data_offset + 57]
        self.pump_i_pwm = body[data_offset + 58]
        self.pwm_pump_out = self.pump_i_pwm


class MessageC3Response(MessageResponse):
    """C3 message response."""

    # Populated dynamically by MessageResponse.set_attr(), which copies
    # every attribute of the parsed body onto the response via setattr().
    # mypy cannot see attributes added that way; declaring them here as
    # class-level annotations has no effect on runtime behaviour (set_attr()
    # remains the only place that assigns them) and only gives mypy the
    # static type it needs for the accesses in message_c3_test.py.
    temp_t1: int | float | None
    ibh1_on: bool
    ibh2_on: bool
    load_output_tbh: bool
    pump_i_running: bool
    sv1_open: bool
    sv2_open: bool
    pump_o_running: bool
    pump_d_running: bool
    pump_c_running: bool
    sv3_open: bool
    crankcase_heater_on: bool
    pump_s_running: bool
    alarm_on: bool
    run_valve_on: bool
    aux_heat_on: bool
    defrost_valve_on: bool
    fact_req_solar_on: bool
    fact_req_ther_cool_on: bool
    cool_run: bool
    heat_run: bool
    dhw_run: bool
    fact_req_ther_heat_on: bool
    edge_version_type: bool
    comp_run_time: int
    comp_total_run_time: int
    fan_total_run_time: int
    pump_i_total_run_time: int
    unit_mode_run: int
    error_code: int
    error_code_description: str
    idu_software_version: int | None
    odu_software_version: int | None
    idu_software_version_str: str | None
    odu_software_version_str: str | None
    fg_capacity_need: int
    current_unit_capacity: int | float
    total_energy_consumption: int
    total_produced_energy: int
    mode: C3DeviceMode
    mode_auto: C3DeviceMode
    dhw_power: bool
    dhw_target_temp: float
    dhw_temp_min: float
    dhw_temp_max: float
    status_dhw: bool
    status_heating: bool
    compressor_on: bool
    tbh: bool
    temp_tw_out: int | float | None
    tank_actual_temperature: float
    instant_power0: int
    temp_t3: int | float | None
    temp_t4: int | float | None
    temp_tp: int | float | None
    temp_tw_in: int | float | None
    outdoor_temperature: float | None
    fan_speed: int
    odu_comp_current: int
    odu_voltage: int
    exv_current: int
    odu_model: int
    temp_t2: int | float | None
    temp_t2b: int | float | None
    temp_t5: int | float | None
    pressure_high: int
    temp_th: int | float | None
    temp_tf: int | float | None
    idu_t1s1: int | float | None
    water_flower: int | float
    pump_i_pwm: int
    pwm_pump_out: int
    dc_bus_voltage: int
    dc_current: int | float
    silent_level: str | None
    zone1_power: bool | None
    zone2_power: bool | None
    room_target_temp: float
    quintuple_arrays: dict[str, dict[int, float | bool | None]]
    quintuple_energy: bool

    def __init__(self, message: bytes, model: str | None = None) -> None:
        """Initialize C3 message response."""
        super().__init__(bytearray(message))
        body = super().body
        x00_command = _c3_x00_inner_command(body)
        if (
            model == C3_X00_TELEMETRY_MODEL
            and self.message_type in (MessageType.query, MessageType.notify1)
            and self.body_type == ListTypes.X00
            and x00_command == ENERGY_TABLE.to_bytes(2, "big")
        ):
            self.set_body(C3QuintupleEnergyBody(body))
        elif (
            model == C3_X00_TELEMETRY_MODEL
            and self.message_type
            in (MessageType.query, MessageType.set, MessageType.notify1)
            and self.body_type == ListTypes.X00
            and x00_command == C3_2010_COMMAND
        ):
            self.set_body(C3QuintupleBasicBody(body))
        elif (
            self.message_type
            in [MessageType.set, MessageType.notify1, MessageType.query]
            and self.body_type == ListTypes.X01
        ) or self.message_type == MessageType.notify2:
            if (
                len(body) == C3_SHORT_X01_BODY_LENGTH
                and self.body_type == ListTypes.X01
                and body[C3_SHORT_X01_MODE_SENTINEL_OFFSET]
                not in C3DeviceMode._value2member_map_
            ):
                self.set_body(C3ShortBasicBody(body))
            else:
                self.set_body(C3BasicBody(body, data_offset=1))
        elif (
            self.message_type in [MessageType.notify1, MessageType.query]
            and self.body_type == ListTypes.X0D
            and len(body) >= C3_DIAGNOSTIC_BODY_MIN_LENGTH
        ):
            self.set_body(C3DiagnosticBody(body))
        elif (
            self.message_type == MessageType.notify1 and self.body_type == ListTypes.X04
        ):
            self.set_body(C3EnergyBody(body, data_offset=1))
        elif self.message_type == MessageType.query and self.body_type == ListTypes.X05:
            self.set_body(C3SilenceBody(body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1 and self.body_type == ListTypes.X05
        ):
            self.set_body(C3UnitParaUpBody(body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1
            and self.body_type == ListTypes.X00
            and len(body) >= C3_2010_MIN_LENGTH
            and x00_command == C3_2010_COMMAND
        ):
            self.set_body(C3Basic2010Body(body))
        elif (
            self.message_type in (MessageType.query, MessageType.notify1)
            and self.body_type == ListTypes.X00
            and model == C3_X00_TELEMETRY_MODEL
            and len(body) >= C3_20B0_MIN_LENGTH
            and x00_command == C3_20B0_COMMAND
        ):
            self.set_body(C3X0020B0TelemetryBody(body))
        elif (
            self.message_type in (MessageType.query, MessageType.notify1)
            and self.body_type == ListTypes.X00
            and model == C3_X00_TELEMETRY_MODEL
            and len(body) >= C3_2F10_MIN_LENGTH
            and x00_command == C3_2F10_COMMAND
        ):
            self.set_body(C3X002F10TelemetryBody(body))
        elif self.body_type == ListTypes.X07:
            self.set_body(C3ECOBody(body, data_offset=1))
        elif self.body_type == ListTypes.X09:
            self.set_body(C3DisinfectBody(body, data_offset=1))
        elif self.body_type == ListTypes.X10:
            self.set_body(C3UnitParaBody(body, data_offset=1))
        self.set_attr()

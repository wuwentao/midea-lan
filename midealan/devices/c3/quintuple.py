"""Model 17100007 protocol from T_0000_C3_10004830_2025112601.lua.

The 0x2010 table has a ten-byte envelope and either sequential values or
two-byte-tag, one-byte-length TLVs. Writes contain only explicitly changed
properties; they must never replay the legacy controller's cached defaults.
"""

from enum import IntEnum
from math import isfinite

from midealan.const import DeviceType
from midealan.message import ListTypes, MessageBody, MessageRequest, MessageType

MODEL = "17100007"
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
ENERGY_SCALE = 100
WATTS_PER_ENERGY_UNIT = 10
ENERGY_SIZES = (1, 4, 2, 2, 2) + (4,) * 31
MIN_ENERGY_LENGTH = ENVELOPE_LENGTH + sum(ENERGY_SIZES[:12])
ENERGY_FIELDS = {
    2: ("current_unit_capacity", 1 / ENERGY_SCALE),
    3: ("instant_renew_power0", WATTS_PER_ENERGY_UNIT),
    4: ("instant_power0", WATTS_PER_ENERGY_UNIT),
    6: ("total_produced_energy", 1 / ENERGY_SCALE),
    9: ("total_energy_consumption", 1 / ENERGY_SCALE),
}
ENERGY_ATTRIBUTES = frozenset(name for name, _ in ENERGY_FIELDS.values())


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
ARRAY_FIELDS = {
    "zone_target_temp": (4, 5),
    "zone_heating_temp_max": (29, 33),
    "zone_heating_temp_min": (30, 34),
    "zone_cooling_temp_max": (31, 35),
    "zone_cooling_temp_min": (32, 36),
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
    """Decode 0x2F12 energy using the vendor's 0.01 kW/kWh scale.

    Existing HA power entities use watts; capacity is already kW in the
    model's telemetry parser. Totals use kWh. All-ones values are unavailable,
    never zero. No lifetime totals are derived by adding unlike counters.
    """

    def __init__(self, body: bytearray) -> None:
        """Expose complete energy fields from sequential or TLV packets."""
        super().__init__(body)
        values = _read_fields(body, ENERGY_SIZES, MIN_ENERGY_LENGTH)
        self.quintuple_energy = bool(values)
        for tag, (name, scale) in ENERGY_FIELDS.items():
            if tag in values:
                raw = values[tag]
                value = int.from_bytes(raw, "big")
                invalid = (1 << (len(raw) * 8)) - 1
                setattr(self, name, None if value == invalid else value * scale)


class C3QuintupleBasicBody(MessageBody):
    """Decode sequential status and sparse control acknowledgements."""

    def __init__(self, body: bytearray) -> None:
        """Expose valid fields, retaining absent array members in the device."""
        super().__init__(body)
        values = _read_fields(body)
        self.quintuple_basic = bool(values)
        self.quintuple_arrays: dict[str, dict[int, float | bool]] = {}
        for tag, name in BOOLEAN_FIELDS.items():
            if tag in values and values[tag][0] in (0, 1):
                setattr(self, name, bool(values[tag][0]))
        for tag, name in TEMPERATURE_FIELDS.items():
            if tag in values and (value := _temperature(values[tag])) is not None:
                setattr(self, name, value)
        for name, tags in ARRAY_FIELDS.items():
            changes: dict[int, float | bool] = {
                index: value
                for index, tag in enumerate(tags)
                if tag in values and (value := _temperature(values[tag])) is not None
            }
            if changes:
                self.quintuple_arrays[name] = changes
        types: dict[int, float | bool] = {
            index: values[tag][0] == 0
            for index, tag in enumerate((18, 19))
            if tag in values and values[tag][0] in (0, 1)
        }
        if types:
            self.quintuple_arrays["zone_temp_type"] = types
        if BasicTag.MODE in values and values[BasicTag.MODE][0] in MODE_FROM_WIRE:
            self.mode = MODE_FROM_WIRE[values[BasicTag.MODE][0]]
        if AUTO_MODE_TAG in values and values[AUTO_MODE_TAG][0] in (1, 2):
            self.mode_auto = values[AUTO_MODE_TAG][0] + 1
        if ERROR_CODE_TAG in values and values[ERROR_CODE_TAG][0] != INVALID_BYTE:
            self.error_code = values[ERROR_CODE_TAG][0]
        for tag, names in {
            4: ("zone1_temp_set", "idu_t1s1"),
            5: ("zone2_temp_set",),
            6: ("tas",),
            7: ("t5s",),
            52: ("temp_t4",),
        }.items():
            if tag in values and (value := _temperature(values[tag])) is not None:
                for name in names:
                    setattr(self, name, value)

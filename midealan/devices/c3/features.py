"""Curated 17100007 energy and user-setting tables from the vendor Lua.

Only stable energy metrics and existing control/status attributes are exposed.
Table widths retain unexposed fields so sequential offsets remain correct.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from midealan.const import DeviceType
from midealan.message import ListTypes, MessageRequest, MessageType

from .quintuple import ENVELOPE_LENGTH, _envelope, _read_fields

ENERGY_SCALE = 100
BYTE_BITS = 8
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
FIELDS: dict[tuple[int, int], tuple[tuple[str, ...], str]] = {
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
ENERGY_ATTRIBUTES = frozenset(
    names[0] for names, kind in FIELDS.values() if kind == "scaled"
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
        spec = FIELDS.get((table, tag))
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
        self._encoded = _envelope(tables.pop(), 1)
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

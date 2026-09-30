"""Midea lan 0x9C message.

0x9C is an integrated kitchen appliance (集成灶) that bundles several independent
sub-appliances (range hood, gas hob, steam cabinets, steam-bake boxes, induction
soup cookers, warming plates, an air conditioner and a built-in oven) behind one
LAN connection.

Unlike the fixed-offset devices, the 0x9C status body is a type-length-value
(TLV) list of *module packages*. The first body byte is a sub-command
(``0x01`` = all modules, ``0x02`` = error list); the module packages then follow
as ``<module_id><length><value...>`` records. Each module is decoded by a
declarative field table (see ``MODULE_FIELDS``) so that adding or adjusting a
field never introduces magic-value comparisons or deeply nested branches.

Control (set) messages write a single module: ``[sub_command, module_id,
field...]`` where ``0xFF`` means "leave unchanged". The set-echo frame
(``message_type`` set, sub-command ``0x01``) uses a different flat byte layout
than the TLV query response; status is instead refreshed through the periodic
notify/query messages, so only the TLV path is parsed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# --- Sub-commands (first body byte) -----------------------------------------
SUBCMD_ALL = 0x01  # full status: TLV list of module packages
SUBCMD_ERROR = 0x02  # error list

# --- Module identifiers (TLV record type) ----------------------------------
MODULE_TOTAL = 0xF0  # whole-appliance summary
MODULE_B6 = 0x01  # range hood
MODULE_B7 = 0x02  # gas hob (left/right burner)
MODULE_B3 = 0x03  # steam cabinet (upper/lower)
MODULE_B2 = 0x04  # steam-bake box (upper/lower)
MODULE_E7 = 0x05  # induction soup cooker
MODULE_SP = 0x06  # fan-drying / heating-disk / uvc plate
MODULE_AC = 0x08  # air conditioner
MODULE_BF = 0x09  # built-in oven

# --- TLV framing constants ---------------------------------------------------
SUBCMD_OFFSET = 1  # body[0] is the sub-command; records start at body[1]
TLV_HEADER_LEN = 2  # module id byte + length byte
UNCHANGED = 0xFF  # a field/byte holding 0xFF means "not present / unchanged"
BYTE_BASE = 256

VALUE_ON = "on"
VALUE_OFF = "off"

# --- Field descriptor kinds --------------------------------------------------
# Each module is described by a tuple of field descriptors. A descriptor is
# ``(name, index, kind, extra)`` where ``index`` is the 1-based package position
# (matching the source protocol) and ``kind`` selects the decoder.
KIND_BYTE = "byte"  # single raw byte
KIND_U16LE = "u16le"  # two little-endian bytes, valid unless both 0xFF
KIND_U16BE = "u16be"  # two big-endian bytes, valid only if both != 0xFF
KIND_U24BE = "u24be"  # three big-endian bytes, valid only if all != 0xFF
KIND_ENUM = "enum"  # map the raw byte through a lookup dict
KIND_BIT = "bit"  # single bit -> on/off (or custom on/off labels)
KIND_BITMAP = "bitmap"  # alias of KIND_BIT with custom labels
KIND_BITFLAG = "bitflag"  # single bit -> "0"/"1" string flag
KIND_MASKENUM = "maskenum"  # (mask, {masked_value: label})
KIND_MASK = "mask"  # numeric ``value & mask``
KIND_BOOLBIT = "boolbit"  # single bit -> Python bool
KIND_ONOFF = "onoff"  # whole byte through enum lookup
KIND_LIGHT = "light"  # 0 -> off, else on (+ companion lightness byte)


@dataclass(frozen=True)
class Field:
    """A declarative decoder for one attribute inside a module package.

    ``index`` is the 1-based byte position within the module value (matching the
    source protocol numbering). ``absolute`` keeps the attribute name unprefixed
    even inside a multi-instance module. ``guard_ff`` skips the field when its
    byte reads ``0xFF`` ("not present").
    """

    name: str
    index: int
    kind: str
    enum: dict[int, str] | dict[int, int] | None = None
    bit: int = 0
    off: str = VALUE_OFF
    on: str = VALUE_ON
    mask: int = 0xFF
    absolute: bool = False
    guard_ff: bool = True
    companion: str = ""


class _Package:
    """1-based accessor over a module's value bytes."""

    def __init__(self, data: bytearray) -> None:
        self._data = data

    def get(self, index: int) -> int | None:
        """Return the 1-based byte, or ``None`` when out of range."""
        pos = index - 1
        if 0 <= pos < len(self._data):
            return self._data[pos]
        return None

    @property
    def selector(self) -> int:
        """Return the sub-instance selector (first byte), 0 when absent."""
        value = self.get(1)
        return value if value is not None else 0


Decoded = tuple[str, object]


def _decode_byte(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or (fld.guard_ff and value == UNCHANGED):
        return None
    return (fld.name, value)


def _decode_u16le(fld: Field, pkg: _Package) -> Decoded | None:
    low = pkg.get(fld.index)
    high = pkg.get(fld.index + 1)
    if low is None or high is None or (low == UNCHANGED and high == UNCHANGED):
        return None
    return (fld.name, low + high * BYTE_BASE)


def _decode_u16be(fld: Field, pkg: _Package) -> Decoded | None:
    high = pkg.get(fld.index)
    low = pkg.get(fld.index + 1)
    if high is None or low is None or UNCHANGED in (high, low):
        return None
    return (fld.name, high * BYTE_BASE + low)


def _decode_u24be(fld: Field, pkg: _Package) -> Decoded | None:
    top = pkg.get(fld.index)
    mid = pkg.get(fld.index + 1)
    low = pkg.get(fld.index + 2)
    if top is None or mid is None or low is None:
        return None
    if UNCHANGED in (top, mid, low):
        return None
    return (fld.name, top * BYTE_BASE * BYTE_BASE + mid * BYTE_BASE + low)


def _decode_enum(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or fld.enum is None:
        return None
    label = fld.enum.get(value)
    if label is None:
        return None
    return (fld.name, label)


def _decode_bit(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or (fld.guard_ff and value == UNCHANGED):
        return None
    return (fld.name, fld.on if (value >> fld.bit) & 1 else fld.off)


def _decode_bitflag(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or (fld.guard_ff and value == UNCHANGED):
        return None
    return (fld.name, str((value >> fld.bit) & 1))


def _decode_maskenum(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or fld.enum is None or (fld.guard_ff and value == UNCHANGED):
        return None
    label = fld.enum.get(value & fld.mask)
    if label is None:
        return None
    return (fld.name, label)


def _decode_mask(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or (fld.guard_ff and value == UNCHANGED):
        return None
    # Right-shift by the mask's lowest set bit so a high-nibble mask such as
    # 0xF0 yields the nibble value (0x20 -> 2) rather than the raw masked byte.
    shift = (fld.mask & -fld.mask).bit_length() - 1
    return (fld.name, (value & fld.mask) >> shift)


def _decode_boolbit(fld: Field, pkg: _Package) -> Decoded | None:
    value = pkg.get(fld.index)
    if value is None or (fld.guard_ff and value == UNCHANGED):
        return None
    return (fld.name, bool((value >> fld.bit) & 1))


_DECODERS = {
    KIND_BYTE: _decode_byte,
    KIND_U16LE: _decode_u16le,
    KIND_U16BE: _decode_u16be,
    KIND_U24BE: _decode_u24be,
    KIND_ENUM: _decode_enum,
    KIND_ONOFF: _decode_enum,
    KIND_BIT: _decode_bit,
    KIND_BITMAP: _decode_bit,
    KIND_BITFLAG: _decode_bitflag,
    KIND_MASKENUM: _decode_maskenum,
    KIND_MASK: _decode_mask,
    KIND_BOOLBIT: _decode_boolbit,
}


def _apply_fields(
    fields: tuple[Field, ...],
    pkg: _Package,
    prefix: str,
    result: dict[str, object],
) -> None:
    """Decode every field in ``fields`` into ``result``.

    ``KIND_LIGHT`` is handled inline because it produces two attributes (an
    on/off flag plus a companion brightness value).
    """
    for fld in fields:
        full = fld.name if fld.absolute else prefix + fld.name
        if fld.kind == KIND_LIGHT:
            value = pkg.get(fld.index)
            if value is None or value == UNCHANGED:
                continue
            if value == 0:
                result[full] = fld.off
            else:
                result[full] = fld.on
                result[prefix + fld.companion] = value
            continue
        decoded = _DECODERS[fld.kind](fld, pkg)
        if decoded is not None:
            result[full] = decoded[1]


# ---------------------------------------------------------------------------
# Enum lookup tables
# ---------------------------------------------------------------------------
_TOTAL_POWER = {
    0x00: VALUE_OFF,
    0x01: VALUE_OFF,
    0x02: VALUE_ON,
    0x03: VALUE_OFF,
    0x04: VALUE_OFF,
    0x05: "delay_off",
    0x06: VALUE_OFF,
}
_ON_OFF_BYTE = {0x00: VALUE_OFF, 0x01: VALUE_ON}
_MICROPHONE = {0x00: VALUE_ON, 0x01: VALUE_OFF}
_AI_VOICE_STATUS = {0x00: "on", 0x01: "off", 0x02: "connecting"}
_AI_RESULT = {0x00: "success", 0x01: "failure"}
_LOCK_ON_TYPE = {0x01: "local", 0x02: "app"}
_LOCK_OFF_TYPE = {0x10: "local"}

_B6_WORK_STATUS = {
    0x00: "initial",
    0x01: "power_off",
    0x02: "working",
    0x03: "power_off_delay",
    0x04: "hotclean",
    0x0C: "hotclean",
    0x05: "error",
    0x06: "clean",
    0x07: "check",
    0x08: "vvvf_gear",
    0x09: "mute_gear",
    0x0A: "ai_dry_clean",
    0x0B: "clean_finish",
    0x0D: "air_duct_detection",
    0x0E: "standby",
}
_B6_POWER = {
    0x00: VALUE_OFF,
    0x01: VALUE_OFF,
    0x02: VALUE_ON,
    0x03: "delay_off",
    0x05: VALUE_OFF,
    0x07: VALUE_OFF,
}
_B6_GESTURE_VALUE = {0x01: "power", 0x02: "wind", 0x03: "light"}
_B6_GESTURE_SENS = {0x10: "1", 0x20: "2", 0x30: "3"}
_B6_SMOKE_VALUE = {0x01: 1, 0x02: 2, 0x03: 3, 0x04: 4, 0x05: 5, 0x06: 6, 0x07: 7}
_B6_INFRARED_VALUE = {0x01: "power", 0x02: "wind"}
_B6_TVOC_VALUE = {0x01: "优", 0x02: "良", 0x03: "中"}
_B6_POWER_ON_TYPE = {0x01: "local", 0x02: "app", 0x03: "gesture", 0x05: "linkage"}
_B6_POWER_OFF_TYPE = {
    0x10: "local",
    0x20: "app",
    0x30: "gesture",
    0x50: "linkage",
    0x70: "delay",
}
_B6_LIGHT_ON_TYPE = {0x01: "local", 0x02: "app", 0x03: "gesture"}
_B6_LIGHT_OFF_TYPE = {0x10: "local", 0x20: "app", 0x30: "gesture", 0x40: "error"}
_B6_GEAR_CONTROL_TYPE = {
    0x01: "local",
    0x02: "app",
    0x03: "gesture",
    0x05: "linkage",
    0x06: "smoke_detector",
}
_B6_SMOKE_STOVE_GEAR = {0x00: 0, 0x01: 1, 0x02: 2, 0x03: 3}
_B6_STOVE_LINKAGE_FLOWIN = {0x00: "no", 0x10: "yes"}
_B6_STOVE_LINKAGE_FIX = {0x00: "positive", 0x20: "negative"}
_B6_DELAY_GEAR = {0x01: 1, 0x02: 2, 0x03: 3}

_B7_STATUS = {0x00: "power_off", 0x01: "power_off", 0x02: "working", 0x03: "ai"}
_B7_POWER_OFF_TYPE = {
    0x01: "local",
    0x02: "app",
    0x03: "delay",
    0x04: "error",
    0x05: "ecu",
}

_B3_STATUS = {
    0x00: "power_off",
    0x01: "power_off",
    0x02: "uperization",
    0x03: "uperization_pause",
    0x04: "drying",
    0x05: "drying_pause",
    0x06: "ion_drying",
    0x07: "ion_drying_pause",
    0x08: "warm_drink",
    0x09: "warm_drink_pause",
}
_TYPE_LOCAL_APP_LOW = {0x01: "local", 0x02: "app"}
_TYPE_LOCAL_APP_HIGH = {0x10: "local", 0x20: "app"}

_B2_WORK_STATUS = {
    0x00: "power_off",
    0x01: "power_off",
    0x02: "working",
    0x03: "pause",
    0x04: "order",
    0x05: "drying",
    0x06: "auto",
    0x07: "finish",
    0x08: "standby",
}
_B2_POWER_ON_TYPE = {0x01: "local", 0x02: "app", 0x05: "order"}
_B2_POWER_OFF_TYPE = {
    0x10: "local",
    0x20: "app",
    0x30: "wifi",
    0x50: "error",
    0x70: "auto",
}

_E7_STATUS = {0x00: "power_off", 0x01: "power_off", 0x02: "working", 0x03: "order"}
_E7_MODE = {
    0x00: "none",
    0x01: "heat_preservation",
    0x02: "stew_soup",
    0x03: "boiling",
    0x04: "stir_frying",
}

_SP_STATUS = {0x00: "off", 0x01: "on", 0x02: "order", 0x04: "pause", 0x05: "preheat"}

_AC_STATUS = {
    0x00: "power_off",
    0x01: "power_off",
    0x02: "working",
    0x03: "order",
    0x04: "reservation",
    0x06: "reservation_and_order_reserving",
    0x07: "reservation_and_order_ordering",
}
_AC_MODE = {
    0x00: "none",
    0x01: "refrigeration",
    0x02: "air_supply",
    0x03: "dehumidification",
    0x04: "net_flavour",
}

_BF_CONTROL_BACK = {
    0x00: "success",
    0x01: "status_notsupport",
    0x02: "func_notsupport",
    0x03: "value_notsupport",
}
_BF_WORK_STATUS = {
    0x01: "power_off",
    0x02: "open",
    0x03: "working",
    0x04: "done",
    0x05: "order",
    0x06: "pause",
    0x07: "pause_temporarily",
    0x08: "love_three_seconds",
    0x09: "cloudmenu_setting",
    0x0A: "self_check",
    0x0B: "check_version",
    0x0C: "demo",
    0x0E: "after_sale",
    0x0F: "keep",
}
_BF_CAVITY = {0x00: "up", 0x80: "down"}
_BF_TIPS_MARK = {
    0x01: "door_open",
    0x02: "change_attachments",
    0x04: "apply",
    0x05: "feed",
    0x06: "stir",
    0x07: "recipe_tips",
}
_BF_WEIGHT_UNIT = {0x00: "g", 0x01: "kg", 0x02: "ounce", 0x03: "pound", 0x04: "other"}
_B2_RECIPE_ON_LOW = {0x01: "local", 0x02: "app", 0x05: "order"}
# Byte 27 high nibble is the "off type" counterpart (like power/light off type on
# bytes 25/26); the source lua mislabels it as another recipe_on_type.
_B2_RECIPE_OFF_TYPE = {
    0x10: "local",
    0x20: "app",
    0x30: "wifi",
    0x50: "error",
    0x70: "auto",
}


# ---------------------------------------------------------------------------
# Per-instance prefixes
# ---------------------------------------------------------------------------
_B7_PREFIX = {1: "b7_left_", 2: "b7_right_"}
_B3_PREFIX = {1: "b3_upstair_", 2: "b3_downstair_"}
_B2_PREFIX = {1: "b2_upstair_", 2: "b2_downstair_"}
_E7_PREFIX = {
    1: "e7_left_",
    2: "e7_right_",
    3: "e7_left_top_",
    4: "e7_left_bottom_",
    5: "e7_right_top_",
    6: "e7_right_bottom_",
}
_SP_PREFIX = {1: "sp_fandrying_", 2: "sp_heatingdisk_", 3: "sp_uvc_"}


# ---------------------------------------------------------------------------
# Regular field tables (specials are patched by the per-module functions below)
# ---------------------------------------------------------------------------
_B7_FIELDS: tuple[Field, ...] = (
    Field("status", 2, KIND_ENUM, enum=_B7_STATUS, guard_ff=False),
    Field("gear", 3, KIND_BYTE),
    Field("destination_time", 4, KIND_U16LE),
    Field("remaining_time", 6, KIND_U16LE),
    Field("destination_temp", 8, KIND_U16LE),
    Field("current_temp", 10, KIND_U16LE),
    Field("work_time", 12, KIND_U16LE),
    Field("has_pot", 14, KIND_BITFLAG, bit=0),
    Field("has_fire", 14, KIND_BITFLAG, bit=1),
    Field("gas_leakage", 14, KIND_BITFLAG, bit=2),
    Field("dry_burning", 14, KIND_BITFLAG, bit=3),
    Field("dry_burning_invalid", 14, KIND_BITFLAG, bit=4),
    Field("power_off_type", 15, KIND_MASKENUM, mask=0x7F, enum=_B7_POWER_OFF_TYPE),
)

_B3_FIELDS: tuple[Field, ...] = (
    Field("status", 2, KIND_ENUM, enum=_B3_STATUS, guard_ff=False),
    Field("destination_time", 3, KIND_U16LE),
    Field("remaining_time", 5, KIND_U16LE),
    Field("sensor", 7, KIND_BYTE),
    Field("door_lock", 7, KIND_BITFLAG, bit=0),
    Field("door", 7, KIND_BIT, bit=1, off="close", on="open"),
    Field("infrared", 7, KIND_BITFLAG, bit=2),
    Field("ultraviolet", 7, KIND_BITFLAG, bit=3),
    Field("destination_temp", 8, KIND_BYTE),
    Field("current_temp", 9, KIND_BYTE),
    Field(
        "b3_disinfect_on_type",
        10,
        KIND_MASKENUM,
        mask=0x0F,
        enum=_TYPE_LOCAL_APP_LOW,
        absolute=True,
    ),
    Field(
        "b3_disinfect_off_type",
        10,
        KIND_MASKENUM,
        mask=0x70,
        enum=_TYPE_LOCAL_APP_HIGH,
        absolute=True,
    ),
    Field(
        "b3_thermotank_on_type",
        11,
        KIND_MASKENUM,
        mask=0x0F,
        enum=_TYPE_LOCAL_APP_LOW,
        absolute=True,
    ),
    Field(
        "b3_thermotank_off_type",
        11,
        KIND_MASKENUM,
        mask=0x70,
        enum=_TYPE_LOCAL_APP_HIGH,
        absolute=True,
    ),
)

_B2_FIELDS: tuple[Field, ...] = (
    Field("work_status", 2, KIND_ENUM, enum=_B2_WORK_STATUS, guard_ff=False),
    Field("work_func", 3, KIND_BYTE),
    Field("work_menu", 4, KIND_BYTE),
    Field("work_destination_time", 5, KIND_U16LE),
    Field("work_remaining_time", 7, KIND_U16LE),
    Field("destination_temp", 9, KIND_U16LE),
    Field("current_temp", 11, KIND_U16LE),
    Field("order_destination_time", 13, KIND_U16LE),
    Field("order_remaining_time", 15, KIND_U16LE),
    Field("door", 17, KIND_BIT, bit=0, off="close", on="open"),
    Field("light", 17, KIND_BIT, bit=7),
    Field("lock", 18, KIND_BIT, bit=0),
    Field("water_shortage", 18, KIND_BITFLAG, bit=3),
    Field("clean_tips", 18, KIND_BITFLAG, bit=4),
    Field("must_clean_tips", 18, KIND_BITFLAG, bit=5),
    Field("fresh_water", 18, KIND_BITFLAG, bit=6),
    Field("recipe_total_steps", 21, KIND_BYTE),
    Field("recipe_current_step", 22, KIND_BYTE),
    Field("recipe_current_mode", 23, KIND_BYTE),
    Field("recipe_after", 24, KIND_BYTE),
    Field("power_on_type", 25, KIND_MASKENUM, mask=0x0F, enum=_B2_POWER_ON_TYPE),
    Field("power_off_type", 25, KIND_MASKENUM, mask=0xF0, enum=_B2_POWER_OFF_TYPE),
    Field("light_on_type", 26, KIND_MASKENUM, mask=0x0F, enum=_TYPE_LOCAL_APP_LOW),
    Field("light_off_type", 26, KIND_MASKENUM, mask=0xF0, enum=_TYPE_LOCAL_APP_HIGH),
    Field("recipe_on_type", 27, KIND_MASKENUM, mask=0x0F, enum=_B2_RECIPE_ON_LOW),
    Field("recipe_off_type", 27, KIND_MASKENUM, mask=0xF0, enum=_B2_RECIPE_OFF_TYPE),
)

_E7_FIELDS: tuple[Field, ...] = (
    Field("work_status", 2, KIND_ENUM, enum=_E7_STATUS, guard_ff=False),
    Field("mode", 3, KIND_ENUM, enum=_E7_MODE, guard_ff=False),
    Field("gear", 4, KIND_BYTE),
    Field("efficiency", 5, KIND_U16LE),
    Field("work_time", 7, KIND_U16LE),
    Field("destination_time", 9, KIND_U16LE),
    Field("remaining_time", 11, KIND_U16LE),
    Field("has_pot", 13, KIND_BITFLAG, bit=0),
    Field("bridge_link", 14, KIND_ENUM, enum=_ON_OFF_BYTE),
)

_SP_FIELDS: tuple[Field, ...] = (
    Field("status", 2, KIND_ENUM, enum=_SP_STATUS, guard_ff=False),
    Field("destination_time", 3, KIND_U16LE),
    Field("remaining_time", 5, KIND_U16LE),
    Field("temperature", 7, KIND_BYTE),
    Field("order_destination_time", 8, KIND_U16LE),
    Field("order_remaining_time", 10, KIND_U16LE),
    Field("setting_linkage", 12, KIND_BIT, bit=0, guard_ff=False),
    Field("setting_automode", 12, KIND_BIT, bit=1, guard_ff=False),
    Field("door", 12, KIND_BIT, bit=2, off="close", on="open", guard_ff=False),
    Field("setting_sync", 12, KIND_BIT, bit=3, guard_ff=False),
    Field("setting_linkcooker", 12, KIND_BIT, bit=4, guard_ff=False),
    Field("setting_automode_day", 13, KIND_BYTE),
    Field("setting_automode_starthour", 14, KIND_BYTE),
    Field("setting_automode_startminute", 15, KIND_BYTE),
)

_AC_FIELDS: tuple[Field, ...] = (
    Field(
        "ac_work_status",
        2,
        KIND_ENUM,
        enum=_AC_STATUS,
        guard_ff=False,
        absolute=True,
    ),
    Field("ac_mode", 3, KIND_ENUM, enum=_AC_MODE, guard_ff=False, absolute=True),
    Field("ac_gear", 4, KIND_BYTE, absolute=True),
    Field("ac_destination_time", 5, KIND_U16LE, absolute=True),
    Field("ac_remaining_time", 7, KIND_U16LE, absolute=True),
    Field("ac_destination_temp", 9, KIND_U16LE, absolute=True),
    Field("ac_current_temp", 11, KIND_U16LE, absolute=True),
    Field("ac_order_destination_time", 13, KIND_U16LE, absolute=True),
    Field("ac_order_remaining_time", 15, KIND_U16LE, absolute=True),
    Field("ac_swing", 17, KIND_BIT, bit=0, guard_ff=False, absolute=True),
    Field("ac_air_direction", 17, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("ac_draining_pump", 17, KIND_BIT, bit=3, guard_ff=False, absolute=True),
    Field("ac_cooling_fan", 17, KIND_BIT, bit=4, guard_ff=False, absolute=True),
    Field("ac_water_full", 18, KIND_BITFLAG, bit=3, guard_ff=False, absolute=True),
    Field(
        "ac_over_temperature",
        18,
        KIND_BITFLAG,
        bit=4,
        guard_ff=False,
        absolute=True,
    ),
    Field("ac_low_temperature", 18, KIND_BITFLAG, bit=5, guard_ff=False, absolute=True),
    Field("ac_ambient_temperature", 19, KIND_U16LE, absolute=True),
    Field("ac_swing_gear", 21, KIND_BYTE, absolute=True),
    Field("ac_swing_min_angle", 22, KIND_BYTE, absolute=True),
    Field("ac_swing_max_angle", 23, KIND_BYTE, absolute=True),
    Field("ac_air_direction_gear", 24, KIND_BYTE, absolute=True),
    Field("ac_air_direction_min_angle", 25, KIND_BYTE, absolute=True),
    Field("ac_air_direction_max_angle", 26, KIND_BYTE, absolute=True),
)

_BF_FIELDS: tuple[Field, ...] = (
    Field(
        "bf_control_back",
        1,
        KIND_ENUM,
        enum=_BF_CONTROL_BACK,
        guard_ff=False,
        absolute=True,
    ),
    Field("bf_recipe_code", 2, KIND_U24BE, absolute=True),
    Field("bf_step_total", 5, KIND_MASK, mask=0x0F, absolute=True),
    Field("bf_step_current", 5, KIND_MASK, mask=0xF0, absolute=True),
    Field("bf_preheat_set", 6, KIND_BOOLBIT, bit=0, absolute=True),
    Field("bf_probe", 6, KIND_BOOLBIT, bit=1, absolute=True),
    Field("bf_order", 6, KIND_BOOLBIT, bit=2, absolute=True),
    Field("bf_turntable", 6, KIND_BOOLBIT, bit=3, absolute=True),
    Field("bf_hotwind_set", 6, KIND_BOOLBIT, bit=4, absolute=True),
    Field("bf_cavity", 6, KIND_MASKENUM, mask=0x80, enum=_BF_CAVITY, absolute=True),
    Field("bf_mode", 7, KIND_U16BE, absolute=True),
    Field("bf_working_time", 9, KIND_U24BE, absolute=True),
    Field("bf_fire", 12, KIND_BYTE, absolute=True),
    Field("bf_temp_up_set", 13, KIND_U16BE, absolute=True),
    Field("bf_temp_down_set", 15, KIND_U16BE, absolute=True),
    Field("bf_temp_probe_set", 17, KIND_U16BE, absolute=True),
    Field("bf_steam", 19, KIND_BYTE, absolute=True),
    Field("bf_end_next", 21, KIND_BYTE, absolute=True),
    Field("bf_remaining_time", 22, KIND_U24BE, absolute=True),
    Field("bf_temp_up", 25, KIND_U16BE, absolute=True),
    Field("bf_temp_down", 27, KIND_U16BE, absolute=True),
    Field("bf_temp_probe", 29, KIND_U16BE, absolute=True),
    Field(
        "bf_work_status",
        31,
        KIND_ENUM,
        enum=_BF_WORK_STATUS,
        guard_ff=False,
        absolute=True,
    ),
    Field("bf_lock", 32, KIND_BIT, bit=0, guard_ff=False, absolute=True),
    Field("bf_door", 32, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("bf_water_box", 32, KIND_BIT, bit=2, guard_ff=False, absolute=True),
    Field("bf_water_shortage", 32, KIND_BIT, bit=3, guard_ff=False, absolute=True),
    Field("bf_water_change", 32, KIND_BIT, bit=4, guard_ff=False, absolute=True),
    Field("bf_preheat", 32, KIND_BIT, bit=5, guard_ff=False, absolute=True),
    Field("bf_preheat_done", 32, KIND_BIT, bit=6, guard_ff=False, absolute=True),
    Field("bf_error", 32, KIND_BIT, bit=7, guard_ff=False, absolute=True),
    Field("bf_flip", 33, KIND_BIT, bit=0, guard_ff=False, absolute=True),
    Field("bf_sensor", 33, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("bf_light", 33, KIND_BIT, bit=2, guard_ff=False, absolute=True),
    Field("bf_hightemp_lock", 33, KIND_BIT, bit=3, guard_ff=False, absolute=True),
    Field("bf_hightemp_error", 33, KIND_BIT, bit=4, guard_ff=False, absolute=True),
    Field("bf_hightemp_over", 33, KIND_BIT, bit=5, guard_ff=False, absolute=True),
    Field("bf_probe_meat", 33, KIND_BIT, bit=6, guard_ff=False, absolute=True),
    Field(
        "bf_order_time_isabsolute",
        34,
        KIND_BIT,
        bit=0,
        guard_ff=False,
        absolute=True,
    ),
    Field("bf_voice_module", 34, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("bf_voice_identify", 34, KIND_BIT, bit=2, guard_ff=False, absolute=True),
    Field("bf_temp_fahrenheit", 34, KIND_BIT, bit=4, guard_ff=False, absolute=True),
    Field("bf_sabbath", 34, KIND_BIT, bit=5, guard_ff=False, absolute=True),
    Field("bf_off_fromapp", 34, KIND_BIT, bit=7, guard_ff=False, absolute=True),
    Field("bf_stove_1", 35, KIND_BIT, bit=0, guard_ff=False, absolute=True),
    Field("bf_stove_2", 35, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("bf_stove_3", 35, KIND_BIT, bit=2, guard_ff=False, absolute=True),
    Field("bf_stove_4", 35, KIND_BIT, bit=3, guard_ff=False, absolute=True),
    Field("bf_stove_5", 35, KIND_BIT, bit=4, guard_ff=False, absolute=True),
    Field("bf_hotwind", 35, KIND_BIT, bit=5, guard_ff=False, absolute=True),
    Field("bf_wintersummertime", 35, KIND_BIT, bit=6, guard_ff=False, absolute=True),
    Field("bf_upload_interval", 35, KIND_BIT, bit=7, guard_ff=False, absolute=True),
    Field("bf_hydrops_full", 36, KIND_BIT, bit=0, guard_ff=False, absolute=True),
    Field("bf_radiating", 36, KIND_BIT, bit=1, guard_ff=False, absolute=True),
    Field("bf_turntable_reset", 36, KIND_BIT, bit=2, guard_ff=False, absolute=True),
    Field("bf_overheat", 36, KIND_BIT, bit=3, guard_ff=False, absolute=True),
    Field("bf_repair_cook", 36, KIND_BIT, bit=6, guard_ff=False, absolute=True),
    Field(
        "bf_scalehandling_remind",
        36,
        KIND_BIT,
        bit=7,
        guard_ff=False,
        absolute=True,
    ),
    Field(
        "bf_tips_mark",
        37,
        KIND_MASKENUM,
        mask=0x3F,
        enum=_BF_TIPS_MARK,
        absolute=True,
    ),
    Field("bf_time_synchronization", 37, KIND_BIT, bit=6, absolute=True),
    Field("bf_on_smart", 37, KIND_BIT, bit=7, absolute=True),
    Field("bf_weight_unit", 39, KIND_ENUM, enum=_BF_WEIGHT_UNIT, absolute=True),
    Field("bf_quick_btn_microwave_id", 41, KIND_U16BE, absolute=True),
    Field("bf_quick_btn_microwave_time", 43, KIND_U24BE, absolute=True),
    Field("bf_quick_btn_microwave_set", 46, KIND_U16BE, absolute=True),
    Field("bf_quick_btn_steam_id", 49, KIND_U16BE, absolute=True),
    Field("bf_quick_btn_steam_time", 51, KIND_U24BE, absolute=True),
    Field("bf_quick_btn_steam_set", 54, KIND_U16BE, absolute=True),
    Field("bf_quick_btn_bake_id", 57, KIND_U16BE, absolute=True),
    Field("bf_quick_btn_bake_time", 59, KIND_U24BE, absolute=True),
    Field("bf_quick_btn_bake_set", 62, KIND_U16BE, absolute=True),
)

# Total (0xF0) regular fields. The sensor/link bytes (12-15) and a few defaults
# are handled by ``_parse_total``.
_TOTAL_FIELDS: tuple[Field, ...] = (
    Field(
        "total_power",
        1,
        KIND_ENUM,
        enum=_TOTAL_POWER,
        guard_ff=False,
        absolute=True,
    ),
    Field("total_lock", 2, KIND_BIT, bit=0, absolute=True),
    Field("total_firewall_temp", 5, KIND_BYTE, absolute=True),
    Field("total_shelving_unit_temp", 6, KIND_BYTE, absolute=True),
    Field(
        "total_lock_on_type",
        15,
        KIND_MASKENUM,
        mask=0x0F,
        enum=_LOCK_ON_TYPE,
        absolute=True,
    ),
    Field(
        "total_lock_off_type",
        15,
        KIND_MASKENUM,
        mask=0x7F,
        enum=_LOCK_OFF_TYPE,
        absolute=True,
    ),
    Field("ai_voice_microphone", 16, KIND_ENUM, enum=_MICROPHONE, absolute=True),
    Field("ai_voice_volume", 17, KIND_BYTE, absolute=True),
    Field("ai_voice_status", 18, KIND_ENUM, enum=_AI_VOICE_STATUS, absolute=True),
    Field("ai_voice_microphone_status", 19, KIND_ENUM, enum=_AI_RESULT, absolute=True),
    Field("ai_voice_volume_status", 20, KIND_ENUM, enum=_AI_RESULT, absolute=True),
)

# b6 range hood (0x01) regular fields; sensor bytes and the trailing dynamic
# TLV section are handled by ``_parse_b6``.
_B6_FIELDS: tuple[Field, ...] = (
    Field("b6_work_status", 2, KIND_ENUM, enum=_B6_WORK_STATUS),
    Field("b6_power", 2, KIND_ENUM, enum=_B6_POWER),
    Field("b6_gear", 3, KIND_BYTE),
    Field("b6_destination_time", 4, KIND_U16LE),
    Field("b6_remaining_time", 6, KIND_U16LE),
    Field("b6_air_volume", 8, KIND_U16LE),
    Field("b6_light", 10, KIND_LIGHT, companion="b6_lightness"),
    Field("b6_hotclean_tips", 11, KIND_MASK, mask=0x01, guard_ff=False),
    Field("b6_lock", 11, KIND_BIT, bit=1, guard_ff=False),
    Field("b6_wind_pressure", 12, KIND_U16LE),
    Field("b6_last_hotclean_hour", 14, KIND_BYTE),
    Field("b6_gesture_value", 15, KIND_MASKENUM, mask=0x0F, enum=_B6_GESTURE_VALUE),
    Field(
        "b6_gesture_sensitivity",
        15,
        KIND_MASKENUM,
        mask=0x70,
        enum=_B6_GESTURE_SENS,
    ),
    Field("b6_gesture_status", 15, KIND_BIT, bit=7),
    Field(
        "b6_smoke_detector_value",
        16,
        KIND_MASKENUM,
        mask=0x7F,
        enum=_B6_SMOKE_VALUE,
    ),
    Field("b6_smoke_detector", 16, KIND_BIT, bit=7),
    Field("b6_infrared_value", 17, KIND_MASKENUM, mask=0x79, enum=_B6_INFRARED_VALUE),
    Field("b6_infrared_status", 17, KIND_BIT, bit=7),
    Field("b6_TVOC_value", 18, KIND_MASKENUM, mask=0x79, enum=_B6_TVOC_VALUE),
    Field("b6_TVOC_status", 18, KIND_BIT, bit=7),
    Field("b6_smoke_potency", 19, KIND_BYTE),
    Field("b6_power_on_type", 20, KIND_MASKENUM, mask=0x0F, enum=_B6_POWER_ON_TYPE),
    Field("b6_power_off_type", 20, KIND_MASKENUM, mask=0x70, enum=_B6_POWER_OFF_TYPE),
    Field("b6_light_on_type", 21, KIND_MASKENUM, mask=0x0F, enum=_B6_LIGHT_ON_TYPE),
    Field("b6_light_off_type", 21, KIND_MASKENUM, mask=0x70, enum=_B6_LIGHT_OFF_TYPE),
    Field(
        "b6_gear_control_type",
        22,
        KIND_MASKENUM,
        mask=0x7F,
        enum=_B6_GEAR_CONTROL_TYPE,
    ),
)

# b6 total-report linkage bytes (present inside the total package, positions
# 12-14) decoded by ``_parse_total``.
_TOTAL_B6_LINK_FIELDS: tuple[Field, ...] = (
    Field(
        "b6_smoke_stove_linkage_gear",
        12,
        KIND_MASKENUM,
        mask=0x07,
        enum=_B6_SMOKE_STOVE_GEAR,
        absolute=True,
    ),
    Field(
        "b6_smoke_stove_linkage_flowin",
        12,
        KIND_MASKENUM,
        mask=0x10,
        enum=_B6_STOVE_LINKAGE_FLOWIN,
        absolute=True,
    ),
    Field(
        "b6_smoke_stove_linkage_gear_fix",
        12,
        KIND_MASKENUM,
        mask=0x20,
        enum=_B6_STOVE_LINKAGE_FIX,
        absolute=True,
    ),
    Field("b6_power_on_light", 12, KIND_BIT, bit=6, absolute=True),
    Field("b6_smoke_stove_linkage", 12, KIND_BIT, bit=7, absolute=True),
    Field(
        "b6_delay_gear_linkage_gear",
        13,
        KIND_MASKENUM,
        mask=0x07,
        enum=_B6_DELAY_GEAR,
        absolute=True,
    ),
    Field("b6_delay_gear_linkage", 13, KIND_BIT, bit=7, absolute=True),
    Field("b6_delay_time_value", 14, KIND_MASK, mask=0x7F, absolute=True),
    Field("b6_delay_time", 14, KIND_BIT, bit=7, absolute=True),
)

# b6 dynamic sub-packages inside the b6 package (from position 23 onwards).
_B6_AIR_DUCT_ID = 0x03
_B6_SMOKE_DITECT_ID = 0x05
_B6_INVERTER_ID = 0x06
_B6_DYNAMIC_START = 23
# b6 hot-clean ("steaming") work-status codes and stage mapping.
_B6_STEAMING_STAGE1 = 0x04
_B6_STEAMING_STAGE2 = 0x0C
# b6 lock-off encoding: low 7 bits equal to this value mean "local".
_B6_LOCK_OFF_LOCAL = 0x10
_LOW_NIBBLE_MASK = 0x0F
_LOW_7BIT_MASK = 0x7F

_B6_AIR_DUCT_FIELDS: tuple[Field, ...] = (
    Field("b6_air_duct_detection_time", 1, KIND_U16BE, absolute=True),
    Field("b6_air_duct_detection_score", 3, KIND_BYTE, absolute=True),
    Field("b6_air_duct_detection_windage", 4, KIND_BYTE, absolute=True),
    Field("b6_air_duct_detection_state", 5, KIND_BYTE, absolute=True),
)

_B6_INVERTER_FIELDS: tuple[Field, ...] = (
    Field("b6_inverter_wind_flow", 1, KIND_U16LE, absolute=True),
    Field("b6_inverter_windage", 3, KIND_BYTE, absolute=True),
    Field("b6_inverter_wind_presssure", 4, KIND_U16LE, absolute=True),
    Field("b6_inverter_voltage", 6, KIND_U16LE, absolute=True),
    Field("b6_inverter_motor_speed", 8, KIND_U16LE, absolute=True),
    Field("b6_inverter_q_axis_current", 10, KIND_U16LE, absolute=True),
    Field("b6_inverter_start_time", 12, KIND_BYTE, absolute=True),
    Field("b6_inverter_efficiency", 13, KIND_BYTE, absolute=True),
    Field("b6_inverter_capacity", 14, KIND_U16LE, absolute=True),
    Field("b6_inverter_temperature", 16, KIND_BYTE, absolute=True),
    Field("b6_inverter_ac_frequency", 17, KIND_BYTE, absolute=True),
    Field("b6_inverter_work_gear", 18, KIND_U16LE, absolute=True),
    Field("b6_inverter_back_electromotive_force", 20, KIND_BYTE, absolute=True),
    Field("b6_inverter_temperature_limit_sign", 21, KIND_BYTE, absolute=True),
    Field("b6_inverter_motor_compensation_angle", 22, KIND_U16LE, absolute=True),
)


# ---------------------------------------------------------------------------
# Special-case parser offsets (1-based package positions) and bit positions.
# The declarative field tables name every regular offset through ``Field``;
# these constants name the ones consumed directly by the parsers below.
# ---------------------------------------------------------------------------
_TOTAL_SENSOR_INDEX = 4
_TOTAL_IR_BIT = 0
_TOTAL_SPEAK_BIT = 1
_TOTAL_GESTURE_BIT = 2
_TOTAL_WATER_SHORTAGE_BIT = 3
_TOTAL_ERROR_TYPE_INDEX = 7
_TOTAL_ERROR_CODE_INDEX = 8
_TOTAL_TIPS_TYPE_INDEX = 9
_TOTAL_TIPS_CODE_INDEX = 10
_TOTAL_VERSION_HIGH_INDEX = 21
_TOTAL_VERSION_LOW_INDEX = 22

_B2_RECIPE_HIGH_INDEX = 20
_B2_RECIPE_LOW_INDEX = 19
_B2_PREHEAT_FLAGS_INDEX = 18
_B2_PREHEAT_FINISH_BIT = 2
_B2_PREHEAT_PROGRESS_BIT = 1

_BF_WEIGHT_FLAGS_INDEX = 38
_BF_WEIGHT_RAW_INDEX = 20
_BF_WEIGHT_RAW_MOUNT_FLAG = 0x04  # byte-38 value selecting the raw mount value
_BF_WEIGHT_TENTHS_FACTOR = 10  # decoded mount is raw * 10 * multiple


# ---------------------------------------------------------------------------
# Module parsers
# ---------------------------------------------------------------------------
def _parse_total(data: bytearray, result: dict[str, object]) -> None:
    """Decode the whole-appliance summary package (0xF0)."""
    pkg = _Package(data)
    _apply_fields(_TOTAL_FIELDS, pkg, "", result)
    # The sensor byte carries several flags with fixed defaults.
    sensors = pkg.get(_TOTAL_SENSOR_INDEX)
    result.setdefault("total_speak", VALUE_OFF)
    result.setdefault("total_gesture", VALUE_OFF)
    result.setdefault("total_ir", VALUE_OFF)
    result.setdefault("total_water_shortage", "0")
    if sensors is not None and sensors != UNCHANGED:
        if (sensors >> _TOTAL_IR_BIT) & 1:
            result["total_ir"] = VALUE_ON
        if (sensors >> _TOTAL_SPEAK_BIT) & 1:
            result["total_speak"] = VALUE_ON
        if (sensors >> _TOTAL_GESTURE_BIT) & 1:
            result["total_gesture"] = VALUE_ON
        result["total_water_shortage"] = str((sensors >> _TOTAL_WATER_SHORTAGE_BIT) & 1)
    # Error/tips codes default to zero when the byte is 0xFF.
    for name, index in (
        ("total_error_type", _TOTAL_ERROR_TYPE_INDEX),
        ("total_error_code", _TOTAL_ERROR_CODE_INDEX),
        ("total_tips_type", _TOTAL_TIPS_TYPE_INDEX),
        ("total_tips_code", _TOTAL_TIPS_CODE_INDEX),
    ):
        value = pkg.get(index)
        result[name] = 0 if value is None or value == UNCHANGED else value
    _apply_fields(_TOTAL_B6_LINK_FIELDS, pkg, "", result)
    high = pkg.get(_TOTAL_VERSION_HIGH_INDEX)
    low = pkg.get(_TOTAL_VERSION_LOW_INDEX)
    if high is not None and low is not None and UNCHANGED not in (high, low):
        result["electronic_version"] = f"{high}.{low}"


def _parse_b6_dynamic(data: bytearray, result: dict[str, object]) -> int:
    """Walk the b6 dynamic sub-packages; return the trailing position (1-based)."""
    position = _B6_DYNAMIC_START
    while position < len(data):
        module_id = data[position - 1]
        length = data[position] if position < len(data) else 0
        sub = _Package(bytearray(data[position + 1 : position + 1 + length]))
        if module_id == _B6_AIR_DUCT_ID:
            _apply_fields(_B6_AIR_DUCT_FIELDS, sub, "", result)
        elif module_id == _B6_INVERTER_ID:
            _apply_fields(_B6_INVERTER_FIELDS, sub, "", result)
        position = position + length + 2
    return position


def _parse_b6(data: bytearray, result: dict[str, object]) -> None:
    """Decode the range-hood package (0x01)."""
    pkg = _Package(data)
    status = pkg.get(2)
    if status is not None and status != UNCHANGED:
        result["b6_steaming"] = VALUE_OFF
        if status in (_B6_STEAMING_STAGE1, _B6_STEAMING_STAGE2):
            result["b6_steaming"] = VALUE_ON
            result["b6_steaming_stage"] = 1 if status == _B6_STEAMING_STAGE1 else 2
    _apply_fields(_B6_FIELDS, pkg, "", result)
    position = _parse_b6_dynamic(data, result)
    tail = pkg.get(position)
    if tail is not None and tail != UNCHANGED:
        low = tail & _LOW_NIBBLE_MASK
        if low in _LOCK_ON_TYPE:
            result["b6_lock_on_type"] = _LOCK_ON_TYPE[low]
        if tail & _LOW_7BIT_MASK == _B6_LOCK_OFF_LOCAL:
            result["b6_lock_off_type"] = "local"


def _parse_prefixed(
    fields: tuple[Field, ...],
    prefixes: dict[int, str],
    data: bytearray,
    result: dict[str, object],
) -> tuple[_Package, str] | None:
    """Decode a module that has per-instance prefixes.

    Returns the package and its resolved prefix, or ``None`` when the selector
    is not one of the known instances. Skipping unknown selectors avoids writing
    unprefixed keys (``status``, ``gear``, ...) that would collide across the
    b7/b3/b2/e7/sp modules and are absent from ``ALL_ATTRIBUTES``.
    """
    pkg = _Package(data)
    prefix = prefixes.get(pkg.selector)
    if prefix is None:
        return None
    _apply_fields(fields, pkg, prefix, result)
    return pkg, prefix


def _parse_b7(data: bytearray, result: dict[str, object]) -> None:
    parsed = _parse_prefixed(_B7_FIELDS, _B7_PREFIX, data, result)
    if parsed is None:
        return
    _pkg, prefix = parsed
    remaining = result.get(prefix + "remaining_time")
    if isinstance(remaining, int) and remaining > 0:
        result[prefix + "status"] = "power_off_delay"


def _parse_b3(data: bytearray, result: dict[str, object]) -> None:
    _parse_prefixed(_B3_FIELDS, _B3_PREFIX, data, result)


def _parse_b2(data: bytearray, result: dict[str, object]) -> None:
    parsed = _parse_prefixed(_B2_FIELDS, _B2_PREFIX, data, result)
    if parsed is None:
        return
    pkg, prefix = parsed
    # recipe_code defaults to -1 and is only set when the pair is present.
    result[prefix + "recipe_code"] = -1
    high = pkg.get(_B2_RECIPE_HIGH_INDEX)
    low = pkg.get(_B2_RECIPE_LOW_INDEX)
    if low is not None and high is not None and (low != UNCHANGED or high != UNCHANGED):
        result[prefix + "recipe_code"] = low + high * BYTE_BASE
    # preheating is a tri-state across the finish/progress bits of the flags byte.
    flags = pkg.get(_B2_PREHEAT_FLAGS_INDEX)
    if flags is not None and flags != UNCHANGED:
        if (flags >> _B2_PREHEAT_FINISH_BIT) & 1:
            result[prefix + "preheating"] = "finish"
        elif (flags >> _B2_PREHEAT_PROGRESS_BIT) & 1:
            result[prefix + "preheating"] = "preheating"
        else:
            result[prefix + "preheating"] = "none"


def _parse_e7(data: bytearray, result: dict[str, object]) -> None:
    _parse_prefixed(_E7_FIELDS, _E7_PREFIX, data, result)


def _parse_sp(data: bytearray, result: dict[str, object]) -> None:
    _parse_prefixed(_SP_FIELDS, _SP_PREFIX, data, result)


def _parse_ac(data: bytearray, result: dict[str, object]) -> None:
    _apply_fields(_AC_FIELDS, _Package(data), "", result)


def _parse_bf(data: bytearray, result: dict[str, object]) -> None:
    pkg = _Package(data)
    _apply_fields(_BF_FIELDS, pkg, "", result)
    _parse_bf_weight(pkg, result)


def _parse_bf_weight(pkg: _Package, result: dict[str, object]) -> None:
    """Decode the oven weight multiple and derived mount value."""
    flags = pkg.get(_BF_WEIGHT_FLAGS_INDEX)
    multiple = 1.0
    if flags is not None and flags != UNCHANGED:
        for bit_index, (label, factor) in _BF_WEIGHT_MULTIPLE.items():
            if (flags >> bit_index) & 1:
                result["bf_weight_multiple"] = label
                multiple = factor
                break
    raw = pkg.get(_BF_WEIGHT_RAW_INDEX)
    if raw is not None and raw != UNCHANGED:
        if flags == _BF_WEIGHT_RAW_MOUNT_FLAG:
            result["bf_weight_mount"] = raw
        else:
            result["bf_weight_mount"] = raw * _BF_WEIGHT_TENTHS_FACTOR * multiple


_BF_WEIGHT_MULTIPLE = {
    0: ("one_of_ten_thousand", 0.0001),
    1: ("one_of_thousand", 0.001),
    2: ("one_of_hundred", 0.01),
    3: ("one_of_ten", 0.1),
    4: ("ten", 10.0),
    5: ("hundred", 100.0),
}


_MODULE_PARSERS = {
    MODULE_TOTAL: _parse_total,
    MODULE_B6: _parse_b6,
    MODULE_B7: _parse_b7,
    MODULE_B3: _parse_b3,
    MODULE_B2: _parse_b2,
    MODULE_E7: _parse_e7,
    MODULE_SP: _parse_sp,
    MODULE_AC: _parse_ac,
    MODULE_BF: _parse_bf,
}

# Attribute names produced by the special-case code above (not covered by a
# plain field descriptor). Kept next to the parsers so the two stay in sync.
_SPECIAL_ATTRIBUTES: tuple[str, ...] = (
    "total_speak",
    "total_gesture",
    "total_ir",
    "total_water_shortage",
    "total_error_type",
    "total_error_code",
    "total_tips_type",
    "total_tips_code",
    "electronic_version",
    "b6_steaming",
    "b6_steaming_stage",
    "b6_lightness",
    "b6_lock_on_type",
    "b6_lock_off_type",
    "bf_weight_multiple",
    "bf_weight_mount",
    "error_list",
)


def _build_all_attributes() -> tuple[str, ...]:
    """Compute every attribute name the parsers can emit.

    Derived from the field tables plus the per-instance prefixes and the
    special-case names, so the device attribute list never drifts from the
    decoder.
    """
    names: set[str] = set(_SPECIAL_ATTRIBUTES)
    for fld in (
        *_TOTAL_FIELDS,
        *_TOTAL_B6_LINK_FIELDS,
        *_B6_FIELDS,
        *_B6_AIR_DUCT_FIELDS,
        *_B6_INVERTER_FIELDS,
        *_AC_FIELDS,
        *_BF_FIELDS,
    ):
        names.add(fld.name)
    prefixed = (
        (_B7_FIELDS, _B7_PREFIX),
        (_B3_FIELDS, _B3_PREFIX),
        (_B2_FIELDS, _B2_PREFIX),
        (_E7_FIELDS, _E7_PREFIX),
        (_SP_FIELDS, _SP_PREFIX),
    )
    for fields, prefixes in prefixed:
        for prefix in prefixes.values():
            for fld in fields:
                names.add(fld.name if fld.absolute else prefix + fld.name)
    for prefix in _B2_PREFIX.values():
        names.add(prefix + "recipe_code")
        names.add(prefix + "preheating")
    return tuple(sorted(names))


ALL_ATTRIBUTES: tuple[str, ...] = _build_all_attributes()


# ---------------------------------------------------------------------------
# Request messages
# ---------------------------------------------------------------------------
class MessageX9CBase(MessageRequest):
    """0x9C message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
    ) -> None:
        """Initialize 0x9C message base."""
        super().__init__(
            device_type=DeviceType.X9C,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=ListTypes.X01,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError

    @property
    def body(self) -> bytearray:
        """Message body (no separate body-type byte prepended)."""
        return self._body


class MessageQuery(MessageX9CBase):
    """0x9C query-all message."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize 0x9C query message."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([SUBCMD_ALL])


class MessageQueryError(MessageX9CBase):
    """0x9C error-list query message."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize 0x9C error query message."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([SUBCMD_ERROR])


class MessageSet(MessageX9CBase):
    """0x9C control message writing a single module.

    Sub-classes populate ``_fields`` (a fixed-length byte list beginning at the
    module identifier). Every field defaults to ``0xFF`` ("unchanged").
    """

    def __init__(self, protocol_version: int, module_id: int, length: int) -> None:
        """Initialize a 0x9C control message."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
        )
        self._fields = bytearray([UNCHANGED] * length)
        self._fields[0] = module_id

    @property
    def _body(self) -> bytearray:
        return bytearray([SUBCMD_ALL]) + self._fields

    def _set_byte(self, index: int, value: int) -> None:
        """Write a single field byte (1-based, matching the protocol)."""
        self._fields[index - 1] = value & 0xFF

    def _set_u16le(self, index: int, value: int) -> None:
        """Write a little-endian 16-bit field (low byte first)."""
        self._fields[index - 1] = value & 0xFF
        self._fields[index] = (value // BYTE_BASE) & 0xFF


# Field byte length of each control frame (module id + payload).
_SET_LEN_TOTAL = 8
_SET_LEN_B6 = 14
_SET_LEN_B7 = 8
_SET_LEN_B3 = 6
_SET_LEN_B2 = 17
_SET_LEN_E7 = 8
_SET_LEN_SP = 13
_SET_LEN_AC = 19

_TOTAL_POWER_SET = {VALUE_OFF: 0x01, VALUE_ON: 0x02}
_B6_WORK_STATUS_SET = {
    "working": 0x02,
    "power_off": 0x01,
    "power_off_delay": 0x03,
    "hotclean": 0x04,
    "vvvf_gear": 0x08,
    "mute_gear": 0x09,
    "ai_dry_clean": 0x0A,
    "air_duct_detection": 0x0D,
}
_B6_POWER_SET = {VALUE_ON: 0x02, VALUE_OFF: 0x01, "delay_off": 0x03}
_B6_GESTURE_VALUE_SET = {"power": 0x01, "wind": 0x02, "light": 0x03}
_B6_INFRARED_VALUE_SET = {"power": 0x01, "wind": 0x02}
_B6_LINKAGE_FIX_SET = {"positive": 0x00, "negative": 0x01}
# Settings that are a plain on/off toggle at a selector byte.
_B6_SIMPLE_SETTINGS = {"TVOC": 0x04, "power_on_light": 0x07, "lock": 0x09}
_B6_SELECTOR_GESTURE = 0x01
_B6_SELECTOR_INFRARED = 0x03
_B6_SELECTOR_SMOKE_STOVE = 0x05
_B6_SELECTOR_DELAY_GEAR = 0x06
_B6_SELECTOR_DELAY_TIME = 0x08
_B6_SMOKE_DETECTOR_TAG = 0x04
_B7_BURNER = {"left": 1, "right": 2}
_B2_STATUS_SET = {
    "power_off": 0x01,
    "working": 0x02,
    "pause": 0x03,
    "order": 0x04,
    "drying": 0x05,
    "auto": 0x06,
}
_E7_STATUS_SET = {"power_off": 0x01, "working": 0x02, "order": 0x03}
_E7_MODE_SET = {
    "none": 0x00,
    "heat_preservation": 0x01,
    "stew_soup": 0x02,
    "boiling": 0x03,
    "stir_frying": 0x04,
}
_AC_STATUS_SET = {
    "power_off": 0x01,
    "working": 0x02,
    "order": 0x03,
    "reservation": 0x04,
    "reservation_and_order": 0x05,
    "setting": 0x08,
}
_AC_MODE_SET = {
    "none": 0x00,
    "refrigeration": 0x01,
    "air_supply": 0x02,
    "dehumidification": 0x03,
    "net_flavour": 0x04,
}


class MessageSetTotal(MessageSet):
    """Control message for the whole-appliance module (0xF0)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the total control message."""
        super().__init__(protocol_version, MODULE_TOTAL, _SET_LEN_TOTAL)
        self.power: str | None = None
        self.lock: bool | None = None
        self.ai_voice_microphone: str | None = None
        self.ai_voice_volume: int | None = None

    @property
    def _body(self) -> bytearray:
        if self.power in _TOTAL_POWER_SET:
            self._set_byte(3, _TOTAL_POWER_SET[self.power])
        if self.lock is not None:
            self._set_byte(4, 0x01 if self.lock else 0x00)
        if self.ai_voice_microphone == VALUE_ON:
            self._set_byte(7, 0x00)
        elif self.ai_voice_microphone == VALUE_OFF:
            self._set_byte(7, 0x01)
        if self.ai_voice_volume is not None:
            self._set_byte(8, self.ai_voice_volume)
        return super()._body


class MessageSetB7(MessageSet):
    """Control message for the gas hob (0x02)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the b7 control message."""
        super().__init__(protocol_version, MODULE_B7, _SET_LEN_B7)
        self.burner: str | None = None
        self.function_control: int | None = None
        self.gear: int | None = None
        self.destination_time: int | None = None
        self.destination_temp: int | None = None

    @property
    def _body(self) -> bytearray:
        if self.burner in _B7_BURNER:
            self._set_byte(2, _B7_BURNER[self.burner])
        if self.function_control is not None:
            self._set_byte(3, self.function_control)
        if self.gear is not None:
            self._set_byte(4, self.gear)
        if self.destination_time is not None:
            self._set_u16le(5, self.destination_time)
        if self.destination_temp is not None:
            self._set_u16le(7, self.destination_temp)
        return super()._body


class MessageSetE7(MessageSet):
    """Control message for the induction soup cooker (0x05)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the e7 control message."""
        super().__init__(protocol_version, MODULE_E7, _SET_LEN_E7)
        self._set_byte(2, 0x01)
        self.burner: int | None = None
        self.status: str | None = None
        self.mode: str | None = None
        self.gear: int | None = None
        self.destination_time: int | None = None
        self.bridge_link: str | None = None

    @property
    def _body(self) -> bytearray:
        if self.burner is not None:
            self._set_byte(2, self.burner)
        if self.status in _E7_STATUS_SET:
            self._set_byte(3, _E7_STATUS_SET[self.status])
        if self.mode in _E7_MODE_SET:
            self._set_byte(4, _E7_MODE_SET[self.mode])
        if self.gear is not None:
            self._set_byte(5, self.gear)
        if self.destination_time is not None:
            self._set_u16le(6, self.destination_time)
        if self.bridge_link == VALUE_OFF:
            self._set_byte(8, 0x00)
        elif self.bridge_link == VALUE_ON:
            self._set_byte(8, 0x01)
        return super()._body


class MessageSetAc(MessageSet):
    """Control message for the air conditioner (0x08)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the ac control message."""
        super().__init__(protocol_version, MODULE_AC, _SET_LEN_AC)
        self._set_byte(2, 0x01)
        self.status: str | None = None
        self.mode: str | None = None
        self.gear: int | None = None
        self.destination_time: int | None = None
        self.destination_temp: int | None = None
        self.swing: str | None = None
        self.air_direction: str | None = None
        self.swing_gear: int | None = None
        self.swing_min_angle: int | None = None
        self.swing_max_angle: int | None = None
        self.air_direction_gear: int | None = None
        self.air_direction_min_angle: int | None = None
        self.air_direction_max_angle: int | None = None

    @property
    def _body(self) -> bytearray:
        if self.status in _AC_STATUS_SET:
            self._set_byte(3, _AC_STATUS_SET[self.status])
        if self.mode in _AC_MODE_SET:
            self._set_byte(4, _AC_MODE_SET[self.mode])
        if self.gear is not None:
            self._set_byte(5, self.gear)
        if self.destination_time is not None:
            self._set_u16le(6, self.destination_time)
        if self.destination_temp is not None:
            self._set_u16le(8, self.destination_temp)
        if self.swing == VALUE_OFF:
            self._set_byte(12, 0x00)
        elif self.swing == VALUE_ON:
            self._set_byte(12, 0x01)
        if self.air_direction == VALUE_OFF:
            self._set_byte(13, 0x00)
        elif self.air_direction == VALUE_ON:
            self._set_byte(13, 0x01)
        if self.swing_gear is not None:
            self._set_byte(14, self.swing_gear)
        if self.swing_min_angle is not None:
            self._set_byte(15, self.swing_min_angle)
        if self.swing_max_angle is not None:
            self._set_byte(16, self.swing_max_angle)
        if self.air_direction_gear is not None:
            self._set_byte(17, self.air_direction_gear)
        if self.air_direction_min_angle is not None:
            self._set_byte(18, self.air_direction_min_angle)
        if self.air_direction_max_angle is not None:
            self._set_byte(19, self.air_direction_max_angle)
        return super()._body


class MessageSetB6(MessageSet):
    """Control message for the range hood (0x01).

    The range hood exposes power/gear/light plus a family of one-shot setting
    commands (gesture, smoke detector, linkage, lock, ...). ``setting`` selects
    which command to emit; the matching ``*_value`` attributes fill it in.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize the b6 control message."""
        super().__init__(protocol_version, MODULE_B6, _SET_LEN_B6)
        self._set_byte(2, 0x01)
        self.work_status: str | None = None
        self.power: str | None = None
        self.gear: int | None = None
        self.light: str | None = None
        self.lightness: int | None = None
        self.setting: str | None = None
        self.gesture_value: str | None = None
        self.gesture_sensitivity: int | None = None
        self.smoke_detector: str | None = None
        self.smoke_detector_value: int | None = None
        self.infrared_value: str | None = None
        self.tvoc: str | None = None
        self.smoke_stove_linkage: str | None = None
        self.smoke_stove_linkage_gear: int | None = None
        self.smoke_stove_linkage_gear_fix: str | None = None
        self.delay_gear_linkage: str | None = None
        self.delay_gear_linkage_gear: int | None = None
        self.power_on_light: str | None = None
        self.delay_time: str | None = None
        self.delay_time_value: int | None = None
        self.lock: str | None = None

    def _apply_power(self) -> None:
        if self.work_status in _B6_WORK_STATUS_SET:
            self._set_byte(3, _B6_WORK_STATUS_SET[self.work_status])
            if self.work_status == "working":
                self._set_byte(4, 0x02)
        elif self.power in _B6_POWER_SET:
            self._set_byte(3, _B6_POWER_SET[self.power])
            if self.power == VALUE_ON:
                self._set_byte(4, 0x02)
        if self.gear is not None:
            self._set_byte(4, self.gear)
            self._set_byte(3, 0x01 if self.gear == 0x00 else 0x02)

    def _apply_light(self) -> None:
        if self.light == VALUE_ON:
            level = 0x64
            if self.lightness is not None and self.lightness != 0x00:
                level = self.lightness
            self._set_byte(7, level)
        elif self.light == VALUE_OFF:
            self._set_byte(7, 0x00)

    def _apply_on_off_value(self, index: int, value: str | None) -> None:
        if value == VALUE_ON:
            self._set_byte(index, 0x01)
        elif value == VALUE_OFF:
            self._set_byte(index, 0x00)

    def _apply_gesture(self) -> None:
        self._set_byte(8, _B6_SELECTOR_GESTURE)
        self._set_byte(9, 0x01)
        if self.gesture_value in _B6_GESTURE_VALUE_SET:
            self._set_byte(10, _B6_GESTURE_VALUE_SET[self.gesture_value])
        elif self.gesture_value == VALUE_OFF:
            self._set_byte(9, 0x00)

    def _apply_smoke_detector(self) -> None:
        self._set_byte(12, _B6_SMOKE_DETECTOR_TAG)
        value = self.smoke_detector_value
        if value is not None:
            if value == 0:
                self._set_byte(13, 0x00)
            else:
                self._set_byte(13, 0x01)
                self._set_byte(14, value)
        elif self.smoke_detector == VALUE_ON:
            self._set_byte(13, 0x01)
        elif self.smoke_detector == VALUE_OFF:
            self._set_byte(13, 0x00)

    def _apply_infrared(self) -> None:
        self._set_byte(8, _B6_SELECTOR_INFRARED)
        self._set_byte(9, 0x01)
        if self.infrared_value in _B6_INFRARED_VALUE_SET:
            self._set_byte(10, _B6_INFRARED_VALUE_SET[self.infrared_value])
        elif self.infrared_value == VALUE_OFF:
            self._set_byte(9, 0x00)

    def _apply_linkage(
        self,
        selector: int,
        enabled: str | None,
        gear: int | None,
    ) -> None:
        self._set_byte(8, selector)
        self._apply_on_off_value(9, enabled)
        if gear is not None:
            if gear == 0:
                self._set_byte(9, 0x00)
            else:
                self._set_byte(9, 0x01)
                self._set_byte(10, gear)

    def _apply_setting(self) -> None:
        if self.setting == "gesture":
            self._apply_gesture()
        elif self.setting == "smoke_detector":
            self._apply_smoke_detector()
        elif self.setting == "infrared":
            self._apply_infrared()
        elif self.setting == "TVOC":
            self._set_byte(8, _B6_SIMPLE_SETTINGS["TVOC"])
            self._apply_on_off_value(9, self.tvoc)
        elif self.setting == "smoke_stove_linkage":
            self._apply_linkage(
                _B6_SELECTOR_SMOKE_STOVE,
                self.smoke_stove_linkage,
                self.smoke_stove_linkage_gear,
            )
            if self.smoke_stove_linkage_gear_fix in _B6_LINKAGE_FIX_SET:
                self._set_byte(
                    11,
                    _B6_LINKAGE_FIX_SET[self.smoke_stove_linkage_gear_fix],
                )
        elif self.setting == "delay_gear_linkage":
            self._apply_linkage(
                _B6_SELECTOR_DELAY_GEAR,
                self.delay_gear_linkage,
                self.delay_gear_linkage_gear,
            )
        elif self.setting == "power_on_light":
            self._set_byte(8, _B6_SIMPLE_SETTINGS["power_on_light"])
            self._apply_on_off_value(9, self.power_on_light)
        elif self.setting == "delay_time":
            self._set_byte(8, _B6_SELECTOR_DELAY_TIME)
            self._apply_on_off_value(9, self.delay_time)
            if self.delay_time_value is not None:
                self._set_byte(10, self.delay_time_value)
        elif self.setting == "lock":
            self._set_byte(8, _B6_SIMPLE_SETTINGS["lock"])
            self._apply_on_off_value(9, self.lock)

    @property
    def _body(self) -> bytearray:
        self._apply_power()
        self._apply_light()
        self._apply_setting()
        if self.gesture_sensitivity is not None:
            self._set_byte(8, _B6_SELECTOR_GESTURE)
            self._set_byte(11, self.gesture_sensitivity)
        return super()._body


class MessageSetB3(MessageSet):
    """Control message for the steam cabinet (0x03)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the b3 control message."""
        super().__init__(protocol_version, MODULE_B3, _SET_LEN_B3)
        self.cabinet: int | None = None
        self.function_control: int | None = None
        self.destination_time: int | None = None
        self.destination_temp: int | None = None

    @property
    def _body(self) -> bytearray:
        if self.cabinet is not None:
            self._set_byte(2, self.cabinet)
        if self.function_control is not None:
            self._set_byte(3, self.function_control)
        if self.destination_time is not None:
            self._set_u16le(4, self.destination_time)
        if self.destination_temp is not None:
            temp = min(self.destination_temp, 0xFE)
            self._set_byte(6, temp)
        return super()._body


class MessageSetB2(MessageSet):
    """Control message for the steam-bake box (0x04)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the b2 control message."""
        super().__init__(protocol_version, MODULE_B2, _SET_LEN_B2)
        self._set_byte(2, 0x01)
        self.cabinet: int | None = None
        self.work_status: str | None = None
        self.work_func: int | None = None
        self.work_menu: int | None = None
        self.recipe_code: int | None = None
        self.work_destination_time: int | None = None
        self.destination_temp: int | None = None
        self.order_destination_time: int | None = None
        self.work_sub_menu: int | None = None
        self.menu_number: int | None = None
        self.menu_weight: int | None = None
        self.light: str | None = None
        self.lock: str | None = None

    @property
    def _body(self) -> bytearray:
        if self.cabinet is not None:
            self._set_byte(2, self.cabinet)
        if self.work_status in _B2_STATUS_SET:
            self._set_byte(3, _B2_STATUS_SET[self.work_status])
        if self.work_func is not None:
            self._set_byte(4, self.work_func)
        if self.work_menu is not None:
            self._set_byte(5, self.work_menu)
        if self.recipe_code is not None:
            self._set_byte(5, self.recipe_code)
        if self.work_destination_time is not None:
            self._set_u16le(6, self.work_destination_time)
        if self.destination_temp is not None:
            self._set_u16le(8, self.destination_temp)
        if self.order_destination_time is not None:
            self._set_u16le(10, self.order_destination_time)
        if self.work_sub_menu is not None:
            self._set_byte(12, self.work_sub_menu)
        if self.menu_number is not None:
            self._set_byte(13, self.menu_number)
        if self.menu_weight is not None:
            self._set_u16le(14, self.menu_weight)
        if self.light == VALUE_ON:
            self._set_byte(16, 0x01)
        elif self.light == VALUE_OFF:
            self._set_byte(16, 0x00)
        if self.lock == VALUE_ON:
            self._set_byte(17, 0x01)
        elif self.lock == VALUE_OFF:
            self._set_byte(17, 0x00)
        return super()._body


class MessageSetSp(MessageSet):
    """Control message for the drying/warming plates (0x06)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the sp control message."""
        super().__init__(protocol_version, MODULE_SP, _SET_LEN_SP)
        self.func: int | None = None
        self.status: str | None = None
        self.destination_time: int | None = None
        self.temperature: int | None = None
        self.order_destination_time: int | None = None
        self.setting_type: int | None = None
        self.setting_value: int | None = None
        self.setting_linkage: str | None = None
        self.setting_automode: str | None = None
        self.automode_day: int | None = None
        self.automode_starthour: int | None = None
        self.automode_startminute: int | None = None

    def _apply_status(self) -> None:
        if self.func is not None:
            self._set_byte(2, self.func)
        mapping = {VALUE_ON: 0x01, VALUE_OFF: 0x00, "order": 0x02, "setting": 0x03}
        if self.status in mapping:
            self._set_byte(3, mapping[self.status])
        if self.destination_time is not None:
            self._set_u16le(4, self.destination_time)
        if self.temperature is not None:
            self._set_byte(6, self.temperature)
        if self.order_destination_time is not None:
            self._set_u16le(7, self.order_destination_time)

    def _apply_setting(self) -> None:
        if self.setting_type is not None and self.setting_value is not None:
            self._set_byte(9, self.setting_type)
            self._set_byte(10, self.setting_value)
        if self.setting_linkage in (VALUE_ON, VALUE_OFF):
            self._set_byte(9, 0x01)
            self._set_byte(10, 0x01 if self.setting_linkage == VALUE_ON else 0x00)
        if self.setting_automode in (VALUE_ON, VALUE_OFF):
            self._set_byte(9, 0x02)
            self._set_byte(10, 0x01 if self.setting_automode == VALUE_ON else 0x00)
            if self.automode_day is not None:
                self._set_byte(11, self.automode_day)
            if self.automode_starthour is not None:
                self._set_byte(12, self.automode_starthour)
            if self.automode_startminute is not None:
                self._set_byte(13, self.automode_startminute)

    @property
    def _body(self) -> bytearray:
        self._apply_status()
        self._apply_setting()
        return super()._body


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
class X9CGeneralMessageBody(MessageBody):
    """Decodes a full-status (sub-command 0x01) TLV body.

    Walks the module packages and dispatches each to its parser, collecting all
    recognised attributes into ``attributes``.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize 0x9C general message body."""
        super().__init__(body)
        self.attributes: dict[str, object] = {}
        self._parse_modules(body)

    def _parse_modules(self, body: bytearray) -> None:
        position = SUBCMD_OFFSET
        while position + TLV_HEADER_LEN <= len(body):
            module_id = body[position]
            length = body[position + 1]
            value_start = position + TLV_HEADER_LEN
            value_end = value_start + length
            if value_end > len(body):
                break
            parser = _MODULE_PARSERS.get(module_id)
            if parser is not None and length > 0:
                parser(bytearray(body[value_start:value_end]), self.attributes)
            position = value_end


class X9CErrorMessageBody(MessageBody):
    """Decodes an error-list (sub-command 0x02) body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize 0x9C error message body."""
        super().__init__(body)
        self.attributes: dict[str, object] = {}
        count = body[SUBCMD_OFFSET] if len(body) > SUBCMD_OFFSET else UNCHANGED
        if count != UNCHANGED:
            start = SUBCMD_OFFSET + 1
            self.attributes["error_list"] = list(body[start : start + count])


class MessageX9CResponse(MessageResponse):
    """0x9C message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize 0x9C message response."""
        super().__init__(bytearray(message))
        self.attributes: dict[str, object] = {}
        body = super().body
        subcmd = body[0] if body else 0
        if self.message_type not in (
            MessageType.query,
            MessageType.notify1,
            MessageType.notify2,
        ):
            self.set_attr()
            return
        if subcmd == SUBCMD_ALL:
            parsed: MessageBody = X9CGeneralMessageBody(body)
            self.set_body(parsed)
            self.attributes = parsed.attributes  # type: ignore[attr-defined]
        elif subcmd == SUBCMD_ERROR:
            error_parsed = X9CErrorMessageBody(body)
            self.set_body(error_parsed)
            self.attributes = error_parsed.attributes
        self.set_attr()

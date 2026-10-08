"""Midea lan x9b message.

0x9B is a microwave + steam + convection combi oven (微蒸烤一体机). Two firmware
revisions of the same appliance exist:

* an older V1 (``VALUE_VERSION=7``) using single-byte temperatures, and
* a newer V2 (``VALUE_VERSION=2``) that is a strict superset -- two-byte
  temperatures plus food-probe, turntable, hot-wind, ramadan, OTA and
  system-time fields.

The status body is a flat, fixed-offset record whose first byte is a
sub-command (``0x01`` = full status, ``0x04`` = system time). The V2 layout is
decoded here as the canonical superset: for the fields that V1 also reports the
two encodings coincide (V1 keeps the value in the low byte of the V2 two-byte
pair), so a single decoder serves both revisions.

Control (set) messages also start with a sub-command byte that selects the
command group: ``0x01`` start cooking, ``0x02`` state controls, ``0x03`` live
parameter adjustment (a type-length-value list) and ``0x04`` set system time.
"""

from __future__ import annotations

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# --- Sub-commands (first body byte) -----------------------------------------
SUBCMD_STATUS = 0x01  # full status record
SUBCMD_COOKING = 0x01  # start-cooking control (same byte, set direction)
SUBCMD_STATE = 0x02  # non-cooking state controls
SUBCMD_PARAM = 0x03  # live parameter adjustment (TLV list)
SUBCMD_SYSTIME = 0x04  # system time (query and set)

# --- Generic framing constants ----------------------------------------------
UNCHANGED = 0xFF  # a byte holding 0xFF means "not present / leave unchanged"
BYTE_BASE = 256  # two-byte big-endian scale factor
BYTE_MASK = 0xFF  # low-byte mask
NIBBLE_MASK = 0x0F  # low-nibble mask
NIBBLE_SHIFT = 4  # bits per nibble
BYTE_MIN = 0  # smallest value a single byte can carry
BYTE_MAX = 0xFF  # largest value a single byte can carry
# Byte controls whose "leave unchanged" sentinel is 0xFF can only carry 0..0xFE
# as a real value; 0xFF would be indistinguishable from "not set".
SETTABLE_BYTE_MAX = UNCHANGED - 1  # 0xFE
U16_MIN = 0  # smallest value a big-endian u16 field can carry
U16_MAX = 0xFFFF  # largest value a big-endian u16 field can carry

# --- Status-flag bit positions ----------------------------------------------
# Named positions for the single-bit flags packed into the status bytes, so the
# decoder never reads a raw numeric bit index. Each name says which bit of which
# status byte it is.
BIT_0 = 0
BIT_1 = 1
BIT_2 = 2
BIT_3 = 3
BIT_4 = 4
BIT_5 = 5
BIT_6 = 6
BIT_7 = 7

# body[6]: step/probe flags
HEADER_PROBE_BIT = BIT_1
HEADER_TURNTABLE_BIT = BIT_3
# body[32]: lock / door / water / preheat / error flags
FLAG32_LOCK_BIT = BIT_0
FLAG32_DOOR_OPEN_BIT = BIT_1
FLAG32_LACK_BOX_BIT = BIT_2
FLAG32_LACK_WATER_BIT = BIT_3
FLAG32_CHANGE_WATER_BIT = BIT_4
FLAG32_PREHEAT_BIT = BIT_5
FLAG32_PREHEAT_END_BIT = BIT_6
FLAG32_ERROR_CODE_BIT = BIT_7
# body[33]: side / light / high-temperature / probe-mode flags
FLAG33_FLIP_SIDE_BIT = BIT_0
FLAG33_REACTION_BIT = BIT_1
FLAG33_FURNACE_LIGHT_BIT = BIT_2
FLAG33_HIGH_TEMP_LOCK_BIT = BIT_3
FLAG33_HIGH_TEMP_WORK_BIT = BIT_4
FLAG33_HIGH_TEMP_BIT = BIT_5
FLAG33_PROBE_MODE_BIT = BIT_6
# body[34] / body[35]: single flags high in the byte
FLAG34_RAMADAN_BIT = BIT_5
FLAG35_HOT_WIND_BIT = BIT_5
# body[56] / body[58]: maintenance flags in the tail
FLAG56_CLEAN_SCALE_BIT = BIT_6
FLAG56_OTA_BIT = BIT_7
FLAG58_CLEAN_SINK_PONDING_BIT = BIT_0
FLAG58_DISSIPATE_HEAT_BIT = BIT_1

# --- Cooking command bit flags (body byte 5) --------------------------------
COOK_FLAG_PREHEAT = 0x01
COOK_FLAG_PROBE = 0x02
COOK_FLAG_TURNTABLE = 0x08
COOK_FLAG_HOT_WIND = 0x10

# --- Single-step cooking framing --------------------------------------------
SINGLE_STEP_FLAG = 0x11  # body[4] value for a single-step recipe
STEP_BLOCK_LEN = 16  # bytes per cooking step
STEP_BASE = 5  # first step block starts at body[5]
WEIGHT_SCALE = 10  # weight is reported/expected in multiples of 10 g

# --- Response body length guards --------------------------------------------
STATUS_MIN_LEN = 36  # last fixed-offset status byte read is body[35]
SYSTIME_MIN_LEN = 10  # system-time body reads body[1] through body[9]

VALUE_ON = "on"
VALUE_OFF = "off"
VALUE_FF = "ff"
VALUE_CLOSE = "close"
VALUE_OPEN = "open"

# --- Parameter-adjust TLV type bytes ----------------------------------------
PARAM_STEAM = 0x00
PARAM_TIME = 0x01
PARAM_FIRE_POWER = 0x02
PARAM_TEMP = 0x03
PARAM_PROBE_TEMP = 0x04
PARAM_SPLIT_TEMP = 0x05  # temp_above (selector 0x00) / temp_underside (0x01)
PARAM_SPLIT_ABOVE = 0x00
PARAM_SPLIT_UNDERSIDE = 0x01

# --- Enumerated fields ------------------------------------------------------
EXECUTE_MAP: dict[int, str] = {
    0x01: "status_nonsupport",
    0x02: "function_nonsupport",
    0x03: "param_range_error",
}

FIRE_POWER_MAP: dict[int, str] = {
    0x0A: "high_power",
    0x08: "medium_high_power",
    0x05: "medium_power",
    0x03: "medium_low_power",
    0x01: "low_power",
}
FIRE_POWER_REVERSE: dict[str, int] = {v: k for k, v in FIRE_POWER_MAP.items()}

WORK_STATUS_MAP: dict[int, str] = {
    0x01: "save_power",
    0x02: "standby",
    0x03: "work",
    0x04: "work_finish",
    0x05: "order",
    0x06: "pause",
    0x07: "pause_c",
    0x08: "three",
    0x0A: "self_inspection",
    0x0B: "query_version",
    0x0C: "demo",
    0x0D: "ramadan",  # V1 only; harmless on V2 (byte never carries it)
    0x0E: "after_checking",
    0x10: "wait_to_start",
}
WORK_STATUS_WRITE: dict[str, int] = {
    "save_power": 0x01,
    "standby": 0x02,
    "work": 0x03,
    "pause": 0x06,
}

POWER_WRITE: dict[str, int] = {VALUE_ON: 0x11, VALUE_OFF: 0x01}

WORKEND_WRITE: dict[str, int] = {
    "auto_next": 0x00,
    "wait_next": 0x01,
    "user_confirm_next": 0x02,
}

SYS_TIME_SRC_MAP: dict[int, str] = {
    0x00: "module",
    0x01: "app",
    0x02: "user_defined",
}
SYS_TIME_SRC_WRITE: dict[str, int] = {v: k for k, v in SYS_TIME_SRC_MAP.items()}

WORK_MODE_MAP: dict[int, str] = {
    0x0100: "microwave",
    0x0101: "microwave_1",
    0x0102: "microwave_2",
    0x0103: "microwave_3",
    0x0104: "microwave_4",
    0x0105: "microwave_5",
    0x0200: "microwave_steam_above_tube",
    0x0300: "microwave_double_tube",
    0x0400: "microwave_hot_wind_tube_fan",
    0x0500: "microwave_underside_tube_hot_wind_tube_fan",
    0x0600: "microwave_double_tube_hot_wind_tube_fan",
    0x0700: "microwave_steam",
    0x0701: "microwave_steam_1",
    0x0900: "unfreeze",
    0x0901: "unfreeze_1",
    0x0902: "unfreeze_2",
    0x0903: "unfreeze_3",
    0x0A00: "unfreeze_t",
    0x0B00: "microwave_above_tube",
    0x0B01: "microwave_above_tube_1",
    0x0B02: "microwave_above_tube_2",
    0x0C00: "microwave_above_tube_fan",
    0x0D00: "fast_unfreeze",
    0x0E00: "fresh_unfreeze",
    0x0F00: "microwave_zymosis",
    0x2900: "pure_steam",
    0x2901: "pure_steam_1",
    0x2902: "pure_steam_2",
    0x2903: "pure_steam_3",
    0x2904: "pure_steam_4",
    0x2905: "pure_steam_5",
    0x2906: "pure_steam_6",
    0x2907: "pure_steam_7",
    0x2908: "pure_steam_8",
    0x2B00: "steam_above_tube",
    0x2C00: "steam_underside_tube",
    0x2D00: "steam_double_tube",
    0x2E00: "steam_hot_wind_tube_fan",
    0x2E01: "steam_hot_wind_tube_fan_1",
    0x2E02: "steam_hot_wind_tube_fan_2",
    0x2F00: "steam_hot_wind_tube",
    0x3000: "steam_double_tube_fan",
    0x3100: "steam_above_inside_outside_tube_fan",
    0x3200: "steam_above_inside_tube_fan",
    0x5100: "above_tube",
    0x5101: "above_tube_1",
    0x5102: "above_tube_2",
    0x5103: "above_tube_3",
    0x5200: "underside_tube",
    0x5201: "underside_tube_1",
    0x5202: "underside_tube_2",
    0x5300: "double_tube",
    0x5301: "double_tube_1",
    0x5302: "double_tube_2",
    0x5303: "double_tube_3",
    0x5304: "double_tube_4",
    0x5305: "double_tube_5",
    0x5400: "hot_wind_tube_fan",
    0x5401: "hot_wind_tube_fan_1",
    0x5402: "hot_wind_tube_fan_2",
    0x5403: "hot_wind_tube_fan_3",
    0x5404: "hot_wind_tube_fan_4",
    0x5405: "hot_wind_tube_fan_5",
    0x5500: "pure_preheat",
    0x5502: "pure_preheat_2",
    0x5600: "above_tube_hot_wind_tube_fan",
    0x5700: "underside_tube_hot_wind_tube_fan",
    0x5800: "zymosis",
    0x5900: "double_tube_hot_wind_tube_fan",
    0x5901: "double_tube_hot_wind_tube_fan_1",
    0x5902: "double_tube_hot_wind_tube_fan_2",
    0x5903: "double_tube_hot_wind_tube_fan_3",
    0x5904: "double_tube_hot_wind_tube_fan_4",
    0x5905: "double_tube_hot_wind_tube_fan_5",
    0x5A00: "above_tube_revolve",
    0x5B00: "underside_tube_revolve",
    0x5C00: "double_tube_revolve",
    0x5D00: "hot_wind_tube_fan_revolve",
    0x5E00: "warm",
    0x5F00: "double_tube_fan",
    0x6000: "above_inside_tube_revolve",
    0x6100: "above_inside_tube_fan",
    0x6200: "above_inside_outside_tube_revolve",
    0x6300: "above_inside_outside_tube_fan",
    0x6400: "above_inside_underside_tube",
    0x6401: "above_inside_underside_tube_1",
    0x6500: "above_inside_underside_tube_fan",
    0x6501: "above_inside_underside_tube_fan_1",
    0x6600: "above_inside_tube",
    0x6700: "above_inside_outside_tube",
    0x6800: "underside_tube_fan",
    0x6900: "above_tube_fan",
    0x7900: "scale_clean",
    0x7A00: "clean",
    0x7B00: "remove_odor",
    0x7B02: "remove_odor_2",
    0x7C00: "high_temperature_clean",
    0x7D00: "dining_utensils_clean",
    0xA100: "auto_menu",
    0xA200: "eco",
}
WORK_MODE_REVERSE: dict[str, int] = {v: k for k, v in WORK_MODE_MAP.items()}

# Every attribute the status/system-time decoders can emit. The device class
# builds its ``DeviceAttributes`` enum from this so the two never drift.
ALL_ATTRIBUTES: tuple[str, ...] = (
    # whole-appliance status
    "execute",
    "cloudmenuid",
    "totalstep",
    "stepnum",
    "probe",
    "turntable",
    "work_mode",
    "hour_set",
    "minute_set",
    "second_set",
    "fire_power",
    "temperature",
    "temperature_above",
    "temperature_underside",
    "probe_temperature",
    "steam_quantity",
    "weight",
    "people_number",
    "work_hour",
    "work_minute",
    "work_second",
    "cur_temperature",
    "cur_temperature_above",
    "cur_temperature_underside",
    "cur_probe_temperature",
    "work_status",
    "door_open",
    "lock",
    "water_status",
    "lack_box",
    "lack_water",
    "change_water",
    "pre_heat",
    "flip_side",
    "error_code",
    "reaction",
    "furnace_light",
    "high_temperature_lock",
    "high_temperature_work",
    "high_temperature",
    "probe_mode",
    "ramadan",
    "hot_wind",
    "cbs_version",
    "clean_scale",
    "ota",
    "clean_sink_ponding",
    "dissipate_heat",
    # Write-only controls (not reported by the device, exposed for callers such
    # as Home Assistant that address every control through ``set_attribute``).
    "power",
    "door",
    "camera",
    "screen_luminance",
    "volume",
    # system time
    "sys_time_src",
    "sys_second",
    "sys_minute",
    "sys_hour",
    "sys_week",
    "sys_day",
    "sys_month",
    "sys_year",
    "sys_timezone",
)

# Attributes that accept a single-value control command, and the type each
# expects. Used by the device layer to route ``set_attribute`` calls.
STATE_STR_ATTRIBUTES = ("lock", "furnace_light", "camera", "hot_wind")
STATE_INT_ATTRIBUTES = ("screen_luminance", "volume")
# Numeric parameters encoded as a two-byte big-endian field (0..65535).
PARAM_U16_ATTRIBUTES = (
    "temperature",
    "probe_temperature",
    "temperature_above",
    "temperature_underside",
)
# Numeric parameters encoded as a single byte (0..255).
PARAM_BYTE_ATTRIBUTES = (
    "steam_quantity",
    "hour_set",
    "minute_set",
    "second_set",
)
PARAM_INT_ATTRIBUTES = PARAM_U16_ATTRIBUTES + PARAM_BYTE_ATTRIBUTES


def _u16be(high: int, low: int) -> int:
    """Combine two bytes into a big-endian unsigned 16-bit integer."""
    return high * BYTE_BASE + low


def _split_u16(value: int) -> tuple[int, int]:
    """Split an unsigned integer into big-endian (high, low) bytes."""
    return (value // BYTE_BASE) & BYTE_MASK, value & BYTE_MASK


def _bit(byte: int, position: int) -> int:
    """Return the single bit at ``position`` (0 = least significant) of ``byte``."""
    return (byte >> position) & 1


class MessageX9BBase(MessageRequest):
    """X9B message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize X9B message base."""
        super().__init__(
            device_type=DeviceType.X9B,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError

    @property
    def body(self) -> bytearray:
        """Return the raw body.

        The 0x9B protocol carries its sub-command in the first body byte
        itself, so the generic ``body_type`` prefix is not prepended here.
        """
        return self._body


class MessageQuery(MessageX9BBase):
    """X9B status query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B status query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X01,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([SUBCMD_STATUS])


class MessageQuerySystemTime(MessageX9BBase):
    """X9B system-time query (V2 only)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B system-time query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X04,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([SUBCMD_SYSTIME])


class MessageSetState(MessageX9BBase):
    """X9B non-cooking state control (power, lock, light, door, ...)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B state control."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        self.power: bool | None = None
        self.work_status: str | None = None
        self.lock: bool | None = None
        self.furnace_light: bool | None = None
        self.camera: bool | None = None
        self.door: str | None = None
        self.screen_luminance: int | None = None
        self.volume: int | None = None
        self.hot_wind: bool | None = None

    def _status_byte(self) -> int:
        if self.work_status is not None:
            return WORK_STATUS_WRITE.get(self.work_status, UNCHANGED)
        if self.power is not None:
            return POWER_WRITE[VALUE_ON] if self.power else POWER_WRITE[VALUE_OFF]
        return UNCHANGED

    @staticmethod
    def _on_off_byte(value: bool | None) -> int:
        if value is None:
            return UNCHANGED
        return 0x01 if value else 0x00

    def _door_byte(self) -> int:
        if self.door == VALUE_CLOSE:
            return 0x00
        if self.door == VALUE_OPEN:
            return 0x01
        return UNCHANGED

    @property
    def _body(self) -> bytearray:
        return bytearray(
            [
                SUBCMD_STATE,
                self._status_byte(),
                self._on_off_byte(self.lock),
                self._on_off_byte(self.furnace_light),
                self._on_off_byte(self.camera),
                self._door_byte(),
                UNCHANGED,
                UNCHANGED,
                UNCHANGED if self.screen_luminance is None else self.screen_luminance,
                UNCHANGED if self.volume is None else self.volume,
                UNCHANGED,
                UNCHANGED,
                self._on_off_byte(self.hot_wind),
            ],
        )


class MessageSetParam(MessageX9BBase):
    """X9B live parameter adjustment (TLV list)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B parameter adjustment."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        self.steam_quantity: int | None = None
        self.hour_set: int | None = None
        self.minute_set: int | None = None
        self.second_set: int | None = None
        self.fire_power: str | None = None
        self.temperature: int | None = None
        self.probe_temperature: int | None = None
        self.temperature_above: int | None = None
        self.temperature_underside: int | None = None

    def _params(self) -> list[list[int]]:
        params: list[list[int]] = []
        if self.steam_quantity is not None:
            params.append([PARAM_STEAM, self.steam_quantity])
        if (
            self.hour_set is not None
            or self.minute_set is not None
            or self.second_set is not None
        ):
            # Encode each omitted field with the protocol's "leave unchanged"
            # sentinel so writing one field (e.g. minute_set) does not reset the
            # others to zero on the device.
            params.append(
                [
                    PARAM_TIME,
                    UNCHANGED if self.hour_set is None else self.hour_set,
                    UNCHANGED if self.minute_set is None else self.minute_set,
                    UNCHANGED if self.second_set is None else self.second_set,
                ],
            )
        if self.fire_power is not None:
            params.append(
                [
                    PARAM_FIRE_POWER,
                    FIRE_POWER_REVERSE.get(self.fire_power, UNCHANGED),
                ],
            )
        if self.temperature is not None:
            params.append([PARAM_TEMP, 0x00, *_split_u16(self.temperature)])
        if self.probe_temperature is not None:
            params.append(
                [PARAM_PROBE_TEMP, 0x00, *_split_u16(self.probe_temperature)],
            )
        if self.temperature_above is not None:
            params.append(
                [
                    PARAM_SPLIT_TEMP,
                    0x00,
                    0x00,
                    PARAM_SPLIT_ABOVE,
                    *_split_u16(self.temperature_above),
                ],
            )
        if self.temperature_underside is not None:
            params.append(
                [
                    PARAM_SPLIT_TEMP,
                    0x00,
                    0x00,
                    PARAM_SPLIT_UNDERSIDE,
                    *_split_u16(self.temperature_underside),
                ],
            )
        return params

    @property
    def _body(self) -> bytearray:
        params = self._params()
        body = bytearray([SUBCMD_PARAM, 0x01, len(params)])
        for param in params:
            body.extend(param)
        return body


class CookingStep:
    """One cooking step in a (possibly multi-step) recipe."""

    def __init__(self) -> None:
        """Initialize a cooking step with all fields unset."""
        self.pre_heat: bool = False
        self.turntable: bool = False
        self.hot_wind: bool = False
        self.work_mode: str | None = None
        self.work_hour: int | None = None
        self.work_minute: int | None = None
        self.work_second: int | None = None
        self.fire_power: str | None = None
        self.temperature: int | None = None
        self.temperature_above: int | None = None
        self.temperature_underside: int | None = None
        self.probe_temperature: int | None = None
        self.steam_quantity: int | None = None
        self.weight: int | None = None
        self.people_number: int | None = None
        self.workend: str | None = None

    def encode(self) -> bytearray:
        """Encode this step to its 16-byte block (excluding the flag byte)."""
        flags = 0
        if self.pre_heat:
            flags |= COOK_FLAG_PREHEAT
        if self.turntable:
            flags |= COOK_FLAG_TURNTABLE
        if self.hot_wind:
            flags |= COOK_FLAG_HOT_WIND
        mode = WORK_MODE_REVERSE.get(self.work_mode or "", 0xFFFF)
        mode_high, mode_low = _split_u16(mode)
        fire_power = (
            FIRE_POWER_REVERSE.get(self.fire_power, UNCHANGED)
            if self.fire_power is not None
            else UNCHANGED
        )
        # Temperature: an overall value fills both above/underside pairs; the
        # split values then override their respective halves.
        above = self.temperature
        underside = self.temperature
        if self.temperature_above is not None:
            above = self.temperature_above
        if self.temperature_underside is not None:
            underside = self.temperature_underside
        above_high, above_low = _split_u16(above or 0)
        underside_high, underside_low = _split_u16(underside or 0)
        if self.probe_temperature is not None:
            flags |= COOK_FLAG_PROBE
            probe_high, probe_low = _split_u16(self.probe_temperature)
        else:
            probe_high, probe_low = 0x00, 0x00
        if self.weight is not None:
            portion = self.weight // WEIGHT_SCALE
        elif self.people_number is not None:
            portion = self.people_number
        else:
            portion = UNCHANGED
        workend = (
            WORKEND_WRITE.get(self.workend, 0x00)
            if self.workend is not None
            else UNCHANGED
        )
        return bytearray(
            [
                flags,
                mode_high,
                mode_low,
                self.work_hour or 0,
                self.work_minute or 0,
                self.work_second or 0,
                fire_power,
                above_high,
                above_low,
                underside_high,
                underside_low,
                probe_high,
                probe_low,
                UNCHANGED if self.steam_quantity is None else self.steam_quantity,
                portion,
                workend,
            ],
        )


class MessageSetCooking(MessageX9BBase):
    """X9B start-cooking control (single or multi-step)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B cooking control."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        self.cloudmenuid: int = 0
        self.stepnum_start: int = 1
        self.steps: list[CookingStep] = []

    @property
    def _body(self) -> bytearray:
        menu_high = (self.cloudmenuid // (BYTE_BASE * BYTE_BASE)) & BYTE_MASK
        menu_mid = (self.cloudmenuid // BYTE_BASE) & BYTE_MASK
        menu_low = self.cloudmenuid & BYTE_MASK
        total = len(self.steps)
        body = bytearray([SUBCMD_COOKING, menu_high, menu_mid, menu_low])
        if total <= 1:
            body.append(SINGLE_STEP_FLAG)
            step = self.steps[0] if self.steps else CookingStep()
            body.extend(step.encode())
            body.append(0x00)
        else:
            body.append(
                (total << NIBBLE_SHIFT) | (self.stepnum_start & NIBBLE_MASK),
            )
            for step in self.steps:
                body.extend(step.encode())
            body.append(0x00)
        return body


class MessageSetSystemTime(MessageX9BBase):
    """X9B set system time (V2 only)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X9B set system time."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X04,
        )
        self.sys_time_src: str | None = None
        self.sys_second: int | None = None
        self.sys_minute: int | None = None
        self.sys_hour: int | None = None
        self.sys_week: int | None = None
        self.sys_day: int | None = None
        self.sys_month: int | None = None
        self.sys_year: int | None = None
        self.sys_timezone: int | None = None

    @property
    def _body(self) -> bytearray:
        src = (
            SYS_TIME_SRC_WRITE.get(self.sys_time_src, UNCHANGED)
            if self.sys_time_src is not None
            else UNCHANGED
        )
        if (
            self.sys_second is not None
            or self.sys_minute is not None
            or self.sys_hour is not None
        ):
            second = self.sys_second or 0
            minute = self.sys_minute or 0
            hour = self.sys_hour or 0
        else:
            second = minute = hour = UNCHANGED
        return bytearray(
            [
                SUBCMD_SYSTIME,
                src,
                second,
                minute,
                hour,
                UNCHANGED if self.sys_week is None else self.sys_week,
                UNCHANGED if self.sys_day is None else self.sys_day,
                UNCHANGED if self.sys_month is None else self.sys_month,
                UNCHANGED if self.sys_year is None else self.sys_year,
                UNCHANGED if self.sys_timezone is None else self.sys_timezone,
            ],
        )


class X9BStatusBody:
    """Decode a 0x9B full-status body into an attribute dict."""

    def __init__(self, body: bytearray) -> None:
        """Decode the status body."""
        self.attributes: dict[str, int | str] = {}
        self._body = body
        self._decode()

    def _get(self, index: int) -> int | None:
        """Return ``body[index]`` or ``None`` when out of range."""
        if 0 <= index < len(self._body):
            return self._body[index]
        return None

    def _decode(self) -> None:
        if len(self._body) < STATUS_MIN_LEN:
            return
        self._decode_header()
        self._decode_time_and_temp()
        self._decode_work_time()
        self._decode_current()
        self._decode_flags()
        self._decode_version()
        self._decode_tail()

    def _decode_header(self) -> None:
        attrs = self.attributes
        execute = self._body[1]
        attrs["execute"] = EXECUTE_MAP.get(execute, "ok")
        attrs["cloudmenuid"] = (
            self._body[2] * BYTE_BASE * BYTE_BASE
            + self._body[3] * BYTE_BASE
            + self._body[4]
        )
        attrs["totalstep"] = self._body[5] >> NIBBLE_SHIFT
        attrs["stepnum"] = self._body[5] & NIBBLE_MASK
        attrs["probe"] = _bit(self._body[6], HEADER_PROBE_BIT)
        attrs["turntable"] = bool(_bit(self._body[6], HEADER_TURNTABLE_BIT))
        attrs["work_mode"] = WORK_MODE_MAP.get(
            _u16be(self._body[7], self._body[8]),
            VALUE_FF,
        )

    def _decode_time_and_temp(self) -> None:
        attrs = self.attributes
        attrs["hour_set"] = self._byte_or_zero(9)
        attrs["minute_set"] = self._byte_or_zero(10)
        attrs["second_set"] = self._byte_or_zero(11)
        attrs["fire_power"] = FIRE_POWER_MAP.get(self._body[12], VALUE_FF)
        above = _u16be(self._body[13], self._body[14])
        underside = _u16be(self._body[15], self._body[16])
        attrs["temperature_above"] = above
        attrs["temperature_underside"] = underside
        attrs["temperature"] = above if above != 0 else underside
        attrs["probe_temperature"] = _u16be(self._body[17], self._body[18])
        attrs["steam_quantity"] = self._byte_or_ff(19)
        weight = self._get(20)
        if weight is None or weight == UNCHANGED:
            attrs["weight"] = VALUE_FF
            attrs["people_number"] = VALUE_FF
        else:
            attrs["weight"] = weight * WEIGHT_SCALE
            attrs["people_number"] = weight

    def _decode_work_time(self) -> None:
        attrs = self.attributes
        attrs["work_hour"] = self._byte_or_zero(22)
        attrs["work_minute"] = self._byte_or_zero(23)
        attrs["work_second"] = self._byte_or_zero(24)

    def _decode_current(self) -> None:
        attrs = self.attributes
        above = _u16be(self._body[25], self._body[26])
        underside = _u16be(self._body[27], self._body[28])
        attrs["cur_temperature_above"] = above
        attrs["cur_temperature_underside"] = underside
        attrs["cur_temperature"] = above if above != 0 else underside
        attrs["cur_probe_temperature"] = _u16be(self._body[29], self._body[30])
        status = WORK_STATUS_MAP.get(self._body[31], VALUE_FF)
        attrs["work_status"] = status
        # The device never reports a dedicated power byte, so infer the on/off
        # state the way the HA power switch expects it: anything other than the
        # power-saving idle (or an unknown byte) counts as powered on.
        attrs["power"] = status not in ("save_power", VALUE_FF)

    def _decode_flags(self) -> None:
        attrs = self.attributes
        byte32 = self._body[32]
        byte33 = self._body[33]
        attrs["lock"] = bool(_bit(byte32, FLAG32_LOCK_BIT))
        attrs["door_open"] = bool(_bit(byte32, FLAG32_DOOR_OPEN_BIT))
        lack_box = _bit(byte32, FLAG32_LACK_BOX_BIT)
        lack_water = _bit(byte32, FLAG32_LACK_WATER_BIT)
        change_water = _bit(byte32, FLAG32_CHANGE_WATER_BIT)
        attrs["lack_box"] = lack_box
        attrs["lack_water"] = lack_water
        attrs["change_water"] = change_water
        attrs["water_status"] = self._water_status(lack_box, lack_water, change_water)
        preheat = _bit(byte32, FLAG32_PREHEAT_BIT)
        preheat_end = _bit(byte32, FLAG32_PREHEAT_END_BIT)
        attrs["pre_heat"] = self._pre_heat(preheat, preheat_end)
        attrs["error_code"] = _bit(byte32, FLAG32_ERROR_CODE_BIT)
        attrs["flip_side"] = _bit(byte33, FLAG33_FLIP_SIDE_BIT)
        attrs["reaction"] = _bit(byte33, FLAG33_REACTION_BIT)
        attrs["furnace_light"] = bool(_bit(byte33, FLAG33_FURNACE_LIGHT_BIT))
        # The high-temperature lock reads inverted: bit set means "off".
        attrs["high_temperature_lock"] = not _bit(byte33, FLAG33_HIGH_TEMP_LOCK_BIT)
        attrs["high_temperature_work"] = _bit(byte33, FLAG33_HIGH_TEMP_WORK_BIT)
        attrs["high_temperature"] = _bit(byte33, FLAG33_HIGH_TEMP_BIT)
        attrs["probe_mode"] = _bit(byte33, FLAG33_PROBE_MODE_BIT)
        attrs["ramadan"] = _bit(self._body[34], FLAG34_RAMADAN_BIT)
        attrs["hot_wind"] = bool(_bit(self._body[35], FLAG35_HOT_WIND_BIT))

    def _decode_version(self) -> None:
        b47, b48, b49 = self._get(47), self._get(48), self._get(49)
        if b47 is not None and b48 is not None and b49 is not None:
            self.attributes["cbs_version"] = f"V{b47}.{b48}.{b49}"
        else:
            self.attributes["cbs_version"] = "V0.0.0"

    def _decode_tail(self) -> None:
        attrs = self.attributes
        attrs["clean_scale"] = 0
        attrs["ota"] = 0
        byte56 = self._get(56)
        if byte56 is not None:
            attrs["clean_scale"] = _bit(byte56, FLAG56_CLEAN_SCALE_BIT)
            attrs["ota"] = _bit(byte56, FLAG56_OTA_BIT)
        attrs["clean_sink_ponding"] = 0
        attrs["dissipate_heat"] = VALUE_OFF
        byte58 = self._get(58)
        if byte58 is not None:
            attrs["clean_sink_ponding"] = _bit(byte58, FLAG58_CLEAN_SINK_PONDING_BIT)
            attrs["dissipate_heat"] = (
                "work" if _bit(byte58, FLAG58_DISSIPATE_HEAT_BIT) else VALUE_OFF
            )

    @staticmethod
    def _water_status(lack_box: int, lack_water: int, change_water: int) -> str:
        if lack_box:
            return "lack_box"
        if lack_water:
            return "lack_water"
        if change_water:
            return "change_water"
        return "normal"

    @staticmethod
    def _pre_heat(preheat: int, preheat_end: int) -> str:
        if preheat_end:
            return "end"
        if preheat:
            return "work"
        return VALUE_OFF

    def _byte_or_zero(self, index: int) -> int:
        value = self._body[index]
        return 0 if value == UNCHANGED else value

    def _byte_or_ff(self, index: int) -> int | str:
        value = self._body[index]
        return VALUE_FF if value == UNCHANGED else value


class X9BSystemTimeBody:
    """Decode a 0x9B system-time body into an attribute dict."""

    _FIELDS = (
        "sys_second",
        "sys_minute",
        "sys_hour",
        "sys_week",
        "sys_day",
        "sys_month",
        "sys_year",
        "sys_timezone",
    )

    def __init__(self, body: bytearray) -> None:
        """Decode the system-time body."""
        self.attributes: dict[str, int | str] = {}
        if len(body) < SYSTIME_MIN_LEN:
            return
        self.attributes["sys_time_src"] = SYS_TIME_SRC_MAP.get(body[1], VALUE_FF)
        for offset, name in enumerate(self._FIELDS, start=2):
            value = body[offset]
            self.attributes[name] = VALUE_FF if value == UNCHANGED else value


class MessageX9BResponse(MessageResponse):
    """X9B message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize X9B message response."""
        super().__init__(bytearray(message))
        body = super().body
        self.attributes: dict[str, int | str] = {}
        sub_command = body[0]
        if self.message_type == MessageType.set:
            # A set-echo report carries the full status record.
            self.attributes = X9BStatusBody(body).attributes
        elif self.message_type in (MessageType.query, MessageType.notify1):
            if sub_command == SUBCMD_SYSTIME:
                self.attributes = X9BSystemTimeBody(body).attributes
            else:
                self.attributes = X9BStatusBody(body).attributes
        self.set_attr()

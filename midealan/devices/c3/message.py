"""Midea local C3 message."""

from enum import IntEnum

from midealocal.const import DeviceType
from midealocal.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

TEMP_NEG_VALUE = 127
ECO_FUNCTION_STATE_MASK = 0x01
ECO_TIMER_STATE_MASK = 0x02


def _parse_ascii_tail(body: bytearray, data_offset: int) -> str | None:
    """Extract the dash-padded, NUL-terminated ASCII tail identifier.

    The WiFi module serial / model identifier is appended to C3 telemetry
    frames as an ASCII block preceded by a run of dash ("-") padding bytes
    and terminated with NUL bytes. Layout observed on captured frames:
    bytes ~96..159 = dashes, ~160..191 = ASCII serial, then NUL. The exact
    offsets vary between firmware revisions so the block is located by
    scanning for the dash run rather than by fixed offset.
    """
    dash_idx = body.find(b"-" * 20, data_offset)
    if dash_idx == -1:
        return None
    tail = body[dash_idx:]
    start = 0
    while start < len(tail) and tail[start : start + 1] == b"-":
        start += 1
    end = start
    while end < len(tail) and tail[end] != 0:
        end += 1
    candidate = bytes(tail[start:end]).strip()
    if not candidate:
        return None
    try:
        decoded = candidate.decode("ascii")
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


class C3SilentLevel(IntEnum):
    """C3 Silent Level."""

    OFF = 0x0
    SILENT = 0x1
    SUPER_SILENT = 0x3


class C3DeviceMode(IntEnum):
    """C3 Device Mode."""

    COOL = 2
    HEAT = 3


class C3FanSpeed(IntEnum):
    """C3 outdoor unit fan speed levels.

    Values correspond to raw_byte * 10 (parser scales
    ``body[data_offset + 3]`` by 10 to expose these values).
    Exact naming for level 1..4 is not confirmed by any publicly
    available documentation for the Galmet Prima 06 GT model - kept
    generic until an authoritative source is available.
    """

    # OFF added after field verification against wired HMI:
    # compressor idle -> raw byte 0 (which fell back to LEVEL_2).
    OFF = 0
    LEVEL_1 = 10
    LEVEL_2 = 20
    LEVEL_3 = 30
    LEVEL_4 = 40


class C3UnitRunMode(IntEnum):
    """C3 unit actual running mode.

    Reported via Modbus register 101 / 199 (V4.7):
    ``0: off, 2: cooling, 3: heating, 5: DHW``.
    DHW=5 added per Modbus doc reg 199 (Heat pump operation mode).
    """

    OFF = 0
    COOL = 2
    HEAT = 3
    DHW = 5


# Error code lookup (source: official Modbus V4.7 documentation, table 1).
# Format: raw_value -> (display_code, human_description).
# NOTE: 4 codes (Hd, HE, L2, L8) have ambiguous descriptions in the source
# PDF due to two-column layout extraction - kept as "unknown" until an
# authoritative source is available.
C3_ERROR_CODE_TABLE: dict[int, tuple[str, str]] = {
    1: ("E0", "Water flow fault (E8 displayed 3 times)"),
    2: ("E1", "Outlet water temp. sensor for Zone 2 (Tw2) fault"),
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
    48: ("H9", "Speed difference > 15Hz between front and back clock"),
    49: ("HA", "Speed difference > 15Hz between real and setting speed"),
    50: ("Hb", "3 times PP protection and Tw_out < 7C"),
    52: ("Hd", "Unknown / description unclear in source document"),
    53: ("HE", "Unknown / description unclear in source document"),
    54: ("HF", "Inverter module board EEPROM fault"),
    55: ("HH", "H6 displayed 10 times in 2 hours"),
    57: ("HP", "Low pressure protection (Pe<0.6) occurred 3 times in 1 hour"),
    65: ("C7", "Transducer module temperature too high protection"),
    112: ("bH", "PED PCB fault"),
    116: ("F1", "Low DC generatrix voltage protection"),
    134: ("L0", "Module protection"),
    135: ("L1", "DC generatrix low voltage protection"),
    136: ("L2", "Unknown / description unclear in source document"),
    138: ("L4", "MCE fault"),
    139: ("L5", "Zero speed protection"),
    141: ("L7", "Phase sequence fault / phase loss (3-phase only)"),
    142: ("L8", "Unknown / description unclear in source document"),
    143: ("L9", "Unknown / description unclear in source document"),
}


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
        _code_info = C3_ERROR_CODE_TABLE.get(self.error_code)
        if self.error_code == 0:
            self.error_code_description = "No error"
        elif _code_info:
            self.error_code_description = f"{_code_info[0]}: {_code_info[1]}"
        else:
            self.error_code_description = f"Unknown code (raw={self.error_code})"
        self.tbh_control = body[data_offset + 23] & 0x80 > 0
        self.SysEnergyAnaEN = body[data_offset + 23] & 0x20 > 0
        self.HMIEnergyAnaSetEN = body[data_offset + 23] & 0x40 > 0
        # snake_case aliases so device attributes can be exposed under
        # canonical names via update_attributes_from_message()
        self.sys_energy_ana_en = self.SysEnergyAnaEN
        self.hmi_energy_ana_set_en = self.HMIEnergyAnaSetEN


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
        # total_energy_consumption
        # Verified against wired-unit spreadsheet (2026-08-16):
        # total_electricity=14599 kWh appears as u16 BE at raw offset 4
        # (data_offset=1 → +3), NOT the u40 shift. Same for total_thermal.
        # Bytes 1-2 stayed 0 across all captures; the 40-bit shift produced
        # spurious ~9e8 readings.
        self.total_energy_consumption = (
            (body[data_offset + 3] << 8) + body[data_offset + 4]
        )
        # total_produced_energy (thermal counter, kWh) - u16 BE at offset 8
        self.total_produced_energy = (
            (body[data_offset + 7] << 8) + body[data_offset + 8]
        )
        base_value = body[data_offset + 9]
        self.outdoor_temperature = float(
            (base_value - 256) if base_value > TEMP_NEG_VALUE else base_value,
        )  # outdoor_temperature is t4
        self.zone1_temp_set = float(body[data_offset + 10])
        self.zone2_temp_set = float(body[data_offset + 11])
        self.t5s = body[data_offset + 12]
        self.tas = body[data_offset + 13]
        # WiFi module serial / model identifier is appended after the main
        # payload; see _parse_ascii_tail for the layout.
        self.wifi_module_serial: str | None = _parse_ascii_tail(body, data_offset)


class C3SilenceBody(MessageBody):
    """C3 Silence message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 query silence message body."""
        super().__init__(body)
        self.silent_mode = body[data_offset] & 0x1 > 0
        # Normalize to lowercase so the reported value matches the options
        # published by MideaC3Device._silent_modes.
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
        self.eco_function_state = (
            len(body) > data_offset and body[data_offset] & ECO_FUNCTION_STATE_MASK > 0
        )
        self.eco_timer_state = (
            len(body) > data_offset and body[data_offset] & ECO_TIMER_STATE_MASK > 0
        )


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
        _umr_raw = body[data_offset + 1]
        try:
            self.unit_mode_run = C3UnitRunMode(_umr_raw).name.lower()
        except ValueError:
            self.unit_mode_run = _umr_raw
        # NOTE: correlation vs wired HMI (Aug-16 pump test) shows fan RPM is
        # located at body[data_offset + 2] * 10 (not +3). Kept +3 as legacy
        # attribute name for backward compat.
        _fs_raw = body[data_offset + 2] * 10
        try:
            self.fan_speed = C3FanSpeed(_fs_raw).name.lower()
        except ValueError:
            self.fan_speed = _fs_raw
        self.fg_capacity_need = body[data_offset + 5]
        # Compressor current in A (verified against wired HMI Aug-16, raw=A)
        self.compressor_current = body[data_offset + 4]
        self.temp_t3 = body[data_offset + 6]
        self.temp_t4 = body[data_offset + 7]
        self.temp_tp = body[data_offset + 8]
        self.temp_tw_in = body[data_offset + 9]
        self.temp_tw_out = body[data_offset + 10]
        # Sensor sentinel: raw byte 127 (0x7F) is the C3 firmware convention
        # for "sensor not connected / not available". Convert to None so HA
        # can render the entity as unavailable instead of showing 127 °C.
        _tsolar = body[data_offset + 11]
        self.temp_tsolar = None if _tsolar == 127 else _tsolar
        self.hydbox_subtype = body[data_offset + 12]
        self.fg_usb_info_connect = body[data_offset + 13]
        # self.usb_index_max  body[data_offset + 14]
        # ODU compressor current in A (raw b[17]). Verified against wired HMI
        # 2026-08-18: raw 0 while compressor idle, raw 3 when compressor runs.
        self.odu_comp_current = body[data_offset + 16]
        # ODU mains voltage - VERIFIED as uint8 (not u16BE).
        # Log analysis (2026-08-18, 229 X10 frames): body[data_offset+17] is
        # 0x00 in 229/229 frames (constant reserved/padding). body[data_offset+18]
        # holds the voltage in Volts (1V/count). It drops 3-4 V under compressor
        # load (238-240 V idle → 234-236 V running), which matches expected
        # mains sag on a ~3 kW draw. Reading as u16BE would multiply by 256 on
        # any future firmware that repurposes the hi byte, so we fix the width.
        self.odu_voltage = body[data_offset + 18]
        # NOTE: body[data_offset + 17] (frame offset 18) is consistently 0 in
        # 229 X10 frames analyzed - kept as unread hi-byte guard for
        # odu_voltage. If a future firmware sets it non-zero, revisit the
        # u8 vs u16BE decision.
        self.exv_current = body[data_offset + 19] * 256 + body[data_offset + 20]
        # canonical name matching Modbus documentation (EXV valve opening)
        self.exv_opening = self.exv_current
        self.odu_model = body[data_offset + 21]
        # self.unit_online_num  body[data_offset + 22]
        # self.current_code  body[data_offset + 23]
        self.temp_t1 = body[data_offset + 33]
        self.temp_tw2 = body[data_offset + 34]
        self.temp_t2 = body[data_offset + 35]
        self.temp_t2b = body[data_offset + 36]
        self.temp_t5 = body[data_offset + 37]
        self.temp_ta = body[data_offset + 38]
        # Buffer tank sensors: 127 = "sensor not connected" (verified against
        # user's installation with no buffer-tank probes wired).
        _tbt1 = body[data_offset + 39]
        _tbt2 = body[data_offset + 40]
        self.temp_tb_t1 = None if _tbt1 == 127 else _tbt1
        self.temp_tb_t2 = None if _tbt2 == 127 else _tbt2
        self.hydrobox_capacity = body[data_offset + 41]
        self.pressure_high = body[data_offset + 42] * 256 + body[data_offset + 43]
        self.pressure_low = body[data_offset + 44] * 256 + body[data_offset + 45]
        self.temp_th = body[data_offset + 46]
        # LOAD_OUTPUT bitmap at body[data_offset + 32] (data[33] in raw frame).
        # Bit-mapping - AUTHORITATIVE source: Midea Modbus doc V4.7, reg 129
        # (Load output, 16-bit). Cross-checked against wired HMI Aug-16 pump test.
        #
        # Low byte (raw b[33], parser body[data_offset+32]):
        #   BIT0 = Electric heater IBH1
        #   BIT1 = Electric heater IBH2
        #   BIT2 = Electric heater TBH
        #   BIT3 = Internal circulation pump (Pump_i)
        #   BIT4 = SV1
        #   BIT5 = SV2
        #   BIT6 = External circulation pump (Pump_o)
        #   BIT7 = Domestic hot water circulation pump (Pump_d)
        # High byte (raw b[32], parser body[data_offset+31]):
        #   BIT8  = Mixed water loop pump Pump_c (Zone 2)
        #   BIT9..BIT15 = RESERVED per Modbus doc
        #
        # Previously this parser exposed sv3/crankcase_heater/pump_s/alarm/
        # aux_heat on hi-byte bits 1..6 - those bit positions belong to
        # reg 128 (Status bit 1) and possibly reside in a different LAN
        # offset. They are NOT part of reg 129 and have been removed.
        # Scenario logs (defrost / alarm / DHW anti-freeze) required to
        # locate reg 128 in the LAN payload before re-adding them.
        _load = body[data_offset + 32]
        _load_hi = body[data_offset + 31]
        # NOTE: load_output_raw / load_output_raw_hi / load_output_reg129
        # entities REMOVED (2026-08-19):
        #   - low byte (_load) is already fully decoded into individual
        #     binary_sensors below (ibh1_on, ibh2_on, load_output_tbh,
        #     pump_i_running, sv1_open, sv2_open, pump_o_running,
        #     pump_d_running) - the raw byte was redundant.
        #   - hi byte (_load_hi) does NOT belong to reg 129 (bits 9-15
        #     are RESERVED per Modbus doc V4.7). Log analysis of 229 X10
        #     frames shows _load_hi has only two values (0/32); bit 5
        #     tracks compressor state with 100% correlation to
        #     comp_run_freq>0 → it is the reg 128 "Compressor status"
        #     flag placed adjacent to reg 129 in the LAN payload.
        #     We do NOT expose it as a separate entity because
        #     compressor_on (derived from comp_run_freq>0) already carries
        #     the same information from the authoritative source
        #     (Modbus reg 100 Operating frequency).
        #   - reg129 (16-bit combined) was a mathematical fiction:
        #     combining bytes from two different registers produced
        #     values with no physical meaning.
        # --- reg 129 low byte (defined bits 0..7) ---
        self.ibh1_on             = bool(_load & 0x01)
        self.ibh2_on             = bool(_load & 0x02)
        self.load_output_tbh     = bool(_load & 0x04)
        self.pump_i_running      = bool(_load & 0x08)
        self.sv1_open            = bool(_load & 0x10)
        self.sv2_open            = bool(_load & 0x20)
        self.pump_o_running      = bool(_load & 0x40)
        self.pump_d_running      = bool(_load & 0x80)
        # --- reg 129 high byte (only BIT8 defined) ---
        self.pump_c_running      = bool(_load_hi & 0x01)  # BIT8 Pump_c (Zone 2)
        # Legacy hi-byte attributes retained for HA entity compatibility
        # (DEPLOY___init__.py / midea_devices.py / en.json still reference
        # them). They belong to reg 128 (Status bit 1) - bit positions
        # differ between reg 128 and reg 129 hi-byte, so exposing them
        # against reg 129 hi-byte would be wrong. Set to False until
        # scenario logs pin the correct LAN offset for reg 128.
        self.sv3_open            = False  # reg 128 BIT0 - LAN offset unknown
        self.crankcase_heater_on = False  # reg 128 BIT1 - LAN offset unknown
        self.pump_s_running      = False  # reg 128 BIT2 - LAN offset unknown
        self.alarm_on            = False  # reg 128 BIT3 - LAN offset unknown
        self.aux_heat_on         = False  # reg 128 BIT5 - LAN offset unknown
        # --- Diagnostic raw bytes: reg 128 (Status bit 1) LAN offset
        # candidates. Byte-variability analysis (2026-08-18 HA log, 229
        # X10 frames) flags these as bit-field-shaped (2-14 unique values,
        # low variability). Expose as raw uint8 for user-side correlation
        # against scenario events (defrost, alarm, DHW anti-freeze, etc.).
        # NOTE (2026-08-19 cleanup, pump-run log validation):
        #   raw_b19 removed - duplicated odu_voltage (same byte).
        #   raw_b20, raw_b21 removed - hi/lo bytes of exv_opening (reg 103).
        #   raw_b56 removed - low byte of water_flow (body[+54]<<8 | body[+55]).
        #   raw_b57 removed - duplicated odu_plan_vol_lmt (body[+56]).
        #   raw_b58 removed - high byte of instant_power (body[+57]<<8 | body[+58]).
        #   raw_b59 removed - low byte of instant_power.
        #   raw_b74 removed - low byte of total_thermal0 (body[+72]<<8 | body[+73]).
        #   raw_b83 removed - high byte of instant_power0 (body[+82]<<8 | body[+83]).
        #   raw_b85 removed - high byte of instant_renew_power0 (body[+84]<<8 | body[+85]).
        # raw_b31 is the only non-duplicate diagnostic byte and is kept for
        # further scenario correlation (idle=32, pump_i+flow=96 observed).
        self.raw_b31 = body[data_offset + 30]  # X10 offset 31, status bitmap candidate
        # raw_b31 decoded across 443 frames (2026-08-19 log): only bit5/bit6 vary,
        # all other bits constant 0. Observed values: 0/32/64/96.
        #   bit6 (0x40): Water circuit active. r=+0.99 vs pump_i, +0.99 vs flow>0,
        #                +0.98 vs sv1, +0.93 vs compressor. High confidence.
        #   bit5 (0x20): Unit demand candidate. Best correlation is r=+0.71 vs TBH,
        #                but no clean 1:1 mapping to any Modbus reg-128 bit - kept
        #                as a DIAGNOSTIC candidate until scenario logs confirm.
        self.water_circuit_active = bool(self.raw_b31 & 0x40)
        self.unit_demand = bool(self.raw_b31 & 0x20)
        # raw_b65: dynamic internal value of the water circuit / pump.
        # NOTE (off-by-one fix): the previous offset (data_offset + 64) read a
        # byte that is constantly 0 in every captured frame. The real dynamic
        # value lives one byte further, at data_offset + 65 (X10 offset 66).
        # Observed behaviour there: values ~46..99, sentinel 99 while idle,
        # dropping to ~51..58 during operation. Strong inverse correlation with
        # water_flow (r=-0.87) and with COP (r=-0.80). No clean Modbus register
        # match - behaves like a derived/scaled internal regulation value.
        # Kept as a HIDDEN raw diagnostic only; do NOT rename or promote until
        # scenario logs (defrost, DHW anti-freeze, alarm events) confirm its
        # meaning. Attribute name kept as raw_b65 for entity_id stability.
        self.raw_b65 = body[data_offset + 65]
        # Compressor running flag - Modbus reg 129 has NO compressor bit.
        # Reg 100 (Operating frequency) > 0 is the authoritative signal.
        # Verified against wired HMI (Aug-18): compressor idle when
        # comp_run_freq == 0, running when > 0.
        # Keep compressor_status_raw exposed as diagnostic for the reserved
        # hi-byte of reg 129 in case future firmware repurposes those bits.
        self.compressor_status_raw = _load_hi
        self.compressor_on = self.comp_run_freq > 0
        self.machine_type = body[data_offset + 47]
        self.odu_target_fre = body[data_offset + 48]
        # DC current in A. Correlation vs wired HMI (Aug-16 test):
        #   raw=3 -> 3 A ; raw=4 -> 4 A ; raw=5 -> 5 A. Unit is A (no scaling).
        self.dc_current = body[data_offset + 49]
        # DC-bus voltage in V. Correlation vs wired HMI: raw 33->330V, 37->370V.
        self.dc_bus_voltage = body[data_offset + 50] * 10
        self.temp_tf = body[data_offset + 51]
        # Zone 1/2 calculated water setpoint (T1s) from the weather-compensation
        # curve. Sentinel 0xFF (255) = "curve control inactive / no calculated
        # value" - verified against the 2026-08-19 log where idu_t1s1 = 255 in
        # 441/443 frames (real 27 °C in only 2) and idu_t1s2 = 255 in all 443.
        # Convert to None so HA renders the entity as unavailable instead of a
        # nonsensical 255 °C reading.
        _t1s1 = body[data_offset + 52]
        _t1s2 = body[data_offset + 53]
        self.idu_t1s1 = None if _t1s1 == 255 else _t1s1
        self.idu_t1s2 = None if _t1s2 == 255 else _t1s2
        # raw uint16 in 0.01 m3/h units -> divide by 100 for m3/h
        # (verified against wired HMI: raw 53 -> 0.53 m3/h)
        _wf_raw = body[data_offset + 54] * 256 + body[data_offset + 55]
        self.water_flow = _wf_raw / 100
        self.odu_plan_vol_lmt = body[data_offset + 56]
        # reg 148 "Real-time heating capacity" - THERMAL OUTPUT in kW (u16 BE
        # /100), i.e. heat delivered to the water, NOT electrical draw.
        # Modbus V4.7 reg 148 + energy-balance validation (2026-08-19 log):
        #   capacity(instant_power) = consumption(instant_power0)
        #                             + renewable(instant_renew_power0)
        # Earlier correlation vs wired HMI (Aug-16) showed 0-4.24 kW; that was
        # the thermal side, not consumption. The electrical draw is
        # instant_power0. See the power-triad block further down.
        self.instant_power = ((body[data_offset + 57] << 8) + body[data_offset + 58]) / 100
        # keep current_unit_capacity attribute (moved to a different offset if needed)
        # setting to None here as the previous mapping was incorrect.
        self.current_unit_capacity = None
        self.sphera_ahs_voltage = body[data_offset + 59]
        self.temp_t4a_ver = body[data_offset + 60]
        self.water_pressure = body[data_offset + 61] * 256 + body[data_offset + 62]
        self.room_rel_hum = body[data_offset + 63]
        # NOTE: pwm_pump_out removed - previous code shared offset 63 with
        # room_rel_hum which is clearly wrong. Actual offset unknown; entity
        # is unregistered until an authoritative source is available.
        # Verified against wired-unit spreadsheet (2026-08-16 09:57 snapshot):
        # total_electricity=14599 kWh at raw byte offset 69 → u16 BE at data_offset+68.
        # Values are 16-bit big-endian, unit = kWh. The previous 40-bit shift
        # produced spurious ~1.6e9 readings; correct decode is u16 BE.
        self.total_electricity0 = (
            (body[data_offset + 68] << 8) + body[data_offset + 69]
        )
        # total_thermal=10867 kWh at raw byte offset 73 → u16 BE at data_offset+72
        self.total_thermal0 = (
            (body[data_offset + 72] << 8) + body[data_offset + 73]
        )
        # heat_elec_total_consum=5834 kWh at raw byte offset 77 → data_offset+76
        self.heat_elec_total_consum0 = (
            (body[data_offset + 76] << 8) + body[data_offset + 77]
        )
        # heat_elec_total_capacity mirrors thermal (10867 kWh) at data_offset+80
        self.heat_elec_total_capacity0 = (
            (body[data_offset + 80] << 8) + body[data_offset + 81]
        )
        # --- Real-time power triad - SEMANTICS VERIFIED against Modbus V4.7 ---
        # Cross-referenced with the Modbus register map (120L doc) AND validated
        # against the 2026-08-19 log (443 X10 frames, full compressor cycle):
        #   reg 148 "Real-time heating capacity"        -> instant_power   (b57/58)
        #   reg 149 "Real-time renewable heating cap."  -> instant_renew_power0 (b84/85)
        #   reg 150 "Real-time heating power consumption"-> instant_power0  (b82/83)
        # Energy balance holds per-frame (median error 0.01 kW over 443 frames):
        #   capacity = consumption + renewable   =>   COP = capacity / consumption
        # IMPORTANT: instant_power is the THERMAL OUTPUT (heat delivered), NOT the
        # electrical draw. The electricity actually consumed is instant_power0.
        # Do NOT feed instant_power into the HA Energy dashboard as consumption.
        #
        # heating power consumption (electrical input) in kW (u16 BE /100)
        self.instant_power0 = ((body[data_offset + 82] << 8) + body[data_offset + 83]) / 100
        # renewable (ambient-harvested) heating capacity in kW (u16 BE /100)
        self.instant_renew_power0 = ((body[data_offset + 84] << 8) + body[data_offset + 85]) / 100
        # TODO: previous version aliased this to instant_renew_power0 bytes.
        # Best-effort correction: use the next uint16 at offset 86-87.
        # Confirm against wired HMI once a non-zero PV production sample exists.
        self.total_renew_power0 = ((body[data_offset + 86] << 8) + body[data_offset + 87]) / 100
        # Real-time heating COP (reg 151). CONFIRMED NOT transmitted in any LAN
        # frame (X10/X04): no byte/u16 offset matches capacity/consumption
        # per-frame across the 2026-08-19 log. We therefore DERIVE it from the
        # verified capacity/consumption triad:  COP = capacity / consumption.
        # Only meaningful while the unit is actually producing heat; guard
        # against divide-by-zero and idle noise (consumption ~0.01 kW off).
        if self.instant_power0 and self.instant_power0 > 0.05:
            self.instant_cop = round(self.instant_power / self.instant_power0, 2)
        else:
            self.instant_cop = None
        # ------------------------------------------------------------------
        # IDU / ODU software versions (Modbus reg 130 / reg 1042 mapped
        # into X10 telemetry frame). Verified against wired HMI:
        #   raw byte offset 94 = IDU sw version = 14  (HMI shows "V14")
        #   raw byte offset 95 = ODU sw version = 64  (HMI shows "V64")
        # HMI software version ("V56A" on wired display) is NOT present in
        # X10 / X04 / long-X05 payloads - the C3 telemetry frames only
        # expose IDU + ODU firmware. Left unimplemented until an
        # authoritative source is available.
        # Guard: leave version bytes unset when the frame is short.
        if len(body) > data_offset + 94:
            self.idu_software_version = body[data_offset + 93]
            self.odu_software_version = body[data_offset + 94]
        else:
            self.idu_software_version = None
            self.odu_software_version = None
        # ------------------------------------------------------------------
        # WiFi module serial: appended as ASCII after a run of "-" padding.
        # Verified: bytes 160..191 = "0000C3310171H120F24114100123MNJ2".
        self.wifi_module_serial: str | None = _parse_ascii_tail(body, data_offset)

        # ------------------------------------------------------------------
        # IDU / ODU software version strings.
        # Numeric byte values at b[93]/b[94] match the wired HMI display
        # ("V14" / "V64") one-to-one. The wired HMI also shows a build date
        # ("V14 24-11-41") but the encoding is NOT reliably present in the
        # X10 telemetry frames captured so far - the ASCII tail contains
        # H<xxx>F<xx><digits> factory identifiers whose meaning is not yet
        # documented. We therefore expose two safe strings and let the
        # printable tail through as a separate diagnostic:
        #   idu_software_version_str = "V<n>"  (matches HMI exactly)
        #   odu_software_version_str = "V<n>"
        #   build_info               = raw ASCII tail (for future decoding)
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
        # Expose the printable ASCII tail as a diagnostic. The tail follows
        # the shape "<serial>H<xxx>F<xx><digits>..." (observed sample:
        # "0000C3310171H120F24114100123MNJ2"). The H<xxx>/F<xx> groups do
        # NOT match the IDU/ODU version bytes at b[93]/b[94] (14 / 64 on
        # this unit) and the trailing digit block has not been decoded to
        # a build date on any captured frame - the previous best-effort
        # YYMMDD parse was speculative and never matched, so it has been
        # removed. Re-add once the F-tail encoding is documented (e.g.
        # from an authoritative Modbus mapping or additional captures).
        self.build_info = self.wifi_module_serial



class C3UnitParaExtBody(MessageBody):
    """C3 extended UnitPara/runtime notification body.

    Sent asynchronously by the device (notify1 + body_type X05, 239 B).
    Overlaps with X10 for most telemetry (temps, pressures, instant power,
    total electricity/thermal counters) - those fields are intentionally
    NOT re-exposed to avoid duplicate entities. Only fields unique to
    this frame are parsed here.

    Layout verified against wired HMI (Galmet Prima 06 GT, 2026-08-16 log):
    - offset 57-58 (u16 BE): compressor total run time in hours (2356 h)
    - other counters at 50, 55-56, 59-60 are candidates for future
      decoding (need more samples over time).
    """

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 UnitParaExt (long X05 notify) message body."""
        super().__init__(body)
        # Compressor total run time (hours). Verified against wired HMI.
        # data_offset=1 skips body_type; absolute frame offsets are 57-58,
        # so relative to data_offset we read + 56 and + 57.
        # Guard: leave the field unset if the frame is truncated.
        if len(body) > data_offset + 57:
            self.comp_total_run_time = (
                body[data_offset + 56] * 256 + body[data_offset + 57]
            )
        else:
            self.comp_total_run_time = None


class MessageC3Response(MessageResponse):
    """C3 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize C3 message response."""
        super().__init__(bytearray(message))
        if (
            self.message_type
            in [MessageType.set, MessageType.notify1, MessageType.query]
            and self.body_type == ListTypes.X01
        ) or self.message_type == MessageType.notify2:
            self.set_body(C3BasicBody(super().body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1 and self.body_type == ListTypes.X04
        ):
            self.set_body(C3EnergyBody(super().body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1
            and self.body_type == ListTypes.X05
        ):
            # Long (239 B) notify1 frame with extra runtime counters.
            self.set_body(C3UnitParaExtBody(super().body, data_offset=1))
        elif self.message_type == MessageType.query and self.body_type == ListTypes.X05:
            self.set_body(C3SilenceBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X07:
            self.set_body(C3ECOBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X09:
            self.set_body(C3DisinfectBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X10:
            self.set_body(C3UnitParaBody(super().body, data_offset=1))
        self.set_attr()

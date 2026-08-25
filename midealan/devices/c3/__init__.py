"""Midea local C3 device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealocal.const import DeviceType
from midealocal.device import MideaDevice, MideaDeviceInitKwargs

from .message import (
    C3DeviceMode,
    C3SilentLevel,
    C3UnitRunMode,
    MessageC3Response,
    MessageQuery,
    MessageQueryBasic,
    MessageQueryDisinfect,
    MessageQueryECO,
    MessageQuerySilence,
    MessageQueryUnitPara,
    MessageSet,
    MessageSetDisinfect,
    MessageSetECO,
    MessageSetSilent,
)

_LOGGER = logging.getLogger(__name__)


class DeviceAttributes(StrEnum):
    """Midea C3 device attributes."""

    zone1_power = "zone1_power"
    zone2_power = "zone2_power"
    dhw_power = "dhw_power"
    zone1_curve = "zone1_curve"
    zone2_curve = "zone2_curve"
    disinfect = "disinfect"
    fast_dhw = "fast_dhw"
    zone_temp_type = "zone_temp_type"
    mode = "mode"
    mode_auto = "mode_auto"
    zone_target_temp = "zone_target_temp"
    dhw_target_temp = "dhw_target_temp"
    room_target_temp = "room_target_temp"
    zone_heating_temp_max = "zone_heating_temp_max"
    zone_heating_temp_min = "zone_heating_temp_min"
    zone_cooling_temp_max = "zone_cooling_temp_max"
    zone_cooling_temp_min = "zone_cooling_temp_min"
    tank_actual_temperature = "tank_actual_temperature"
    room_temp_max = "room_temp_max"
    room_temp_min = "room_temp_min"
    dhw_temp_max = "dhw_temp_max"
    dhw_temp_min = "dhw_temp_min"
    status_heating = "status_heating"
    status_dhw = "status_dhw"
    status_tbh = "status_tbh"
    status_ibh = "status_ibh"
    total_energy_consumption = "total_energy_consumption"
    total_produced_energy = "total_produced_energy"
    outdoor_temperature = "outdoor_temperature"
    temp_tw_in = "temp_tw_in"
    temp_tw_out = "temp_tw_out"
    silent_mode = "silent_mode"
    silent_level = "silent_level"
    eco_mode = "eco_mode"
    zone1_room_temp_mode = "zone1_room_temp_mode"
    zone2_room_temp_mode = "zone2_room_temp_mode"
    zone1_water_temp_mode = "zone1_water_temp_mode"
    zone2_water_temp_mode = "zone2_water_temp_mode"
    target_temperature = "target_temperature"
    temperature_max = "temperature_max"
    temperature_min = "temperature_min"
    tbh = "tbh"
    error_code = "error_code"
    # --- Extended attributes exposing data already parsed by C3 message bodies ---
    error_code_description = "error_code_description"
    # Notify1 bit flags (device capability / runtime flags)
    heat = "heat"
    cool = "cool"
    dhw = "dhw"
    double_zone = "double_zone"
    room_thermal_support = "room_thermal_support"
    room_thermal_state = "room_thermal_state"
    time_set = "time_set"
    holiday_on = "holiday_on"
    remote_onoff = "remote_onoff"
    tbh_control = "tbh_control"
    sys_energy_ana_en = "sys_energy_ana_en"
    hmi_energy_ana_set_en = "hmi_energy_ana_set_en"
    # Energy / heat pump status
    status_cool = "status_cool"
    # ECO body
    eco_function_state = "eco_function_state"
    eco_timer_state = "eco_timer_state"
    # Disinfect body
    disinfect_run = "disinfect_run"
    # UnitPara body (unit runtime telemetry)
    comp_run_freq = "comp_run_freq"
    fan_speed = "fan_speed"
    unit_mode_run = "unit_mode_run"
    temp_t1 = "temp_t1"
    temp_t2 = "temp_t2"
    temp_t2b = "temp_t2b"
    temp_t3 = "temp_t3"
    temp_t4 = "temp_t4"
    temp_t5 = "temp_t5"
    temp_ta = "temp_ta"
    temp_tp = "temp_tp"
    temp_th = "temp_th"
    temp_tf = "temp_tf"
    temp_tw2 = "temp_tw2"
    temp_tb_t1 = "temp_tb_t1"
    temp_tb_t2 = "temp_tb_t2"
    temp_tsolar = "temp_tsolar"
    pressure_high = "pressure_high"
    pressure_low = "pressure_low"
    water_flow = "water_flow"
    water_pressure = "water_pressure"
    exv_opening = "exv_opening"
    odu_voltage = "odu_voltage"
    dc_current = "dc_current"
    # Aug-16 pump-test correlation additions
    dc_bus_voltage = "dc_bus_voltage"
    # --- Real-time power triad + derived COP (semantics verified vs Modbus V4.7,
    # regs 148/149/150/151, and per-frame energy balance on 2026-08-19 log) ---
    #   instant_power        = heating CAPACITY / thermal output (reg 148)
    #   instant_power0       = heating power CONSUMPTION / electrical draw (reg 150)
    #   instant_renew_power0 = renewable (ambient-harvested) capacity (reg 149)
    #   instant_cop          = derived capacity/consumption (reg 151 NOT sent on LAN)
    instant_power = "instant_power"
    instant_power0 = "instant_power0"
    instant_renew_power0 = "instant_renew_power0"
    instant_cop = "instant_cop"
    # LOAD_OUTPUT bitmap decoded flags (X10 byte[33]) - Aug-16 pump test.
    # Raw bytes (load_output_raw / _hi / reg129) removed 2026-08-19 -
    # individual bits are already exposed as binary_sensors below, and
    # the reg129 16-bit combination had no physical meaning.
    ibh1_on = "ibh1_on"
    ibh2_on = "ibh2_on"
    sv3_open = "sv3_open"
    crankcase_heater_on = "crankcase_heater_on"
    alarm_on = "alarm_on"
    aux_heat_on = "aux_heat_on"
    load_output_tbh = "load_output_tbh"
    pump_i_running = "pump_i_running"
    pump_o_running = "pump_o_running"
    pump_d_running = "pump_d_running"
    pump_c_running = "pump_c_running"
    pump_s_running = "pump_s_running"
    sv1_open = "sv1_open"
    sv2_open = "sv2_open"
    # Diagnostic raw uint8 exposures - LAN offset candidates for Modbus
    # reg 128 (Status bit 1) whose exact position is not yet known.
    # Users can correlate these against scenario events (defrost, alarm,
    # DHW anti-freeze, etc.) to pin down bit assignments.
    raw_b31 = "raw_b31"
    # Decoded flags from raw_b31 (bit6 = water circuit active, bit5 = demand
    # candidate) and the raw b65 diagnostic byte (unmapped derived value).
    water_circuit_active = "water_circuit_active"
    unit_demand = "unit_demand"
    raw_b65 = "raw_b65"
    # NOTE (2026-08-19 cleanup): raw_b56/57/58/59/74/83/85 removed - all were
    # low/high bytes of already-parsed u16 registers (water_flow, instant_power,
    # total_thermal0, instant_power0, instant_renew_power0) or duplicates
    # (odu_plan_vol_lmt). raw_b31 kept as the only non-duplicate diagnostic.
    # System-active flag (candidate for Modbus reg 128 BIT0 - compressor/
    # NOTE: system_active_reg128 removed 2026-08-19 - only 79% correlation
    # with compressor state; compressor_on (from comp_run_freq>0) is the
    # authoritative single-source-of-truth for compressor running state.
    room_rel_hum = "room_rel_hum"
    # Energy totals from UnitPara body
    # Compressor total run time (hours) - from long X05 notify1 frame
    comp_total_run_time = "comp_total_run_time"
    # WiFi module identifier (parsed from tail of energy frame)
    wifi_module_serial = "wifi_module_serial"
    # --- Additional low-level diagnostic attributes exposed 1:1 from parser ---
    hydbox_subtype = "hydbox_subtype"
    hydrobox_capacity = "hydrobox_capacity"
    # IDU / ODU firmware versions (from X10 telemetry, bytes 94/95).
    # Verified against wired HMI: IDU=V14, ODU=V64.
    # String form with build date parsed from the X10 ASCII tail
    # (e.g. "V14 24-11-41"). Falls back to plain "V<n>" when the date
    # cannot be located.
    idu_software_version_str = "idu_software_version_str"
    odu_software_version_str = "odu_software_version_str"
    # Compressor telemetry (Aug-18 verification).
    compressor_on = "compressor_on"
    compressor_status_raw = "compressor_status_raw"
    odu_comp_current = "odu_comp_current"
    # ASCII tail from X10 payload (factory identifier + build code)
    machine_type = "machine_type"
    odu_model = "odu_model"
    odu_target_fre = "odu_target_fre"
    fg_capacity_need = "fg_capacity_need"
    t5s = "t5s"
    tas = "tas"
    idu_t1s1 = "idu_t1s1"
    idu_t1s2 = "idu_t1s2"
    zone1_temp_set = "zone1_temp_set"
    zone2_temp_set = "zone2_temp_set"
    disinfect_set_weekday = "disinfect_set_weekday"
    disinfect_start_hour = "disinfect_start_hour"
    disinfect_start_minutes = "disinfect_start_minutes"


class MideaC3Device(MideaDevice):
    """Midea C3 device."""

    _silent_modes: ClassVar[list[str]] = [
        C3SilentLevel.OFF.name.lower(),
        C3SilentLevel.SILENT.name.lower(),
        C3SilentLevel.SUPER_SILENT.name.lower(),
    ]

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea C3 device."""
        super().__init__(
            device_type=DeviceType.C3,
            **kwargs,
            attributes={
                DeviceAttributes.zone1_power: False,
                DeviceAttributes.zone2_power: False,
                DeviceAttributes.dhw_power: False,
                DeviceAttributes.zone1_curve: False,
                DeviceAttributes.zone2_curve: False,
                DeviceAttributes.disinfect: False,
                DeviceAttributes.fast_dhw: False,
                DeviceAttributes.zone_temp_type: [False, False],
                DeviceAttributes.zone1_room_temp_mode: False,
                DeviceAttributes.zone2_room_temp_mode: False,
                DeviceAttributes.zone1_water_temp_mode: False,
                DeviceAttributes.zone2_water_temp_mode: False,
                DeviceAttributes.silent_mode: False,
                DeviceAttributes.silent_level: C3SilentLevel.OFF.name.lower(),
                DeviceAttributes.eco_mode: False,
                DeviceAttributes.tbh: False,
                DeviceAttributes.mode: 1,
                DeviceAttributes.mode_auto: 1,
                DeviceAttributes.zone_target_temp: [25.0, 25.0],
                DeviceAttributes.dhw_target_temp: 25.0,
                DeviceAttributes.room_target_temp: 30.0,
                DeviceAttributes.zone_heating_temp_max: [55.0, 55.0],
                DeviceAttributes.zone_heating_temp_min: [25.0, 25.0],
                DeviceAttributes.zone_cooling_temp_max: [25.0, 25.0],
                DeviceAttributes.zone_cooling_temp_min: [5.0, 5.0],
                DeviceAttributes.room_temp_max: 60.0,
                DeviceAttributes.room_temp_min: 34.0,
                DeviceAttributes.dhw_temp_max: 60.0,
                DeviceAttributes.dhw_temp_min: 20.0,
                DeviceAttributes.tank_actual_temperature: None,
                DeviceAttributes.target_temperature: [25.0, 25.0],
                DeviceAttributes.temperature_max: [0.0, 0.0],
                DeviceAttributes.temperature_min: [0.0, 0.0],
                DeviceAttributes.total_energy_consumption: None,
                DeviceAttributes.status_heating: None,
                DeviceAttributes.status_dhw: None,
                DeviceAttributes.status_tbh: None,
                DeviceAttributes.status_ibh: None,
                DeviceAttributes.total_produced_energy: None,
                DeviceAttributes.outdoor_temperature: None,
                DeviceAttributes.temp_tw_in: None,
                DeviceAttributes.temp_tw_out: None,
                DeviceAttributes.error_code: 0,
                DeviceAttributes.error_code_description: "No error",
                DeviceAttributes.heat: False,
                DeviceAttributes.cool: False,
                DeviceAttributes.dhw: False,
                DeviceAttributes.double_zone: False,
                DeviceAttributes.room_thermal_support: False,
                DeviceAttributes.room_thermal_state: False,
                DeviceAttributes.time_set: False,
                DeviceAttributes.holiday_on: False,
                DeviceAttributes.remote_onoff: False,
                DeviceAttributes.tbh_control: False,
                DeviceAttributes.sys_energy_ana_en: False,
                DeviceAttributes.hmi_energy_ana_set_en: False,
                DeviceAttributes.status_cool: None,
                DeviceAttributes.eco_function_state: False,
                DeviceAttributes.eco_timer_state: False,
                DeviceAttributes.disinfect_run: False,
                DeviceAttributes.comp_run_freq: None,
                DeviceAttributes.fan_speed: None,
                DeviceAttributes.unit_mode_run: C3UnitRunMode.OFF.name.lower(),
                DeviceAttributes.temp_t1: None,
                DeviceAttributes.temp_t2: None,
                DeviceAttributes.temp_t2b: None,
                DeviceAttributes.temp_t3: None,
                DeviceAttributes.temp_t4: None,
                DeviceAttributes.temp_t5: None,
                DeviceAttributes.temp_ta: None,
                DeviceAttributes.temp_tp: None,
                DeviceAttributes.temp_th: None,
                DeviceAttributes.temp_tf: None,
                DeviceAttributes.temp_tw2: None,
                DeviceAttributes.temp_tb_t1: None,
                DeviceAttributes.temp_tb_t2: None,
                DeviceAttributes.temp_tsolar: None,
                DeviceAttributes.pressure_high: None,
                DeviceAttributes.pressure_low: None,
                DeviceAttributes.water_flow: None,
                DeviceAttributes.water_pressure: None,
                DeviceAttributes.exv_opening: None,
                DeviceAttributes.odu_voltage: None,
                DeviceAttributes.dc_current: None,
                DeviceAttributes.dc_bus_voltage: None,
                DeviceAttributes.instant_power: None,
                DeviceAttributes.instant_power0: None,
                DeviceAttributes.instant_renew_power0: None,
                DeviceAttributes.instant_cop: None,
                DeviceAttributes.ibh1_on: None,
                DeviceAttributes.ibh2_on: None,
                DeviceAttributes.sv3_open: None,
                DeviceAttributes.crankcase_heater_on: None,
                DeviceAttributes.alarm_on: None,
                DeviceAttributes.aux_heat_on: None,
                DeviceAttributes.load_output_tbh: None,
                DeviceAttributes.pump_i_running: None,
                DeviceAttributes.pump_o_running: None,
                DeviceAttributes.pump_d_running: None,
                DeviceAttributes.pump_c_running: None,
                DeviceAttributes.pump_s_running: None,
                DeviceAttributes.sv1_open: None,
                DeviceAttributes.sv2_open: None,
                DeviceAttributes.raw_b31: None,
                DeviceAttributes.water_circuit_active: None,
                DeviceAttributes.unit_demand: None,
                DeviceAttributes.raw_b65: None,
                DeviceAttributes.room_rel_hum: None,
                DeviceAttributes.comp_total_run_time: None,
                DeviceAttributes.wifi_module_serial: None,
                DeviceAttributes.hydbox_subtype: None,
                DeviceAttributes.hydrobox_capacity: None,
                DeviceAttributes.idu_software_version_str: None,
                DeviceAttributes.odu_software_version_str: None,
                DeviceAttributes.compressor_on: None,
                DeviceAttributes.compressor_status_raw: None,
                DeviceAttributes.odu_comp_current: None,
                DeviceAttributes.machine_type: None,
                DeviceAttributes.odu_model: None,
                DeviceAttributes.odu_target_fre: None,
                DeviceAttributes.fg_capacity_need: None,
                DeviceAttributes.t5s: None,
                DeviceAttributes.tas: None,
                DeviceAttributes.idu_t1s1: None,
                DeviceAttributes.idu_t1s2: None,
                DeviceAttributes.zone1_temp_set: None,
                DeviceAttributes.zone2_temp_set: None,
                DeviceAttributes.disinfect_set_weekday: None,
                DeviceAttributes.disinfect_start_hour: None,
                DeviceAttributes.disinfect_start_minutes: None,
            },
        )
        self._default_temperature_step: float = 0.5
        self._temperature_step: float = 0.5
        self.set_customize(customize)

    @property
    def temperature_step(self) -> float | None:
        """Midea C3 device temperature step."""
        return self._temperature_step

    @property
    def silent_modes(self) -> list[str]:
        """Midea C3 device silent modes."""
        return MideaC3Device._silent_modes

    def build_query(self) -> list[MessageQuery]:
        """Midea C3 device build query."""
        return [
            MessageQueryBasic(self._message_protocol_version),
            MessageQueryDisinfect(self._message_protocol_version),
            MessageQuerySilence(self._message_protocol_version),
            MessageQueryECO(self._message_protocol_version),
            MessageQueryUnitPara(self._message_protocol_version),
        ]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea C3 device process message."""
        message = MessageC3Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                self._attributes[status] = getattr(message, str(status))
                new_status[str(status)] = getattr(message, str(status))
        if "zone_temp_type" in new_status:
            for zone in [0, 1]:
                if self._attributes[DeviceAttributes.zone_temp_type][
                    zone
                ]:  # Water temp mode
                    self._attributes[DeviceAttributes.target_temperature][zone] = (
                        self._attributes[DeviceAttributes.zone_target_temp][zone]
                    )
                    if (
                        self._attributes[DeviceAttributes.mode_auto]
                        == C3DeviceMode.COOL
                    ):  # cooling mode
                        self._attributes[DeviceAttributes.temperature_max][zone] = (
                            self._attributes[DeviceAttributes.zone_cooling_temp_max][
                                zone
                            ]
                        )
                        self._attributes[DeviceAttributes.temperature_min][zone] = (
                            self._attributes[DeviceAttributes.zone_cooling_temp_min][
                                zone
                            ]
                        )
                    elif (
                        self._attributes[DeviceAttributes.mode] == C3DeviceMode.HEAT
                    ):  # heating mode
                        self._attributes[DeviceAttributes.temperature_max][zone] = (
                            self._attributes[DeviceAttributes.zone_heating_temp_max][
                                zone
                            ]
                        )
                        self._attributes[DeviceAttributes.temperature_min][zone] = (
                            self._attributes[DeviceAttributes.zone_heating_temp_min][
                                zone
                            ]
                        )
                else:  # Room temp mode
                    self._attributes[DeviceAttributes.target_temperature][zone] = (
                        self._attributes[DeviceAttributes.room_target_temp]
                    )
                    self._attributes[DeviceAttributes.temperature_max][zone] = (
                        self._attributes[DeviceAttributes.room_temp_max]
                    )
                    self._attributes[DeviceAttributes.temperature_min][zone] = (
                        self._attributes[DeviceAttributes.room_temp_min]
                    )
            if self._attributes[DeviceAttributes.zone1_power]:
                if self._attributes[DeviceAttributes.zone_temp_type][zone]:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
            if self._attributes[DeviceAttributes.zone2_power]:
                if self._attributes[DeviceAttributes.zone_temp_type][zone]:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
            new_status[DeviceAttributes.zone1\_water\_temp\_mode.value] = self._attributes[
                DeviceAttributes.zone1_water_temp_mode
            ]
            new_status[DeviceAttributes.zone2\_water\_temp\_mode.value] = self._attributes[
                DeviceAttributes.zone2_water_temp_mode
            ]
            new_status[DeviceAttributes.zone1\_room\_temp\_mode.value] = self._attributes[
                DeviceAttributes.zone1_room_temp_mode
            ]
            new_status[DeviceAttributes.zone2\_room\_temp\_mode.value] = self._attributes[
                DeviceAttributes.zone2_room_temp_mode
            ]

        return new_status

    def make_message_set(self) -> MessageSet:
        """Midea C3 device make message set."""
        message = MessageSet(self._message_protocol_version)
        message.zone1_power = self._attributes[DeviceAttributes.zone1_power]
        message.zone2_power = self._attributes[DeviceAttributes.zone2_power]
        message.dhw_power = self._attributes[DeviceAttributes.dhw_power]
        message.mode = self._attributes[DeviceAttributes.mode]
        message.zone_target_temp = self._attributes[DeviceAttributes.zone_target_temp]
        message.dhw_target_temp = self._attributes[DeviceAttributes.dhw_target_temp]
        message.room_target_temp = self._attributes[DeviceAttributes.room_target_temp]
        message.zone1_curve = self._attributes[DeviceAttributes.zone1_curve]
        message.zone2_curve = self._attributes[DeviceAttributes.zone2_curve]
        message.tbh = self._attributes[DeviceAttributes.tbh]
        message.fast_dhw = self._attributes[DeviceAttributes.fast_dhw]
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea C3 device set attribute."""
        message: (
            MessageSet | MessageSetECO | MessageSetSilent | MessageSetDisinfect | None
        ) = None
        if attr in [
            DeviceAttributes.zone1_power,
            DeviceAttributes.zone2_power,
            DeviceAttributes.dhw_power,
            DeviceAttributes.zone1_curve,
            DeviceAttributes.zone2_curve,
            DeviceAttributes.tbh,
            DeviceAttributes.fast_dhw,
            DeviceAttributes.dhw_target_temp,
        ]:
            message = self.make_message_set()
            setattr(message, str(attr), value)
        elif attr == DeviceAttributes.eco_mode:
            message = MessageSetECO(self._message_protocol_version)
            setattr(message, str(attr), value)
        elif attr == DeviceAttributes.disinfect:
            message = MessageSetDisinfect(self._message_protocol_version)
            setattr(message, str(attr), value)
        elif attr in [
            DeviceAttributes.silent_mode.value,
            DeviceAttributes.silent_level.value,
        ]:
            if attr == DeviceAttributes.silent_mode.value and isinstance(value, bool):
                message = MessageSetSilent(self._message_protocol_version)
                # Normalize the stored level once so both sides of the
                # comparison use the same casing (C3SilentLevel names are
                # uppercase; _silent_modes publishes lowercase options).
                current_level = str(
                    self._attributes[DeviceAttributes.silent_level] or "",
                ).upper()
                message.silent_mode = bool(value)
                message.silent_level = (
                    C3SilentLevel.SILENT
                    if value and current_level == C3SilentLevel.OFF.name
                    else C3SilentLevel[current_level]
                )
            elif attr == DeviceAttributes.silent_level.value and isinstance(value, str):
                message = MessageSetSilent(self._message_protocol_version)
                normalized_value = value.upper()
                message.silent_level = C3SilentLevel[normalized_value]
                message.silent_mode = normalized_value != C3SilentLevel.OFF.name
        if message is not None:
            self.build_send(message)

    def set_mode(self, zone: int, mode: int) -> None:
        """Midea C3 device set mode."""
        message = self.make_message_set()
        if zone == 0:
            message.zone1_power = True
        else:
            message.zone2_power = True
        message.mode = mode
        self.build_send(message)

    def set_target_temperature(
        self,
        target_temperature: float,
        mode: int | None,
        zone: int | None = None,
    ) -> None:
        """Midea C3 device set target temperature."""
        if zone is None:
            raise ValueError("[C3] Parameter `zone` must be set")

        message = self.make_message_set()
        if self._attributes[DeviceAttributes.zone_temp_type][zone]:
            message.zone_target_temp[zone] = target_temperature
        else:
            message.room_target_temp = target_temperature
        if mode is not None:
            if zone == 0:
                message.zone1_power = True
            else:
                message.zone2_power = True
            message.mode = mode
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea C3 device set customize."""
        self._temperature_step = self._default_temperature_step
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "temperature_step" in params:
                    temp_step = params.get("temperature_step")
                    if isinstance(temp_step, float | int):
                        self._temperature_step = float(temp_step)
                    else:
                        _LOGGER.error(
                            "[%s] Invalid type for temperature_step: %s",
                            self.device_id,
                            temp_step,
                        )
            except json.JSONDecodeError:
                _LOGGER.exception(
                    "[%s] JSON decode error in set_customize",
                    self.device_id,
                )
            self.update_all({"temperature_step": self._temperature_step})


class MideaAppliance(MideaC3Device):
    """Midea C3 appliance."""
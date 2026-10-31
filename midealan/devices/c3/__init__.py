"""Midea lan C3 device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.message import ListTypes, MessageQuestCustom, MessageRequest, MessageType

from .features import (
    CONTROL_TABLES,
    ENERGY_TABLES,
    FeatureSetting,
    MessageSetSettings,
    decode_table,
    query_table,
)
from .features import ENERGY_ATTRIBUTES as FEATURE_ENERGY_ATTRIBUTES
from .message import (
    C3_SHORT_DHW_POWER_MASK,
    C3_SHORT_SETPOINT_BIAS,
    C3_SHORT_TBH_MASK,
    C3_SHORT_X01_BODY_LENGTH,
    C3_SHORT_X01_POWER_OFFSET,
    C3_SHORT_X01_SETPOINT_OFFSET,
    C3_SHORT_X01_TBH_OFFSET,
    C3DeviceMode,
    C3SilentLevel,
    MessageC3Response,
    MessageQueryBasic,
    MessageQueryDiagnostic,
    MessageQueryDisinfect,
    MessageQueryECO,
    MessageQuerySilence,
    MessageQueryUnitPara,
    MessageSet,
    MessageSetDisinfect,
    MessageSetECO,
    MessageSetSilent,
)
from .quintuple import (
    ENERGY_ATTRIBUTES,
    MODE_TO_WIRE,
    BasicTag,
    MessageQuery2F12,
    MessageQuery2010,
    MessageSet2010,
)
from .quintuple import (
    MODEL as QUINTUPLE_MODEL,
)

_LOGGER = logging.getLogger(__name__)
C3_SHORT_PROTOCOL_MODELS = ("17100003", "171000AU")


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
    zone1_room_temp_mode = "zone1_room_temp_mode"
    zone2_room_temp_mode = "zone2_room_temp_mode"
    zone1_water_temp_mode = "zone1_water_temp_mode"
    zone2_water_temp_mode = "zone2_water_temp_mode"
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
    target_temperature = "target_temperature"
    temperature_max = "temperature_max"
    temperature_min = "temperature_min"
    status_heating = "status_heating"
    status_dhw = "status_dhw"
    status_tbh = "status_tbh"
    status_ibh = "status_ibh"
    total_energy_consumption = "total_energy_consumption"
    total_produced_energy = "total_produced_energy"
    outdoor_temperature = "outdoor_temperature"
    temp_tw_in = "temp_tw_in"
    temp_tw_out = "temp_tw_out"
    comp_run_freq = "comp_run_freq"
    unit_mode_run = "unit_mode_run"
    fan_speed = "fan_speed"
    temp_t1 = "temp_t1"
    temp_t2 = "temp_t2"
    temp_t2b = "temp_t2b"
    temp_t3 = "temp_t3"
    temp_tp = "temp_tp"
    temp_th = "temp_th"
    temp_tf = "temp_tf"
    pressure_high = "pressure_high"
    pressure_low = "pressure_low"
    odu_voltage = "odu_voltage"
    odu_comp_current = "odu_comp_current"
    odu_target_fre = "odu_target_fre"
    exv_current = "exv_current"
    fg_capacity_need = "fg_capacity_need"
    instant_power0 = "instant_power0"
    silent_mode = "silent_mode"
    silent_level = "silent_level"
    eco_mode = "eco_mode"
    tbh = "tbh"
    error_code = "error_code"
    ibh1_on = "ibh1_on"
    ibh2_on = "ibh2_on"
    load_output_tbh = "load_output_tbh"
    pump_i_running = "pump_i_running"
    sv1_open = "sv1_open"
    sv2_open = "sv2_open"
    pump_o_running = "pump_o_running"
    pump_d_running = "pump_d_running"
    pump_c_running = "pump_c_running"
    sv3_open = "sv3_open"
    crankcase_heater_on = "crankcase_heater_on"
    pump_s_running = "pump_s_running"
    alarm_on = "alarm_on"
    run_valve_on = "run_valve_on"
    aux_heat_on = "aux_heat_on"
    defrost_valve_on = "defrost_valve_on"
    fact_req_solar_on = "fact_req_solar_on"
    fact_req_ther_cool_on = "fact_req_ther_cool_on"
    cool_run = "cool_run"
    heat_run = "heat_run"
    dhw_run = "dhw_run"
    fact_req_ther_heat_on = "fact_req_ther_heat_on"
    edge_version_type = "edge_version_type"
    comp_run_time = "comp_run_time"
    comp_total_run_time = "comp_total_run_time"
    fan_total_run_time = "fan_total_run_time"
    pump_i_total_run_time = "pump_i_total_run_time"
    pump_i_pwm = "pump_i_pwm"
    hmi_sn_code = "hmi_sn_code"
    idu_software_version_str = "idu_software_version_str"
    odu_software_version_str = "odu_software_version_str"
    error_code_description = "error_code_description"

    # --- additive attributes already parsed by message.py, now exposed ---
    remote_onoff = "remote_onoff"
    heat = "heat"
    cool = "cool"
    dhw = "dhw"
    double_zone = "double_zone"
    room_thermal_support = "room_thermal_support"
    room_thermal_state = "room_thermal_state"
    time_set = "time_set"
    holiday_on = "holiday_on"
    tbh_control = "tbh_control"
    sys_energy_ana_en = "sys_energy_ana_en"
    hmi_energy_ana_set_en = "hmi_energy_ana_set_en"
    status_cool = "status_cool"
    zone1_temp_set = "zone1_temp_set"
    zone2_temp_set = "zone2_temp_set"
    t5s = "t5s"
    tas = "tas"
    eco_function_state = "eco_function_state"
    eco_timer_state = "eco_timer_state"
    disinfect_run = "disinfect_run"
    disinfect_set_weekday = "disinfect_set_weekday"
    disinfect_start_hour = "disinfect_start_hour"
    disinfect_start_minutes = "disinfect_start_minutes"
    temp_t4 = "temp_t4"
    temp_t5 = "temp_t5"
    temp_ta = "temp_ta"
    temp_tw2 = "temp_tw2"
    temp_tb_t1 = "temp_tb_t1"
    temp_tb_t2 = "temp_tb_t2"
    temp_tsolar = "temp_tsolar"
    hydbox_subtype = "hydbox_subtype"
    hydrobox_capacity = "hydrobox_capacity"
    machine_type = "machine_type"
    odu_model = "odu_model"
    dc_current = "dc_current"
    idu_t1s1 = "idu_t1s1"
    idu_t1s2 = "idu_t1s2"
    water_flower = "water_flower"
    water_pressure = "water_pressure"
    room_rel_hum = "room_rel_hum"
    current_unit_capacity = "current_unit_capacity"
    instant_renew_power0 = "instant_renew_power0"

    # --- additive attributes backed by new parsing logic ---
    dc_bus_voltage = "dc_bus_voltage"
    compressor_on = "compressor_on"
    heating_power = "heating_power"
    heating_heat_output = "heating_heat_output"
    heating_cop = "heating_cop"
    heating_total_energy = "heating_total_energy"
    heating_total_heat = "heating_total_heat"
    heating_total_cop = "heating_total_cop"
    heating_energy_today = "heating_energy_today"
    heating_heat_today = "heating_heat_today"
    heating_cop_today = "heating_cop_today"
    heating_energy_this_week = "heating_energy_this_week"
    heating_heat_this_week = "heating_heat_this_week"
    heating_cop_this_week = "heating_cop_this_week"
    heating_energy_this_month = "heating_energy_this_month"
    heating_heat_this_month = "heating_heat_this_month"
    heating_cop_this_month = "heating_cop_this_month"
    heating_energy_this_year = "heating_energy_this_year"
    heating_heat_this_year = "heating_heat_this_year"
    heating_cop_this_year = "heating_cop_this_year"
    cooling_power = "cooling_power"
    cooling_heat_output = "cooling_heat_output"
    cooling_cop = "cooling_cop"
    cooling_total_energy = "cooling_total_energy"
    cooling_total_heat = "cooling_total_heat"
    cooling_total_cop = "cooling_total_cop"
    cooling_energy_today = "cooling_energy_today"
    cooling_heat_today = "cooling_heat_today"
    cooling_cop_today = "cooling_cop_today"
    cooling_energy_this_week = "cooling_energy_this_week"
    cooling_heat_this_week = "cooling_heat_this_week"
    cooling_cop_this_week = "cooling_cop_this_week"
    cooling_energy_this_month = "cooling_energy_this_month"
    cooling_heat_this_month = "cooling_heat_this_month"
    cooling_cop_this_month = "cooling_cop_this_month"
    cooling_energy_this_year = "cooling_energy_this_year"
    cooling_heat_this_year = "cooling_heat_this_year"
    cooling_cop_this_year = "cooling_cop_this_year"
    dhw_power_consumption = "dhw_power_consumption"
    dhw_heat_output = "dhw_heat_output"
    dhw_cop = "dhw_cop"
    dhw_total_energy = "dhw_total_energy"
    dhw_total_heat = "dhw_total_heat"
    dhw_total_cop = "dhw_total_cop"
    dhw_energy_today = "dhw_energy_today"
    dhw_heat_today = "dhw_heat_today"
    dhw_cop_today = "dhw_cop_today"
    dhw_energy_this_week = "dhw_energy_this_week"
    dhw_heat_this_week = "dhw_heat_this_week"
    dhw_cop_this_week = "dhw_cop_this_week"
    dhw_energy_this_month = "dhw_energy_this_month"
    dhw_heat_this_month = "dhw_heat_this_month"
    dhw_cop_this_month = "dhw_cop_this_month"
    dhw_energy_this_year = "dhw_energy_this_year"
    dhw_heat_this_year = "dhw_heat_this_year"
    dhw_cop_this_year = "dhw_cop_this_year"
    heat_output = "heat_output"
    instant_cop = "instant_cop"
    total_cop = "total_cop"


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
                DeviceAttributes.comp_run_freq: None,
                DeviceAttributes.unit_mode_run: None,
                DeviceAttributes.fan_speed: None,
                DeviceAttributes.temp_t1: None,
                DeviceAttributes.temp_t2: None,
                DeviceAttributes.temp_t2b: None,
                DeviceAttributes.temp_t3: None,
                DeviceAttributes.temp_tp: None,
                DeviceAttributes.temp_th: None,
                DeviceAttributes.temp_tf: None,
                DeviceAttributes.pressure_high: None,
                DeviceAttributes.pressure_low: None,
                DeviceAttributes.odu_voltage: None,
                DeviceAttributes.odu_comp_current: None,
                DeviceAttributes.odu_target_fre: None,
                DeviceAttributes.exv_current: None,
                DeviceAttributes.fg_capacity_need: None,
                DeviceAttributes.instant_power0: None,
                DeviceAttributes.error_code: 0,
                DeviceAttributes.ibh1_on: None,
                DeviceAttributes.ibh2_on: None,
                DeviceAttributes.load_output_tbh: None,
                DeviceAttributes.pump_i_running: None,
                DeviceAttributes.sv1_open: None,
                DeviceAttributes.sv2_open: None,
                DeviceAttributes.pump_o_running: None,
                DeviceAttributes.pump_d_running: None,
                DeviceAttributes.pump_c_running: None,
                DeviceAttributes.sv3_open: None,
                DeviceAttributes.crankcase_heater_on: None,
                DeviceAttributes.pump_s_running: None,
                DeviceAttributes.alarm_on: None,
                DeviceAttributes.run_valve_on: None,
                DeviceAttributes.aux_heat_on: None,
                DeviceAttributes.defrost_valve_on: None,
                DeviceAttributes.fact_req_solar_on: None,
                DeviceAttributes.fact_req_ther_cool_on: None,
                DeviceAttributes.cool_run: None,
                DeviceAttributes.heat_run: None,
                DeviceAttributes.dhw_run: None,
                DeviceAttributes.fact_req_ther_heat_on: None,
                DeviceAttributes.edge_version_type: None,
                DeviceAttributes.comp_run_time: None,
                DeviceAttributes.comp_total_run_time: None,
                DeviceAttributes.fan_total_run_time: None,
                DeviceAttributes.pump_i_total_run_time: None,
                DeviceAttributes.pump_i_pwm: None,
                DeviceAttributes.hmi_sn_code: None,
                DeviceAttributes.idu_software_version_str: None,
                DeviceAttributes.odu_software_version_str: None,
                DeviceAttributes.error_code_description: "No error",
                DeviceAttributes.remote_onoff: None,
                DeviceAttributes.heat: None,
                DeviceAttributes.cool: None,
                DeviceAttributes.dhw: None,
                DeviceAttributes.double_zone: None,
                DeviceAttributes.room_thermal_support: None,
                DeviceAttributes.room_thermal_state: None,
                DeviceAttributes.time_set: None,
                DeviceAttributes.holiday_on: None,
                DeviceAttributes.tbh_control: None,
                DeviceAttributes.sys_energy_ana_en: None,
                DeviceAttributes.hmi_energy_ana_set_en: None,
                DeviceAttributes.status_cool: None,
                DeviceAttributes.zone1_temp_set: None,
                DeviceAttributes.zone2_temp_set: None,
                DeviceAttributes.t5s: None,
                DeviceAttributes.tas: None,
                DeviceAttributes.eco_function_state: None,
                DeviceAttributes.eco_timer_state: None,
                DeviceAttributes.disinfect_run: None,
                DeviceAttributes.disinfect_set_weekday: None,
                DeviceAttributes.disinfect_start_hour: None,
                DeviceAttributes.disinfect_start_minutes: None,
                DeviceAttributes.temp_t4: None,
                DeviceAttributes.temp_t5: None,
                DeviceAttributes.temp_ta: None,
                DeviceAttributes.temp_tw2: None,
                DeviceAttributes.temp_tb_t1: None,
                DeviceAttributes.temp_tb_t2: None,
                DeviceAttributes.temp_tsolar: None,
                DeviceAttributes.hydbox_subtype: None,
                DeviceAttributes.hydrobox_capacity: None,
                DeviceAttributes.machine_type: None,
                DeviceAttributes.odu_model: None,
                DeviceAttributes.dc_current: None,
                DeviceAttributes.idu_t1s1: None,
                DeviceAttributes.idu_t1s2: None,
                DeviceAttributes.water_flower: None,
                DeviceAttributes.water_pressure: None,
                DeviceAttributes.room_rel_hum: None,
                DeviceAttributes.current_unit_capacity: None,
                DeviceAttributes.instant_renew_power0: None,
                DeviceAttributes.dc_bus_voltage: None,
                DeviceAttributes.compressor_on: None,
            },
        )
        self._default_temperature_step: float = 0.5
        self._temperature_step: float = 0.5
        self._short_protocol = str(self.model) in C3_SHORT_PROTOCOL_MODELS
        self._quintuple_protocol = str(self.model) == QUINTUPLE_MODEL
        self._quintuple_ready = False
        self._feature_query_index = 0
        self._silent_level_setting: str | None = None
        if self._quintuple_protocol:
            self._attributes.update(
                (DeviceAttributes(name), None) for name in FEATURE_ENERGY_ATTRIBUTES
            )
        self._last_short_x01_body: bytes | None = None
        if self._short_protocol:
            self._default_temperature_step = 1.0
            self._temperature_step = 1.0
        self.set_customize(customize)

    @property
    def temperature_step(self) -> float | None:
        """Midea C3 device temperature step."""
        return self._temperature_step

    @property
    def silent_modes(self) -> list[str]:
        """Midea C3 device silent modes."""
        if self._quintuple_protocol:
            return ["off", "level_1", "level_2", "level_3"]
        return MideaC3Device._silent_modes

    def build_query(self) -> list[MessageRequest]:
        """Midea C3 device build query."""
        if self._quintuple_protocol:
            slow = CONTROL_TABLES[self._feature_query_index % len(CONTROL_TABLES)]
            self._feature_query_index += 1
            return [
                MessageQuery2010(self._message_protocol_version),
                MessageQuery2F12(self._message_protocol_version),
                *(
                    query_table(table, self._message_protocol_version)
                    for table in (*ENERGY_TABLES, slow)
                ),
            ]
        queries: list[MessageRequest] = [
            MessageQueryBasic(self._message_protocol_version),
            MessageQueryDisinfect(self._message_protocol_version),
            MessageQuerySilence(self._message_protocol_version),
            MessageQueryECO(self._message_protocol_version),
            MessageQueryUnitPara(self._message_protocol_version),
        ]
        if self._short_protocol:
            queries.append(MessageQueryDiagnostic(self._message_protocol_version))
        return queries

    def build_send(self, cmd: MessageRequest, query: bool = False) -> None:
        """Serialize and send, preserving raw short-protocol commands."""
        if self._short_protocol and not query and isinstance(cmd, MessageQuestCustom):
            _LOGGER.debug(
                "[%s] Sending C3 short raw command: %s",
                self.device_id,
                cmd.body.hex(),
            )
        super().build_send(cmd, query=query)

    def _cache_short_x01_body(self, message: MessageC3Response) -> None:
        """Cache the latest short X01 body so writes mirror device state."""
        if (
            message.body_type == ListTypes.X01
            and message.message_type in (MessageType.set, MessageType.query)
            and len(message.body) == C3_SHORT_X01_BODY_LENGTH
        ):
            self._last_short_x01_body = bytes(message.body)

    def _send_short_set(
        self,
        attr: DeviceAttributes,
        value: bool | float | str,
    ) -> bool:
        """Send a 171000-series X01 mirror SET when the attribute is supported."""
        if attr not in (
            DeviceAttributes.dhw_power,
            DeviceAttributes.dhw_target_temp,
            DeviceAttributes.tbh,
        ):
            return False
        if self._last_short_x01_body is None:
            _LOGGER.warning(
                "[%s] C3 short SET skipped because no X01 body has been cached",
                self.device_id,
            )
            return True
        body = bytearray(self._last_short_x01_body)
        if attr == DeviceAttributes.dhw_target_temp:
            body[C3_SHORT_X01_SETPOINT_OFFSET] = (
                int(float(value)) + C3_SHORT_SETPOINT_BIAS
            ) & 0xFF
        elif attr == DeviceAttributes.dhw_power:
            if bool(value):
                body[C3_SHORT_X01_POWER_OFFSET] |= C3_SHORT_DHW_POWER_MASK
            else:
                body[C3_SHORT_X01_POWER_OFFSET] &= ~C3_SHORT_DHW_POWER_MASK & 0xFF
        elif bool(value):
            body[C3_SHORT_X01_TBH_OFFSET] |= C3_SHORT_TBH_MASK
        else:
            body[C3_SHORT_X01_TBH_OFFSET] &= ~C3_SHORT_TBH_MASK & 0xFF
        self._attributes[attr] = value
        self.send_command(MessageType.set, body)
        return True

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea C3 device process message."""
        message = MessageC3Response(msg, model=self.model)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        if self._short_protocol:
            self._cache_short_x01_body(message)
        if self._quintuple_protocol:
            self._merge_quintuple_status(message)
            self._parse_features(message)
        new_status = {}
        for status in self._attributes:
            if (
                self._quintuple_protocol
                and status in ENERGY_ATTRIBUTES
                and not getattr(message, "quintuple_energy", False)
            ):
                continue
            if hasattr(message, str(status)):
                self._attributes[status] = getattr(message, str(status))
                new_status[str(status)] = getattr(message, str(status))
        if self._quintuple_protocol:
            if self._quintuple_ready and new_status:
                self._refresh_quintuple_targets(new_status)
            return new_status
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
                if self._attributes[DeviceAttributes.zone_temp_type][0]:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
            if self._attributes[DeviceAttributes.zone2_power]:
                if self._attributes[DeviceAttributes.zone_temp_type][1]:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
            new_status[DeviceAttributes.zone1_water_temp_mode.value] = self._attributes[
                DeviceAttributes.zone1_water_temp_mode
            ]
            new_status[DeviceAttributes.zone2_water_temp_mode.value] = self._attributes[
                DeviceAttributes.zone2_water_temp_mode
            ]
            new_status[DeviceAttributes.zone1_room_temp_mode.value] = self._attributes[
                DeviceAttributes.zone1_room_temp_mode
            ]
            new_status[DeviceAttributes.zone2_room_temp_mode.value] = self._attributes[
                DeviceAttributes.zone2_room_temp_mode
            ]

        return new_status

    def _merge_quintuple_status(self, message: MessageC3Response) -> None:
        """Retain untouched array members when the controller acknowledges one TLV."""
        arrays = getattr(message, "quintuple_arrays", {})
        for name, changes in arrays.items():
            merged = list(self._attributes[DeviceAttributes(name)])
            for index, value in changes.items():
                merged[index] = value
            setattr(message, name, merged)
        if hasattr(message, "mode") and "zone_temp_type" in arrays:
            self._quintuple_ready = True

    def _refresh_quintuple_targets(self, status: dict[str, Any]) -> None:
        """Recompute HA targets after both full replies and sparse acknowledgements."""
        attributes = self._attributes
        mode = attributes[DeviceAttributes.mode]
        actual_mode = attributes[DeviceAttributes.mode_auto] if mode == 1 else mode
        cooling = actual_mode == C3DeviceMode.COOL
        for zone in (0, 1):
            water = attributes[DeviceAttributes.zone_temp_type][zone]
            if water:
                target = attributes[DeviceAttributes.zone_target_temp][zone]
                lower = attributes[
                    DeviceAttributes.zone_cooling_temp_min
                    if cooling
                    else DeviceAttributes.zone_heating_temp_min
                ][zone]
                upper = attributes[
                    DeviceAttributes.zone_cooling_temp_max
                    if cooling
                    else DeviceAttributes.zone_heating_temp_max
                ][zone]
            else:
                target = attributes[DeviceAttributes.room_target_temp]
                lower = attributes[DeviceAttributes.room_temp_min]
                upper = attributes[DeviceAttributes.room_temp_max]
            for attr, value in (
                (DeviceAttributes.target_temperature, target),
                (DeviceAttributes.temperature_min, lower),
                (DeviceAttributes.temperature_max, upper),
            ):
                attributes[attr][zone] = value
                status[attr.value] = attributes[attr]
            power_attr = (
                DeviceAttributes.zone1_power
                if zone == 0
                else DeviceAttributes.zone2_power
            )
            water_attr = (
                DeviceAttributes.zone1_water_temp_mode
                if zone == 0
                else DeviceAttributes.zone2_water_temp_mode
            )
            room_attr = (
                DeviceAttributes.zone1_room_temp_mode
                if zone == 0
                else DeviceAttributes.zone2_room_temp_mode
            )
            for attr, value in (
                (water_attr, bool(attributes[power_attr] and water)),
                (room_attr, bool(attributes[power_attr] and not water)),
            ):
                attributes[attr] = value
                status[attr.value] = value

    def _send_quintuple(self, values: dict[BasicTag, bool | float | int]) -> None:
        """Send a sparse control only after receiving this controller's status."""
        if not self._quintuple_ready:
            raise ValueError(
                "Wait for first 0x2010 status before controlling this heat pump",
            )
        self.build_send(MessageSet2010(values, self._message_protocol_version))

    def _parse_features(self, message: MessageC3Response) -> None:
        """Map complete verified tables and common controls to existing entities."""
        if message.body_type != ListTypes.X00 or message.message_type not in (
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        ):
            return
        values = decode_table(message.body)
        level_present = "_silent_level" in values
        if level_present:
            level = values.pop("_silent_level")
            self._silent_level_setting = level if isinstance(level, str) else None
        for name, value in values.items():
            setattr(message, name, value)
        if "silent_mode" in values or level_present:
            enabled = values.get(
                "silent_mode",
                self._attributes[DeviceAttributes.silent_mode],
            )
            message.silent_level = (
                None
                if enabled is None
                else self._silent_level_setting
                if enabled
                else "off"
            )

    def _send_features(self, values: dict[FeatureSetting, bool | str]) -> None:
        """Require actual basic status before sending a native user setting."""
        if not self._quintuple_ready:
            raise ValueError(
                "Wait for first 0x2010 status before controlling this heat pump",
            )
        self.build_send(MessageSetSettings(values, self._message_protocol_version))

    def _set_quintuple_attribute(self, attr: str, value: bool | float | str) -> None:
        """Route supported controls without ever falling back to legacy packets."""
        controls: dict[str, FeatureSetting] = {
            DeviceAttributes.eco_mode: FeatureSetting.ECO,
            DeviceAttributes.disinfect: FeatureSetting.DISINFECT,
            DeviceAttributes.silent_mode: FeatureSetting.SILENT_POWER,
        }
        if attr in controls:
            if not isinstance(value, bool):
                raise ValueError("C3 switches require boolean values")
            self._send_features({controls[attr]: value})
            return
        if attr == DeviceAttributes.silent_level:
            if not isinstance(value, str) or value not in self.silent_modes:
                raise ValueError("Invalid silent level")
            settings: dict[FeatureSetting, bool | str] = {
                FeatureSetting.SILENT_POWER: value != "off",
            }
            if value != "off":
                settings[FeatureSetting.SILENT_LEVEL] = value
            self._send_features(settings)
            return

        tags: dict[str, BasicTag] = {
            DeviceAttributes.zone1_power: BasicTag.ZONE1_POWER,
            DeviceAttributes.zone2_power: BasicTag.ZONE2_POWER,
            DeviceAttributes.dhw_power: BasicTag.DHW_POWER,
            DeviceAttributes.zone1_curve: BasicTag.ZONE1_CURVE,
            DeviceAttributes.zone2_curve: BasicTag.ZONE2_CURVE,
            DeviceAttributes.tbh: BasicTag.TANK_BOOSTER,
            DeviceAttributes.fast_dhw: BasicTag.FAST_DHW,
            DeviceAttributes.dhw_target_temp: BasicTag.DHW_TEMPERATURE,
        }
        if attr not in tags:
            raise ValueError(
                f"Control {attr} is not implemented for C3 model {QUINTUPLE_MODEL}",
            )
        if attr in (DeviceAttributes.zone2_power, DeviceAttributes.zone2_curve):
            self._check_quintuple_zone(1)
        if attr == DeviceAttributes.dhw_target_temp:
            temperature = float(value)
            if (
                not self._attributes[DeviceAttributes.dhw_temp_min]
                <= temperature
                <= self._attributes[DeviceAttributes.dhw_temp_max]
            ):
                raise ValueError(
                    "DHW temperature is outside the controller's reported limits",
                )
            self._send_quintuple({tags[attr]: temperature})
        else:
            if not isinstance(value, bool):
                raise ValueError("Power and curve controls require a boolean")
            self._send_quintuple({tags[attr]: value})

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
        if self._quintuple_protocol:
            self._set_quintuple_attribute(attr, value)
            return
        if self._short_protocol:
            if attr in DeviceAttributes:
                self._send_short_set(DeviceAttributes(attr), value)
            return
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
                message.silent_mode = bool(value)
                message.silent_level = (
                    C3SilentLevel.SILENT
                    if value
                    and self._attributes[DeviceAttributes.silent_level]
                    == C3SilentLevel.OFF.name.lower()
                    else C3SilentLevel[
                        str(self._attributes[DeviceAttributes.silent_level]).upper()
                    ]
                )
            elif attr == DeviceAttributes.silent_level.value and isinstance(value, str):
                message = MessageSetSilent(self._message_protocol_version)
                message.silent_level = C3SilentLevel[value.upper()]
                message.silent_mode = value != C3SilentLevel.OFF.name.lower()
        if message is not None:
            self.build_send(message)

    def set_mode(self, zone: int, mode: int) -> None:
        """Midea C3 device set mode."""
        if self._quintuple_protocol:
            self._check_quintuple_zone(zone)
            if mode not in MODE_TO_WIRE:
                raise ValueError("Invalid C3 zone or mode")
            power = BasicTag.ZONE1_POWER if zone == 0 else BasicTag.ZONE2_POWER
            values: dict[BasicTag, bool | float | int] = {power: mode != 0}
            if mode:
                values[BasicTag.MODE] = MODE_TO_WIRE[mode]
            self._send_quintuple(values)
            return
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

        if self._quintuple_protocol:
            self._check_quintuple_zone(zone)
            if not self._quintuple_ready:
                raise ValueError(
                    "Wait for first 0x2010 status before controlling this heat pump",
                )
            if (
                not self._attributes[DeviceAttributes.temperature_min][zone]
                <= target_temperature
                <= self._attributes[DeviceAttributes.temperature_max][zone]
            ):
                raise ValueError(
                    "Temperature is outside the controller's reported limits",
                )
            tag = (
                BasicTag.ZONE1_TEMPERATURE if zone == 0 else BasicTag.ZONE2_TEMPERATURE
            )
            values: dict[BasicTag, bool | float | int] = {tag: target_temperature}
            if not self._attributes[DeviceAttributes.zone_temp_type][zone]:
                values[BasicTag.ROOM_TEMPERATURE] = target_temperature
            if mode is not None:
                if mode not in MODE_TO_WIRE:
                    raise ValueError("Invalid C3 operating mode")
                power = BasicTag.ZONE1_POWER if zone == 0 else BasicTag.ZONE2_POWER
                values[power] = mode != 0
                if mode:
                    values[BasicTag.MODE] = MODE_TO_WIRE[mode]
            self._send_quintuple(values)
            return

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

    def _check_quintuple_zone(self, zone: int) -> None:
        """Reject nonexistent zones rather than writing to unsupported hardware."""
        if zone not in (0, 1):
            raise ValueError("Invalid C3 zone")
        if zone == 1 and not self._attributes[DeviceAttributes.double_zone]:
            raise ValueError("Zone 2 is not enabled on this controller")

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

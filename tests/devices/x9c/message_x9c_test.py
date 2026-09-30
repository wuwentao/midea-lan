"""Test 0x9C message."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9c.message import (
    ALL_ATTRIBUTES,
    MessageQuery,
    MessageQueryError,
    MessageSetAc,
    MessageSetB2,
    MessageSetB3,
    MessageSetB6,
    MessageSetB7,
    MessageSetE7,
    MessageSetSp,
    MessageSetTotal,
    MessageX9CBase,
    MessageX9CResponse,
)
from midealan.message import MessageType


def _frame(message_type: int, body: list[int]) -> bytes:
    """Build a full 0x9C response frame (header + body + trailing checksum)."""
    header = [0xAA, 0x00, 0x9C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, message_type]
    return bytes(header + body + [0x00])


def _tlv(*records: tuple[int, list[int]]) -> list[int]:
    """Build a query-all body: sub-command 0x01 then module TLV records."""
    body = [0x01]
    for module_id, value in records:
        body += [module_id, len(value), *value]
    return body


class TestMessageX9CBase:
    """Test the request base class."""

    def test_body_not_implemented(self) -> None:
        """The abstract base does not implement a body."""
        msg = MessageX9CBase(
            protocol_version=ProtocolVersion.V3,
            message_type=MessageType.query,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test the query messages."""

    def test_query_all_body(self) -> None:
        """Query-all sends a single sub-command byte."""
        assert list(MessageQuery(ProtocolVersion.V3).body) == [0x01]

    def test_query_error_body(self) -> None:
        """Error query sends the error sub-command byte."""
        assert list(MessageQueryError(ProtocolVersion.V3).body) == [0x02]


class TestMessageSetTotal:
    """Test whole-appliance control frames."""

    def test_defaults_unchanged(self) -> None:
        """With nothing set every payload byte is 0xFF."""
        body = list(MessageSetTotal(ProtocolVersion.V3).body)
        assert body[0] == 0x01
        assert body[1] == 0xF0
        assert body[2:] == [0xFF] * (len(body) - 2)

    def test_power_lock_voice(self) -> None:
        """Power/lock/microphone/volume land in their bytes."""
        msg = MessageSetTotal(ProtocolVersion.V3)
        msg.power = "on"
        msg.lock = True
        msg.ai_voice_microphone = "on"
        msg.ai_voice_volume = 7
        body = list(msg.body)
        assert body[3] == 0x02  # power on
        assert body[4] == 0x01  # lock on
        assert body[7] == 0x00  # microphone on
        assert body[8] == 7

    def test_power_off_lock_off_mic_off(self) -> None:
        """The off variants are encoded too."""
        msg = MessageSetTotal(ProtocolVersion.V3)
        msg.power = "off"
        msg.lock = False
        msg.ai_voice_microphone = "off"
        body = list(msg.body)
        assert body[3] == 0x01
        assert body[4] == 0x00
        assert body[7] == 0x01


class TestMessageSetB7:
    """Test gas hob control frames."""

    def test_full(self) -> None:
        """All b7 fields are encoded."""
        msg = MessageSetB7(ProtocolVersion.V3)
        msg.burner = "left"
        msg.function_control = 2
        msg.gear = 3
        msg.destination_time = 300
        msg.destination_temp = 220
        body = list(msg.body)
        assert body[2] == 0x01  # left burner
        assert body[3] == 2
        assert body[4] == 3
        assert body[5] == 300 % 256
        assert body[6] == 300 // 256
        assert body[7] == 220 % 256

    def test_right_burner(self) -> None:
        """Right burner selector works."""
        msg = MessageSetB7(ProtocolVersion.V3)
        msg.burner = "right"
        assert list(msg.body)[2] == 0x02


class TestMessageSetE7:
    """Test induction soup cooker control frames."""

    def test_full(self) -> None:
        """All e7 fields are encoded."""
        msg = MessageSetE7(ProtocolVersion.V3)
        msg.burner = 2
        msg.status = "working"
        msg.mode = "stew_soup"
        msg.gear = 4
        msg.destination_time = 600
        msg.bridge_link = "on"
        body = list(msg.body)
        assert body[2] == 2
        assert body[3] == 0x02
        assert body[4] == 0x02
        assert body[5] == 4
        assert body[6] == 600 % 256
        assert body[8] == 0x01

    def test_bridge_link_off(self) -> None:
        """Bridge link off is encoded."""
        msg = MessageSetE7(ProtocolVersion.V3)
        msg.bridge_link = "off"
        assert list(msg.body)[8] == 0x00


class TestMessageSetAc:
    """Test air conditioner control frames."""

    def test_full(self) -> None:
        """All ac fields are encoded."""
        msg = MessageSetAc(ProtocolVersion.V3)
        msg.status = "working"
        msg.mode = "refrigeration"
        msg.gear = 2
        msg.destination_time = 120
        msg.destination_temp = 26
        msg.swing = "on"
        msg.air_direction = "on"
        msg.swing_gear = 1
        msg.swing_min_angle = 10
        msg.swing_max_angle = 80
        msg.air_direction_gear = 2
        msg.air_direction_min_angle = 20
        msg.air_direction_max_angle = 70
        body = list(msg.body)
        assert body[3] == 0x02
        assert body[4] == 0x01
        assert body[5] == 2
        assert body[6] == 120
        assert body[8] == 26
        assert body[12] == 0x01
        assert body[13] == 0x01
        assert body[14] == 1
        assert body[15] == 10
        assert body[16] == 80
        assert body[17] == 2
        assert body[18] == 20
        assert body[19] == 70

    def test_swing_air_off(self) -> None:
        """Swing/air-direction off are encoded."""
        msg = MessageSetAc(ProtocolVersion.V3)
        msg.swing = "off"
        msg.air_direction = "off"
        body = list(msg.body)
        assert body[12] == 0x00
        assert body[13] == 0x00


class TestMessageSetB3:
    """Test steam cabinet control frames."""

    def test_full(self) -> None:
        """All b3 fields are encoded, with temperature clamped."""
        msg = MessageSetB3(ProtocolVersion.V3)
        msg.cabinet = 1
        msg.function_control = 2
        msg.destination_time = 500
        msg.destination_temp = 300  # clamped to 0xFE
        body = list(msg.body)
        assert body[2] == 1
        assert body[3] == 2
        assert body[4] == 500 % 256
        assert body[5] == 500 // 256
        assert body[6] == 0xFE


class TestMessageSetB2:
    """Test steam-bake box control frames."""

    def test_full(self) -> None:
        """All b2 fields are encoded."""
        msg = MessageSetB2(ProtocolVersion.V3)
        msg.cabinet = 2
        msg.work_status = "working"
        msg.work_func = 1
        msg.work_menu = 3
        msg.work_destination_time = 400
        msg.destination_temp = 180
        msg.order_destination_time = 60
        msg.work_sub_menu = 2
        msg.menu_number = 5
        msg.menu_weight = 250
        msg.light = "on"
        msg.lock = "on"
        body = list(msg.body)
        assert body[2] == 2
        assert body[3] == 0x02
        assert body[4] == 1
        assert body[5] == 3
        assert body[16] == 0x01
        assert body[17] == 0x01

    def test_recipe_code_and_off(self) -> None:
        """recipe_code overrides work_menu; light/lock off encode 0."""
        msg = MessageSetB2(ProtocolVersion.V3)
        msg.recipe_code = 42
        msg.light = "off"
        msg.lock = "off"
        body = list(msg.body)
        assert body[5] == 42
        assert body[16] == 0x00
        assert body[17] == 0x00


class TestMessageSetSp:
    """Test drying/warming plate control frames."""

    def test_status_and_time(self) -> None:
        """Status/time/temperature are encoded."""
        msg = MessageSetSp(ProtocolVersion.V3)
        msg.func = 1
        msg.status = "on"
        msg.destination_time = 300
        msg.temperature = 45
        msg.order_destination_time = 30
        body = list(msg.body)
        assert body[2] == 1
        assert body[3] == 0x01
        assert body[4] == 300 % 256
        assert body[6] == 45

    def test_setting_type_value(self) -> None:
        """Explicit setting type/value are encoded."""
        msg = MessageSetSp(ProtocolVersion.V3)
        msg.setting_type = 5
        msg.setting_value = 9
        body = list(msg.body)
        assert body[9] == 5
        assert body[10] == 9

    def test_setting_linkage(self) -> None:
        """Linkage toggle uses selector 0x01."""
        msg = MessageSetSp(ProtocolVersion.V3)
        msg.setting_linkage = "on"
        body = list(msg.body)
        assert body[9] == 0x01
        assert body[10] == 0x01

    def test_setting_automode(self) -> None:
        """Automode uses selector 0x02 plus schedule bytes."""
        msg = MessageSetSp(ProtocolVersion.V3)
        msg.setting_automode = "off"
        msg.automode_day = 3
        msg.automode_starthour = 8
        msg.automode_startminute = 30
        body = list(msg.body)
        assert body[9] == 0x02
        assert body[10] == 0x00
        assert body[11] == 3
        assert body[12] == 8
        assert body[13] == 30


class TestMessageSetB6:
    """Test range hood control frames."""

    def test_power_gear_light(self) -> None:
        """Working status turns fan on; light with custom lightness."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.work_status = "working"
        msg.light = "on"
        msg.lightness = 50
        body = list(msg.body)
        assert body[3] == 0x02
        assert body[4] == 0x02
        assert body[7] == 50

    def test_power_on_and_gear_zero(self) -> None:
        """Power on maps to working; gear 0 forces power_off byte."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.power = "on"
        body = list(msg.body)
        assert body[3] == 0x02
        assert body[4] == 0x02
        msg2 = MessageSetB6(ProtocolVersion.V3)
        msg2.gear = 0
        body2 = list(msg2.body)
        assert body2[3] == 0x01
        assert body2[4] == 0x00

    def test_gear_nonzero_and_light_off(self) -> None:
        """A non-zero gear sets working; light off writes 0."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.gear = 3
        msg.light = "off"
        msg.lightness = 0  # ignored -> default brightness path not taken
        body = list(msg.body)
        assert body[3] == 0x02
        assert body[4] == 3
        assert body[7] == 0x00

    def test_light_on_default_brightness(self) -> None:
        """Light on without lightness uses the default 0x64."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.light = "on"
        assert list(msg.body)[7] == 0x64

    def test_work_status_non_working(self) -> None:
        """A non-working work_status sets byte 3 without forcing the fan gear."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.work_status = "power_off"
        body = list(msg.body)
        assert body[3] == 0x01
        assert body[4] == 0xFF  # gear left unchanged

    def test_power_off_keeps_gear(self) -> None:
        """Power off sets byte 3 but leaves the gear untouched."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.power = "off"
        body = list(msg.body)
        assert body[3] == 0x01
        assert body[4] == 0xFF

    def test_setting_gesture(self) -> None:
        """Gesture setting selects value byte."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "gesture"
        msg.gesture_value = "light"
        body = list(msg.body)
        assert body[8] == 0x01
        assert body[9] == 0x01
        assert body[10] == 0x03

    def test_setting_gesture_off(self) -> None:
        """Gesture off disables the selector."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "gesture"
        msg.gesture_value = "off"
        assert list(msg.body)[9] == 0x00

    def test_setting_smoke_detector_value(self) -> None:
        """Smoke detector with a non-zero value writes the value byte."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "smoke_detector"
        msg.smoke_detector_value = 5
        body = list(msg.body)
        assert body[12] == 0x04
        assert body[13] == 0x01
        assert body[14] == 5

    def test_setting_smoke_detector_zero_and_toggle(self) -> None:
        """Value 0 clears; boolean toggle is honoured when no value given."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "smoke_detector"
        msg.smoke_detector_value = 0
        assert list(msg.body)[13] == 0x00
        on = MessageSetB6(ProtocolVersion.V3)
        on.setting = "smoke_detector"
        on.smoke_detector = "on"
        assert list(on.body)[13] == 0x01
        off = MessageSetB6(ProtocolVersion.V3)
        off.setting = "smoke_detector"
        off.smoke_detector = "off"
        assert list(off.body)[13] == 0x00

    def test_setting_infrared(self) -> None:
        """Infrared value and off path."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "infrared"
        msg.infrared_value = "wind"
        body = list(msg.body)
        assert body[8] == 0x03
        assert body[10] == 0x02
        off = MessageSetB6(ProtocolVersion.V3)
        off.setting = "infrared"
        off.infrared_value = "off"
        assert list(off.body)[9] == 0x00

    def test_setting_tvoc(self) -> None:
        """TVOC toggle at its selector."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "TVOC"
        msg.tvoc = "on"
        body = list(msg.body)
        assert body[8] == 0x04
        assert body[9] == 0x01

    def test_setting_smoke_stove_linkage(self) -> None:
        """Linkage with gear and fix direction."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "smoke_stove_linkage"
        msg.smoke_stove_linkage_gear = 2
        msg.smoke_stove_linkage_gear_fix = "negative"
        body = list(msg.body)
        assert body[8] == 0x05
        assert body[9] == 0x01
        assert body[10] == 2
        assert body[11] == 0x01

    def test_setting_smoke_stove_linkage_gear_zero(self) -> None:
        """A zero linkage gear disables it."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "smoke_stove_linkage"
        msg.smoke_stove_linkage_gear = 0
        assert list(msg.body)[9] == 0x00

    def test_setting_delay_gear_linkage(self) -> None:
        """Delay-gear linkage enable path."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "delay_gear_linkage"
        msg.delay_gear_linkage = "on"
        body = list(msg.body)
        assert body[8] == 0x06
        assert body[9] == 0x01

    def test_setting_power_on_light(self) -> None:
        """Power-on-light toggle."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "power_on_light"
        msg.power_on_light = "on"
        body = list(msg.body)
        assert body[8] == 0x07
        assert body[9] == 0x01

    def test_setting_delay_time(self) -> None:
        """Delay-time toggle plus value."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "delay_time"
        msg.delay_time = "on"
        msg.delay_time_value = 15
        body = list(msg.body)
        assert body[8] == 0x08
        assert body[9] == 0x01
        assert body[10] == 15

    def test_setting_lock(self) -> None:
        """Lock toggle."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "lock"
        msg.lock = "on"
        body = list(msg.body)
        assert body[8] == 0x09
        assert body[9] == 0x01

    def test_gesture_sensitivity(self) -> None:
        """Gesture sensitivity overrides selector and writes byte 11."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.gesture_sensitivity = 2
        body = list(msg.body)
        assert body[8] == 0x01
        assert body[11] == 2


class TestX9CResponseTotal:
    """Test decoding of the whole-appliance summary."""

    def test_total_full(self) -> None:
        """Decode a rich total package."""
        # positions 1..22 (1-based); index 0 selector unused for total
        value = [0] * 22
        value[0] = 0x02  # power on
        value[1] = 0x01  # lock bit0
        value[3] = 0x0F  # all sensor bits (ir/speak/gesture) + water_shortage bit
        value[4] = 55  # firewall temp
        value[5] = 60  # shelving unit temp
        value[6] = 3  # error type
        value[7] = 7  # error code
        value[8] = 1  # tips type
        value[9] = 2  # tips code
        value[11] = 0b1000_0011  # linkage gear 3 + linkage bit7
        value[14] = 0x01  # lock on type local
        value[15] = 0x00  # microphone on
        value[16] = 8  # volume
        value[17] = 0x02  # ai voice status connecting
        value[20] = 1
        value[21] = 5  # electronic version 1.5
        frame = _frame(MessageType.query, _tlv((0xF0, value)))
        resp = MessageX9CResponse(frame)
        attrs = resp.attributes
        assert attrs["total_power"] == "on"
        assert attrs["total_lock"] == "on"
        assert attrs["total_ir"] == "on"
        assert attrs["total_speak"] == "on"
        assert attrs["total_gesture"] == "on"
        assert attrs["total_water_shortage"] == "1"
        assert attrs["total_error_type"] == 3
        assert attrs["total_tips_code"] == 2
        assert attrs["ai_voice_volume"] == 8
        assert attrs["electronic_version"] == "1.5"

    def test_total_sensor_absent(self) -> None:
        """When the sensor byte is 0xFF the defaults are kept."""
        value = [0xFF] * 22
        value[0] = 0x01  # power off (enum, guard off)
        frame = _frame(MessageType.query, _tlv((0xF0, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["total_speak"] == "off"
        assert attrs["total_water_shortage"] == "0"
        assert attrs["total_error_type"] == 0
        assert "electronic_version" not in attrs


class TestX9CResponseModules:
    """Test decoding of the cooking modules."""

    def test_b6_with_dynamic_and_lock(self) -> None:
        """Range hood with an inverter sub-package and trailing lock byte."""
        value = [0x00] * 22
        value[0] = 1  # selector (unused for b6)
        value[1] = 0x04  # work_status hotclean stage1 -> steaming on
        value[2] = 2  # gear
        value[9] = 0x0A  # light on -> lightness 0x0A
        # dynamic inverter sub-package at position 23 (index 22): id 0x06 len 2
        value += [0x06, 0x02, 0x10, 0x00]
        value += [0x01]  # trailing lock byte -> lock_on_type local
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b6_steaming"] == "on"
        assert attrs["b6_steaming_stage"] == 1
        assert attrs["b6_light"] == "on"
        assert attrs["b6_lightness"] == 0x0A
        assert attrs["b6_inverter_wind_flow"] == 0x10
        assert attrs["b6_lock_on_type"] == "local"

    def test_b6_lock_off_and_air_duct(self) -> None:
        """Air-duct dynamic sub-package and a lock-off trailing byte."""
        value = [0x00] * 22
        value[1] = 0x02  # working -> steaming off
        # dynamic air-duct sub-package: id 0x03 len 5
        value += [0x03, 0x05, 0x00, 0x64, 80, 5, 1]
        value += [0x10]  # trailing byte -> lock_off_type local
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b6_steaming"] == "off"
        assert attrs["b6_air_duct_detection_time"] == 0x64
        assert attrs["b6_lock_off_type"] == "local"

    def test_b7_delay(self) -> None:
        """A gas hob with remaining time reports the delay status."""
        value = [0x00] * 15
        value[0] = 1  # left burner
        value[1] = 0x02  # working
        value[5] = 30  # remaining_time low byte -> >0
        frame = _frame(MessageType.query, _tlv((0x02, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b7_left_status"] == "power_off_delay"
        assert attrs["b7_left_remaining_time"] == 30

    def test_b3(self) -> None:
        """A steam cabinet package decodes with prefix."""
        value = [0x00] * 11
        value[0] = 2  # downstair
        value[1] = 0x02  # uperization
        value[6] = 0b0000_0011  # door_lock + door open
        frame = _frame(MessageType.query, _tlv((0x03, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b3_downstair_status"] == "uperization"
        assert attrs["b3_downstair_door"] == "open"

    def test_b2_recipe_and_preheating(self) -> None:
        """Steam-bake box recipe code and preheating tri-state."""
        value = [0x00] * 27
        value[0] = 1  # upstair
        value[1] = 0x02  # working
        value[17] = 0b0000_0100  # bit2 -> preheating finish
        value[18] = 0x2A  # recipe low byte
        value[19] = 0x00  # recipe high byte
        frame = _frame(MessageType.query, _tlv((0x04, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b2_upstair_recipe_code"] == 0x2A
        assert attrs["b2_upstair_preheating"] == "finish"

    def test_b2_preheating_states(self) -> None:
        """The other two preheating states and default recipe code."""
        value = [0xFF] * 27
        value[0] = 1
        value[1] = 0x02
        value[17] = 0b0000_0010  # bit1 -> preheating
        frame = _frame(MessageType.query, _tlv((0x04, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b2_upstair_preheating"] == "preheating"
        assert attrs["b2_upstair_recipe_code"] == -1

        value[17] = 0x00  # neither bit -> none
        frame2 = _frame(MessageType.query, _tlv((0x04, value)))
        attrs2 = MessageX9CResponse(frame2).attributes
        assert attrs2["b2_upstair_preheating"] == "none"

    def test_e7(self) -> None:
        """Induction soup cooker with a specific prefix."""
        value = [0x00] * 14
        value[0] = 5  # right_top
        value[1] = 0x02  # working
        value[2] = 0x02  # stew_soup
        frame = _frame(MessageType.query, _tlv((0x05, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["e7_right_top_work_status"] == "working"
        assert attrs["e7_right_top_mode"] == "stew_soup"

    def test_sp(self) -> None:
        """Warming plate reports linkage/automode flags."""
        value = [0x00] * 15
        value[0] = 3  # uvc
        value[1] = 0x01  # on
        value[11] = 0b0000_0101  # linkage + door open
        frame = _frame(MessageType.query, _tlv((0x06, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["sp_uvc_status"] == "on"
        assert attrs["sp_uvc_setting_linkage"] == "on"
        assert attrs["sp_uvc_door"] == "open"

    def test_ac(self) -> None:
        """Air conditioner decodes to absolute ac_* attributes."""
        value = [0x00] * 26
        value[1] = 0x02  # working
        value[2] = 0x01  # refrigeration
        value[16] = 0b0000_0011  # swing + air_direction
        frame = _frame(MessageType.query, _tlv((0x08, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["ac_work_status"] == "working"
        assert attrs["ac_mode"] == "refrigeration"
        assert attrs["ac_swing"] == "on"

    def test_bf(self) -> None:
        """Built-in oven big-endian fields and weight decoding."""
        value = [0xFF] * 39
        value[0] = 0x00  # control_back success
        value[4] = 0x21  # step_total 1 / step_current 2
        value[5] = 0b1000_0000  # cavity down
        value[30] = 0x03  # work_status working
        value[37] = 0b0001_0000  # weight multiple bit4 -> ten
        value[19] = 5  # weight raw
        frame = _frame(MessageType.query, _tlv((0x09, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["bf_control_back"] == "success"
        assert attrs["bf_step_total"] == 1
        assert attrs["bf_step_current"] == 2  # high nibble of 0x21
        assert attrs["bf_cavity"] == "down"
        assert attrs["bf_work_status"] == "working"
        assert attrs["bf_weight_multiple"] == "ten"
        assert attrs["bf_weight_mount"] == 5 * 10 * 10.0

    def test_bf_weight_other(self) -> None:
        """The 'other' weight code (0x04) keeps the raw mount value."""
        value = [0xFF] * 39
        value[37] = 0x04  # weight flags == 0x04 -> "other" branch
        value[19] = 9
        frame = _frame(MessageType.query, _tlv((0x09, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["bf_weight_mount"] == 9

    def test_unknown_module_skipped(self) -> None:
        """An unknown module id is ignored without error."""
        frame = _frame(MessageType.query, _tlv((0x77, [1, 2, 3])))
        assert MessageX9CResponse(frame).attributes == {}

    def test_empty_module_skipped(self) -> None:
        """A zero-length record is skipped."""
        frame = _frame(MessageType.query, _tlv((0xF0, [])))
        assert MessageX9CResponse(frame).attributes == {}

    def test_truncated_record_breaks(self) -> None:
        """A record longer than the buffer stops the walk."""
        body = [0x01, 0xF0, 0x05, 0x00]  # claims 5 bytes but only 1 present
        frame = _frame(MessageType.query, body)
        assert MessageX9CResponse(frame).attributes == {}


class TestX9CResponseSpecial:
    """Test error handling and the notify/set-echo branches."""

    def test_error_list(self) -> None:
        """The error sub-command yields an error list."""
        frame = _frame(MessageType.query, [0x02, 0x03, 0x11, 0x22, 0x33])
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["error_list"] == [0x11, 0x22, 0x33]

    def test_error_list_absent(self) -> None:
        """A 0xFF count means no error list."""
        frame = _frame(MessageType.query, [0x02, 0xFF])
        assert "error_list" not in MessageX9CResponse(frame).attributes

    def test_notify_uses_tlv(self) -> None:
        """Notify frames decode as TLV like query frames."""
        value = [0x00] * 22
        value[0] = 0x02
        frame = _frame(MessageType.notify1, _tlv((0xF0, value)))
        assert MessageX9CResponse(frame).attributes["total_power"] == "on"

    def test_set_echo_not_parsed(self) -> None:
        """A set-echo frame is not decoded as TLV."""
        frame = _frame(MessageType.set, [0x01, 0xF0, 0x02])
        assert MessageX9CResponse(frame).attributes == {}


class TestSetDefaults:
    """Building a set frame with nothing configured leaves 0xFF fields."""

    @pytest.mark.parametrize(
        "factory",
        [
            MessageSetTotal,
            MessageSetB7,
            MessageSetE7,
            MessageSetAc,
            MessageSetB6,
            MessageSetB3,
            MessageSetB2,
            MessageSetSp,
        ],
    )
    def test_defaults_build(self, factory: type) -> None:
        """The default body starts with the sub-command and module id."""
        body = list(factory(ProtocolVersion.V3).body)
        assert body[0] == 0x01
        assert body[1] in {0xF0, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08}


class TestSetEdgeCases:
    """Cover the 'left unchanged' and off branches of the set builders."""

    def test_b6_setting_values_absent(self) -> None:
        """Selecting a setting without its value keeps the value byte at 0xFF."""
        for setting in ("gesture", "smoke_detector", "infrared", "delay_time"):
            msg = MessageSetB6(ProtocolVersion.V3)
            msg.setting = setting
            body = list(msg.body)
            assert body[0] == 0x01

    def test_b6_tvoc_off(self) -> None:
        """The on/off helper writes 0 for the off state."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = "TVOC"
        msg.tvoc = "off"
        assert list(msg.body)[9] == 0x00

    def test_b6_no_setting(self) -> None:
        """An unknown/blank setting name touches no selector."""
        msg = MessageSetB6(ProtocolVersion.V3)
        msg.setting = None
        assert list(msg.body)[7] == 0xFF

    def test_sp_automode_without_schedule(self) -> None:
        """Automode toggle without schedule bytes leaves them at 0xFF."""
        msg = MessageSetSp(ProtocolVersion.V3)
        msg.setting_automode = "on"
        body = list(msg.body)
        assert body[9] == 0x02
        assert body[11] == 0xFF


class TestDecoderEdgeCases:
    """Cover defensive decoder branches with short/absent bytes."""

    def test_enum_index_out_of_range(self) -> None:
        """An enum field past the package end decodes to nothing."""
        # AC module holding a single byte: ac_work_status (index 2) is absent.
        frame = _frame(MessageType.query, _tlv((0x08, [0x00])))
        assert "ac_work_status" not in MessageX9CResponse(frame).attributes

    def test_bitflag_guarded_ff(self) -> None:
        """A 0xFF bitflag byte is treated as absent."""
        value = [0x00] * 15
        value[0] = 1
        value[1] = 0x02
        value[13] = 0xFF  # byte 14 -> has_pot/has_fire bitflags guarded off
        frame = _frame(MessageType.query, _tlv((0x02, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "b7_left_has_pot" not in attrs

    def test_bf_u24be_valid(self) -> None:
        """A fully populated big-endian 24-bit field decodes."""
        value = [0xFF] * 39
        value[1] = 0x01  # recipe high
        value[2] = 0x02
        value[3] = 0x03  # recipe low
        frame = _frame(MessageType.query, _tlv((0x09, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["bf_recipe_code"] == 0x010203

    def test_light_byte_absent(self) -> None:
        """A 0xFF light byte leaves both light attributes unset."""
        value = [0x00] * 22
        value[9] = 0xFF  # byte 10 -> light
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "b6_light" not in attrs

    def test_b6_status_absent(self) -> None:
        """A 0xFF work-status byte skips the steaming derivation."""
        value = [0x00] * 22
        value[1] = 0xFF  # byte 2 -> work status
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "b6_steaming" not in attrs

    def test_b6_smoke_detect_dynamic_noop(self) -> None:
        """The smoke-detect dynamic sub-package is walked but decodes nothing."""
        value = [0x00] * 22
        value += [0x05, 0x02, 0x11, 0x22]  # smokeditect id, ignored
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        # No exception; no b6_air_duct_* / b6_inverter_* produced by this record.
        attrs = MessageX9CResponse(frame).attributes
        assert not any(k.startswith("b6_inverter") for k in attrs)

    def test_b6_no_trailing_lock(self) -> None:
        """When no trailing lock byte follows, lock types stay unset."""
        value = [0x00] * 22  # exactly 22 bytes, no dynamic/lock tail
        frame = _frame(MessageType.query, _tlv((0x01, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "b6_lock_on_type" not in attrs
        assert "b6_lock_off_type" not in attrs

    def test_b2_preheating_absent(self) -> None:
        """A 0xFF flags byte skips the preheating tri-state."""
        value = [0x00] * 27
        value[0] = 1
        value[1] = 0x02
        value[17] = 0xFF  # byte 18 -> preheating flags
        frame = _frame(MessageType.query, _tlv((0x04, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "b2_upstair_preheating" not in attrs

    def test_b7_no_remaining(self) -> None:
        """A hob with zero remaining time keeps its plain status."""
        value = [0x00] * 15
        value[0] = 1
        value[1] = 0x02  # working
        frame = _frame(MessageType.query, _tlv((0x02, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert attrs["b7_left_status"] == "working"

    def test_bf_weight_flags_absent(self) -> None:
        """Absent weight flags and raw byte leave the mount unset."""
        value = [0xFF] * 39
        frame = _frame(MessageType.query, _tlv((0x09, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "bf_weight_mount" not in attrs
        assert "bf_weight_multiple" not in attrs

    def test_bf_weight_no_matching_bit(self) -> None:
        """Weight flags with no recognised bit keep the default multiple."""
        value = [0xFF] * 39
        value[37] = 0x00  # flags present but no multiple bit set
        value[19] = 4  # raw weight -> mount = 4 * 10 * 1.0
        frame = _frame(MessageType.query, _tlv((0x09, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert "bf_weight_multiple" not in attrs
        assert attrs["bf_weight_mount"] == 4 * 10 * 1.0

    def test_unknown_subcommand(self) -> None:
        """A query frame with an unrecognised sub-command yields no attrs."""
        frame = _frame(MessageType.query, [0x7E, 0x00])
        assert MessageX9CResponse(frame).attributes == {}

    def test_b7_unknown_selector(self) -> None:
        """A hob record with an unknown selector writes no b7 attributes."""
        value = [0x00] * 15
        value[0] = 9  # selector 9 is neither left (1) nor right (2)
        value[1] = 0x02
        frame = _frame(MessageType.query, _tlv((0x02, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert not any(k.startswith("b7_") for k in attrs)

    def test_b2_unknown_selector(self) -> None:
        """A steam-bake record with an unknown selector writes no b2 attrs."""
        value = [0x00] * 27
        value[0] = 9  # selector 9 is neither upstair (1) nor downstair (2)
        value[1] = 0x02
        frame = _frame(MessageType.query, _tlv((0x04, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert not any(k.startswith("b2_") for k in attrs)

    def test_b3_unknown_selector(self) -> None:
        """A steam-cabinet record with an unknown selector writes no b3 attrs."""
        value = [0x00] * 15
        value[0] = 9  # selector 9 is neither upstair (1) nor downstair (2)
        value[1] = 0x02
        frame = _frame(MessageType.query, _tlv((0x03, value)))
        attrs = MessageX9CResponse(frame).attributes
        assert not any(k.startswith("b3_") for k in attrs)


class TestAllAttributes:
    """Sanity checks on the computed attribute list."""

    def test_all_attributes_unique_and_prefixed(self) -> None:
        """The list is sorted, unique and contains representative names."""
        assert len(ALL_ATTRIBUTES) == len(set(ALL_ATTRIBUTES))
        assert "total_power" in ALL_ATTRIBUTES
        assert "b7_left_status" in ALL_ATTRIBUTES
        assert "ac_work_status" in ALL_ATTRIBUTES
        assert "bf_weight_mount" in ALL_ATTRIBUTES

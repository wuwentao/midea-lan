"""Test x9b messages."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9b.message import (
    CookingStep,
    MessageQuery,
    MessageQuerySystemTime,
    MessageSetCooking,
    MessageSetParam,
    MessageSetState,
    MessageSetSystemTime,
    MessageX9BBase,
    MessageX9BResponse,
)
from midealan.message import ListTypes, MessageType


def _frame(message_type: int, body: list[int]) -> bytes:
    """Build a full x9b response frame: header + body + trailing checksum."""
    header = [0xAA, 0x00, 0x9B, 0x00, 0x00, 0x00, 0x00, 0x00, ProtocolVersion.V3]
    header.append(message_type)
    return bytes(header + body + [0x00])


def _status_body() -> list[int]:
    """Return a fully populated status body (sub-command 0x01)."""
    body = [0xFF] * 60
    body[0] = 0x01
    body[1] = 0x00  # execute -> ok
    body[2] = 0x00
    body[3] = 0x01
    body[4] = 0x02  # cloudmenuid = 258
    body[5] = 0x23  # totalstep=2 stepnum=3
    body[6] = 0b0000_1010  # probe bit1, turntable bit3
    body[7] = 0x51
    body[8] = 0x00  # work_mode above_tube
    body[9] = 1
    body[10] = 30
    body[11] = 0  # hour/min/sec set
    body[12] = 0x0A  # fire_power high
    body[13] = 0x00
    body[14] = 200  # temperature_above 200
    body[15] = 0x00
    body[16] = 0x00  # temperature_underside 0
    body[17] = 0x00
    body[18] = 0x50  # probe_temperature 80
    body[19] = 3  # steam_quantity
    body[20] = 5  # weight 50 / people 5
    body[22] = 0
    body[23] = 10
    body[24] = 5  # work time
    body[25] = 0
    body[26] = 150  # cur_temperature_above 150
    body[27] = 0
    body[28] = 0  # cur_temperature_underside 0
    body[29] = 0
    body[30] = 70  # cur_probe_temperature 70
    body[31] = 0x03  # work_status work
    body[32] = 0b0010_0011  # lock, door, preheat
    body[33] = 0b0000_0100  # furnace_light on
    body[34] = 0b0010_0000  # ramadan
    body[35] = 0b0010_0000  # hot_wind
    body[47] = 1
    body[48] = 2
    body[49] = 3  # cbs_version V1.2.3
    body[56] = 0b1100_0000  # clean_scale, ota
    body[58] = 0b0000_0011  # clean_sink_ponding, dissipate_heat
    return body


class TestX9BRequests:
    """Test x9b request messages."""

    def test_query_body(self) -> None:
        """Status query body is a single sub-command byte."""
        message = MessageQuery(ProtocolVersion.V3)
        assert message.body_type == ListTypes.X01
        assert list(message.body) == [0x01]

    def test_query_system_time_body(self) -> None:
        """System-time query body is a single sub-command byte."""
        message = MessageQuerySystemTime(ProtocolVersion.V3)
        assert message.body_type == ListTypes.X04
        assert list(message.body) == [0x04]

    def test_base_body_not_implemented(self) -> None:
        """The abstract base raises for a missing body."""
        message = MessageX9BBase(
            ProtocolVersion.V3,
            MessageType.query,
            ListTypes.X01,
        )
        with pytest.raises(NotImplementedError):
            _ = message.body


class TestX9BSetState:
    """Test x9b state-control messages."""

    def test_power_on(self) -> None:
        """Power on writes 0x11 in the status byte."""
        message = MessageSetState(ProtocolVersion.V3)
        message.power = True
        assert list(message.body)[:2] == [0x02, 0x11]

    def test_power_off(self) -> None:
        """Power off writes 0x01 in the status byte."""
        message = MessageSetState(ProtocolVersion.V3)
        message.power = False
        assert list(message.body)[:2] == [0x02, 0x01]

    def test_work_status_known(self) -> None:
        """A known work status maps to its byte."""
        message = MessageSetState(ProtocolVersion.V3)
        message.work_status = "pause"
        assert list(message.body)[1] == 0x06

    def test_work_status_unknown(self) -> None:
        """An unknown work status falls back to 0xFF."""
        message = MessageSetState(ProtocolVersion.V3)
        message.work_status = "bogus"
        assert list(message.body)[1] == 0xFF

    def test_bool_and_int_controls(self) -> None:
        """Bool on/off and integer controls land at their offsets."""
        message = MessageSetState(ProtocolVersion.V3)
        message.lock = True
        message.furnace_light = False
        message.camera = True
        message.screen_luminance = 5
        message.volume = 7
        message.hot_wind = True
        body = list(message.body)
        assert body[2] == 0x01  # lock on
        assert body[3] == 0x00  # furnace_light off
        assert body[4] == 0x01  # camera on
        assert body[8] == 5  # screen luminance
        assert body[9] == 7  # volume
        assert body[12] == 0x01  # hot wind on

    def test_door_open_close_unset(self) -> None:
        """Door accepts open/close and defaults to unchanged."""
        opened = MessageSetState(ProtocolVersion.V3)
        opened.door = "open"
        assert list(opened.body)[5] == 0x01
        closed = MessageSetState(ProtocolVersion.V3)
        closed.door = "close"
        assert list(closed.body)[5] == 0x00
        unset = MessageSetState(ProtocolVersion.V3)
        assert list(unset.body)[5] == 0xFF


class TestX9BSetParam:
    """Test x9b live-parameter messages."""

    def test_no_params(self) -> None:
        """With nothing set the TLV list is empty."""
        message = MessageSetParam(ProtocolVersion.V3)
        assert list(message.body) == [0x03, 0x01, 0x00]

    def test_steam_and_time(self) -> None:
        """Steam and time params are appended with their type bytes.

        A single-field time write leaves the omitted hour/second as the 0xFF
        "unchanged" sentinel so the device does not reset them to zero.
        """
        message = MessageSetParam(ProtocolVersion.V3)
        message.steam_quantity = 4
        message.minute_set = 30
        body = list(message.body)
        assert body[:3] == [0x03, 0x01, 0x02]  # two params
        assert body[3:5] == [0x00, 4]  # steam
        assert body[5:9] == [0x01, 0xFF, 30, 0xFF]  # time h/m/s (h/s unchanged)

    def test_time_all_fields_set(self) -> None:
        """When every clock field is set they are all encoded verbatim."""
        message = MessageSetParam(ProtocolVersion.V3)
        message.hour_set = 10
        message.minute_set = 20
        message.second_set = 30
        body = list(message.body)
        assert body[3:7] == [0x01, 10, 20, 30]

    def test_fire_power_known_and_unknown(self) -> None:
        """Fire power maps known names and defaults unknown to 0xFF."""
        known = MessageSetParam(ProtocolVersion.V3)
        known.fire_power = "medium_power"
        assert list(known.body)[3:5] == [0x02, 0x05]
        unknown = MessageSetParam(ProtocolVersion.V3)
        unknown.fire_power = "nope"
        assert list(unknown.body)[3:5] == [0x02, 0xFF]

    def test_temperature_params(self) -> None:
        """Temperature params encode as big-endian two-byte values."""
        message = MessageSetParam(ProtocolVersion.V3)
        message.temperature = 300  # 0x012C
        message.probe_temperature = 80
        message.temperature_above = 200
        message.temperature_underside = 150
        body = list(message.body)
        assert body[2] == 4  # four params
        assert body[3:7] == [0x03, 0x00, 0x01, 0x2C]  # temperature 300
        assert body[7:11] == [0x04, 0x00, 0x00, 80]  # probe
        assert body[11:17] == [0x05, 0x00, 0x00, 0x00, 0x00, 200]  # above
        assert body[17:23] == [0x05, 0x00, 0x00, 0x01, 0x00, 150]  # underside


class TestX9BSetCooking:
    """Test x9b start-cooking messages."""

    def test_single_step_defaults(self) -> None:
        """An empty recipe still produces a single-step frame."""
        message = MessageSetCooking(ProtocolVersion.V3)
        body = list(message.body)
        assert body[0] == 0x01  # sub-command
        assert body[4] == 0x11  # single-step flag
        assert body[-1] == 0x00

    def test_single_step_full(self) -> None:
        """A fully described single step encodes all its fields."""
        step = CookingStep()
        step.pre_heat = True
        step.turntable = True
        step.hot_wind = True
        step.work_mode = "above_tube"
        step.work_hour = 1
        step.work_minute = 30
        step.work_second = 15
        step.fire_power = "high_power"
        step.temperature = 200
        step.probe_temperature = 80
        step.steam_quantity = 3
        step.weight = 500
        message = MessageSetCooking(ProtocolVersion.V3)
        message.cloudmenuid = 258
        message.steps = [step]
        body = list(message.body)
        assert body[1:4] == [0x00, 0x01, 0x02]  # cloudmenuid 258
        flags = body[5]
        assert flags & 0x01  # pre_heat
        assert flags & 0x02  # probe present
        assert flags & 0x08  # turntable
        assert flags & 0x10  # hot_wind
        assert body[6:8] == [0x51, 0x00]  # work_mode above_tube
        assert body[11] == 0x0A  # fire power high
        assert body[12:16] == [0x00, 200, 0x00, 200]  # both temp pairs
        assert body[19] == 50  # weight / 10

    def test_split_temperatures_and_people(self) -> None:
        """Above/underside overrides and people_number encode correctly."""
        step = CookingStep()
        step.work_mode = "double_tube"
        step.temperature_above = 210
        step.temperature_underside = 160
        step.people_number = 4
        message = MessageSetCooking(ProtocolVersion.V3)
        message.steps = [step]
        body = list(message.body)
        assert body[12:16] == [0x00, 210, 0x00, 160]
        assert body[19] == 4  # people number

    def test_multi_step(self) -> None:
        """A multi-step recipe packs total/start in body[4] and workend."""
        step1 = CookingStep()
        step1.work_mode = "above_tube"
        step1.workend = "wait_next"
        step2 = CookingStep()
        step2.work_mode = "underside_tube"
        message = MessageSetCooking(ProtocolVersion.V3)
        message.stepnum_start = 1
        message.steps = [step1, step2]
        body = list(message.body)
        assert body[4] == (2 << 4) | 1  # total=2, start=1
        # first step workend byte
        assert body[5 + 15] == 0x01  # wait_next in step 1 block

    def test_unknown_work_mode(self) -> None:
        """An unknown work mode encodes as 0xFFFF."""
        step = CookingStep()
        step.work_mode = "does_not_exist"
        message = MessageSetCooking(ProtocolVersion.V3)
        message.steps = [step]
        body = list(message.body)
        assert body[6:8] == [0xFF, 0xFF]


class TestX9BSetSystemTime:
    """Test x9b set-system-time messages."""

    def test_source_and_time(self) -> None:
        """Source name and hh:mm:ss encode with defaults for missing parts."""
        message = MessageSetSystemTime(ProtocolVersion.V3)
        message.sys_time_src = "app"
        message.sys_hour = 12
        body = list(message.body)
        assert body[0] == 0x04
        assert body[1] == 0x01  # app
        assert body[2:5] == [0, 0, 12]  # sec/min default 0, hour 12

    def test_all_unset(self) -> None:
        """With nothing set the time fields are all 0xFF."""
        message = MessageSetSystemTime(ProtocolVersion.V3)
        body = list(message.body)
        assert body[1] == 0xFF  # source unset
        assert body[2:5] == [0xFF, 0xFF, 0xFF]  # time unset
        assert body[5:] == [0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

    def test_unknown_source_and_date(self) -> None:
        """An unknown source is 0xFF; date fields pass through."""
        message = MessageSetSystemTime(ProtocolVersion.V3)
        message.sys_time_src = "bogus"
        message.sys_week = 3
        message.sys_day = 15
        message.sys_month = 6
        message.sys_year = 25
        message.sys_timezone = 8
        body = list(message.body)
        assert body[1] == 0xFF
        assert body[5:] == [3, 15, 6, 25, 8]


class TestX9BResponse:
    """Test x9b response decoding."""

    def test_status_query(self) -> None:
        """A status query response decodes every documented field."""
        response = MessageX9BResponse(_frame(MessageType.query, _status_body()))
        attrs = response.attributes
        assert attrs["execute"] == "ok"
        assert attrs["cloudmenuid"] == 258
        assert attrs["totalstep"] == 2
        assert attrs["stepnum"] == 3
        assert attrs["probe"] == 1
        assert attrs["turntable"] is True
        assert attrs["work_mode"] == "above_tube"
        assert attrs["hour_set"] == 1
        assert attrs["minute_set"] == 30
        assert attrs["fire_power"] == "high_power"
        assert attrs["temperature"] == 200
        assert attrs["temperature_above"] == 200
        assert attrs["probe_temperature"] == 80
        assert attrs["steam_quantity"] == 3
        assert attrs["weight"] == 50
        assert attrs["people_number"] == 5
        assert attrs["cur_temperature"] == 150
        assert attrs["work_status"] == "work"
        assert attrs["power"] is True
        assert attrs["lock"] is True
        assert attrs["door_open"] is True
        assert attrs["pre_heat"] == "work"
        assert attrs["furnace_light"] is True
        assert attrs["high_temperature_lock"] is True
        assert attrs["ramadan"] == 1
        assert attrs["hot_wind"] is True
        assert attrs["cbs_version"] == "V1.2.3"
        assert attrs["clean_scale"] == 1
        assert attrs["ota"] == 1
        assert attrs["clean_sink_ponding"] == 1
        assert attrs["dissipate_heat"] == "work"
        assert attrs["water_status"] == "normal"

    def test_execute_error_codes(self) -> None:
        """The execute byte maps its error codes."""
        for raw, expected in (
            (0x01, "status_nonsupport"),
            (0x02, "function_nonsupport"),
            (0x03, "param_range_error"),
        ):
            body = _status_body()
            body[1] = raw
            response = MessageX9BResponse(_frame(MessageType.query, body))
            assert response.attributes["execute"] == expected

    def test_temperature_underside_fallback(self) -> None:
        """When the above temperature is zero, underside is used."""
        body = _status_body()
        body[13] = 0x00
        body[14] = 0x00  # above 0
        body[15] = 0x00
        body[16] = 190  # underside 190
        body[25] = 0x00
        body[26] = 0x00  # cur above 0
        body[27] = 0x00
        body[28] = 170  # cur underside 170
        response = MessageX9BResponse(_frame(MessageType.query, body))
        assert response.attributes["temperature"] == 190
        assert response.attributes["cur_temperature"] == 170

    def test_water_status_variants(self) -> None:
        """Each water-tank flag maps to its status string."""
        for bit, expected in (
            (2, "lack_box"),
            (3, "lack_water"),
            (4, "change_water"),
        ):
            body = _status_body()
            body[32] = 1 << bit
            response = MessageX9BResponse(_frame(MessageType.query, body))
            assert response.attributes["water_status"] == expected

    def test_pre_heat_end(self) -> None:
        """The preheat-end bit takes priority over preheat."""
        body = _status_body()
        body[32] = 1 << 6  # preheat_end
        response = MessageX9BResponse(_frame(MessageType.query, body))
        assert response.attributes["pre_heat"] == "end"

    def test_missing_and_ff_values(self) -> None:
        """0xFF bytes decode to their documented sentinels."""
        body = _status_body()
        body[9] = 0xFF  # hour_set -> 0
        body[19] = 0xFF  # steam_quantity -> "ff"
        body[20] = 0xFF  # weight/people -> "ff"
        body[12] = 0xFF  # fire_power -> "ff"
        body[7] = 0xFF
        body[8] = 0xFF  # work_mode -> "ff"
        response = MessageX9BResponse(_frame(MessageType.query, body))
        attrs = response.attributes
        assert attrs["hour_set"] == 0
        assert attrs["steam_quantity"] == "ff"
        assert attrs["weight"] == "ff"
        assert attrs["people_number"] == "ff"
        assert attrs["fire_power"] == "ff"
        assert attrs["work_mode"] == "ff"

    def test_short_body_defaults(self) -> None:
        """A truncated status body falls back to version and tail defaults."""
        body = [0xFF] * 46
        body[0] = 0x01
        body[1] = 0x00
        response = MessageX9BResponse(_frame(MessageType.query, body))
        attrs = response.attributes
        assert attrs["cbs_version"] == "V0.0.0"
        assert attrs["clean_scale"] == 0
        assert attrs["ota"] == 0
        assert attrs["clean_sink_ponding"] == 0
        assert attrs["dissipate_heat"] == "off"

    def test_status_body_too_short_skips_decode(self) -> None:
        """A status body shorter than the fixed-offset span decodes to nothing."""
        response = MessageX9BResponse(_frame(MessageType.query, [0x01, 0x00, 0x00]))
        assert response.attributes == {}

    def test_system_time_body_too_short_skips_decode(self) -> None:
        """A truncated system-time body decodes to nothing rather than raising."""
        response = MessageX9BResponse(_frame(MessageType.query, [0x04, 0x01, 30]))
        assert response.attributes == {}

    def test_system_time_response(self) -> None:
        """A system-time response decodes each clock field."""
        body = [0x04, 0x01, 30, 45, 12, 3, 15, 6, 25, 8]
        response = MessageX9BResponse(_frame(MessageType.query, body))
        attrs = response.attributes
        assert attrs["sys_time_src"] == "app"
        assert attrs["sys_second"] == 30
        assert attrs["sys_hour"] == 12
        assert attrs["sys_timezone"] == 8

    def test_system_time_unknown_source_and_ff(self) -> None:
        """Unknown source and 0xFF fields decode to their sentinels."""
        body = [0x04, 0x09, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response = MessageX9BResponse(_frame(MessageType.query, body))
        attrs = response.attributes
        assert attrs["sys_time_src"] == "ff"
        assert attrs["sys_second"] == "ff"

    def test_set_echo_is_status(self) -> None:
        """A set-type report is decoded as a full status record."""
        response = MessageX9BResponse(_frame(MessageType.set, _status_body()))
        assert response.attributes["work_mode"] == "above_tube"

    def test_notify_status(self) -> None:
        """A notify-type report is decoded as a full status record."""
        response = MessageX9BResponse(_frame(MessageType.notify1, _status_body()))
        assert response.attributes["work_status"] == "work"

    def test_unhandled_message_type(self) -> None:
        """An unrelated message type yields no attributes."""
        response = MessageX9BResponse(_frame(MessageType.exception, [0x01, 0x00]))
        assert response.attributes == {}

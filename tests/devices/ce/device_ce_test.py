"""Test CE Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ce import DeviceAttributes, MideaCEDevice
from midealan.devices.ce.message import (
    MessageQuery,
    MessageQueryDailyTimer,
    MessageQueryWeeklyTimer,
    MessageSet,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType

# All distinct status frames attached to midea_ac_lan#1171. They cover response
# types 0x02/0x03/0x04 and are decoded by the merged vendor Lua protocol:
# https://github.com/wuwentao/midea-lua/blob/main/lua/0xCE/T_0000_CE_171120H4_9.lua
COMPACT_STATUS_FRAMES = (
    "aa12ce000000000000020101010014140000f3",
    "aa12ce000000000000030101010014140000f2",
    "aa12ce000000000000030101040015140001ed",
    "aa12ce000000000000030103040015140001eb",
    "aa12ce000000000000030104040015110002ec",
    "aa12ce000000000000030104040015120002eb",
    "aa12ce000000000000030104040015130002ea",
    "aa12ce000000000000030104040015140002e9",
    "aa12ce000000000000030104040114100002ed",
    "aa12ce000000000000030104040114110002ec",
    "aa12ce000000000000030104040114120002eb",
    "aa12ce000000000000030104040114130002ea",
    "aa12ce000000000000030105000015130000ef",
    "aa12ce000000000000030105000015140000ee",
    "aa12ce000000000000030105000114120000f0",
    "aa12ce000000000000030105040015120002ea",
    "aa12ce000000000000030105040015130001ea",
    "aa12ce000000000000030105040015130002e9",
    "aa12ce000000000000030105040015140001e9",
    "aa12ce000000000000030105040015140002e8",
    "aa12ce000000000000030105040015150002e7",
    "aa12ce000000000000030105040114110002eb",
    "aa12ce000000000000030105040114120001eb",
    "aa12ce000000000000030105040114120002ea",
    "aa12ce000000000000030105040114130002e9",
    "aa12ce000000000000040101010014140000f1",
    "aa12ce000000000000040101040015140001ec",
    "aa12ce000000000000040103040015140001ea",
    "aa12ce000000000000040104040015110002eb",
    "aa12ce000000000000040104040015120002ea",
    "aa12ce000000000000040104040015130002e9",
    "aa12ce000000000000040104040015140001e9",
    "aa12ce000000000000040104040015140002e8",
    "aa12ce000000000000040104040114100002ec",
    "aa12ce000000000000040104040114110002eb",
    "aa12ce000000000000040104040114120002ea",
    "aa12ce000000000000040104040114130002e9",
    "aa12ce000000000000040105000015130000ee",
    "aa12ce000000000000040105000015140000ed",
    "aa12ce000000000000040105000114120000ef",
    "aa12ce000000000000040105040015110002ea",
    "aa12ce000000000000040105040015120002e9",
    "aa12ce000000000000040105040015130001e9",
    "aa12ce000000000000040105040015130002e8",
    "aa12ce000000000000040105040015140001e8",
    "aa12ce000000000000040105040015140002e7",
    "aa12ce000000000000040105040015150002e6",
    "aa12ce000000000000040105040114110002ea",
    "aa12ce000000000000040105040114120001ea",
    "aa12ce000000000000040105040114120002e9",
    "aa12ce000000000000040105040114130002e8",
    "aa12ce000000000000040105040114140002e7",
)


class TestMideaCEDevice:
    """Test Midea CE Device."""

    device: MideaCEDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea CE Device setup."""
        self.device = MideaCEDevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="test_model",
            subtype=1,
            customize="",
        )

    def test_initial_attributes(self) -> None:
        """Test initial attributes."""
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.mode] is None
        assert self.device.attributes[DeviceAttributes.child_lock] is False
        assert self.device.attributes[DeviceAttributes.scheduled] is False
        assert self.device.attributes[DeviceAttributes.fan_speed] == 0
        assert self.device.attributes[DeviceAttributes.pm25] is None
        assert self.device.attributes[DeviceAttributes.co2] is None
        assert self.device.attributes[DeviceAttributes.current_humidity] is None
        assert self.device.attributes[DeviceAttributes.current_temperature] is None
        assert self.device.attributes[DeviceAttributes.hcho] is None
        assert self.device.attributes[DeviceAttributes.link_to_ac] is False
        assert self.device.attributes[DeviceAttributes.sleep_mode] is False
        assert self.device.attributes[DeviceAttributes.eco_mode] is False
        assert self.device.attributes[DeviceAttributes.aux_heating] is None
        assert self.device.attributes[DeviceAttributes.powerful_purify] is False
        assert (
            self.device.attributes[DeviceAttributes.filter_cleaning_reminder] is False
        )
        assert self.device.attributes[DeviceAttributes.filter_change_reminder] is False
        assert self.device.attributes[DeviceAttributes.error_code] == 0
        assert self.device.attributes[DeviceAttributes.auto_set] is None
        assert self.device.attributes[DeviceAttributes.silent_mode] is None
        assert self.device.attributes[DeviceAttributes.silence_level] is None
        assert self.device.attributes[DeviceAttributes.mode_raw] is None
        assert self.device.attributes[DeviceAttributes.target_temperature] is None
        assert self.device.attributes[DeviceAttributes.automatic_run_mode] is None
        assert self.device.attributes[DeviceAttributes.daily_timer_1_enabled] is None
        assert self.device.attributes[DeviceAttributes.weekly_timer_weekday] is None
        assert (
            self.device.attributes[DeviceAttributes.weekly_timer_5_end_minute] is None
        )
        assert self.device.compact_protocol is None
        assert self.device.speed_count == 7
        assert self.device.preset_modes == ["normal", "sleep_mode", "eco_mode"]

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    @pytest.mark.parametrize(
        ("message_type", "body_type"),
        [
            (MessageType.query, 0x01),
            (MessageType.set, 0x01),
            (MessageType.notify1, 0x02),
        ],
    )
    def test_general_response(
        self,
        message_type: MessageType,
        body_type: int,
    ) -> None:
        """Test general response with sleep mode and valid sensor values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
        )
        body = bytearray(25)
        body[0] = body_type
        body[1] = 0x80 | 0x20 | 0x40  # power, child_lock, scheduled
        body[2] = 5  # fan_speed
        body[3] = 0x00
        body[4] = 53  # pm25
        body[5] = 0x01
        body[6] = 0x00  # co2 = 256
        body[7] = 0x00
        body[8] = 50  # current_humidity = 5.0
        body[9] = 0x00
        body[10] = 100  # current_temperature = 20.0
        body[11] = 0x00
        body[12] = 200  # hcho = 0.2
        body[17] = 0x01 | 0x02 | 0x08 | 0x10  # link_to_ac, sleep, aux, purify
        body[18] = 0x03  # both filter reminders
        body[19] = 0x02  # aux_heating supported
        body[24] = 7  # error_code
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.child_lock] is True
        assert self.device.attributes[DeviceAttributes.scheduled] is True
        assert self.device.attributes[DeviceAttributes.fan_speed] == 5
        assert self.device.attributes[DeviceAttributes.pm25] == 53
        assert self.device.attributes[DeviceAttributes.co2] == 256
        assert self.device.attributes[DeviceAttributes.current_humidity] == 5.0
        assert self.device.attributes[DeviceAttributes.current_temperature] == 20.0
        assert self.device.attributes[DeviceAttributes.hcho] == 0.2
        assert self.device.attributes[DeviceAttributes.link_to_ac] is True
        assert self.device.attributes[DeviceAttributes.sleep_mode] is True
        assert self.device.attributes[DeviceAttributes.eco_mode] is False
        assert self.device.attributes[DeviceAttributes.powerful_purify] is True
        assert self.device.attributes[DeviceAttributes.filter_cleaning_reminder] is True
        assert self.device.attributes[DeviceAttributes.filter_change_reminder] is True
        assert self.device.attributes[DeviceAttributes.error_code] == 7
        assert self.device.attributes[DeviceAttributes.mode] == "sleep_mode"
        assert self.device.attributes[DeviceAttributes.aux_heating] is True
        assert new_status[DeviceAttributes.mode.value] == "sleep_mode"

    def test_general_response_eco_mode_and_sensor_sentinels(self) -> None:
        """Test general response with ECO mode and 0xFF sensor sentinels."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(25)
        body[0] = 0x01
        body[7] = 0xFF  # no humidity
        body[9] = 0xFF  # no temperature
        body[11] = 0xFF  # no hcho
        body[17] = 0x04  # eco_mode
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.current_humidity] is None
        assert self.device.attributes[DeviceAttributes.current_temperature] is None
        assert self.device.attributes[DeviceAttributes.hcho] is None
        assert self.device.attributes[DeviceAttributes.eco_mode] is True
        assert self.device.attributes[DeviceAttributes.mode] == "eco_mode"

    def test_notify_response(self) -> None:
        """Test notify1 response with body type 0x01."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(13)
        body[0] = 0x01
        body[1] = 0x00
        body[2] = 42  # pm25
        body[3] = 0x00
        body[4] = 120  # co2
        body[5] = 0x00
        body[6] = 80  # current_humidity = 8.0
        body[7] = 0x00
        body[8] = 70  # current_temperature = 5.0
        body[9] = 0x00
        body[10] = 100  # hcho = 0.1
        body[12] = 3  # error_code
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.pm25] == 42
        assert self.device.attributes[DeviceAttributes.co2] == 120
        assert self.device.attributes[DeviceAttributes.current_humidity] == 8.0
        assert self.device.attributes[DeviceAttributes.current_temperature] == 5.0
        assert self.device.attributes[DeviceAttributes.hcho] == 0.1
        assert self.device.attributes[DeviceAttributes.error_code] == 3
        assert self.device.attributes[DeviceAttributes.mode] == "none"

    def test_notify_response_sensor_sentinels(self) -> None:
        """Test notify1 response with 0xFF sensor sentinels."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(13)
        body[0] = 0x01
        body[5] = 0xFF
        body[7] = 0xFF
        body[9] = 0xFF
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.current_humidity] is None
        assert self.device.attributes[DeviceAttributes.current_temperature] is None
        assert self.device.attributes[DeviceAttributes.hcho] is None

    def test_process_message_unhandled_type(self) -> None:
        """Test an unhandled frame does not synthesize a misleading status."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify2],
        )
        body = bytearray(25)
        body[0] = 0x01
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}
        assert self.device.compact_protocol is None

    def test_compact_status_auto_detection_and_timer_queries(self) -> None:
        """Test wire length detection and one-shot optional compact queries."""
        status = self.device.process_message(
            bytes.fromhex("aa12ce000000000000030105040015140002e8"),
        )
        assert self.device.compact_protocol is True
        assert self.device.preset_modes == ["auto", "heat", "cool", "fan"]
        assert status[DeviceAttributes.power] is True
        assert status[DeviceAttributes.auto_set] is False
        assert status[DeviceAttributes.silent_mode] is True
        assert status[DeviceAttributes.mode] == "auto"
        assert status[DeviceAttributes.mode_raw] == 4
        assert status[DeviceAttributes.silence_level] == "level_1"
        assert status[DeviceAttributes.silence_level_raw] == 0
        assert status[DeviceAttributes.target_temperature] == 21
        assert status[DeviceAttributes.current_temperature] == 20
        assert status[DeviceAttributes.error_code] == 0
        assert status[DeviceAttributes.automatic_run_mode] == 2

        queries = self.device.build_query()
        assert len(queries) == 9
        assert isinstance(queries[0], MessageQuery)
        assert isinstance(queries[1], MessageQueryDailyTimer)
        assert all(isinstance(query, MessageQueryWeeklyTimer) for query in queries[2:])
        assert [query.body for query in queries] == [
            bytearray([0x01]),
            bytearray([0x02]),
            bytearray([0x03, 0x01]),
            bytearray([0x03, 0x02]),
            bytearray([0x03, 0x04]),
            bytearray([0x03, 0x08]),
            bytearray([0x03, 0x10]),
            bytearray([0x03, 0x20]),
            bytearray([0x03, 0x40]),
        ]
        assert len(self.device.build_query()) == 1

        self.device.reset_init_query()
        assert len(self.device.build_query()) == 9

    def test_compact_timer_responses_update_read_only_attributes(self) -> None:
        """Test compact daily and weekly timer fields are exposed as attributes."""
        daily_body = bytearray([0x02, 0b10101])
        weekly_body = bytearray([0x03, 0x04, 0b01010])
        for timer_index in range(5):
            timer = [20 + timer_index, timer_index, 5, 10 + timer_index, 55]
            daily_body.extend(timer)
            weekly_body.extend(timer)
        header = bytearray(
            [0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, MessageType.query],
        )

        daily_status = self.device.process_message(
            bytes(header + daily_body + bytearray([0x00])),
        )
        weekly_status = self.device.process_message(
            bytes(header + weekly_body + bytearray([0x00])),
        )

        assert daily_status[DeviceAttributes.daily_timer_1_enabled] is True
        assert daily_status[DeviceAttributes.daily_timer_5_temperature] == 24
        assert daily_status[DeviceAttributes.daily_timer_5_end_minute] == 55
        assert weekly_status[DeviceAttributes.weekly_timer_weekday] == 3
        assert weekly_status[DeviceAttributes.weekly_timer_1_enabled] is False
        assert weekly_status[DeviceAttributes.weekly_timer_2_enabled] is True
        assert weekly_status[DeviceAttributes.weekly_timer_5_temperature] == 24

    def test_compact_protocol_rejects_generic_writes(self) -> None:
        """Test compact detection blocks the incompatible generic CE encoder."""
        self.device.process_message(
            bytes.fromhex("aa12ce000000000000030105040015140002e8"),
        )
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType, match="compact protocol attributes"),
        ):
            self.device.set_attribute(DeviceAttributes.power, False)
        mock_build_send.assert_not_called()

    def test_all_captured_compact_status_frames(self) -> None:
        """Replay every distinct status frame supplied with issue 1171."""
        assert len(COMPACT_STATUS_FRAMES) == 52
        for frame in COMPACT_STATUS_FRAMES:
            status = self.device.process_message(bytes.fromhex(frame))
            assert self.device.compact_protocol is True
            assert DeviceAttributes.power in status
            assert DeviceAttributes.mode_raw in status
            assert DeviceAttributes.target_temperature in status
            assert DeviceAttributes.current_temperature in status
            assert DeviceAttributes.error_code in status

    @pytest.mark.parametrize(
        ("value", "sleep_mode", "eco_mode"),
        [
            ("sleep_mode", True, False),
            ("eco_mode", False, True),
            ("normal", False, False),
        ],
    )
    def test_set_attribute_mode(
        self,
        value: str,
        sleep_mode: bool,
        eco_mode: bool,
    ) -> None:
        """Test set attribute mode."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, value)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.sleep_mode is sleep_mode
            assert message.eco_mode is eco_mode

    def test_set_attribute(self) -> None:
        """Test set attribute sends a set message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_speed.value, 3)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.fan_speed == 3

    def test_set_customize(self) -> None:
        """Test set customize."""
        self.device.set_customize('{"speed_count": 5}')
        assert self.device.speed_count == 5

    def test_set_customize_empty_object(self) -> None:
        """Test set customize with an empty JSON object keeps the default."""
        self.device.set_customize("{}")
        assert self.device.speed_count == 7

    def test_set_customize_empty(self) -> None:
        """Test set customize with empty input keeps the default."""
        self.device.set_customize("")
        assert self.device.speed_count == 7

    def test_set_customize_invalid_json(self) -> None:
        """Test set customize with invalid JSON keeps the default."""
        self.device.set_customize("{")
        assert self.device.speed_count == 7

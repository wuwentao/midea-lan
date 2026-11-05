"""Test CE message."""

from typing import Any

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ce.message import (
    MessageCEBase,
    MessageCEResponse,
    MessageQuery,
    MessageQueryDailyTimer,
    MessageQueryWeeklyTimer,
    MessageSet,
)
from midealan.message import ListTypes, MessageType


class TestMessageCEBase:
    """Test CE Message Base."""

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = MessageCEBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X01,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test CE Message Query."""

    def test_query_body(self) -> None:
        """Test query body contains only the body type."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x01])

    def test_daily_timer_query_body(self) -> None:
        """Test daily timer query body."""
        msg = MessageQueryDailyTimer(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x02])

    @pytest.mark.parametrize(
        ("weekday", "weekday_flag"),
        [(1, 0x01), (4, 0x08), (7, 0x40)],
    )
    def test_weekly_timer_query_body(self, weekday: int, weekday_flag: int) -> None:
        """Test weekly timer query selects one weekday bit."""
        msg = MessageQueryWeeklyTimer(
            protocol_version=ProtocolVersion.V1,
            weekday=weekday,
        )
        assert msg.body == bytearray([0x03, weekday_flag])

    @pytest.mark.parametrize("weekday", [0, 8])
    def test_weekly_timer_query_rejects_invalid_weekday(self, weekday: int) -> None:
        """Test weekly timer query rejects out-of-range weekdays."""
        with pytest.raises(ValueError, match="weekday must be between 1 and 7"):
            MessageQueryWeeklyTimer(
                protocol_version=ProtocolVersion.V1,
                weekday=weekday,
            )


class TestMessageSet:
    """Test CE Message Set."""

    def test_set_body_defaults(self) -> None:
        """Test set body with default values."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_set_body_with_values(self) -> None:
        """Test set body with all flags enabled."""
        msg = MessageSet(protocol_version=ProtocolVersion.V1)
        msg.power = True
        msg.fan_speed = 5
        msg.link_to_ac = True
        msg.sleep_mode = True
        msg.eco_mode = True
        msg.aux_heating = True
        msg.powerful_purify = True
        msg.scheduled = True
        msg.child_lock = True
        assert msg.body == bytearray([0x01, 0x81, 5, 0x1F, 0x01, 0x00, 0x7F])


class TestMessageCEResponse:
    """Test CE response layout detection and parsing."""

    @staticmethod
    def _response(message_type: MessageType, body: bytearray) -> bytes:
        header = bytearray(
            [0xAA] + ([0x00] * 7) + [ProtocolVersion.V1, message_type],
        )
        return bytes(header + body + bytearray([0x00]))

    @pytest.mark.parametrize(
        "message_type",
        [MessageType.set, MessageType.query, MessageType.notify1],
    )
    def test_compact_status(self, message_type: MessageType) -> None:
        """Test the compact X01 layout shared by replies and notifications."""
        response: Any = MessageCEResponse(
            self._response(
                message_type,
                bytearray([0x01, 0x07, 0x04, 0x01, 21, 20, 3, 2]),
            ),
        )
        assert response.compact_protocol is True
        assert response.is_compact_status is True
        assert response.power is True
        assert response.auto_set is True
        assert response.silent_mode is True
        assert response.mode == "auto"
        assert response.mode_raw == 4
        assert response.silence_level == "level_2"
        assert response.silence_level_raw == 1
        assert response.target_temperature == 21
        assert response.current_temperature == 20
        assert response.error_code == 3
        assert response.automatic_run_mode == 2

    def test_compact_status_signed_temperature_and_unknown_enums(self) -> None:
        """Test signed temperature and preservation of unknown raw enum values."""
        response: Any = MessageCEResponse(
            self._response(
                MessageType.query,
                bytearray([0x01, 0x00, 0x00, 0x07, 18, 0xFF, 0, 0]),
            ),
        )
        assert response.current_temperature == -1
        assert response.mode is None
        assert response.mode_raw == 0
        assert response.silence_level is None
        assert response.silence_level_raw == 7

    def test_daily_timer_status(self) -> None:
        """Test all five slots in the compact daily timer reply."""
        body = bytearray([0x02, 0b10101])
        for timer_index in range(5):
            body.extend(
                [20 + timer_index, timer_index, 5, 10 + timer_index, 55],
            )
        response: Any = MessageCEResponse(
            self._response(MessageType.query, body),
        )
        assert response.compact_protocol is True
        assert response.daily_timer_1_enabled is True
        assert response.daily_timer_1_temperature == 20
        assert response.daily_timer_1_start_hour == 0
        assert response.daily_timer_1_start_minute == 5
        assert response.daily_timer_1_end_hour == 10
        assert response.daily_timer_1_end_minute == 55
        assert response.daily_timer_2_enabled is False
        assert response.daily_timer_5_enabled is True
        assert response.daily_timer_5_temperature == 24
        assert response.daily_timer_5_end_hour == 14

    def test_weekly_timer_status(self) -> None:
        """Test weekday and all five slots in a compact weekly timer reply."""
        body = bytearray([0x03, 0x08, 0b10010])
        for timer_index in range(5):
            body.extend(
                [18 + timer_index, timer_index, 15, 12 + timer_index, 45],
            )
        response: Any = MessageCEResponse(
            self._response(MessageType.set, body),
        )
        assert response.compact_protocol is True
        assert response.weekly_timer_weekday == 4
        assert response.weekly_timer_1_enabled is False
        assert response.weekly_timer_2_enabled is True
        assert response.weekly_timer_2_temperature == 19
        assert response.weekly_timer_2_start_hour == 1
        assert response.weekly_timer_2_start_minute == 15
        assert response.weekly_timer_2_end_hour == 13
        assert response.weekly_timer_2_end_minute == 45
        assert response.weekly_timer_5_enabled is True

    def test_weekly_timer_status_without_weekday(self) -> None:
        """Test an empty weekday mask remains unknown."""
        body = bytearray([0x03, 0x00, 0x00] + ([0x00] * 25))
        response: Any = MessageCEResponse(
            self._response(MessageType.query, body),
        )
        assert response.weekly_timer_weekday is None

    @pytest.mark.parametrize(
        ("message_type", "body"),
        [
            (MessageType.query, bytearray([0x01] + ([0x00] * 6))),
            (MessageType.query, bytearray([0x02] + ([0x00] * 25))),
            (MessageType.query, bytearray([0x03] + ([0x00] * 26))),
            (MessageType.notify1, bytearray([0x01] + ([0x00] * 11))),
            (MessageType.notify1, bytearray([0x02] + ([0x00] * 23))),
        ],
    )
    def test_short_body_is_ignored(
        self,
        message_type: MessageType,
        body: bytearray,
    ) -> None:
        """Test truncated known body types do not raise or select a parser."""
        response = MessageCEResponse(self._response(message_type, body))
        assert response.compact_protocol is None
        assert not hasattr(response, "power")

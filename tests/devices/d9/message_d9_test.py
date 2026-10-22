"""Test D9 message."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.d9.message import (
    BUCKET_DB,
    BUCKET_DC,
    D9GeneralMessageBody,
    MessageD9Base,
    MessageD9Response,
    MessagePower,
    MessageProgram,
    MessageQuery,
    MessageStart,
)
from midealan.message import ListTypes, MessageType


class TestMessageD9Base:
    """Test D9 Message Base."""

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = MessageD9Base(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.DB,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test D9 Message Query."""

    def test_query_body_db(self) -> None:
        """Test DB query body contains only the bucket byte."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DB)
        assert msg.body == bytearray([ListTypes.DB])

    def test_query_body_dc(self) -> None:
        """Test DC query body contains only the bucket byte."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DC)
        assert msg.body == bytearray([ListTypes.DC])


class TestMessagePower:
    """Test D9 Message Power."""

    def test_power_body_on(self) -> None:
        """Test power body with power on."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DB)
        msg.power = True
        assert msg.body == bytearray([ListTypes.DB, 0x01, 0x01, 0x01])

    def test_power_body_off(self) -> None:
        """Test power body with power off."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DC)
        assert msg.body == bytearray([ListTypes.DC, 0x01, 0x01, 0x00])


class TestMessageStart:
    """Test D9 Message Start."""

    def test_start_body(self) -> None:
        """Test start body."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DB)
        msg.start = True
        assert msg.body == bytearray([ListTypes.DB, 0x02, 0x01, 0x01])

    def test_pause_body(self) -> None:
        """Test pause body."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DB)
        assert msg.body == bytearray([ListTypes.DB, 0x02, 0x01, 0x00])


class TestMessageProgram:
    """Test D9 Message Program."""

    def test_program_body(self) -> None:
        """Test program body."""
        msg = MessageProgram(protocol_version=ProtocolVersion.V1, bucket=BUCKET_DC)
        msg.program = 0x11
        assert msg.body == bytearray([ListTypes.DC, 0x04, 0x01, 0x11])


class TestD9GeneralMessageBody:
    """Test D9 general message body TLV parsing."""

    def test_parse_db_bucket(self) -> None:
        """Test parsing DB bucket TLV records."""
        body = bytearray(
            [
                ListTypes.DB,
                0x01,
                0x01,
                0x01,  # db_power = 1
                0x04,
                0x01,
                0x02,  # db_program = 2
                0x23,
                0x02,
                0x1E,
                0x00,  # db_remain_time = 30
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_power"] == 1
        assert parsed.attributes["db_program"] == 2
        assert parsed.attributes["db_remain_time"] == 30

    def test_parse_dc_bucket(self) -> None:
        """Test parsing DC bucket TLV records."""
        body = bytearray(
            [
                ListTypes.DC,
                0x01,
                0x01,
                0x01,  # dc_power = 1
                0x13,
                0x01,
                0x02,  # dc_running_status = 2
                0x16,
                0x02,
                0x2D,
                0x00,  # dc_remain_time = 45
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["dc_power"] == 1
        assert parsed.attributes["dc_running_status"] == 2
        assert parsed.attributes["dc_remain_time"] == 45

    def test_parse_appointment_end_time_tomorrow(self) -> None:
        """Test 3-byte appointment end time with tomorrow flag."""
        body = bytearray(
            [
                ListTypes.DB,
                0x35,
                0x03,
                0x1E,
                0x00,
                0x01,  # 30 minutes + tomorrow (1440)
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_appointment_end_time"] == 1470

    def test_parse_appointment_end_time_today(self) -> None:
        """Test 3-byte appointment end time with today flag."""
        body = bytearray(
            [
                ListTypes.DB,
                0x35,
                0x03,
                0x1E,
                0x00,
                0x00,  # 30 minutes + today (no offset)
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_appointment_end_time"] == 30

    def test_parse_appointment_end_time_two_byte_fallback(self) -> None:
        """Test a 2-byte appointment end time decodes as plain minutes."""
        body = bytearray(
            [
                ListTypes.DB,
                0x35,
                0x02,
                0x1E,
                0x00,  # 30 minutes, no day flag
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_appointment_end_time"] == 30

    def test_parse_truncated_record_stops(self) -> None:
        """Test a truncated trailing record is ignored."""
        body = bytearray(
            [
                ListTypes.DB,
                0x01,
                0x01,
                0x01,  # db_power = 1
                0x04,
                0x02,
                0x02,  # db_program declares len 2 but only 1 byte follows
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_power"] == 1
        assert "db_program" not in parsed.attributes

    def test_da_bucket_not_parsed_with_washer_map(self) -> None:
        """Test a DA bucket body is not decoded with the DB washer map."""
        body = bytearray(
            [
                ListTypes.DA,
                0x01,
                0x01,
                0x01,  # would be db_power if wrongly parsed
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes == {}

    def test_empty_body_parses_nothing(self) -> None:
        """Test an empty body yields no attributes."""
        parsed = D9GeneralMessageBody(bytearray([]))
        assert parsed.attributes == {}

    def test_unknown_data_type_ignored(self) -> None:
        """Test unknown data type is skipped without error."""
        body = bytearray(
            [
                ListTypes.DB,
                0xEE,
                0x01,
                0x05,  # unknown type
                0x01,
                0x01,
                0x01,  # db_power = 1
            ],
        )
        parsed = D9GeneralMessageBody(body)
        assert parsed.attributes["db_power"] == 1
        assert len(parsed.attributes) == 1


class TestMessageD9Response:
    """Test D9 message response."""

    def test_response_db(self) -> None:
        """Test response parses DB bucket."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray([ListTypes.DB, 0x01, 0x01, 0x01])
        crc = bytearray([0x00])
        response = MessageD9Response(bytes(header + body + crc))
        assert response.attributes["db_power"] == 1

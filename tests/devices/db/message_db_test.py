"""Test DB message."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.db.message import (
    ControlAttributes,
    DBControls,
    MessageDBBase,
    MessageDBResponse,
    MessagePower,
    MessageQuery,
    MessageStart,
    MessageToshibaDBResponse,
    MessageToshibaQuery,
    toshiba_crc16,
    toshiba_frame,
)
from midealan.exceptions import ValueWrongType
from midealan.message import ListTypes, MessageType

DB_BODY = bytes.fromhex(
    "030101001f0520010300030400400000204f0000db5933b10000002d08080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
DB_RESERVED = bytes.fromhex(
    "040106001f0540060303020400427a01208a0000db5933b10000003f0c080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
NOW = datetime(2026, 10, 12, 15, 24, 30, tzinfo=UTC)


def controls(body: bytes | bytearray = DB_BODY) -> DBControls:
    """Decode a complete anonymous status body."""
    result = DBControls()
    result.update(bytearray(body))
    return result


def frame(
    body: bytes | bytearray,
    message_type: MessageType = MessageType.query,
) -> bytes:
    """Build an identity-free response frame for parser tests."""
    return bytes([0xAA] + [0] * 7 + [ProtocolVersion.V1, message_type]) + body + b"\x00"


def toshiba_body() -> bytearray:
    """Build a complete anonymous T_0008 base report."""
    body = bytearray(47)
    body[2] = 2
    body[3] = 1
    body[9] = 0x82
    body[11] = 10
    body[14] = 40
    body[15] = 0x14
    body[18] = 0x02
    body[22] = 1
    body[23:27] = (125).to_bytes(4, "little")
    return body


class TestMessageDBBase:
    """Test DB Message Base."""

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = MessageDBBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X03,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test DB Message Query."""

    def test_query_body(self) -> None:
        """Test query body contains only the body type."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x03])


class TestMessagePower:
    """Test DB Message Power."""

    def test_power_body_on(self) -> None:
        """Test power body with power on."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1)
        msg.power = True
        assert msg.body == bytearray([0x02, 0x01] + [0xFF] * 20)

    def test_power_body_off(self) -> None:
        """Test power body with power off."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x02, 0x00] + [0xFF] * 20)


class TestMessageStart:
    """Test DB Message Start."""

    def test_start_body(self) -> None:
        """Test start body with washing data."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1)
        msg.start = True
        msg.washing_data = bytearray([0x01, 0x02])
        assert msg.body == bytearray([0x02, 0xFF, 0x01, 0x01, 0x02])

    def test_pause_body(self) -> None:
        """Test pause body."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x02, 0xFF, 0x00])


class TestMessageDBResponse:
    """Test DB status response validation."""

    @pytest.mark.parametrize("message_type", [MessageType.query, MessageType.set])
    def test_status_response(self, message_type: MessageType) -> None:
        """Decode complete query and set status bodies."""
        message = MessageDBResponse(frame(DB_BODY, message_type))
        assert getattr(message, "program", None) == 31
        assert getattr(message, "time_remaining", None) == 79

    @pytest.mark.parametrize(
        "body",
        [DB_BODY[:30], DB_BODY[:1] + bytes([2]) + DB_BODY[2:]],
    )
    def test_invalid_status_response(self, body: bytes) -> None:
        """Leave truncated, acknowledgement and invalid-power bodies undecoded."""
        message = MessageDBResponse(frame(body))
        assert not hasattr(message, "program")


class TestToshibaDBProtocol:
    """Test the common 55AA protocol used by T_0008 DB versions 24 through 33."""

    def test_query_uart_frame_and_crc(self) -> None:
        """Match the Lua query header, length, type, body and CRC byte order."""
        message = MessageToshibaQuery(ProtocolVersion.V1)
        frame_data = message.serialize()
        assert frame_data == bytes.fromhex("55aacc330f0001db000000000000030000e687")
        assert frame_data[:4] == bytes.fromhex("55aacc33")
        assert int.from_bytes(frame_data[4:6], "little") == len(frame_data) - 4
        assert frame_data[7] == 0xDB
        assert frame_data[14:17] == bytes.fromhex("030000")
        assert int.from_bytes(frame_data[-2:], "little") == toshiba_crc16(
            frame_data[:-2],
        )
        assert message._body == bytearray([0])

    def test_response_decodes_common_base_status(self) -> None:
        """Translate Toshiba status, mode, program, time and process fields."""
        message = MessageToshibaDBResponse(bytes(toshiba_frame(toshiba_body(), 3)))
        assert message.power is True
        assert message.start is False
        assert message.status == 1
        assert message.mode == "wash"
        assert message.program == "standard"
        assert message.temperature == 40
        assert message.wash_time == 120
        assert message.dehydration_time == 10
        assert message.progress == 3
        assert message.time_remaining == 125

    @pytest.mark.parametrize(
        ("wash_time", "process_info", "expected_wash", "expected_progress"),
        [
            (12, 0x00, 12, 0),
            (12, 0x04, 12, 2),
            (12, 0x08, 12, 1),
            (12, 0x10, 12, 5),
            (12, 0x20, 12, 8),
        ],
    )
    def test_response_raw_wash_time_and_process_flags(
        self,
        wash_time: int,
        process_info: int,
        expected_wash: int,
        expected_progress: int,
    ) -> None:
        """Preserve minute values and map every common process flag."""
        body = toshiba_body()
        body[9], body[18] = (wash_time, process_info)
        message = MessageToshibaDBResponse(bytes(toshiba_frame(body, 3)))
        assert message.wash_time == expected_wash
        assert message.progress == expected_progress

    @pytest.mark.parametrize(
        "mutation",
        ["crc", "length", "device_type", "frame_type", "short"],
    )
    def test_response_rejects_invalid_frames(self, mutation: str) -> None:
        """Ignore corrupt or unrelated Toshiba UART frames."""
        frame_data = toshiba_frame(toshiba_body(), 3)
        if mutation == "crc":
            frame_data[-1] ^= 1
        elif mutation == "length":
            frame_data[4] ^= 1
        elif mutation == "device_type":
            frame_data[7] = 0xAC
        elif mutation == "frame_type":
            frame_data = toshiba_frame(toshiba_body(), 5)
        else:
            frame_data = frame_data[:10]
        message = MessageToshibaDBResponse(bytes(frame_data))
        assert message.body == bytearray()
        assert not hasattr(message, "program")

    def test_response_rejects_complete_frame_with_short_body(self) -> None:
        """Require all offsets even when the UART envelope and CRC are valid."""
        message = MessageToshibaDBResponse(bytes(toshiba_frame(bytearray([0]), 3)))
        assert message.body == bytearray()


class TestDBControls:
    """Test verified washer parameter decoding and encoding."""

    def test_decode_and_options(self) -> None:
        """Decode verified values and publish dynamic minute options."""
        control = controls()
        assert control.attributes[ControlAttributes.parameter_control_supported] is True
        assert (
            control.attributes[ControlAttributes.parameter_controls_available] is True
        )
        assert (
            control.attributes[ControlAttributes.program_control] == "water_mixed_wash"
        )
        assert control.attributes[ControlAttributes.temperature_control] == "cold"
        assert control.attributes[ControlAttributes.rinse_count] == "2"
        assert control.attributes[ControlAttributes.wash_time_control] == "45"
        assert control.attributes[ControlAttributes.spin_time_control] == "8"
        assert control.options(ControlAttributes.wash_time_control) == [
            "42",
            "45",
            "50",
            "55",
            "60",
        ]
        assert control.options(ControlAttributes.spin_time_control) == [
            "8",
            "9",
            "10",
            "11",
            "12",
        ]
        assert len(control.options(ControlAttributes.program_control)) == 30

    @pytest.mark.parametrize(
        ("attribute", "label", "offset", "raw"),
        [
            (ControlAttributes.program_control, "big", 4, 11),
            (ControlAttributes.program_control, "yoga", 4, 147),
            (ControlAttributes.program_control, "quick_drying_clothes", 4, 145),
            (ControlAttributes.temperature_control, "20", 7, 2),
            (ControlAttributes.spin_speed_control, "1000", 8, 4),
            (ControlAttributes.rinse_count, "3", 6, 63),
            (ControlAttributes.water_level_control, "l2", 5, 2),
            (ControlAttributes.detergent_control, "l4", 11, 5),
            (ControlAttributes.detergent_control, "smart", 11, 4),
        ],
    )
    def test_single_parameter_packets(
        self,
        attribute: str,
        label: str,
        offset: int,
        raw: int,
    ) -> None:
        """Write one measured byte while leaving power and start unchanged."""
        control = controls()
        before = dict(control.attributes)
        message = control.make_message(attribute, label, ProtocolVersion.V1)
        expected = bytearray([2] + [255] * 21)
        expected[offset] = raw
        assert message.body == expected
        assert control.attributes == before

    @pytest.mark.parametrize(
        ("minutes", "request_code"),
        [(42, 4), (45, 0), (50, 1), (55, 2), (60, 3)],
    )
    def test_wash_actual_minutes_and_non_linear_requests(
        self,
        minutes: int,
        request_code: int,
    ) -> None:
        """Encode minus three or increasing five-minute wash steps."""
        body = bytearray(DB_BODY)
        body[9], body[27] = (4, 42)
        control = controls(body)
        assert (
            control.make_message(
                ControlAttributes.wash_time_control,
                str(minutes),
                ProtocolVersion.V1,
            ).body[9]
            == request_code
        )
        body[7], body[9], body[27] = (3, 0, 14)
        control.update(body)
        assert control.options(ControlAttributes.wash_time_control) == [
            "11",
            "14",
            "19",
            "24",
            "29",
        ]

    @pytest.mark.parametrize(
        ("minutes", "request_code"),
        [(8, 3), (9, 4), (10, 0), (11, 1), (12, 2)],
    )
    def test_spin_actual_minutes_and_non_linear_requests(
        self,
        minutes: int,
        request_code: int,
    ) -> None:
        """Encode ten minutes as request zero rather than the shortest option."""
        message = controls().make_message(
            ControlAttributes.spin_time_control,
            str(minutes),
            ProtocolVersion.V1,
        )
        assert message.body[10] == request_code

    @pytest.mark.parametrize(("enabled", "raw"), [(False, 63), (True, 127)])
    def test_forget_free_preserves_parameters_and_cloud_program(
        self,
        enabled: bool,
        raw: int,
    ) -> None:
        """Preserve custom times and cloud-cycle fields in the complete V2 body."""
        report = bytearray(DB_BODY)
        report[9], report[10], report[27], report[28] = (3, 2, 60, 12)
        control = controls(report)
        body = control.make_message(
            ControlAttributes.forget_free,
            enabled,
            ProtocolVersion.V1,
        ).body
        assert len(body) == 54
        assert body[1:3] == b"\xff\xff"
        assert body[3:16] == bytes.fromhex("001f0520010303020400400000")
        assert body[22] == 2
        assert body[24] == raw
        assert body[36:38] == b"\x00\x00"

    @pytest.mark.parametrize(
        ("status", "power", "mode"),
        [(2, 1, 0), (3, 1, 0), (6, 1, 0), (1, 0, 0), (1, 1, 1)],
    )
    def test_rejects_running_off_or_service_mode(
        self,
        status: int,
        power: int,
        mode: int,
    ) -> None:
        """Never construct a parameter write outside an editable state."""
        report = bytearray(DB_BODY)
        report[1], report[2], report[3] = (power, status, mode)
        control = controls(report)
        assert (
            control.attributes[ControlAttributes.parameter_controls_available] is False
        )
        with pytest.raises(ValueError, match="standby"):
            control.make_message(
                ControlAttributes.temperature_control,
                "20",
                ProtocolVersion.V1,
            )

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            (ControlAttributes.temperature_control, True),
            (ControlAttributes.rinse_count, "0"),
            (ControlAttributes.spin_speed_control, "1600"),
            (ControlAttributes.wash_time_control, "99"),
            (ControlAttributes.forget_free, "on"),
        ],
    )
    def test_invalid_options(self, attribute: str, value: str | bool) -> None:
        """Reject unsupported or incorrectly typed options."""
        with pytest.raises((ValueError, ValueWrongType)):
            controls().make_message(attribute, value, ProtocolVersion.V1)

    def test_missing_extended_fields_disable_forget_free(self) -> None:
        """A short report must clear stale extended state and reject writes."""
        control = controls()
        control.update(bytearray(DB_BODY[:31]))
        assert control.attributes[ControlAttributes.forget_free] is None
        with pytest.raises(ValueError, match="unavailable"):
            control.make_message(
                ControlAttributes.forget_free,
                True,
                ProtocolVersion.V1,
            )

    def test_integral_numeric_select(self) -> None:
        """Normalize whole-number floats without a decimal suffix."""
        message = controls().make_message(
            ControlAttributes.temperature_control,
            20.0,
            ProtocolVersion.V1,
        )
        expected = bytearray([2] + [255] * 21)
        expected[7] = 2
        assert message.body == expected

    @pytest.mark.parametrize("report", [b"", DB_BODY[:30], bytes([2]) + DB_BODY[1:]])
    def test_invalid_reports_preserve_snapshot(self, report: bytes) -> None:
        """Ignore truncated reports and acknowledgements after a valid snapshot."""
        control = controls()
        before = dict(control.attributes)
        assert control.update(bytearray(report)) == {}
        assert control.body == DB_BODY
        assert control.attributes == before

    def test_options_before_first_report(self) -> None:
        """Do not invent writable choices before the first status report."""
        control = DBControls()
        assert control.options(ControlAttributes.wash_time_control) == []
        assert control.options(ControlAttributes.spin_time_control) == []
        assert control.options(ControlAttributes.temperature_control) == []
        assert control.options(ControlAttributes.forget_free) == []

    @pytest.mark.parametrize(
        ("request_code", "minutes"),
        [(5, 45), (255, 45), (0, 0), (0, 254), (0, 255), (0, 3)],
    )
    def test_invalid_minute_reports(
        self,
        request_code: int,
        minutes: int,
    ) -> None:
        """Treat unknown codes, sentinels and nonpositive options as read-only."""
        report = bytearray(DB_BODY)
        report[9], report[27] = request_code, minutes
        control = controls(report)
        assert control.attributes[ControlAttributes.wash_time_control] is None
        assert control.options(ControlAttributes.wash_time_control) == []
        with pytest.raises(ValueError, match="unavailable"):
            control.make_message(
                ControlAttributes.wash_time_control,
                "45",
                ProtocolVersion.V1,
            )


class TestDBAppointmentControls:
    """Test verified completion reservation decoding and encoding."""

    @pytest.mark.parametrize("value", [True, 1, "true"])
    def test_reservation_requires_a_deadline(self, value: bool | int | str) -> None:
        """Reject enabling the flag without a completion deadline."""
        with pytest.raises(ValueError, match="Use appointment_finish"):
            controls().make_message(
                ControlAttributes.appointment,
                value,
                ProtocolVersion.V1,
            )

    def test_decode_app_reservation(self) -> None:
        """Decode active reservations with independent availability and finish time."""
        with patch("midealan.devices.db.message.datetime") as clock:
            clock.now.return_value = NOW
            control = controls(DB_RESERVED)
        assert control.attributes[ControlAttributes.appointment] is True
        assert (
            control.attributes[ControlAttributes.parameter_controls_available] is False
        )
        assert (
            control.attributes[ControlAttributes.appointment_controls_available] is True
        )
        finish = control.attributes[ControlAttributes.appointment_finish]
        assert isinstance(finish, str)
        assert datetime.fromisoformat(finish) == NOW.replace(second=0) + timedelta(
            minutes=378 + 138,
        )

    def test_finish_time_subtracts_program_duration(self) -> None:
        """Encode waiting minutes from a timezone-bearing completion deadline."""
        control = controls()
        before = dict(control.attributes)
        target = (NOW.replace(second=0) + timedelta(hours=10)).isoformat()
        with patch("midealan.devices.db.message.datetime") as clock:
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            body = control.make_message(
                ControlAttributes.appointment_finish,
                target,
                ProtocolVersion.V1,
            ).body
        assert body[1] == 255
        assert body[2] == 1
        assert int.from_bytes(body[14:16], "little") == 600 - 79
        assert body[3:12] == DB_BODY[3:12]
        assert len(body) == 54
        assert body[13] == DB_BODY[13] | 2
        assert body[22] == 2
        assert body[35] == 247
        assert body[36:38] == DB_BODY[36:38]
        assert control.attributes == before

    def test_cancel_pauses_and_clears_both_fields(self) -> None:
        """Pause explicitly and clear both reservation representations."""
        control = controls(DB_RESERVED)
        body = control.make_message(
            ControlAttributes.appointment,
            False,
            ProtocolVersion.V1,
        ).body
        assert body[1:3] == bytes([255, 0])
        assert body[14:16] == bytes(2)
        assert body[3:12] == DB_RESERVED[3:12]
        assert body[13] == DB_RESERVED[13] & ~2
        assert body[22] == 2
        assert body[35] == 243
        assert body[36:38] == DB_RESERVED[36:38]
        cancelled = bytearray(DB_RESERVED)
        cancelled[2], cancelled[14], cancelled[15] = (1, 0, 0)
        cancelled[13] &= ~2
        control.update(cancelled)
        assert control.attributes[ControlAttributes.appointment] is False
        assert control.attributes[ControlAttributes.appointment_finish] is None

    @pytest.mark.parametrize(
        "value",
        [True, False, 0, 170.5, "bad", "2026-10-13T08:00:00"],
    )
    def test_invalid_completion_values(self, value: bool | float | str) -> None:
        """Reject invalid types, syntax and naive local timestamps."""
        with pytest.raises((ValueError, ValueWrongType)):
            controls().make_message(
                ControlAttributes.appointment_finish,
                value,
                ProtocolVersion.V1,
            )

    @pytest.mark.parametrize("offset", [-1, 0, 1, 60, 1500])
    def test_invalid_completion_range(self, offset: int) -> None:
        """Reject deadlines without a positive wait or beyond the next 24 hours."""
        target = (NOW.replace(second=0) + timedelta(minutes=offset)).isoformat()
        with patch("midealan.devices.db.message.datetime") as clock:
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            with pytest.raises(ValueError, match="Completion time"):
                controls().make_message(
                    ControlAttributes.appointment_finish,
                    target,
                    ProtocolVersion.V1,
                )

    @pytest.mark.parametrize(("power", "status"), [(0, 1), (1, 2), (1, 3), (1, 7)])
    def test_reservation_rejects_active_cycles(self, power: int, status: int) -> None:
        """Never interrupt a running, paused or faulted cycle."""
        report = bytearray(DB_BODY)
        report[1], report[2] = (power, status)
        control = controls(report)
        assert (
            control.attributes[ControlAttributes.appointment_controls_available]
            is False
        )
        with pytest.raises(ValueError, match="standby"):
            control.make_message(
                ControlAttributes.appointment,
                False,
                ProtocolVersion.V1,
            )

    def test_short_v2_report_disables_reservations(self) -> None:
        """Require cloud-cycle fields before constructing a reservation write."""
        control = controls(DB_BODY[:31])
        assert (
            control.attributes[ControlAttributes.appointment_controls_available]
            is False
        )
        with pytest.raises(ValueError, match="standby"):
            control.make_message(
                ControlAttributes.appointment,
                False,
                ProtocolVersion.V1,
            )

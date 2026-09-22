"""Test FA Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.fa import DeviceAttributes, MideaFADevice
from midealan.devices.fa.message import (
    V6_DEFAULT_SWING_ANGLE,
    V6_DEFAULT_SWING_ANGLE_CODE,
    MessageNewSet,
    MessageQuery,
    MessageSet,
    MessageV6Set,
)
from midealan.message import MessageType


def _build_message(
    protocol_version: int,
    message_type: MessageType,
    body: bytearray,
) -> bytes:
    """Build a full FA response message."""
    header = bytearray(
        [0xAA] + ([0x0] * 7) + [protocol_version] + [message_type],
    )
    return bytes(header + body + bytearray([0x00]))


class TestMideaFADevice:
    """Test Midea FA Device."""

    device: MideaFADevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea FA Device setup."""
        self.device = MideaFADevice(
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
        assert self.device.attributes[DeviceAttributes.child_lock] is False
        assert self.device.attributes[DeviceAttributes.mode] == 0
        assert self.device.attributes[DeviceAttributes.fan_speed] == 0
        assert self.device.attributes[DeviceAttributes.oscillate] is False
        assert self.device.attributes[DeviceAttributes.oscillation_angle] is None
        assert self.device.attributes[DeviceAttributes.tilting_angle] is None
        assert self.device.attributes[DeviceAttributes.oscillation_mode] is None
        assert self.device.attributes[DeviceAttributes.humidify] is False
        assert self.device.attributes[DeviceAttributes.waterions] is False
        assert self.device.attributes[DeviceAttributes.display_on_off] is False

    def test_properties(self) -> None:
        """Test properties."""
        assert self.device.speed_count == 3
        assert self.device.oscillation_angles == [
            "Off",
            "30",
            "60",
            "90",
            "120",
            "180",
            "360",
        ]
        assert self.device.tilting_angles == [
            "Off",
            "30",
            "60",
            "90",
            "120",
            "180",
            "360",
            "+60",
            "-60",
            "40",
        ]
        assert self.device.oscillation_modes == [
            "Off",
            "Oscillation",
            "Tilting",
            "Curve-W",
            "Curve-8",
            "Reserved",
            "Both",
        ]

        assert self.device.preset_modes[0] == "Invalid"
        assert len(self.device.preset_modes) == 21

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_query_response_full_body(self) -> None:
        """Test query response with a full-length body and valid values."""
        body = bytearray(36)
        body[3] = 0x01  # child lock on
        body[4] = 0x03  # power on, mode raw 1 -> Normal
        body[5] = 0x03  # fan speed 3
        body[8] = 0x33  # oscillate on, angle 3 -> 90, mode 1 -> Oscillation
        body[9] = 0x20  # humidify on
        body[19] = 0x40  # display on
        body[25] = 0x02  # tilting angle 2 -> 60
        body[34] = 0x01  # waterions on
        new_status = self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.child_lock] is True
        assert self.device.attributes[DeviceAttributes.mode] == "Normal"
        assert self.device.attributes[DeviceAttributes.fan_speed] == 3
        assert self.device.attributes[DeviceAttributes.oscillate] is True
        assert self.device.attributes[DeviceAttributes.oscillation_angle] == "90"
        assert self.device.attributes[DeviceAttributes.tilting_angle] == "60"
        assert (
            self.device.attributes[DeviceAttributes.oscillation_mode] == "Oscillation"
        )
        assert self.device.attributes[DeviceAttributes.humidify] is True
        assert self.device.attributes[DeviceAttributes.waterions] is True
        assert self.device.attributes[DeviceAttributes.display_on_off] is True
        assert new_status[DeviceAttributes.mode.value] == "Normal"
        assert new_status[DeviceAttributes.fan_speed.value] == 3

    def test_notify_response_out_of_range_values(self) -> None:
        """Test notify1 response with out-of-range values mapped to None."""
        body = bytearray(36)
        body[4] = 0x2B  # power on, mode raw 21 -> out of range
        body[5] = 27  # fan speed out of range -> 0
        body[8] = 0x7F  # oscillate on, angle 7 and mode 7 out of range
        body[25] = 20  # tilting angle out of range
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.notify1, body),
        )
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.mode] is None
        assert self.device.attributes[DeviceAttributes.fan_speed] == 0
        assert self.device.attributes[DeviceAttributes.oscillate] is True
        assert self.device.attributes[DeviceAttributes.oscillation_angle] is None
        assert self.device.attributes[DeviceAttributes.tilting_angle] is None
        assert self.device.attributes[DeviceAttributes.oscillation_mode] is None

    def test_set_response_power_off_short_body(self) -> None:
        """Test set response with a short body and power off."""
        body = bytearray(10)
        body[3] = 0x02  # child lock off
        body[5] = 0x05  # fan speed, ignored as power is off
        new_status = self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.set, body),
        )
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.child_lock] is False
        assert self.device.attributes[DeviceAttributes.fan_speed] == 0
        assert self.device.attributes[DeviceAttributes.oscillate] is False
        assert self.device.attributes[DeviceAttributes.oscillation_angle] == "Off"
        assert self.device.attributes[DeviceAttributes.tilting_angle] == "Off"
        assert self.device.attributes[DeviceAttributes.oscillation_mode] == "Off"
        assert self.device.attributes[DeviceAttributes.humidify] is False
        assert self.device.attributes[DeviceAttributes.waterions] is False
        assert self.device.attributes[DeviceAttributes.display_on_off] is False
        assert new_status[DeviceAttributes.mode.value] == "Invalid"

    def test_unexpected_response(self) -> None:
        """Test notify2 response is not parsed."""
        body = bytearray(10)
        new_status = self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.notify2, body),
        )
        assert new_status == {}

    def test_set_attribute_oscillate(self) -> None:
        """Test set attribute oscillate."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillate.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillate is True
            assert message.oscillation_angle == 3
            assert message.oscillation_mode == 1
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.oscillate.value, False)
            mock_build_send.assert_not_called()

            self.device._attributes[DeviceAttributes.oscillate] = True
            self.device.set_attribute(DeviceAttributes.oscillate.value, False)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillate is False

    def test_protocol_v5_oscillation_commands(self) -> None:
        """Test protocol v5 uses the model-specific set message."""
        self.device.process_message(
            _build_message(
                ProtocolVersion.V1,
                MessageType.query,
                bytearray(52),
            ),
        )
        body = bytearray(52)
        body[23] = 5
        body[51] = 0
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillate.value, True)

        mock_build_send.assert_called_once()
        message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageNewSet)
        assert message.oscillate is True
        assert message.oscillation_angle == 1275
        assert message.oscillation_mode == "Oscillation"
        assert message._body[22] == 5
        assert message._body[50] == 0xFF

    def test_protocol_v5_oscillation_command_branches(self) -> None:
        """Test v5 off, mode, angle, and generic command branches."""
        body = bytearray(52)
        body[8] = 0x02
        body[23] = 5
        body[51] = 12
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        self.device._attributes[DeviceAttributes.oscillate] = True
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillate.value, False)
        message = mock_build_send.call_args[0][0]
        assert message.oscillation_mode == "Oscillation"
        assert message._body[7] == 0x02
        mock_build_send.reset_mock()

        self.device._attributes[DeviceAttributes.oscillation_mode] = "Oscillation"
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Tilting",
            )
        message = mock_build_send.call_args[0][0]
        assert message.oscillation_mode == "Tilting"
        assert message.oscillation_angle == 60
        mock_build_send.reset_mock()

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
        assert mock_build_send.call_args[0][0].power is True

        assert (
            self.device.set_new_oscillation(
                DeviceAttributes.power.value,
                True,
            )
            is None
        )
        self.device._attributes[DeviceAttributes.oscillate] = False
        assert (
            self.device.set_new_oscillation(
                DeviceAttributes.oscillate.value,
                False,
            )
            is None
        )
        assert self.device._legacy_angle_code("invalid", {}) is None
        assert (
            self.device.set_new_oscillation(
                DeviceAttributes.oscillation_mode.value,
                "invalid",
            )
            is None
        )
        self.device._attributes[DeviceAttributes.oscillation_angle] = 60
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.oscillation_angle.value,
                "Off",
            )
        message = mock_build_send.call_args[0][0]
        assert message.oscillation_mode == "Oscillation"
        assert message.oscillation_angle == 0

    def test_process_message_skips_missing_attributes(self) -> None:
        """Test status processing tolerates a response without FA fields."""
        response = type(
            "Response",
            (),
            {
                "message_type": MessageType.query,
                "protocol_version": 0,
                "is_new_protocol": False,
            },
        )()
        with patch(
            "midealan.devices.fa.MessageFAResponse",
            return_value=response,
        ):
            assert self.device.process_message(b"") == {}

    def test_protocol_v5_status_fields(self) -> None:
        """Test protocol v5 status fields are exposed and decoded."""
        body = bytearray(52)
        body[1] = 0x12
        body[2] = 4
        body[3] = 0x01
        body[4] = 0x07
        body[5] = 3
        body[6] = 66
        body[7] = 50
        body[9] = 0x35
        body[12] = 55
        body[13] = 66
        body[15] = 1
        body[16] = 4
        body[19] = 0x40
        body[23] = 5
        body[24] = 0x40
        body[34] = 1
        body[51] = 12

        status = self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        assert status[DeviceAttributes.voice.value] == "open_buzzer"
        assert status[DeviceAttributes.error_code.value] == 0x12
        assert status[DeviceAttributes.target_temperature.value] == 25.0
        assert status[DeviceAttributes.humidity.value] == 50
        assert status[DeviceAttributes.humidify_mode.value] == "1"
        assert status[DeviceAttributes.scene.value] == "sleep"
        assert status[DeviceAttributes.humidify_feedback.value] == 55
        assert status[DeviceAttributes.temperature_feedback.value] == 25.0

    def test_legacy_long_body_does_not_select_protocol_v5(self) -> None:
        """Test a legacy long body is not detected as protocol v5."""
        body = MessageSet(ProtocolVersion.V1, 0).body
        body[23] = 5
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillate.value, True)

        mock_build_send.assert_called_once()
        message = mock_build_send.call_args[0][0]
        assert type(message) is MessageSet
        assert self.device.fa_protocol == 0

    def test_protocol_v5_oscillation_mode_off(self) -> None:
        """Test protocol v5 turns swing off for the Off mode."""
        body = bytearray(52)
        body[8] = 0x02
        body[23] = 5
        body[51] = 0xFF
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Off",
            )

        mock_build_send.assert_called_once()
        message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageNewSet)
        assert message.oscillate is False
        assert message.oscillation_angle == 0
        assert message.oscillation_mode == "Oscillation"
        assert message._body[7] == 0x02
        assert message._body[50] == 0

    def test_protocol_v5_angle_commands_set_direction(self) -> None:
        """Test v5 angle commands include their Lua default direction."""
        body = bytearray(52)
        body[23] = 5
        body[51] = 0
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.oscillation_angle.value,
                "60",
            )
        message = mock_build_send.call_args[0][0]
        assert message.oscillation_mode == "Oscillation"
        assert message._body[7] == 0x02
        assert message._body[50] == 12

        mock_build_send.reset_mock()
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.tilting_angle.value,
                "60",
            )
        message = mock_build_send.call_args[0][0]
        assert message.oscillation_mode == "Tilting"
        assert message._body[7] == 0x04
        assert message._body[24] == 12

    def test_protocol_v6_oscillation_commands(self) -> None:
        """Test protocol v6 uses the 63-byte model-specific set message."""
        body = bytearray(63)
        body[23] = 6
        body[35] = 0x02
        body[51] = 0
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        assert self.device.fa_protocol == 6
        assert self.device.attributes[DeviceAttributes.oscillate] is False

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillate.value, True)

        mock_build_send.assert_called_once()
        message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageV6Set)
        assert message.oscillate is True
        assert message.oscillation_angle == V6_DEFAULT_SWING_ANGLE
        assert message.oscillation_mode == "Oscillation"
        assert len(message.body) == 63
        assert message._body[22] == 6
        assert message._body[34] == 0x02
        assert message._body[50] == V6_DEFAULT_SWING_ANGLE_CODE

    def test_protocol_v6_power_command_uses_v6_body(self) -> None:
        """Test v6 power commands do not fall back to the legacy body."""
        body = bytearray(63)
        body[23] = 6
        self.device.process_message(
            _build_message(ProtocolVersion.V1, MessageType.query, body),
        )

        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)

        message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageV6Set)
        assert len(message.body) == 63
        assert message._body[22] == 6

    def test_set_attribute_oscillation_mode(self) -> None:
        """Test set attribute oscillation mode."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.oscillation_mode.value, "Off")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].oscillate is False
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "Off"
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Oscillation",
            )
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_mode == 1
            assert message.oscillation_angle == 3
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "60"
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Oscillation",
            )
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].oscillation_angle == 2
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.tilting_angle] = "Off"
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Tilting",
            )
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_mode == 2
            assert message.tilting_angle == 3
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.tilting_angle] = "30"
            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "Tilting",
            )
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].tilting_angle == 1
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "Off"
            self.device._attributes[DeviceAttributes.tilting_angle] = "Off"
            self.device.set_attribute(DeviceAttributes.oscillation_mode.value, "Both")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_mode == 6
            assert message.oscillation_angle == 3
            assert message.tilting_angle == 3
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "60"
            self.device._attributes[DeviceAttributes.tilting_angle] = "30"
            self.device.set_attribute(DeviceAttributes.oscillation_mode.value, "Both")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_angle == 2
            assert message.tilting_angle == 1
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_mode] = "Both"
            self.device.set_attribute(DeviceAttributes.oscillation_mode.value, "")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].oscillate is False
            mock_build_send.reset_mock()

            self.device.set_attribute(
                DeviceAttributes.oscillation_mode.value,
                "invalid",
            )
            mock_build_send.assert_not_called()

    def test_set_attribute_oscillation_angle(self) -> None:
        """Test set attribute oscillation angle."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device._attributes[DeviceAttributes.tilting_angle] = "Off"
            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "Off")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].oscillate is False
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "90"
            self.device._attributes[DeviceAttributes.tilting_angle] = "30"
            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "Off")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillate is True
            assert message.oscillation_mode == 2
            assert message.tilting_angle == 1
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = None
            self.device._attributes[DeviceAttributes.tilting_angle] = "Off"
            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "90")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_angle == 3
            assert message.oscillation_mode == 1
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.tilting_angle] = "60"
            self.device._attributes[DeviceAttributes.oscillation_mode] = "Tilting"
            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "90")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_mode == 6
            assert message.tilting_angle == 2
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_mode] = "Both"
            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "120")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_angle == 4
            assert message.oscillation_mode is None
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.oscillation_angle.value, "45")
            mock_build_send.assert_not_called()

    def test_set_attribute_tilting_angle(self) -> None:
        """Test set attribute tilting angle."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device._attributes[DeviceAttributes.oscillation_angle] = "Off"
            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "Off")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].oscillate is False
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.tilting_angle] = "60"
            self.device._attributes[DeviceAttributes.oscillation_angle] = "30"
            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "Off")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillate is True
            assert message.oscillation_mode == 1
            assert message.oscillation_angle == 1
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.tilting_angle] = None
            self.device._attributes[DeviceAttributes.oscillation_angle] = "Off"
            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "60")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.tilting_angle == 2
            assert message.oscillation_mode == 2
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_angle] = "90"
            self.device._attributes[DeviceAttributes.oscillation_mode] = "Oscillation"
            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "60")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.oscillation_mode == 6
            assert message.oscillation_angle == 3
            mock_build_send.reset_mock()

            self.device._attributes[DeviceAttributes.oscillation_mode] = "Both"
            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "40")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.tilting_angle == 9
            assert message.oscillation_mode is None
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.tilting_angle.value, "45")
            mock_build_send.assert_not_called()

    def test_set_attribute_fan_speed(self) -> None:
        """Test set attribute fan speed."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_speed.value, 2)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.fan_speed == 2
            assert message.power is True
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.fan_speed.value, 0)
            mock_build_send.assert_not_called()

            self.device._attributes[DeviceAttributes.power] = True
            self.device.set_attribute(DeviceAttributes.fan_speed.value, 3)
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].fan_speed == 3

    def test_set_attribute_mode(self) -> None:
        """Test set attribute mode."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.mode.value, "Sleep")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].mode == 3
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.mode.value, "Ionic")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].mode == 14
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.mode.value, "invalid")
            mock_build_send.assert_not_called()

    def test_set_attribute_other(self) -> None:
        """Test set attribute for plain attributes."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_build_send.assert_called_once()
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.child_lock.value, True)
            mock_build_send.assert_called_once()
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.humidify.value, True)
            mock_build_send.assert_called_once()
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.waterions.value, True)
            mock_build_send.assert_called_once()
            mock_build_send.reset_mock()

            self.device.set_attribute(DeviceAttributes.display_on_off.value, True)
            mock_build_send.assert_called_once()

    def test_turn_on(self) -> None:
        """Test turn on."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.turn_on()
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.power is True
            assert message.mode is None
            mock_build_send.reset_mock()

            self.device.turn_on(fan_speed=3, mode="Normal")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert message.power is True
            assert message.fan_speed == 3
            assert message.mode == 1
            mock_build_send.reset_mock()

            self.device.turn_on(mode="invalid")
            mock_build_send.assert_called_once()
            assert mock_build_send.call_args[0][0].mode is None

    def test_set_customize(self) -> None:
        """Test set customize."""
        self.device.set_customize('{"speed_count": 5}')
        assert self.device.speed_count == 5

    def test_set_customize_empty_params(self) -> None:
        """Test set customize with an empty JSON object."""
        self.device.set_customize("{}")
        assert self.device.speed_count == 3

    def test_set_customize_invalid(self) -> None:
        """Test set customize with invalid JSON keeps defaults."""
        self.device.set_customize("{")
        assert self.device.speed_count == 3

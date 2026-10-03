"""Test D9 Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.d9 import DeviceAttributes, MideaAppliance, MideaD9Device
from midealan.devices.d9.message import (
    BUCKET_DB,
    BUCKET_DC,
    MessagePower,
    MessageProgram,
    MessageQuery,
    MessageStart,
)
from midealan.exceptions import ValueWrongType
from midealan.message import ListTypes, MessageType


class TestMideaD9Device:
    """Test Midea D9 Device."""

    device: MideaD9Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea D9 Device setup."""
        self.device = MideaD9Device(
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
        """Test initial attributes are all None."""
        for attr in DeviceAttributes:
            assert self.device.attributes[attr] is None

    def test_build_query(self) -> None:
        """Test build query returns one query per bucket."""
        queries = self.device.build_query()
        assert len(queries) == 2
        assert all(isinstance(q, MessageQuery) for q in queries)
        assert queries[0].body_type == ListTypes.DB
        assert queries[1].body_type == ListTypes.DC

    @pytest.mark.parametrize(
        "message_type",
        [MessageType.query, MessageType.set, MessageType.notify1],
    )
    def test_db_response_mapped(self, message_type: MessageType) -> None:
        """Test DB bucket response with mapped values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
        )
        body = bytearray(
            [
                ListTypes.DB,
                0x01,
                0x01,
                0x01,  # db_power = 1
                0x04,
                0x01,
                0x02,  # db_program = fast_wash
                0x24,
                0x01,
                0x02,  # db_running_status = start
                0x23,
                0x02,
                0x1E,
                0x00,  # db_remain_time = 30
            ],
        )
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.db_power] == 1
        assert self.device.attributes[DeviceAttributes.db_program] == "fast_wash"
        assert self.device.attributes[DeviceAttributes.db_running_status] == "start"
        assert self.device.attributes[DeviceAttributes.db_remain_time] == 30

    def test_dc_response_mapped(self) -> None:
        """Test DC bucket response with mapped values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(
            [
                ListTypes.DC,
                0x01,
                0x01,
                0x01,  # dc_power = 1
                0x04,
                0x01,
                0x11,  # dc_program = quick_dry
                0x13,
                0x01,
                0x03,  # dc_running_status = pause
                0x15,
                0x01,
                0x02,  # dc_dry_status = ironing
            ],
        )
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.dc_power] == 1
        assert self.device.attributes[DeviceAttributes.dc_program] == "quick_dry"
        assert self.device.attributes[DeviceAttributes.dc_running_status] == "pause"
        assert self.device.attributes[DeviceAttributes.dc_dry_status] == "ironing"

    def test_response_unmapped_values(self) -> None:
        """Test unmapped enum values fall back to the raw number."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(
            [
                ListTypes.DB,
                0x04,
                0x01,
                0x7D,  # unmapped program
                0x24,
                0x01,
                0x63,  # unmapped running status
            ],
        )
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.db_program] == 0x7D
        assert self.device.attributes[DeviceAttributes.db_running_status] == 0x63

    def test_response_skips_unexposed_record(self) -> None:
        """Test a parsed record that is not an exposed attribute is skipped."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        # db_project_no (0x2B) is parsed by the report map but is not a
        # DeviceAttributes member, so it must be ignored, while db_power is kept.
        body = bytearray(
            [
                ListTypes.DB,
                0x2B,
                0x01,
                0x05,  # db_project_no = 5 (not an exposed attribute)
                0x01,
                0x01,
                0x01,  # db_power = 1
            ],
        )
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert "db_project_no" not in new_status
        assert new_status["db_power"] == 1

    def test_unexpected_body_type(self) -> None:
        """Test response with an unrelated body type updates no attribute."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray([ListTypes.B5, 0x01, 0x01, 0x01])
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

    def test_set_attribute_db_power(self) -> None:
        """Test set DB power sends a power message on the DB bucket."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.db_power.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessagePower)
            assert message.power is True
            assert message.body_type == BUCKET_DB

    def test_set_attribute_dc_power(self) -> None:
        """Test set DC power sends a power message on the DC bucket."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.dc_power.value, False)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessagePower)
            assert message.power is False
            assert message.body_type == BUCKET_DC

    def test_set_attribute_running_status(self) -> None:
        """Test set running status sends a start message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.db_running_status.value,
                True,
            )
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageStart)
            assert message.start is True

    def test_set_attribute_program_by_name(self) -> None:
        """Test set program by name resolves to the raw byte."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.dc_program.value,
                "quick_dry",
            )
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageProgram)
            assert message.program == 0x11
            assert message.body_type == BUCKET_DC

    def test_set_attribute_program_by_value(self) -> None:
        """Test set program by raw int value."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.db_program.value, 0x02)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageProgram)
            assert message.program == 0x02

    def test_set_attribute_program_unknown_name(self) -> None:
        """Test set program with an unknown name does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(
                DeviceAttributes.db_program.value,
                "does_not_exist",
            )
            mock_build_send.assert_not_called()

    @pytest.mark.parametrize("value", [2.5, -1, 256])
    def test_set_attribute_program_invalid_value(self, value: float) -> None:
        """Test set program with fractional/out-of-range value does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.db_program.value, value)
            mock_build_send.assert_not_called()

    def test_set_attribute_not_supported(self) -> None:
        """Test set attribute with an unsupported attribute does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.db_light.value, True)
            mock_build_send.assert_not_called()

    def test_set_attribute_power_wrong_type(self) -> None:
        """Test set power with a non-bool value raises and does not send."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(DeviceAttributes.db_power.value, 5)
        mock_build_send.assert_not_called()

    def test_set_attribute_running_status_wrong_type(self) -> None:
        """Test set running status with a non-bool value raises."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(
                DeviceAttributes.db_running_status.value,
                5,
            )
        mock_build_send.assert_not_called()

    def test_set_attribute_program_bool_ignored(self) -> None:
        """Test set program with a bool value does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.db_program.value, True)
            mock_build_send.assert_not_called()


class TestMideaD9Appliance:
    """Test D9 appliance alias."""

    def test_appliance_is_d9_device(self) -> None:
        """Test the appliance alias subclasses the D9 device."""
        assert issubclass(MideaAppliance, MideaD9Device)

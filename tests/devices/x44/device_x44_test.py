"""Test x44 device."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices import device_selector
from midealan.devices.x44 import DeviceAttributes, MideaX44Device
from midealan.devices.x44.message import MessageQuery, MessageSetScreen
from midealan.exceptions import ValueOutOfRange, ValueWrongType

SCREEN_REPORT = bytes.fromhex(
    "aa1f4400000000000003080201ff000101000000321700080015010004000023",
)


class TestMideaX44Device:
    """Test Midea x44 device."""

    device: MideaX44Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Create a panel device."""
        self.device = MideaX44Device(
            name="panel",
            device_id=212305753821233,
            ip_address="192.168.30.23",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="404M0001",
            subtype=0,
            customize="",
        )

    def test_selector_loads_x44(self) -> None:
        """Test device_selector imports the x44 package."""
        selected = device_selector(
            name="panel",
            device_id=1,
            device_type=DeviceType.X44,
            ip_address="192.168.30.23",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="404M0001",
            subtype=0,
            customize="",
        )
        assert isinstance(selected, MideaX44Device)

    def test_build_query(self) -> None:
        """Test the periodic query is the screen query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_process_message(self) -> None:
        """Test a live report updates exposed attributes."""
        status = self.device.process_message(SCREEN_REPORT)
        assert status[DeviceAttributes.voice_volume] == 50
        assert status[DeviceAttributes.sleep_start_hour] == 23
        assert self.device.attributes[DeviceAttributes.error_code] == 0
        assert DeviceAttributes.panel_status not in status

    def test_process_message_ignores_other_body(self) -> None:
        """Test an appliance response does not clear stored status."""
        self.device.process_message(SCREEN_REPORT)
        other = bytes.fromhex("aa0c44000000000000a00044eb0200000000ff")
        assert self.device.process_message(other) == {}
        assert self.device.attributes[DeviceAttributes.voice_volume] == 50

    def test_set_voice_volume(self) -> None:
        """Test setting voice volume sends one screen command."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.voice_volume, 40)
        message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageSetScreen)
        assert message.values == {DeviceAttributes.voice_volume: 40}

    def test_set_flag(self) -> None:
        """Test a boolean flag is encoded as 0 or 1."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.voice_control, False)
        message = mock_build_send.call_args[0][0]
        assert message.values[DeviceAttributes.voice_control] == 0

    def test_set_read_only_is_ignored(self) -> None:
        """Test read-only fields are not sent."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.error_code, 1)
        mock_build_send.assert_not_called()

    def test_set_wrong_type(self) -> None:
        """Test a fractional value is rejected."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.voice_volume, 1.5)

    def test_set_whole_float(self) -> None:
        """Test a whole-number float is sent as that integer."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.voice_volume, 40.0)
        message = mock_build_send.call_args[0][0]
        assert message.values[DeviceAttributes.voice_volume] == 40

    def test_set_number_rejects_bool_and_text(self) -> None:
        """Test a number field does not accept a switch value or text."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.voice_volume, True)
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.voice_volume, "40")

    def test_set_out_of_range(self) -> None:
        """Test an hour outside 0-23 is rejected."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute(DeviceAttributes.sleep_start_hour, 24)
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute(DeviceAttributes.sleep_start_hour, 24.0)

    def test_process_message_skips_unknown_names(self) -> None:
        """Test names outside the attribute map are ignored."""
        with patch(
            "midealan.devices.x44.MessageX44Response",
        ) as mock_response:
            mock_response.return_value.attributes = {
                "not_a_field": 1,
                DeviceAttributes.voice_volume: 9,
            }
            status = self.device.process_message(b"")
        assert status == {DeviceAttributes.voice_volume: 9}

    def test_set_flag_out_of_set(self) -> None:
        """Test a flag value other than 0 or 1 is rejected."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(DeviceAttributes.left_button, 2)

    def test_set_flag_number(self) -> None:
        """Test a flag also accepts the integer 1."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.left_button, 1)
        message = mock_build_send.call_args[0][0]
        assert message.values[DeviceAttributes.left_button] == 1

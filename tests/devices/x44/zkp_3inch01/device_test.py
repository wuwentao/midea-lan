"""Test ZKP-3INCH01 state and controls."""

from unittest.mock import patch

import pytest

from midealan.device import MideaDevice
from midealan.devices.x44.zkp_3inch01 import DeviceAttributes, ZKP3Inch01Device
from midealan.devices.x44.zkp_3inch01.message import MessageQuery, MessageSetScreen
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from tests.devices.x44 import ZKP_REPORT, identity, select_device


def test_screen_lifecycle_uses_normal_transport() -> None:
    """Verified models keep the connection, polling and send paths of MideaDevice."""
    device = select_device("404M0001")
    with (
        patch.object(MideaDevice, "open", autospec=True) as start,
        patch.object(
            MideaDevice,
            "connect",
            autospec=True,
            return_value=True,
        ) as connect,
        patch.object(MideaDevice, "refresh_status", autospec=True) as refresh,
        patch.object(MideaDevice, "build_send", autospec=True) as send,
    ):
        device.open()
        assert device.connect(check_protocol=True)
        device.refresh_status(check_protocol=True)
        device.set_attribute("brightness", 50)
    start.assert_called_once_with(device)
    connect.assert_called_once_with(device, check_protocol=True)
    refresh.assert_called_once_with(device, check_protocol=True)
    command = send.call_args.args[1]
    assert isinstance(command, MessageSetScreen)
    assert command.values == {"brightness": 50}


class TestZKP3Inch01Device:
    """Test the screen driver directly."""

    device: ZKP3Inch01Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Create a panel device."""
        self.device = ZKP3Inch01Device(customize="", **identity("404M0001"))

    def test_build_query(self) -> None:
        """Test the periodic query is the screen query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_process_message(self) -> None:
        """Test a live report updates exposed attributes."""
        status = self.device.process_message(ZKP_REPORT)
        assert status[DeviceAttributes.voice_volume] == 50
        assert status[DeviceAttributes.sleep_start_hour] == 23
        assert self.device.attributes[DeviceAttributes.error_code] == 0
        assert DeviceAttributes.panel_status not in status

    def test_process_message_ignores_other_body(self) -> None:
        """Test an appliance response does not clear stored status."""
        self.device.process_message(ZKP_REPORT)
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
            "midealan.devices.x44.zkp_3inch01.message.ScreenResponse",
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

"""Test 0x9C Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9c import (
    ATTR_AI_VOICE_MICROPHONE,
    ATTR_AI_VOICE_VOLUME,
    ATTR_TOTAL_LOCK,
    ATTR_TOTAL_POWER,
    MideaX9CDevice,
)
from midealan.devices.x9c.message import (
    MessageQuery,
    MessageSetTotal,
)
from midealan.exceptions import ValueWrongType


class TestMideaX9CDevice:
    """Test Midea 0x9C Device."""

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea 0x9C Device setup."""
        self.device = MideaX9CDevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.100",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="test_model",
            subtype=1,
            customize="test_customize",
        )

    def test_initial_attributes(self) -> None:
        """Every decoder attribute starts as None."""
        assert self.device.attributes[ATTR_TOTAL_POWER] is None
        assert self.device.attributes["b6_gear"] is None
        assert self.device.attributes["ac_work_status"] is None
        assert len(self.device.attributes) > 0

    def test_build_query(self) -> None:
        """build_query returns a single query-all message."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)
        assert list(queries[0].body) == [0x01]

    def test_process_message(self) -> None:
        """process_message copies known attributes into state."""
        with patch("midealan.devices.x9c.MessageX9CResponse") as mock_response:
            mock = mock_response.return_value
            mock.attributes = {
                "total_power": "on",
                "b6_gear": 3,
                "not_a_real_attribute": 1,  # ignored, unknown key
            }
            new_status = self.device.process_message(b"")
        assert new_status["total_power"] == "on"
        assert new_status["b6_gear"] == 3
        assert "not_a_real_attribute" not in new_status
        assert self.device.attributes["total_power"] == "on"
        assert self.device.attributes["b6_gear"] == 3

    def test_set_power(self) -> None:
        """total_power builds and sends a total message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(ATTR_TOTAL_POWER, "on")
        mock_send.assert_called_once()
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetTotal)
        assert message.power == "on"

    def test_set_lock(self) -> None:
        """total_lock accepts a bool."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(ATTR_TOTAL_LOCK, value=True)
        message = mock_send.call_args.args[0]
        assert message.lock is True

    def test_set_lock_wrong_type(self) -> None:
        """total_lock rejects non-bool values."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(ATTR_TOTAL_LOCK, "yes")

    def test_set_microphone(self) -> None:
        """ai_voice_microphone forwards the string state."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(ATTR_AI_VOICE_MICROPHONE, "off")
        message = mock_send.call_args.args[0]
        assert message.ai_voice_microphone == "off"

    def test_set_volume(self) -> None:
        """ai_voice_volume accepts a number."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute(ATTR_AI_VOICE_VOLUME, 6)
        message = mock_send.call_args.args[0]
        assert message.ai_voice_volume == 6

    def test_set_volume_wrong_type(self) -> None:
        """ai_voice_volume rejects bool and non-numeric values."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(ATTR_AI_VOICE_VOLUME, value=True)
        with pytest.raises(ValueWrongType):
            self.device.set_attribute(ATTR_AI_VOICE_VOLUME, "loud")

    def test_set_unknown_attribute_noop(self) -> None:
        """An unsupported attribute produces no message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("b6_gear", 3)
        mock_send.assert_not_called()

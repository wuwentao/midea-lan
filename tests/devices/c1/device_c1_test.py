"""Test C1 device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.c1 import DeviceAttributes, MideaC1Device
from midealan.exceptions import ValueWrongType
from midealan.message import MessageBase, MessageType


class TestMideaC1Device:
    """Test Midea C1 device."""

    @pytest.fixture
    def device_v3(self) -> MideaC1Device:
        """C1 device on V3 transport."""
        return MideaC1Device(
            name="c1",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="00" * 32,
            key="00" * 32,
            device_protocol=ProtocolVersion.V3,
            model="2760001Z",
            subtype=0,
            customize="",
        )

    def test_heating_modes(self, device_v3: MideaC1Device) -> None:
        """Heating mode names match Lua codes (for HA / midea_ac_lan)."""
        assert device_v3.heating_modes == ["user", "activity", "sleep"]

    def test_build_query(self, device_v3: MideaC1Device) -> None:
        """Build the full-status query with the current protocol version."""
        query = device_v3.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x01, 0x01])

    @pytest.mark.parametrize(
        ("power", "heating", "fault", "expected"),
        [
            (True, False, True, "fault"),
            (False, False, False, "off"),
        ],
    )
    def test_derive_status_priority(
        self,
        power: bool,
        heating: bool,
        fault: bool,
        expected: str,
    ) -> None:
        """Fault and power-off states take priority over heating state."""
        assert MideaC1Device._derive_status(power, heating, fault) == expected

    def test_set_customize_temperature_step_and_refresh(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """JSON customize rejects unsupported precision and applies refresh interval."""
        device_v3.set_customize(
            '{"temperature_step": 0.5, "refresh_interval": 45}',
        )
        assert device_v3.temperature_step == 1.0
        assert device_v3._refresh_interval == 45

    def test_set_customize_invalid_json(self, device_v3: MideaC1Device) -> None:
        """Invalid customize JSON is logged; device keeps defaults."""
        device_v3.set_customize("{")
        assert device_v3.temperature_step == 1.0

    def test_set_customize_supported_temperature_step(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """The supported whole-degree temperature step is accepted."""
        device_v3.set_customize('{"temperature_step": 1}')
        assert device_v3.temperature_step == 1.0

    def test_set_customize_invalid_refresh_interval(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """A non-numeric refresh interval leaves the default unchanged."""
        device_v3.set_customize('{"refresh_interval": "invalid"}')
        assert device_v3._refresh_interval == 30

    def test_set_customize_ignores_unrelated_keys(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Unrelated customization keys leave both settings unchanged."""
        device_v3.set_customize('{"other": true}')
        assert device_v3.temperature_step == 1.0
        assert device_v3._refresh_interval == 30

    def test_process_message_syncs_protocol_version(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Incoming frames update _message_protocol_version like other devices."""
        device_v3._message_protocol_version = 0
        body = bytearray(30)
        body[0] = 0x01
        body[2] = 0x01
        header = bytearray(
            [
                0xAA,
                0x00,
                0xC1,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                int(ProtocolVersion.V3),
                int(MessageType.query),
            ],
        )
        frame = header + body
        full = frame + bytes([MessageBase.checksum(frame)])
        device_v3.process_message(bytes(full))
        assert device_v3._message_protocol_version == int(ProtocolVersion.V3)

    def test_process_message_derives_status_running(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Status is running when power and heating are on."""
        body = bytearray(30)
        body[0] = 0x01
        body[2] = 0x05  # power + heating
        header = bytearray(
            [
                0xAA,
                0x00,
                0xC1,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                int(ProtocolVersion.V3),
                int(MessageType.query),
            ],
        )
        frame = header + body
        full = frame + bytes([MessageBase.checksum(frame)])
        device_v3.process_message(bytes(full))
        assert device_v3._attributes[DeviceAttributes.status] == "running"

    def test_set_attribute_heating_mode(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """set_attribute(heating_mode) sends heating segment with current target."""
        device_v3._message_protocol_version = ProtocolVersion.V3
        device_v3._attributes[DeviceAttributes.heating_target_temperature] = 50.0
        with patch.object(device_v3, "build_send") as mock_send:
            device_v3.set_attribute(DeviceAttributes.heating_mode, "sleep")
            mock_send.assert_called_once()
            sent = mock_send.call_args[0][0]
            assert sent.heating_mode == 3
            assert sent.target_temperature == 50.0

    def test_set_attribute_unknown_heating_mode_uses_user_mode(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Unknown heating mode names fall back to the user-mode code."""
        device_v3._attributes[DeviceAttributes.heating_target_temperature] = 45.0
        with patch.object(device_v3, "build_send") as mock_send:
            device_v3.set_attribute(DeviceAttributes.heating_mode, "unknown")
        assert mock_send.call_args[0][0].heating_mode == 1

    def test_set_attribute_heating_target_temperature(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """A numeric target delegates to the heating command builder."""
        with patch.object(device_v3, "set_heating_target_temperature") as mock_set:
            device_v3.set_attribute(
                DeviceAttributes.heating_target_temperature,
                48.5,
            )
        mock_set.assert_called_once_with(48.5)

    def test_set_heating_target_temperature_uses_numeric_gap(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """A numeric configured gap is included in the heating command."""
        device_v3._attributes[DeviceAttributes.heating_gap_temperature] = 3.5
        with patch.object(device_v3, "build_send") as mock_send:
            device_v3.set_heating_target_temperature(50.0, heating_mode=2)
        sent = mock_send.call_args[0][0]
        assert sent.heating_mode == 2
        assert sent.gap_temperature == 3

    def test_set_attribute_ignores_invalid_heating_values(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Invalid target types and mode updates without a target do not send."""
        device_v3._attributes[DeviceAttributes.heating_target_temperature] = None
        with patch.object(device_v3, "build_send") as mock_send:
            device_v3.set_attribute(
                DeviceAttributes.heating_target_temperature,
                "50",
            )
            device_v3.set_attribute(DeviceAttributes.heating_mode, "user")
            device_v3.set_attribute("unknown", True)
        mock_send.assert_not_called()

    def test_set_attribute_power(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """set_attribute(power) sends MessagePower."""
        device_v3._message_protocol_version = ProtocolVersion.V3
        with patch.object(device_v3, "build_send") as mock_send:
            device_v3.set_attribute(DeviceAttributes.power, True)
            mock_send.assert_called_once()
            sent = mock_send.call_args[0][0]
            assert sent.power is True

    def test_set_attribute_power_rejects_non_bool(
        self,
        device_v3: MideaC1Device,
    ) -> None:
        """Non-bool power must not send; bool('off') would otherwise turn on."""
        device_v3._message_protocol_version = ProtocolVersion.V3
        with (
            patch.object(device_v3, "build_send") as mock_send,
            pytest.raises(ValueWrongType),
        ):
            device_v3.set_attribute(DeviceAttributes.power, "off")
        mock_send.assert_not_called()

"""Test E2 Device."""

import logging
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.e2 import (
    DeviceAttributes,
    E2SubType,
    MideaE2Device,
    OldProtocol,
)
from midealan.devices.e2.message import (
    MessagePower,
    MessageQuery,
    MessageSet,
    NewProtocolSet,
)


class TestMideaE2Device:
    """Test Midea E2 Device."""

    def _device(
        self,
        customize: str = "",
        subtype: int = 1,
        model: str = "test_model",
    ) -> MideaE2Device:
        return MideaE2Device(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model=model,
            subtype=subtype,
            customize=customize,
        )

    @pytest.mark.parametrize(
        ("customize", "expected_power"),
        [
            ("", 2000),
            ('{"heating_power_multiplier": 0.75}', 1500),
        ],
    )
    def test_process_message_applies_heating_power_multiplier(
        self,
        customize: str,
        expected_power: int,
    ) -> None:
        """E2 heating power can be calibrated while preserving the default."""

        class FakeMessage:
            heating_power = 2000

        device = self._device(customize)

        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=FakeMessage(),
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.heating_power.value] == expected_power
        assert isinstance(status[DeviceAttributes.heating_power.value], int)
        assert device.attributes[DeviceAttributes.heating_power] == expected_power

    @pytest.mark.parametrize(
        "customize",
        [
            '{"heating_power_multiplier": "nan"}',
            '{"heating_power_multiplier": "inf"}',
            '{"heating_power_multiplier": "-inf"}',
        ],
    )
    def test_process_message_ignores_non_finite_heating_power_multiplier(
        self,
        customize: str,
    ) -> None:
        """Non-finite multipliers are ignored to keep published values valid."""

        class FakeMessage:
            heating_power = 2000

        device = self._device(customize)

        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=FakeMessage(),
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.heating_power.value] == 2000
        assert isinstance(status[DeviceAttributes.heating_power.value], int)
        assert device.attributes[DeviceAttributes.heating_power] == 2000

    def test_default_properties(self) -> None:
        """Test default precision halves and temperature step."""
        device = self._device()
        assert device.precision_halves is False
        assert device.temperature_step == 1.0

    def test_set_customize(self) -> None:
        """Test customize sets old protocol, step and precision halves."""
        device = self._device(
            '{"old_protocol": "false", "temperature_step": 0.5,'
            ' "precision_halves": true}',
        )
        assert device.temperature_step == 0.5
        assert device.precision_halves is True
        assert device._old_protocol == OldProtocol.false

    def test_set_customize_invalid_json(self) -> None:
        """Test invalid customize keeps the defaults."""
        device = self._device("{")
        assert device.precision_halves is False
        assert device.temperature_step == 1.0
        assert device._old_protocol == OldProtocol.auto

    @pytest.mark.parametrize(
        ("value", "subtype", "expected"),
        [
            ("true", 1, OldProtocol.true),
            ("false", 1, OldProtocol.false),
            ("auto", 1, OldProtocol.true),
            ("auto", E2SubType.T85, OldProtocol.true),
            # subtype 100 is neither <= T82 nor in [T85, T36353], so "auto"
            # resolves to OldProtocol.false.
            ("auto", 100, OldProtocol.false),
            (True, 1, OldProtocol.true),
            (False, 1, OldProtocol.false),
            (1, 1, OldProtocol.true),
            (0, 1, OldProtocol.false),
        ],
    )
    def test_normalize_old_protocol(
        self,
        value: str | bool | int,
        subtype: int,
        expected: OldProtocol,
    ) -> None:
        """Test old protocol normalization."""
        device = self._device(subtype=subtype)
        assert device._normalize_old_protocol(value) == expected

    def test_build_query(self) -> None:
        """Test build query."""
        device = self._device()
        queries = device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_make_message_set(self) -> None:
        """Test make message set mirrors the current attributes."""
        device = self._device()
        device._attributes[DeviceAttributes.protection] = True
        device._attributes[DeviceAttributes.whole_tank_heating] = True
        device._attributes[DeviceAttributes.variable_heating] = True
        message = device.make_message_set()
        assert message.protection is True
        assert message.whole_tank_heating is True
        assert message.variable_heating is True
        assert message.target_temperature == 40.0

    @pytest.mark.parametrize(
        "attr",
        [
            DeviceAttributes.heating,
            DeviceAttributes.keep_warm,
            DeviceAttributes.current_temperature,
        ],
    )
    def test_set_attribute_read_only(self, attr: DeviceAttributes) -> None:
        """Test read-only attributes do not send a message."""
        device = self._device()
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(attr.value, True)
            mock_build_send.assert_not_called()

    def test_set_attribute_power(self) -> None:
        """Test power sends a power message."""
        device = self._device()
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.power.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessagePower)
        assert message.power is True

    def test_set_attribute_sends_literal_temperature_by_default(self) -> None:
        """Target temperature is sent literally, matching the literal read."""
        device = self._device()
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.target_temperature.value, 40)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageSet)
        assert message.target_temperature == 40

    def test_set_attribute_precision_halves_doubles_temperature(self) -> None:
        """precision_halves means the device speaks half-degrees on the wire."""
        device = self._device('{"precision_halves": true}')
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.target_temperature.value, 40)
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageSet)
        assert message.target_temperature == 80

    def test_process_message_precision_halves_halves_temperatures(self) -> None:
        """precision_halves halves temperatures on read, mirroring the write."""

        class FakeMessage:
            current_temperature = 130
            target_temperature = 150

        device = self._device('{"precision_halves": true}')
        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=FakeMessage(),
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.current_temperature.value] == 65
        assert status[DeviceAttributes.target_temperature.value] == 75

    def test_process_message_keeps_literal_temperatures_by_default(self) -> None:
        """Without precision_halves the wire value is already Celsius."""

        class FakeMessage:
            current_temperature = 65
            target_temperature = 75

        device = self._device()
        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=FakeMessage(),
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.current_temperature.value] == 65
        assert status[DeviceAttributes.target_temperature.value] == 75

    @pytest.mark.parametrize(
        ("model", "subtype", "expected_bottom", "expected_top"),
        [
            ("510003CN", E2SubType.T255, False, True),
            ("other", E2SubType.T255, True, False),
            ("510003CN", 1, True, False),
        ],
    )
    def test_process_message_reverses_tank_heat_for_verified_device_only(
        self,
        model: str,
        subtype: int,
        expected_bottom: bool,
        expected_top: bool,
    ) -> None:
        """Reverse tank-heater states only for model 510003CN subtype 255."""

        class FakeMessage:
            bottom_heat = True
            top_heat = False

        device = self._device(model=model, subtype=subtype)
        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=FakeMessage(),
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.bottom_heat.value] is expected_bottom
        assert status[DeviceAttributes.top_heat.value] is expected_top

    @pytest.mark.parametrize(
        ("model", "subtype", "one_egg", "two_egg", "expected"),
        [
            ("51032DV5", E2SubType.T123, True, False, False),
            ("51032DV5", E2SubType.T123, False, True, True),
            ("51032DV5", E2SubType.T123, False, False, False),
            ("other", E2SubType.T123, False, True, False),
            ("51032DV5", 1, False, True, False),
        ],
    )
    def test_process_message_maps_double_tank_status_for_verified_device_only(
        self,
        model: str,
        subtype: int,
        one_egg: bool,
        two_egg: bool,
        expected: bool,
    ) -> None:
        """Map one_egg/two_egg only for model 51032DV5 subtype 123."""

        class FakeMessage:
            whole_tank_heating = False
            one_egg = False
            two_egg = False

        message = FakeMessage()
        message.one_egg = one_egg
        message.two_egg = two_egg
        device = self._device(model=model, subtype=subtype)
        with patch(
            "midealan.devices.e2.MessageE2Response",
            return_value=message,
        ):
            status = device.process_message(b"")

        assert status[DeviceAttributes.whole_tank_heating.value] is expected

    def test_temperature_round_trips(self) -> None:
        """What is written must read back unchanged, in both modes."""
        for customize in ("", '{"precision_halves": true}'):
            device = self._device(customize)
            with patch.object(device, "build_send") as mock_build_send:
                device.set_attribute(DeviceAttributes.target_temperature.value, 65)
                on_wire = mock_build_send.call_args[0][0].target_temperature

            class FakeMessage:
                target_temperature = on_wire

            with patch(
                "midealan.devices.e2.MessageE2Response",
                return_value=FakeMessage(),
            ):
                status = device.process_message(b"")
            assert status[DeviceAttributes.target_temperature.value] == 65

    def test_set_attribute_literal_temperature_for_subtype_255(
        self,
    ) -> None:
        """Subtype 255 sends literal Celsius values on the wire."""
        device = self._device(subtype=255)
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.target_temperature.value, 45)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, NewProtocolSet)
        assert message.target_temperature == 45
        assert message._body == bytearray([0x07, 45])

    @pytest.mark.parametrize(
        "attr",
        [
            DeviceAttributes.sterilization,
            DeviceAttributes.screen_off,
            DeviceAttributes.sleep,
        ],
    )
    def test_set_attribute_old_protocol_unsupported_is_ignored(
        self,
        attr: DeviceAttributes,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Old protocol ignores and logs attributes MessageSet cannot carry."""
        device = self._device('{"old_protocol": "true"}')
        with (
            patch.object(device, "build_send") as mock_build_send,
            caplog.at_level(logging.WARNING, logger="midealan.devices.e2"),
        ):
            device.set_attribute(attr.value, True)
        # Without this guard a MessageSet went out with the flag silently
        # dropped, which looks like a working command that does nothing.
        mock_build_send.assert_not_called()
        assert attr.value in caplog.text
        assert '{"old_protocol": false}' in caplog.text

    def test_set_attribute_old_protocol_keeps_supported_attributes(self) -> None:
        """Attributes MessageSet does carry must still use the old message."""
        device = self._device('{"old_protocol": "true"}')
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.whole_tank_heating.value, True)
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, MessageSet)
        assert message.whole_tank_heating is True

    def test_set_attribute_new_protocol(self) -> None:
        """Test new protocol attributes use the new protocol set message."""
        device = self._device('{"old_protocol": "false"}')
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.sterilization.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
        assert isinstance(message, NewProtocolSet)
        assert message.sterilization is True

    @pytest.mark.parametrize("customize", ["", '{"old_protocol": "true"}'])
    def test_set_whole_tank_uses_double_tank_command_for_51032dv5(
        self,
        customize: str,
    ) -> None:
        """51032DV5 subtype 123 always uses the plugin's property 0x19."""
        device = self._device(
            customize,
            model="51032DV5",
            subtype=E2SubType.T123,
        )
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.whole_tank_heating.value, True)
            message = mock_build_send.call_args[0][0]

        assert isinstance(message, NewProtocolSet)
        assert message._body == bytearray([0x19, 0x02])

    def test_set_whole_tank_keeps_existing_command_for_other_devices(self) -> None:
        """Other E2 devices keep the half_heat/whole_heat property 0x04."""
        device = self._device('{"old_protocol": "false"}', subtype=E2SubType.T123)
        with patch.object(device, "build_send") as mock_build_send:
            device.set_attribute(DeviceAttributes.whole_tank_heating.value, True)
            message = mock_build_send.call_args[0][0]

        assert isinstance(message, NewProtocolSet)
        assert message._body == bytearray([0x04, 0x02])

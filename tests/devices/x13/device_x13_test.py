"""Test x13 Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x13 import DeviceAttributes, Midea13Device
from midealan.devices.x13.message import MessageQuery, MessageSet
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import ListTypes, MessageType


class TestMidea13Device:
    """Test Midea x13 Device."""

    device: Midea13Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea x13 Device setup."""
        self.device = Midea13Device(
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
        assert self.device.attributes[DeviceAttributes.brightness] is None
        assert self.device.attributes[DeviceAttributes.color_temperature] is None
        assert self.device.attributes[DeviceAttributes.rgb_color] is None
        assert self.device.attributes[DeviceAttributes.effect] is None
        assert self.device.attributes[DeviceAttributes.power] is False
        # Fan attributes only exist on fan-light models.
        assert DeviceAttributes.fan_power not in self.device.attributes
        assert DeviceAttributes.fan_speed not in self.device.attributes

    def test_effects(self) -> None:
        """Test effects property."""
        assert self.device.effects == [
            "manual",
            "living",
            "reading",
            "mildly",
            "cinema",
            "night",
        ]

    def test_color_temp_range(self) -> None:
        """Test default color temperature range."""
        assert self.device.color_temp_range == [2700, 6500]

    @pytest.mark.parametrize(
        ("kelvin", "midea"),
        [(2700, 0), (6500, 255)],
    )
    def test_kelvin_conversions(self, kelvin: int, midea: int) -> None:
        """Test kelvin/midea conversions."""
        assert self.device.kelvin_to_midea(kelvin) == midea
        assert self.device.midea_to_kelvin(midea) == kelvin

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    @pytest.mark.parametrize(
        ("effect_raw", "expected_effect"),
        [
            (3, "reading"),
            (7, "living"),  # out of range raw value falls back to index 1
            (0, "night"),  # raw 0 becomes index -1, the last effect
        ],
    )
    def test_process_message_main_light(
        self,
        effect_raw: int,
        expected_effect: str,
    ) -> None:
        """Test process message with a main light body updates attributes."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(9)
        body[0] = 0xA4  # main light body type
        body[1] = 100  # brightness
        body[2] = 255  # color temperature
        body[3] = effect_raw
        body[8] = 1  # power on
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.brightness] == 100
        assert self.device.attributes[DeviceAttributes.color_temperature] == 6500
        assert self.device.attributes[DeviceAttributes.effect] == expected_effect
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.rgb_color] is None
        assert new_status[DeviceAttributes.power.value] is True
        assert DeviceAttributes.rgb_color.value not in new_status

    def test_process_message_control_success(self) -> None:
        """Test process message with a successful set response refreshes."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.set],
        )
        body = bytearray(4)
        body[0] = 0x81  # set response body type
        body[1] = 1  # success
        crc = bytearray([0x00])
        with patch.object(self.device, "refresh_status") as mock_refresh:
            new_status = self.device.process_message(bytes(header + body + crc))
            mock_refresh.assert_called_once()
        assert new_status == {"control_success": True}

    def test_process_message_control_failure(self) -> None:
        """Test process message with a failed set response does not refresh."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.set],
        )
        body = bytearray(4)
        body[0] = 0x81  # set response body type
        body[1] = 0  # failure
        crc = bytearray([0x00])
        with patch.object(self.device, "refresh_status") as mock_refresh:
            new_status = self.device.process_message(bytes(header + body + crc))
            mock_refresh.assert_not_called()
        assert new_status == {"control_success": False}

    def test_process_message_unhandled(self) -> None:
        """Test process message with an unhandled message updates nothing."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(9)
        body[0] = 0x24  # unhandled body type
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

    def test_set_attribute_brightness(self) -> None:
        """Test set attribute brightness sends the value."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.brightness.value, 100)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.brightness == 100

    def test_set_attribute_color_temperature(self) -> None:
        """Test set attribute color temperature converts kelvin to midea."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.color_temperature.value, 6500)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.color_temperature == 255

    def test_set_attribute_effect(self) -> None:
        """Test set attribute effect converts the name to its index."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.effect.value, "reading")
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.effect == 2

    def test_set_attribute_effect_invalid(self) -> None:
        """Test set attribute with an unknown effect sends the raw value."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.effect.value, -1)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.effect == -1

    def test_set_attribute_power(self) -> None:
        """Test set attribute power sends the value."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.power is True

    def test_set_attribute_not_settable(self) -> None:
        """Test set attribute with a read-only attribute does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.rgb_color.value, 1)
            mock_build_send.assert_not_called()

    def test_set_customize(self) -> None:
        """Test set customize overrides the color temperature range."""
        with patch.object(self.device, "update_all") as mock_update_all:
            self.device.set_customize('{"color_temp_range_kelvin": [3000, 6000]}')
            mock_update_all.assert_called_once_with(
                {"color_temp_range": [3000, 6000]},
            )
        assert self.device.color_temp_range == [3000, 6000]

    def test_set_customize_without_key(self) -> None:
        """Test set customize without the key keeps the default range."""
        with patch.object(self.device, "update_all") as mock_update_all:
            self.device.set_customize('{"other": 1}')
            mock_update_all.assert_called_once_with(
                {"color_temp_range": [2700, 6500]},
            )
        assert self.device.color_temp_range == [2700, 6500]

    def test_set_customize_invalid(self) -> None:
        """Test set customize with invalid JSON keeps the default range."""
        with patch.object(self.device, "update_all") as mock_update_all:
            self.device.set_customize("{")
            mock_update_all.assert_called_once_with(
                {"color_temp_range": [2700, 6500]},
            )
        assert self.device.color_temp_range == [2700, 6500]

    def test_set_attribute_fan_ignored_on_legacy_model(self) -> None:
        """Test fan controls are ignored on models without a fan."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_power.value, True)
            self.device.set_attribute(DeviceAttributes.fan_speed.value, 41)
            mock_build_send.assert_not_called()


class TestMidea13FanLightDevice:
    """Test Midea x13 fan-light Device."""

    device: Midea13Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea x13 fan-light Device setup."""
        self.device = Midea13Device(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="M0200008",
            subtype=0,
            customize="",
        )

    def test_initial_attributes(self) -> None:
        """Test initial attributes include the fan state."""
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.fan_power] is False
        assert self.device.attributes[DeviceAttributes.fan_speed] == 0

    def test_effects_follow_lua_protocol(self) -> None:
        """Test the fan-light model exposes its protocol scene names."""
        assert self.device.effects == ["manual", "work", "eating", "night", "film"]

    def test_process_message_fan_light(self) -> None:
        """Test process message parses the fan-light layout."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(11)
        body[0] = 0xA4  # main light body type
        body[1] = 0  # brightness
        body[2] = 127  # color temperature
        body[3] = 1  # effect raw value
        body[5] = 1  # light power
        body[6] = 41  # fan speed
        body[8] = 0  # constant on fan-light models
        body[10] = 1  # fan power
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.effect] == "manual"
        assert self.device.attributes[DeviceAttributes.fan_speed] == 41
        assert self.device.attributes[DeviceAttributes.fan_power] is True
        assert new_status[DeviceAttributes.fan_speed.value] == 41
        assert new_status[DeviceAttributes.fan_power.value] is True

    @pytest.mark.parametrize(
        ("effect", "expected"),
        [("manual", 1), ("work", 2), ("eating", 3), ("night", 4), ("film", 5)],
    )
    def test_set_effect(self, effect: str, expected: int) -> None:
        """Test fan-light scenes use register 0x02 and Lua values 1..5."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.effect.value, effect)
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.serialize()[10:-1] == bytearray(
                [ListTypes.X02, expected, 0x00, 0x00, 0x00, 0x00, 0x00],
            )
            assert message.body_type == ListTypes.X02

    def test_process_message_truncated_fan_light(self) -> None:
        """Test a truncated report updates only the present fan speed."""
        self.device._attributes[DeviceAttributes.fan_speed] = 55
        self.device._attributes[DeviceAttributes.fan_power] = True
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(10)  # stops before the fan power byte (offset 10)
        body[0] = 0xA4  # main light body type
        body[1] = 0  # brightness
        body[2] = 127  # color temperature
        body[3] = 1  # effect raw value
        body[5] = 1  # light power
        body[6] = 41  # fan speed
        body[8] = 0  # constant on fan-light models
        new_status = self.device.process_message(
            bytes(header + body + bytearray([0x00])),
        )
        assert self.device.attributes[DeviceAttributes.fan_speed] == 41
        assert self.device.attributes[DeviceAttributes.fan_power] is True
        assert new_status[DeviceAttributes.fan_speed.value] == 41
        assert DeviceAttributes.fan_power.value not in new_status

    @pytest.mark.parametrize(("value", "expected"), [(True, 0x01), (False, 0x00)])
    def test_set_fan_power(self, value: bool, expected: int) -> None:
        """Test set fan power sends the fan power register."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_power.value, value)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.fan_light is True
            assert message.fan_power is value
            assert message._body[0] == expected

    @pytest.mark.parametrize("speed", [1, 41, 100])
    def test_set_fan_speed(self, speed: int) -> None:
        """Test set fan speed sends the fan speed register."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_speed.value, speed)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageSet)
            assert message.fan_light is True
            assert message.fan_speed == speed

    @pytest.mark.parametrize("speed", [0, 101])
    def test_set_fan_speed_out_of_range(self, speed: int) -> None:
        """Test set fan speed rejects values outside 1..100."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueOutOfRange),
        ):
            self.device.set_attribute(DeviceAttributes.fan_speed.value, speed)
        mock_build_send.assert_not_called()

    @pytest.mark.parametrize("speed", ["fast", 41.5, True])
    def test_set_fan_speed_wrong_type(self, speed: bool | float | str) -> None:
        """Test set fan speed rejects non-integral values."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(DeviceAttributes.fan_speed.value, speed)
        mock_build_send.assert_not_called()

    def test_set_fan_power_wrong_type(self) -> None:
        """Test set fan power rejects non-bool values."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(DeviceAttributes.fan_power.value, 1)
        mock_build_send.assert_not_called()


class TestMidea13FanLightSubtypeGate:
    """Fan-light support is limited to model M0200008 with subtype 0."""

    device: Midea13Device

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea x13 fan-light device opened with a non-zero subtype."""
        self.device = Midea13Device(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="M0200008",
            subtype=1,
            customize="",
        )

    def test_other_subtype_keeps_legacy_layout(self) -> None:
        """Test other subtypes do not get the fan-light layout."""
        assert self.device._fan_light is False
        assert DeviceAttributes.fan_power not in self.device.attributes
        assert DeviceAttributes.fan_speed not in self.device.attributes

    def test_fan_attribute_ignored_for_other_subtype(self) -> None:
        """Test fan controls are ignored for other subtypes."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.fan_power.value, True)
            self.device.set_attribute(DeviceAttributes.fan_speed.value, 41)
        mock_build_send.assert_not_called()

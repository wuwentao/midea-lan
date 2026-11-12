"""Test x9b Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9b import (
    DeviceAttributes,
    MideaAppliance,
    MideaX9BDevice,
    X9BProfileRule,
)
from midealan.devices.x9b.message import (
    MessageQuery,
    MessageQueryCameraOta,
    MessageSetParam,
    MessageSetState,
    X9BProfile,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType


class TestMideaX9BDevice:
    """Test Midea x9b Device."""

    device: MideaX9BDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea x9b Device setup."""
        self.device = MideaX9BDevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="test_model",
            subtype=1,
            customize="test_customize",
        )

    def test_appliance_alias(self) -> None:
        """The MideaAppliance alias resolves to the device class."""
        assert issubclass(MideaAppliance, MideaX9BDevice)

    def test_initial_attributes(self) -> None:
        """All decoder attributes start as None."""
        assert "work_mode" in self.device.attributes
        assert self.device.attributes["work_mode"] is None
        assert DeviceAttributes("work_mode") == "work_mode"

    def test_build_query(self) -> None:
        """An unknown identity adds the safe camera-family probe."""
        queries = self.device.build_query()
        assert len(queries) == 2
        assert isinstance(queries[0], MessageQuery)
        assert isinstance(queries[1], MessageQueryCameraOta)

    @pytest.mark.parametrize(
        ("model", "sn8", "expected"),
        [
            ("test_model", "700ZG249", X9BProfile.CAMERA),
            ("700zg249", None, X9BProfile.CAMERA),
            ("S50E5", None, X9BProfile.CAMERA),
            ("70100277", None, X9BProfile.EXTENDED),
            ("0BS5053W", None, X9BProfile.LEGACY),
            ("unlisted", None, X9BProfile.UNKNOWN),
        ],
    )
    def test_profile_selection(
        self,
        model: str,
        sn8: str | None,
        expected: X9BProfile,
    ) -> None:
        """Known model/SN8 identities choose their shared wire profile."""
        device = self._make_device(model=model, sn8=sn8)
        assert device.profile == expected

    def test_profile_rule_can_share_multiple_subtypes(self) -> None:
        """One future profile rule can cover several verified subtypes."""
        rule = X9BProfileRule(
            profile=X9BProfile.CAMERA,
            subtypes=frozenset({101, 102}),
        )
        assert rule.match(sn8=None, model="unknown", subtype=101) == "subtype=101"
        assert rule.match(sn8=None, model="unknown", subtype=102) == "subtype=102"
        assert rule.match(sn8=None, model="unknown", subtype=103) is None

    def test_known_non_camera_profile_skips_camera_probe(self) -> None:
        """Verified legacy/extended identities only receive the common query."""
        device = self._make_device(model="70100277")
        queries = device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_known_camera_profile_includes_camera_probe(self) -> None:
        """A verified camera identity receives both read-only queries."""
        device = self._make_device(model="S50E5")
        queries = device.build_query()
        assert [type(query) for query in queries] == [
            MessageQuery,
            MessageQueryCameraOta,
        ]

    def test_process_message(self) -> None:
        """Known attributes are copied and unknown keys ignored."""
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.profile = self.device.profile
            instance.attributes = {
                "work_mode": "above_tube",
                "lock": "on",
                "not_an_attribute": 1,
            }
            new_status = self.device.process_message(b"")
        assert new_status == {"work_mode": "above_tube", "lock": "on"}
        assert self.device.attributes["work_mode"] == "above_tube"
        assert "not_an_attribute" not in self.device.attributes

    def test_distinctive_response_promotes_unknown_profile(self) -> None:
        """A camera OTA response can classify an identity absent from the table."""
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.profile = X9BProfile.CAMERA
            instance.attributes = {"camera_version": "V1.2.3"}
            self.device.process_message(b"camera response")
        assert self.device.profile == X9BProfile.CAMERA
        mock_response.assert_called_once_with(
            b"camera response",
            profile=X9BProfile.UNKNOWN,
        )

    def test_camera_profile_controls_are_read_only(self) -> None:
        """Unverified camera-family controls are ignored until device testing."""
        device = self._make_device(model="700ZG249")
        with patch.object(device, "build_send") as mock_send:
            device.set_attribute("power", value=True)
        mock_send.assert_not_called()

    def test_set_power(self) -> None:
        """Setting power sends a state message with the power flag."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("power", value=True)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetState)
        assert message.power is True

    def test_set_work_status(self) -> None:
        """Setting work status sends a state message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("work_status", "pause")
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetState)
        assert message.work_status == "pause"

    def test_set_door(self) -> None:
        """Setting door sends a state message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("door", "open")
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetState)
        assert message.door == "open"

    def test_set_bool_control(self) -> None:
        """A bool control (lock) routes through a state message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("lock", value=True)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetState)
        assert message.lock is True

    def test_set_bool_control_wrong_type(self) -> None:
        """A non-bool value for a bool control raises."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute("hot_wind", 5)

    def test_set_int_control(self) -> None:
        """An int control (volume) routes through a state message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("volume", 7)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetState)
        assert message.volume == 7

    def test_set_int_control_wrong_type(self) -> None:
        """A non-numeric value for an int control raises."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute("screen_luminance", value=True)

    def test_set_fire_power_param(self) -> None:
        """fire_power routes through a parameter message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("fire_power", "high_power")
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetParam)
        assert message.fire_power == "high_power"

    def test_set_temp_param(self) -> None:
        """Temperature routes through a parameter message."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("temperature", 180)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetParam)
        assert message.temperature == 180

    def test_set_param_wrong_type(self) -> None:
        """A non-numeric value for a numeric parameter raises."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute("temperature", value=True)

    def test_set_u16_param_out_of_range(self) -> None:
        """A u16 parameter above 65535 raises instead of wrapping."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("temperature", 70000)

    def test_set_u16_param_negative(self) -> None:
        """A negative u16 parameter raises instead of wrapping."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("temperature", -1)

    def test_set_byte_param_out_of_range(self) -> None:
        """A single-byte parameter above the settable max raises before encoding."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("steam_quantity", 300)

    def test_set_int_control_out_of_range(self) -> None:
        """A single-byte state control above the settable max raises."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("volume", 256)

    def test_set_byte_param_rejects_sentinel(self) -> None:
        """0xFF (the leave-unchanged sentinel) is not a settable byte param."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("steam_quantity", 0xFF)

    def test_set_int_control_rejects_sentinel(self) -> None:
        """0xFF (the leave-unchanged sentinel) is not a settable byte control."""
        with pytest.raises(ValueOutOfRange):
            self.device.set_attribute("volume", 0xFF)

    def test_set_byte_param_accepts_settable_max(self) -> None:
        """0xFE (one below the sentinel) is the largest settable byte value."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("steam_quantity", 0xFE)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetParam)
        assert message.steam_quantity == 0xFE

    def test_set_int_control_fractional(self) -> None:
        """A fractional value for an int control raises instead of truncating."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute("volume", 7.5)

    def test_set_param_fractional(self) -> None:
        """A fractional numeric parameter raises instead of truncating."""
        with pytest.raises(ValueWrongType):
            self.device.set_attribute("temperature", 42.7)

    def test_set_param_integral_float(self) -> None:
        """An integral float (180.0) is accepted and coerced to int."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("temperature", 180.0)
        message = mock_send.call_args.args[0]
        assert isinstance(message, MessageSetParam)
        assert message.temperature == 180

    def test_set_unknown_attribute_noop(self) -> None:
        """An unknown attribute sends nothing."""
        with patch.object(self.device, "build_send") as mock_send:
            self.device.set_attribute("does_not_exist", 1)
        mock_send.assert_not_called()

    @staticmethod
    def _make_device(
        *,
        model: str,
        sn8: str | None = None,
        subtype: int = 1,
    ) -> MideaX9BDevice:
        """Build a device with a selectable identity."""
        return MideaX9BDevice(
            name="Profile Device",
            device_id=2,
            ip_address="192.168.1.2",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model=model,
            subtype=subtype,
            sn8=sn8,
            customize="",
        )

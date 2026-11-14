"""Test x9b Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x9b import (
    DeviceAttributes,
    MideaAppliance,
    MideaX9BDevice,
)
from midealan.devices.x9b.message import (
    MessageQuery,
    MessageQueryCameraOta,
    MessageSetCooking,
    MessageSetParam,
    MessageSetState,
    X9BProtocol,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


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
        """An unidentified device receives every known protocol probe."""
        queries = self.device.build_query()
        assert [type(query) for query in queries] == [
            MessageQueryCameraOta,
            MessageQuery,
        ]
        assert self.device.protocol_flags == {
            X9BProtocol.STATUS: False,
            X9BProtocol.CAMERA: False,
        }

    @pytest.mark.parametrize(
        ("model", "sn8", "subtype"),
        [
            ("test_model", "700ZG249", 1),
            ("S50E5", None, 99),
            ("70100277", None, 2),
            ("0BS5053W", None, 3),
            ("unlisted", None, 255),
        ],
    )
    def test_identity_does_not_select_protocol(
        self,
        model: str,
        sn8: str | None,
        subtype: int,
    ) -> None:
        """SN8, model and subtype never decide a wire protocol."""
        device = self._make_device(model=model, sn8=sn8, subtype=subtype)
        assert device.protocol_flags == {
            X9BProtocol.STATUS: False,
            X9BProtocol.CAMERA: False,
        }
        assert [type(query) for query in device.build_query()] == [
            MessageQueryCameraOta,
            MessageQuery,
        ]

    def test_status_capability_stops_unknown_camera_probe(self) -> None:
        """A standard response leaves only the standard query for refreshes."""
        self.device._protocol_flags[X9BProtocol.STATUS] = True
        assert [type(query) for query in self.device.build_query()] == [MessageQuery]

    def test_camera_capability_keeps_both_queries(self) -> None:
        """A camera response keeps its extension query and common status query."""
        self.device._protocol_flags[X9BProtocol.CAMERA] = True
        assert [type(query) for query in self.device.build_query()] == [
            MessageQueryCameraOta,
            MessageQuery,
        ]

    def test_process_message(self) -> None:
        """Status attributes and the status capability come from the response."""
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.response_protocol = X9BProtocol.STATUS
            instance.detected_protocols = {X9BProtocol.STATUS}
            instance.protocol_evidence = {X9BProtocol.STATUS: "status frame"}
            instance.attributes = {
                "work_mode": "above_tube",
                "lock": "on",
                "not_an_attribute": 1,
            }
            new_status = self.device.process_message(b"")
            self.device.process_message(b"")
        assert new_status == {"work_mode": "above_tube", "lock": "on"}
        assert self.device.attributes["work_mode"] == "above_tube"
        assert "not_an_attribute" not in self.device.attributes
        assert self.device.supports_protocol(X9BProtocol.STATUS)
        assert self.device._last_response_protocol == X9BProtocol.STATUS

    def test_distinctive_response_enables_camera_flag(self) -> None:
        """A camera OTA response enables the camera capability for any identity."""
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.response_protocol = X9BProtocol.CAMERA
            instance.detected_protocols = {X9BProtocol.CAMERA}
            instance.protocol_evidence = {X9BProtocol.CAMERA: "camera OTA frame"}
            instance.attributes = {
                "ota_status_hardware": "camera",
                "camera_version": "V1.2.3",
            }
            self.device.process_message(b"camera response")
        assert self.device.supports_protocol(X9BProtocol.CAMERA)
        assert [type(query) for query in self.device.build_query()] == [
            MessageQueryCameraOta,
            MessageQuery,
        ]
        mock_response.assert_called_once_with(
            b"camera response",
            camera_protocol=False,
        )

    def test_camera_protocol_controls_are_read_only(self) -> None:
        """Unverified camera-family controls are ignored until device testing."""
        device = self._make_device(model="unlisted")
        device._protocol_flags[X9BProtocol.CAMERA] = True
        with patch.object(device, "build_send") as mock_send:
            device.set_attribute("power", value=True)
        mock_send.assert_not_called()

    def test_camera_protocol_blocks_direct_set_commands(self) -> None:
        """The outbound path also blocks structured and custom set commands."""
        device = self._make_device(model="unlisted")
        device._protocol_flags[X9BProtocol.CAMERA] = True
        with patch.object(device, "send_message") as mock_send:
            device.build_send(MessageSetCooking(ProtocolVersion.V3))
            mock_send.assert_not_called()
            device.send_command(MessageType.set, bytearray([0x01]))
            mock_send.assert_not_called()
            device.build_send(MessageQuery(ProtocolVersion.V3), query=True)
            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs == {"query": True}

    def test_camera_detection_clears_standard_only_attributes(self) -> None:
        """Values decoded before camera detection do not survive the switch."""
        self.device._attributes["probe"] = 1
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.response_protocol = X9BProtocol.CAMERA
            instance.detected_protocols = {X9BProtocol.CAMERA}
            instance.protocol_evidence = {X9BProtocol.CAMERA: "camera OTA frame"}
            instance.attributes = {
                "ota_status_hardware": "camera",
                "camera_version": "V1.2.3",
            }
            status = self.device.process_message(b"camera response")
        assert status["probe"] is None
        assert self.device.attributes["probe"] is None

    def test_query_response_validation_uses_capability_response(self) -> None:
        """Heartbeats do not validate an x9b query without a matching flag."""
        self.device._last_response_protocol = None
        assert (
            self.device._is_query_response_valid(MessageQuery(ProtocolVersion.V3))
            is False
        )
        assert (
            self.device._is_query_response_valid(
                MessageQueryCameraOta(ProtocolVersion.V3),
            )
            is False
        )
        self.device._last_response_protocol = X9BProtocol.STATUS
        assert (
            self.device._is_query_response_valid(MessageQuery(ProtocolVersion.V3))
            is True
        )
        assert (
            self.device._is_query_response_valid(
                MessageQueryCameraOta(ProtocolVersion.V3),
            )
            is False
        )
        assert self.device._is_query_response_valid(
            MessageSetState(ProtocolVersion.V3),
        )

    def test_build_send_non_query_uses_common_transport(self) -> None:
        """Standard SET traffic still uses the inherited transport path."""
        with patch.object(self.device, "send_message"):
            self.device.build_send(MessageSetState(ProtocolVersion.V3))

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

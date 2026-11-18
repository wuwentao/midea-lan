"""Test x9b Device."""

from unittest.mock import Mock, patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MessageResult, MideaDevice, ResponseException
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
from midealan.exceptions import SocketException, ValueOutOfRange, ValueWrongType
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
            MessageQuery,
            MessageQueryCameraOta,
        ]
        assert self.device.protocol_flags == {
            X9BProtocol.STATUS: False,
            X9BProtocol.STATUS_V4: False,
            X9BProtocol.CAMERA_OTA: False,
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
            X9BProtocol.STATUS_V4: False,
            X9BProtocol.CAMERA_OTA: False,
        }
        assert [type(query) for query in device.build_query()] == [
            MessageQuery,
            MessageQueryCameraOta,
        ]

    def test_status_capability_stops_unknown_camera_probe(self) -> None:
        """A standard response leaves only the standard query for refreshes."""
        self.device._protocol_flags[X9BProtocol.STATUS] = True
        assert [type(query) for query in self.device.build_query()] == [MessageQuery]

    def test_camera_ota_capability_keeps_both_queries(self) -> None:
        """A camera OTA response keeps its extension and common status queries."""
        self.device._protocol_flags[X9BProtocol.CAMERA_OTA] = True
        assert [type(query) for query in self.device.build_query()] == [
            MessageQuery,
            MessageQueryCameraOta,
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

    def test_distinctive_response_enables_camera_ota_flag(self) -> None:
        """A camera OTA response enables only its independent query capability."""
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.response_protocol = X9BProtocol.CAMERA_OTA
            instance.detected_protocols = {X9BProtocol.CAMERA_OTA}
            instance.protocol_evidence = {
                X9BProtocol.CAMERA_OTA: "camera OTA frame",
            }
            instance.attributes = {
                "ota_status_hardware": "camera",
                "camera_version": "V1.2.3",
            }
            self.device.process_message(b"camera response")
        assert self.device.supports_protocol(X9BProtocol.CAMERA_OTA)
        assert not self.device.supports_protocol(X9BProtocol.STATUS_V4)
        assert [type(query) for query in self.device.build_query()] == [
            MessageQuery,
            MessageQueryCameraOta,
        ]
        mock_response.assert_called_once_with(
            b"camera response",
            status_v4_protocol=False,
        )

    def test_status_v4_controls_are_read_only(self) -> None:
        """Unverified VALUE_VERSION=4 controls are ignored until device testing."""
        device = self._make_device(model="unlisted")
        device._protocol_flags[X9BProtocol.STATUS_V4] = True
        with patch.object(device, "build_send") as mock_send:
            device.set_attribute("power", value=True)
        mock_send.assert_not_called()

    def test_status_v4_blocks_direct_set_commands(self) -> None:
        """The outbound path also blocks V4 structured and custom set commands."""
        device = self._make_device(model="unlisted")
        device._protocol_flags[X9BProtocol.STATUS_V4] = True
        with patch.object(device, "send_message") as mock_send:
            device.build_send(MessageSetCooking(ProtocolVersion.V3))
            mock_send.assert_not_called()
            device.send_command(MessageType.set, bytearray([0x01]))
            mock_send.assert_not_called()
            device.build_send(MessageQuery(ProtocolVersion.V3), query=True)
            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs == {"query": True}

    def test_camera_ota_alone_does_not_block_standard_set(self) -> None:
        """An OTA extension response alone does not select the V4 write layout."""
        self.device._protocol_flags[X9BProtocol.CAMERA_OTA] = True
        with patch.object(self.device, "send_message") as mock_send:
            self.device.build_send(MessageSetState(ProtocolVersion.V3))
        mock_send.assert_called_once()

    def test_status_v4_detection_clears_standard_only_attributes(self) -> None:
        """Values decoded before V4 layout detection do not survive the switch."""
        self.device._attributes["probe"] = 1
        with patch("midealan.devices.x9b.MessageX9BResponse") as mock_response:
            instance = mock_response.return_value
            instance.protocol_version = ProtocolVersion.V3
            instance.response_protocol = X9BProtocol.STATUS
            instance.detected_protocols = {
                X9BProtocol.STATUS,
                X9BProtocol.STATUS_V4,
            }
            instance.protocol_evidence = {
                X9BProtocol.STATUS: "status frame",
                X9BProtocol.STATUS_V4: "complete V4 status tail",
            }
            instance.attributes = {
                "ota_status_hardware": "camera",
                "camera_version": "V1.2.3",
            }
            status = self.device.process_message(b"V4 status response")
        assert status["probe"] is None
        assert self.device.attributes["probe"] is None
        assert [type(query) for query in self.device.build_query()] == [MessageQuery]

    def test_tcp_reconnect_preserves_detected_status_layout(self) -> None:
        """Socket recovery keeps positive flags and does not repeat silent probes."""
        self.device._protocol_flags[X9BProtocol.STATUS] = True
        self.device._protocol_flags[X9BProtocol.STATUS_V4] = True
        self.device._unsupported_protocol = ["MessageQueryCameraOta"]
        self.device.close_socket()
        assert self.device.protocol_flags == {
            X9BProtocol.STATUS: True,
            X9BProtocol.STATUS_V4: True,
            X9BProtocol.CAMERA_OTA: False,
        }
        assert self.device._unsupported_protocol == []
        assert [type(query) for query in self.device.build_query()] == [MessageQuery]

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
        self.device._probe_response_protocols.add(X9BProtocol.STATUS)
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
        self.device._probe_response_protocols = {X9BProtocol.CAMERA_OTA}
        assert self.device._is_query_response_valid(
            MessageQueryCameraOta(ProtocolVersion.V3),
        )
        assert self.device._is_query_response_valid(
            MessageSetState(ProtocolVersion.V3),
        )

    def test_probe_wait_ignores_heartbeat_until_matching_status_response(self) -> None:
        """A heartbeat does not finish a probe before its status frame arrives."""
        self.device._active_probe_protocol = X9BProtocol.STATUS
        self.device._probe_response_protocols.clear()
        self.device._socket = Mock()
        self.device._socket.recv.side_effect = [b"heartbeat", b"status"]

        def parse_message(message: bytes) -> MessageResult:
            if message == b"status":
                self.device._probe_response_protocols.add(X9BProtocol.STATUS)
            return MessageResult.SUCCESS

        with patch.object(self.device, "parse_message", side_effect=parse_message):
            self.device._await_query_reply()

        assert self.device._socket.recv.call_count == 2
        self.device._socket.settimeout.assert_called_with(10)
        assert self.device._is_query_response_valid(
            MessageQuery(ProtocolVersion.V3),
        )

    def test_probe_wait_deadline_is_not_extended_by_heartbeat(self) -> None:
        """Repeated unrelated frames cannot extend a checked query indefinitely."""
        self.device._active_probe_protocol = X9BProtocol.STATUS
        self.device._probe_response_protocols.clear()
        self.device._socket = Mock()
        self.device._socket.recv.return_value = b"heartbeat"
        with (
            patch.object(
                self.device,
                "parse_message",
                return_value=MessageResult.SUCCESS,
            ),
            patch(
                "midealan.devices.x9b.time.monotonic",
                side_effect=[0.0, 0.0, 6.0],
            ),
            pytest.raises(TimeoutError),
        ):
            self.device._await_query_reply()
        self.device._socket.recv.assert_called_once_with(512)

    def test_probe_wait_propagates_parse_error_without_matching_response(self) -> None:
        """Malformed replies retain common transport error handling."""
        self.device._active_probe_protocol = X9BProtocol.STATUS
        self.device._probe_response_protocols.clear()
        self.device._socket = Mock()
        self.device._socket.recv.return_value = b"invalid"
        with (
            patch.object(
                self.device,
                "parse_message",
                return_value=MessageResult.ERROR,
            ),
            pytest.raises(ResponseException),
        ):
            self.device._await_query_reply()

    def test_probe_wait_uses_common_behavior_without_x9b_probe(self) -> None:
        """Non-X9B probes continue to use the common waiter."""
        with patch.object(MideaDevice, "_await_query_reply") as await_reply:
            self.device._active_probe_protocol = None
            self.device._await_query_reply()
        await_reply.assert_called_once_with()

    def test_build_send_non_probe_query_clears_active_probe(self) -> None:
        """A non-protocol query does not inherit a preceding x9b probe family."""
        self.device._active_probe_protocol = X9BProtocol.STATUS
        with patch.object(self.device, "send_message"):
            self.device.build_send(MessageQuery(ProtocolVersion.V3), query=True)
            self.device.build_send(
                MessageQueryCameraOta(ProtocolVersion.V3),
                query=True,
            )
            self.device.build_send(
                MessageQuery(ProtocolVersion.V3),
                query=True,
            )
            self.device.build_send(
                MessageSetState(ProtocolVersion.V3),
                query=True,
            )
        assert self.device._active_probe_protocol is None

    def test_probe_wait_raises_if_socket_is_missing_or_closed(self) -> None:
        """Socket failure remains visible to the common reconnect loop."""
        self.device._active_probe_protocol = X9BProtocol.STATUS
        self.device._socket = None
        with pytest.raises(SocketException):
            self.device._await_query_reply()
        self.device._socket = Mock()
        self.device._socket.recv.return_value = b""
        with pytest.raises(ConnectionResetError):
            self.device._await_query_reply()

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

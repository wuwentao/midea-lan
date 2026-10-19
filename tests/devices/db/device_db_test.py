"""Test DB Device."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MideaDeviceInitKwargs
from midealan.devices.db import DeviceAttributes, MideaDBDevice
from midealan.devices.db.message import (
    MessageParameters,
    MessagePower,
    MessageQuery,
    MessageStart,
    MessageToshibaQuery,
    toshiba_frame,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType

DB_BODY = bytes.fromhex(
    "030101001f0520010300030400400000204f0000db5933b10000002d08080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
DB_RESERVED = bytes.fromhex(
    "040106001f0540060303020400427a01208a0000db5933b10000003f0c080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
BASE_ARGS: MideaDeviceInitKwargs = {
    "name": "Test laundry appliance",
    "device_id": 1,
    "ip_address": "192.0.2.1",
    "port": 6444,
    "token": "00",
    "key": "00",
    "device_protocol": ProtocolVersion.V1,
    "model": "test",
    "subtype": 0,
}


def device_args(
    model: str,
    subtype: int,
    *,
    sn8: str | None = None,
    manufacturer_code: str | None = None,
    cloud_name: str | None = None,
) -> MideaDeviceInitKwargs:
    """Return typed connection arguments for a DB device."""
    args = BASE_ARGS.copy()
    args["model"] = model
    args["subtype"] = subtype
    if sn8 is not None:
        args["sn8"] = sn8
    if manufacturer_code is not None:
        args["manufacturer_code"] = manufacturer_code
    if cloud_name is not None:
        args["cloud_name"] = cloud_name
    return args


def frame(
    body: bytes | bytearray,
    message_type: MessageType = MessageType.query,
) -> bytes:
    """Use an identity-free header; direct decoders do not validate its checksum."""
    return bytes([0xAA] + [0] * 7 + [ProtocolVersion.V1, message_type]) + body + b"\x00"


def verified_washer(body: bytes | bytearray | None = None) -> MideaDBDevice:
    """Create the verified profile without opening a socket."""
    device = MideaDBDevice(
        customize="",
        **device_args("38131140", 13145),
    )
    if body is not None:
        device.process_message(frame(body))
    return device


def toshiba_body() -> bytearray:
    """Build an anonymous Toshiba base-status body."""
    body = bytearray(47)
    body[2] = 2
    body[3] = 1
    body[9] = 0x82
    body[11] = 10
    body[14] = 40
    body[15] = 0x14
    body[18] = 0x02
    body[22] = 1
    body[23:27] = (125).to_bytes(4, "little")
    return body


class TestMideaDBDevice:
    """Test Midea DB Device."""

    device: MideaDBDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea DB Device setup."""
        self.device = MideaDBDevice(
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
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.start] is False
        assert self.device.attributes[DeviceAttributes.status] is None
        assert self.device.attributes[DeviceAttributes.mode] is None
        assert self.device.attributes[DeviceAttributes.program] is None
        assert self.device.attributes[DeviceAttributes.water_level] is None
        assert self.device.attributes[DeviceAttributes.temperature] is None
        assert self.device.attributes[DeviceAttributes.dehydration_speed] is None
        assert self.device.attributes[DeviceAttributes.wash_time] is None
        assert self.device.attributes[DeviceAttributes.dehydration_time] is None
        assert self.device.attributes[DeviceAttributes.detergent] is None
        assert self.device.attributes[DeviceAttributes.softener] is None
        assert self.device.attributes[DeviceAttributes.washing_data] == bytearray([])
        assert self.device.attributes[DeviceAttributes.progress] is None
        assert self.device.attributes[DeviceAttributes.stains] is None
        assert self.device.attributes[DeviceAttributes.time_remaining] is None
        assert self.device.attributes[DeviceAttributes.wash_time_value] is None
        assert self.device.attributes[DeviceAttributes.dehydration_time_value] is None
        assert self.device.attributes[DeviceAttributes.dirty_degree] is None

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    @pytest.mark.parametrize(
        "message_type",
        [MessageType.query, MessageType.set],
    )
    def test_query_set_response(self, message_type: MessageType) -> None:
        """Test query/set response with mapped values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
        )
        body = bytearray(31)
        body[0] = 0x03  # Body type
        body[1] = 0x01  # power
        body[2] = 0x02  # status start
        body[3] = 0x00  # mode normal
        body[4] = 0x02  # program fast_wash
        body[5] = 0x03  # water level High
        body[7] = 0x04  # temperature 40
        body[8] = 0x05  # dehydration speed 1200
        body[9] = 0x28  # wash time
        body[10] = 0x0A  # dehydration time
        body[11] = 0x01  # detergent
        body[12] = 0x02  # softener
        body[16] = 0x01  # progress Spin
        body[17] = 30  # time remaining low byte
        body[18] = 1  # time remaining high byte
        body[26] = 0x03  # stains
        body[27] = 0x28  # wash time value
        body[28] = 0x0A  # dehydration time value
        body[30] = 0x04  # dirty degree
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.start] is True
        assert self.device.attributes[DeviceAttributes.status] == "start"
        assert self.device.attributes[DeviceAttributes.mode] == "normal"
        assert self.device.attributes[DeviceAttributes.program] == "fast_wash"
        assert self.device.attributes[DeviceAttributes.water_level] == "high"
        assert self.device.attributes[DeviceAttributes.temperature] == "40"
        assert self.device.attributes[DeviceAttributes.dehydration_speed] == "1200"
        assert self.device.attributes[DeviceAttributes.wash_time] == 0x28
        assert self.device.attributes[DeviceAttributes.dehydration_time] == 0x0A
        assert self.device.attributes[DeviceAttributes.detergent] == 1
        assert self.device.attributes[DeviceAttributes.softener] == 2
        assert self.device.attributes[DeviceAttributes.washing_data] == body[3:16]
        assert self.device.attributes[DeviceAttributes.progress] == "spin"
        assert self.device.attributes[DeviceAttributes.stains] == 3
        assert self.device.attributes[DeviceAttributes.time_remaining] == 286
        assert self.device.attributes[DeviceAttributes.wash_time_value] == 0x28
        assert self.device.attributes[DeviceAttributes.dehydration_time_value] == 0x0A
        assert self.device.attributes[DeviceAttributes.dirty_degree] == 4

    def test_notify1_response_unmapped_values(self) -> None:
        """Test notify1 response with unmapped values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(31)
        body[0] = 0x04  # Body type
        body[2] = 9  # unmapped status
        body[3] = 5  # unmapped mode
        body[4] = 0x41  # unmapped program
        body[5] = 0x06  # unmapped water level
        body[7] = 0x10  # unmapped temperature
        body[8] = 0x09  # unmapped dehydration speed
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.start] is False
        assert self.device.attributes[DeviceAttributes.status] == 9
        assert self.device.attributes[DeviceAttributes.mode] == 5
        assert self.device.attributes[DeviceAttributes.program] == 0x41
        assert self.device.attributes[DeviceAttributes.water_level] == 6
        assert self.device.attributes[DeviceAttributes.temperature] == 0x10
        assert self.device.attributes[DeviceAttributes.dehydration_speed] == 9
        assert self.device.attributes[DeviceAttributes.progress] == "idle"
        assert self.device.attributes[DeviceAttributes.time_remaining] is None

    def test_unexpected_response(self) -> None:
        """Test notify1 response with unexpected body type updates no attribute."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(31)
        body[0] = 0x03  # unexpected body type for notify1
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

    def test_set_attribute_power(self) -> None:
        """Test set attribute power sends a power message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessagePower)
            assert message.power is True

    def test_set_attribute_start(self) -> None:
        """Test set attribute start sends a start message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.start.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageStart)
            assert message.start is True
            assert message.washing_data == bytearray([])

    def test_set_attribute_not_supported(self) -> None:
        """Test set attribute with an unsupported attribute does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.detergent.value, True)
            mock_build_send.assert_not_called()

    def test_set_attribute_wrong_type(self) -> None:
        """Test set attribute with a non-bool value raises and does not send."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(DeviceAttributes.power.value, 5)
        mock_build_send.assert_not_called()

    @pytest.mark.parametrize(
        ("model", "subtype"),
        [("other", 13145), ("38131140", 13146), ("38132386", 1)],
    )
    def test_unverified_profiles_keep_legacy_attributes(
        self,
        model: str,
        subtype: int,
    ) -> None:
        """Do not infer controls from the shared DB device type or Lua family."""
        device = MideaDBDevice(
            customize="",
            **device_args(model, subtype),
        )
        assert DeviceAttributes.parameter_control_supported not in device.attributes
        assert DeviceAttributes.appointment_control_supported not in device.attributes
        assert device.get_parameter_options(DeviceAttributes.program_control) == []

    def test_verified_profile_exposes_controls_for_model_or_sn8(self) -> None:
        """Require the verified subtype and accept its identity from model or SN8."""
        for model, sn8 in (
            ("38131140", None),
            ("marketing name", "38131140"),
        ):
            device = MideaDBDevice(
                customize="",
                **device_args(model, 13145, sn8=sn8),
            )
            assert (
                device.get_attribute(DeviceAttributes.parameter_control_supported)
                is True
            )
            assert (
                device.get_attribute(DeviceAttributes.parameter_controls_available)
                is False
            )
            assert (
                device.get_attribute(DeviceAttributes.appointment_control_supported)
                is True
            )
            assert (
                len(
                    device.get_parameter_options(DeviceAttributes.program_control),
                )
                == 30
            )

    def test_v41_profile_decodes_program_without_unverified_controls(self) -> None:
        """Decode the v41 vocabulary while keeping model capabilities read-only."""
        device = MideaDBDevice(
            customize="",
            **device_args("38132386", 0),
        )
        body = bytearray(DB_BODY)
        body[4], body[7], body[8] = (0x6F, 0x08, 0x07)
        device.process_message(frame(body))
        assert device.get_attribute(DeviceAttributes.program) == "greatwaves"
        assert DeviceAttributes.program_control not in device.attributes
        assert DeviceAttributes.temperature_control not in device.attributes
        assert DeviceAttributes.spin_speed_control not in device.attributes
        assert DeviceAttributes.rinse_count not in device.attributes
        assert DeviceAttributes.wash_time_control not in device.attributes
        assert DeviceAttributes.forget_free not in device.attributes
        assert DeviceAttributes.appointment_control_supported not in device.attributes
        assert device.get_parameter_options(DeviceAttributes.program_control) == []
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueWrongType),
        ):
            device.set_attribute(DeviceAttributes.temperature_control, "50")
        send.assert_not_called()

    @pytest.mark.parametrize(
        "identity",
        [
            {"manufacturer_code": "0008"},
            {"cloud_name": "Toshiba Iolife"},
            {"cloud_name": "TSmartLife"},
        ],
    )
    def test_toshiba_profile_uses_uart_query_and_status(
        self,
        identity: dict[str, str],
    ) -> None:
        """Select the common T_0008 frame from explicit cloud identity."""
        device = MideaDBDevice(
            customize="",
            **device_args("toshiba", 0, **identity),
        )
        query = device.build_query()[0]
        assert isinstance(query, MessageToshibaQuery)
        assert query.serialize()[:4] == bytes.fromhex("55aacc33")
        device.process_message(bytes(toshiba_frame(toshiba_body(), 3)))
        assert device.get_attribute(DeviceAttributes.power) is True
        assert device.get_attribute(DeviceAttributes.status) == "standby"
        assert device.get_attribute(DeviceAttributes.mode) == "wash"
        assert device.get_attribute(DeviceAttributes.program) == "standard"
        assert device.get_attribute(DeviceAttributes.wash_time) == 120
        assert device.get_attribute(DeviceAttributes.progress) == "wash"
        assert device.get_attribute(DeviceAttributes.time_remaining) == 125
        assert DeviceAttributes.program_control not in device.attributes
        assert device.get_parameter_options(DeviceAttributes.program_control) == []

    def test_toshiba_fallback_detects_frame_without_cloud_identity(self) -> None:
        """Switch an unknown DB device after the alternative query answers."""
        device = MideaDBDevice(
            customize="",
            **device_args("unknown", 0),
        )
        assert isinstance(device.build_query()[0], MessageQuery)
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, MessageToshibaQuery)
        device.process_message(bytes(toshiba_frame(toshiba_body(), 3)))
        assert device._is_query_response_valid(fallback) is True
        assert isinstance(device.build_query()[0], MessageToshibaQuery)
        assert device.get_attribute(DeviceAttributes.program) == "standard"
        assert DeviceAttributes.program_control not in device.attributes

    def test_toshiba_detection_replaces_preselected_profile_attributes(self) -> None:
        """Remove fixed-frame controls if a colliding model answers as Toshiba."""
        device = MideaDBDevice(
            customize="",
            **device_args("38131140", 13145),
        )
        assert DeviceAttributes.temperature_control in device.attributes
        status = device.process_message(bytes(toshiba_frame(toshiba_body(), 3)))
        assert DeviceAttributes.temperature_control not in device.attributes
        assert DeviceAttributes.program_control not in device.attributes
        assert status[str(DeviceAttributes.temperature_control)] is None
        assert status[str(DeviceAttributes.program_control)] is None

    def test_query_family_validation_and_toshiba_fallback_completion(self) -> None:
        """Match ordinary replies and stop offering fallback after Toshiba detection."""
        device = MideaDBDevice(
            customize="",
            **device_args("unknown", 0),
        )
        query = device.build_query()[0]
        device.process_message(frame(DB_BODY))
        assert device._is_query_response_valid(query) is True
        device.process_message(bytes(toshiba_frame(toshiba_body(), 3)))
        assert device.build_query_fallback() == []

    def test_toshiba_program_write_is_not_exposed_without_version_profile(self) -> None:
        """Keep generic Toshiba support read-only until its Lua version is known."""
        device = MideaDBDevice(
            customize="",
            **device_args("toshiba", 0, manufacturer_code="0008"),
        )
        device.process_message(bytes(toshiba_frame(toshiba_body(), 3)))
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueWrongType),
        ):
            device.set_attribute(DeviceAttributes.program_control, "fast")
        send.assert_not_called()

    @pytest.mark.parametrize(
        "mutation",
        ["crc", "length", "device_type", "frame_type", "short"],
    )
    def test_invalid_toshiba_fallback_does_not_switch_protocol(
        self,
        mutation: str,
    ) -> None:
        """Require a complete valid Toshiba report before switching query family."""
        device = MideaDBDevice(customize="", **device_args("38131140", 13145))
        fallback = device.build_query_fallback()[0]
        frame_data = toshiba_frame(toshiba_body(), 3)
        if mutation == "crc":
            frame_data[-1] ^= 1
        elif mutation == "length":
            frame_data[4] ^= 1
        elif mutation == "device_type":
            frame_data[7] = 0xAC
        elif mutation == "frame_type":
            frame_data = toshiba_frame(toshiba_body(), 5)
        else:
            frame_data = frame_data[:10]
        assert device.process_message(bytes(frame_data)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert isinstance(device.build_query()[0], MessageQuery)
        assert DeviceAttributes.temperature_control in device.attributes

    @pytest.mark.parametrize(
        "attribute",
        [DeviceAttributes.power, DeviceAttributes.start],
    )
    def test_toshiba_rejects_unverified_legacy_writes(
        self,
        attribute: DeviceAttributes,
    ) -> None:
        """Never send ordinary Midea power/start frames to a Toshiba device."""
        device = MideaDBDevice(
            customize="",
            **device_args("toshiba", 0, manufacturer_code="0008"),
        )
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="verification"),
        ):
            device.set_attribute(attribute, True)
        send.assert_not_called()

    def test_verified_response_updates_control_attributes(self) -> None:
        """Publish decoded controls and the profile-specific program name together."""
        device = verified_washer(DB_BODY)
        assert device.get_attribute(DeviceAttributes.program) == "water_mixed_wash"
        assert (
            device.get_attribute(DeviceAttributes.parameter_controls_available) is True
        )
        assert device.get_attribute(DeviceAttributes.temperature_control) == "cold"
        assert device.get_parameter_options(DeviceAttributes.spin_time_control) == [
            "8",
            "9",
            "10",
            "11",
            "12",
        ]

    def test_verified_set_attribute_dispatches_parameter_and_query(self) -> None:
        """Route supported controls through the model helper and refresh real state."""
        device = verified_washer(DB_BODY)
        before = dict(device.attributes)
        with patch.object(device, "build_send") as send:
            device.set_attribute(DeviceAttributes.temperature_control, "20")
        assert len(send.call_args_list) == 2
        assert isinstance(send.call_args_list[0].args[0], MessageParameters)
        assert isinstance(send.call_args_list[1].args[0], MessageQuery)
        assert device.attributes == before

    def test_verified_control_error_does_not_send(self) -> None:
        """Validate a supported control before sending either command or query."""
        device = verified_washer()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="standby"),
        ):
            device.set_attribute(DeviceAttributes.program_control, "cotton")
        send.assert_not_called()

    def test_verified_reservation_response_merges_device_and_control_state(
        self,
    ) -> None:
        """Publish legacy cycle state and reservation controls from one response."""
        device = verified_washer(DB_RESERVED)
        assert device.get_attribute(DeviceAttributes.start) is True
        assert device.get_attribute(DeviceAttributes.status) == "delay"
        assert device.get_attribute(DeviceAttributes.time_remaining) == 138
        assert device.get_attribute(DeviceAttributes.appointment) is True
        assert (
            device.get_attribute(DeviceAttributes.parameter_controls_available) is False
        )
        assert (
            device.get_attribute(DeviceAttributes.appointment_controls_available)
            is True
        )

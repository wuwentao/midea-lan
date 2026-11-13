"""Test DB Device."""

import logging
from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.device import MideaDeviceInitKwargs
from midealan.devices.db import DeviceAttributes, MideaDBDevice
from midealan.devices.db.message import (
    MessageParameters,
    MessagePower,
    MessageQuery,
    MessageStart,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType, ToshibaMessageRequest, encode_toshiba_frame

DB_BODY = bytes.fromhex(
    "030101001f0520010300030400400000204f0000db5933b10000002d08080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
DB_RESERVED = bytes.fromhex(
    "040106001f0540060303020400427a01208a0000db5933b10000003f0c080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
# Real notify1 frames from a v41 washer-dryer (SN8 38123703, subtype 16695):
# drying status of a wash & dry cycle, then the end-of-cycle report (0405).
V41_DRYING = (
    "aa33db000000000000040401020002012101050000000000000010290000db37414c"
    "0000000403000000000000000000000000de"
)
V41_CONSUMPTION = (
    "aa33db000000000000040553017902090000ffffffffffffffffffffffffdb37414c"
    "ffffffffffffff0000000000000000000085"
)
# Real query response from the MD10L7PRO (SN8 38131780, subtype 13914),
# captured in midea_ac_lan issue #1140 (fast_wash_30, washing, dryer off).
# The device's cloud decoder reported the matching values used below.
V41_MD10L7PRO_STATUS = (
    "aa47db00000000000003"
    "0300000017022001030401000100000004010000db5a364c0000000f050000d0"
    "ffffffffffffffffffffffffffff000101ffffffffff0000ffff08ffff"
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
) -> MideaDeviceInitKwargs:
    """Return typed connection arguments for a DB device."""
    args = BASE_ARGS.copy()
    args["model"] = model
    args["subtype"] = subtype
    if sn8 is not None:
        args["sn8"] = sn8
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
    """Build a Toshiba DB base-status body."""
    body = bytearray(47)
    body[2] = 2
    body[3] = 1
    body[9] = 0x82
    body[11] = 10
    body[14] = 40
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
        "identity",
        [
            {"manufacturer_code": "0008"},
            {"manufacturer_code": "0008", "cloud_name": "Toshiba Iolife"},
            {"manufacturer_code": "0008", "cloud_name": "TSmartLife"},
        ],
    )
    def test_toshiba_query_status_and_read_only_policy(
        self,
        identity: dict[str, str],
    ) -> None:
        """Select, decode, and keep the Toshiba DB profile read-only."""
        args = device_args("toshiba", 0)
        args["manufacturer_code"] = identity["manufacturer_code"]
        if "cloud_name" in identity:
            args["cloud_name"] = identity["cloud_name"]
        device = MideaDBDevice(customize="", **args)
        assert device._controls is None
        query = device.build_query()[0]
        assert isinstance(query, ToshibaMessageRequest)
        assert query.serialize() == bytes.fromhex(
            "55aacc330f0001db000000000000030000e687",
        )
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())),
        )
        assert status[DeviceAttributes.power] is True
        assert status[DeviceAttributes.status] == "power_on"
        assert status[DeviceAttributes.mode] == "wash"
        assert status[DeviceAttributes.program] == "standard"
        assert status[DeviceAttributes.wash_time] == 120
        assert DeviceAttributes.progress not in status
        assert device.attributes[DeviceAttributes.progress] is None
        assert status[DeviceAttributes.time_remaining] == 125
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.power, True)
        send.assert_not_called()

        body = toshiba_body()
        body[18] = 0x20
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, body)),
        )
        assert DeviceAttributes.progress not in status
        assert device.attributes[DeviceAttributes.progress] is None

        body[9] = 30
        body[18] = 0
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, body)),
        )
        assert status[DeviceAttributes.wash_time] == 30
        assert DeviceAttributes.progress not in status
        assert device.attributes[DeviceAttributes.progress] is None
        assert (
            device.process_message(
                bytes(encode_toshiba_frame(DeviceType.DB, 3, b"\x00")),
            )
            == {}
        )

    def test_toshiba_fallback_switches_only_after_valid_status(self) -> None:
        """Keep the primary protocol until a complete Toshiba status is parsed."""
        device = MideaDBDevice(customize="", **device_args("unknown", 0))
        primary = device.build_query()[0]
        assert device._is_query_response_valid(primary) is True
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, ToshibaMessageRequest)
        invalid = encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())
        invalid[-1] ^= 1
        assert device.process_message(bytes(invalid)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert isinstance(device.build_query()[0], MessageQuery)

        device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())),
        )
        assert device._is_query_response_valid(fallback) is True
        assert isinstance(device.build_query()[0], ToshibaMessageRequest)

    def test_toshiba_fallback_skips_known_non_toshiba_identity(self) -> None:
        """Do not probe Toshiba framing for an explicit different manufacturer."""
        args = device_args("known-midea", 0)
        args["manufacturer_code"] = "1234"
        device = MideaDBDevice(customize="", **args)
        assert isinstance(device.build_query()[0], MessageQuery)
        assert device.build_query_fallback() == []
        assert device.build_query_fallback_stages() == []

    @pytest.mark.parametrize(
        ("frame_type", "accepted"),
        [
            (MessageType.set, True),
            (MessageType.query, True),
            (MessageType.notify1, True),
            (MessageType.notify2, False),
        ],
    )
    def test_toshiba_base_status_frame_types(
        self,
        frame_type: MessageType,
        accepted: bool,
    ) -> None:
        """Accept only the frame types used for DB base status in the Lua protocol."""
        args = device_args("toshiba", 0)
        args["manufacturer_code"] = "0008"
        device = MideaDBDevice(customize="", **args)
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, frame_type, toshiba_body())),
        )
        assert bool(status) is accepted

    def test_toshiba_fallback_removes_incompatible_verified_controls(self) -> None:
        """Drop profile-specific Midea controls after Toshiba is selected."""
        device = verified_washer()
        controls = device._controls
        assert controls is not None
        control_attributes = set(controls.attributes)
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())),
        )
        assert device._controls is None
        assert all(status[str(attr)] is None for attr in control_attributes)
        assert all(attr not in device.attributes for attr in control_attributes)

    def test_toshiba_fallback_clears_stale_midea_progress_once(self) -> None:
        """Publish one clear when validated Toshiba traffic replaces Midea state."""
        device = MideaDBDevice(customize="", **device_args("unknown", 0))
        body = bytearray(31)
        body[0] = 0x03
        body[16] = 0x01
        device.process_message(frame(body))
        assert device.attributes[DeviceAttributes.progress] == "spin"

        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())),
        )
        assert status[DeviceAttributes.progress] is None
        assert device.attributes[DeviceAttributes.progress] is None

        repeated = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DB, 3, toshiba_body())),
        )
        assert DeviceAttributes.progress not in repeated
        assert device.attributes[DeviceAttributes.progress] is None

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

    @pytest.mark.parametrize(
        ("model", "subtype", "sn8", "manufacturer_code", "tag"),
        [
            ("38131140", 13145, None, None, "v33-write"),
            ("38132386", 0, None, None, "v41-readonly"),
            ("unknown", 99, None, None, "legacy"),
            ("toshiba", 0, None, "0008", "legacy"),
        ],
    )
    def test_profile_tag_is_logged_for_each_identity(
        self,
        model: str,
        subtype: int,
        sn8: str | None,
        manufacturer_code: str | None,
        tag: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Log the recognized profile (v33-write/v41-readonly/legacy) at init."""
        args = device_args(model, subtype, sn8=sn8)
        if manufacturer_code is not None:
            args["manufacturer_code"] = manufacturer_code
        with caplog.at_level(logging.DEBUG, logger="midealan.devices.db"):
            MideaDBDevice(customize="", **args)
        assert f"DB profile tag={tag}" in caplog.text

    @pytest.mark.parametrize(
        ("model", "sn8"),
        [("38132386", None), ("marketing name", "38132386")],
    )
    def test_v41_profile_decodes_read_only_status(
        self,
        model: str,
        sn8: str | None,
    ) -> None:
        """Decode v41 status for model or SN8 without exposing controls."""
        device = MideaDBDevice(
            customize="",
            **device_args(model, 0, sn8=sn8),
        )
        body = bytearray(DB_BODY)
        body[4], body[7], body[8] = (0x6F, 0x08, 0x07)
        device.process_message(frame(body))
        assert device.get_attribute(DeviceAttributes.program) == "greatwaves"
        assert device.get_attribute(DeviceAttributes.temperature) == "90"
        assert device.get_attribute(DeviceAttributes.dehydration_speed) == "1600"
        assert DeviceAttributes.program_control not in device.attributes
        assert DeviceAttributes.temperature_control not in device.attributes
        assert DeviceAttributes.spin_speed_control not in device.attributes
        assert DeviceAttributes.rinse_count not in device.attributes
        assert DeviceAttributes.wash_time_control not in device.attributes
        assert DeviceAttributes.forget_free not in device.attributes
        assert DeviceAttributes.appointment_control_supported not in device.attributes
        assert device.get_parameter_options(DeviceAttributes.program_control) == []
        for attr in (DeviceAttributes.power, DeviceAttributes.start):
            with (
                patch.object(device, "build_send") as send,
                pytest.raises(ValueWrongType, match="read-only"),
            ):
                device.set_attribute(attr, True)
            send.assert_not_called()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueWrongType),
        ):
            device.set_attribute(DeviceAttributes.temperature_control, "50")
        send.assert_not_called()

    @pytest.mark.parametrize(
        ("model", "subtype", "temperature"),
        [
            ("other", 0, 0x08),
            ("other", 0, 0x09),
            ("38131140", 13145, 0x08),
            ("38131140", 13145, 0x09),
        ],
    )
    def test_v41_temperature_values_are_profile_scoped(
        self,
        model: str,
        subtype: int,
        temperature: int,
    ) -> None:
        """Keep v41-only temperature codes raw on unrelated DB profiles."""
        device = MideaDBDevice(customize="", **device_args(model, subtype))
        body = bytearray(DB_BODY)
        body[7] = temperature
        device.process_message(frame(body))
        assert device.get_attribute(DeviceAttributes.temperature) == temperature

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

    def test_verified_start_preserves_parameters(self) -> None:
        """Start without replaying the stale snapshot that reset spin/time.

        The verified v33 washer restored program-default spin speed and
        minutes when start replayed MessageStart.washing_data. The profile
        now sends a no-change parameter body with only the start status and
        the current function flags (byte 13), so confirmed parameters stay.
        """
        device = verified_washer(DB_BODY)
        with patch.object(device, "build_send") as send:
            device.set_attribute(DeviceAttributes.start, True)
        assert len(send.call_args_list) == 2
        message = send.call_args_list[0].args[0]
        assert isinstance(message, MessageParameters)
        assert isinstance(send.call_args_list[1].args[0], MessageQuery)
        body = message._body
        # Status byte set to start; all parameters no-change; flags preserved.
        assert body[1] == 0x01
        assert body[12] == DB_BODY[13]
        assert all(byte == 0xFF for i, byte in enumerate(body) if i not in (1, 12))

    def test_verified_pause_preserves_parameters(self) -> None:
        """Pause sends a no-change body with the pause status (not a snapshot)."""
        device = verified_washer(DB_BODY)
        with patch.object(device, "build_send") as send:
            device.set_attribute(DeviceAttributes.start, False)
        message = send.call_args_list[0].args[0]
        assert isinstance(message, MessageParameters)
        assert message._body[1] == 0x00

    def test_verified_start_without_status_raises(self) -> None:
        """Reject start before the washer has reported a real status."""
        device = verified_washer()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="powered on"),
        ):
            device.set_attribute(DeviceAttributes.start, True)
        send.assert_not_called()

    @pytest.mark.parametrize(
        ("model", "sn8"),
        [("38123703", None), ("MF200D80WB/T-A1", "38123703")],
    )
    def test_v41_washer_dryer_profile_publishes_lua_fields(
        self,
        model: str,
        sn8: str | None,
    ) -> None:
        """Expose drying, option, error and consumption fields for the profile."""
        device = MideaDBDevice(customize="", **device_args(model, 16695, sn8=sn8))
        assert DeviceAttributes.dryer in device.attributes
        assert device.get_attribute(DeviceAttributes.dryer) is None
        status = device.process_message(bytes.fromhex(V41_DRYING))
        assert status[DeviceAttributes.program] == "fast_wash"
        assert status[DeviceAttributes.progress] == "dry"
        assert status[DeviceAttributes.dryer] == 1
        assert status[DeviceAttributes.wind_dispel] is False
        assert status[DeviceAttributes.remote_control_flag] is False
        report = device.process_message(bytes.fromhex(V41_CONSUMPTION))
        assert report == {
            DeviceAttributes.water_consumption: 339,
            DeviceAttributes.power_consumption: 633,
            DeviceAttributes.wash_count: 9,
        }
        assert device.get_attribute(DeviceAttributes.dryer) == 1
        assert device.get_attribute(DeviceAttributes.progress) == "dry"

    @pytest.mark.parametrize(
        ("model", "sn8"),
        [("38131780", None), ("MD10L7PRO", "38131780")],
    )
    def test_v41_md10l7pro_profile_decodes_real_frame(
        self,
        model: str,
        sn8: str | None,
    ) -> None:
        """Decode the MD10L7PRO (#1140) real status frame as the v41 profile.

        Values match the device cloud decoder in the issue debug log.
        """
        device = MideaDBDevice(customize="", **device_args(model, 13914, sn8=sn8))
        assert DeviceAttributes.dryer in device.attributes
        status = device.process_message(bytes.fromhex(V41_MD10L7PRO_STATUS))
        assert status[DeviceAttributes.program] == "fast_wash_30"
        assert status[DeviceAttributes.progress] == "wash"
        assert status[DeviceAttributes.dryer] == 0
        assert status[DeviceAttributes.soak_count] == 2
        assert status[DeviceAttributes.speedy] is False
        assert status[DeviceAttributes.lock] is False
        assert status[DeviceAttributes.appointment_time] == 0
        assert status[DeviceAttributes.error_code] == 0
        assert status[DeviceAttributes.beforehand_wash] is False
        assert status[DeviceAttributes.steam_wash] is False
        assert status[DeviceAttributes.add_rinse] is False
        assert status[DeviceAttributes.wind_dispel] is False
        assert status[DeviceAttributes.remote_control_flag] is False

    @pytest.mark.parametrize(
        ("model", "subtype"),
        [("38123703", 0), ("other", 16695), ("other", 0)],
    )
    def test_v41_fields_are_profile_scoped(self, model: str, subtype: int) -> None:
        """Keep legacy DB profiles free of v41-only attributes."""
        device = MideaDBDevice(customize="", **device_args(model, subtype))
        status = device.process_message(bytes.fromhex(V41_DRYING))
        assert DeviceAttributes.dryer not in device.attributes
        assert DeviceAttributes.dryer not in status
        assert device.process_message(bytes.fromhex(V41_CONSUMPTION)) == {}

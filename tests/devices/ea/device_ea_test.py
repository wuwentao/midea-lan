"""Test EA Device."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.ea import DeviceAttributes, MideaEADevice
from midealan.devices.ea.message import MessageQuery
from midealan.message import (
    MessageType,
    ToshibaMessageRequest,
    encode_toshiba_frame,
)

PROTOCOL_NONE = 0x00

# Lua-derived fixture layout, intentionally independent of production constants.
_TOSHIBA_STATUS_LENGTH = 25
_TOSHIBA_COURSE_OFFSET = 16
_TOSHIBA_REMAINING_MINUTES_OFFSET = 21
_TOSHIBA_REMAINING_HOURS_OFFSET = 22
_TOSHIBA_COOKING_STATE_OFFSET = 23
_TOSHIBA_FRAME_TYPES = (0x0003, 0x8003, 0x0004)
_TOSHIBA_STATE_NAMES = (
    (0x01, "stop"),
    (0x02, "error"),
    (0x03, "reserved"),
    (0x04, "soak"),
    (0x05, "rice_cooking"),
    (0x06, "steam"),
    (0x07, "keep_warm"),
    (0x08, "heat_cleaning"),
    (0x0A, "cooking"),
    (0xFF, "stop"),
)


def _build_toshiba_device(
    manufacturer_code: str | None = "0008",
) -> MideaEADevice:
    """Build an EA device with optional manufacturer identity."""
    identity = (
        {"manufacturer_code": manufacturer_code}
        if manufacturer_code is not None
        else {}
    )
    return MideaEADevice(
        name="Toshiba EA Device",
        device_id=2,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="test_model",
        subtype=1,
        customize="",
        **identity,
    )


def _toshiba_status_body() -> bytearray:
    """Build a minimum complete Toshiba EA base-status body."""
    return bytearray(_TOSHIBA_STATUS_LENGTH)


class TestMideaEADevice:
    """Test Midea EA Device."""

    device: MideaEADevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea EA Device setup."""
        self.device = MideaEADevice(
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
        assert self.device.attributes[DeviceAttributes.cooking] is False
        assert self.device.attributes[DeviceAttributes.keep_warm] is False
        assert self.device.attributes[DeviceAttributes.mode] == 0
        assert self.device.attributes[DeviceAttributes.time_remaining] is None
        assert self.device.attributes[DeviceAttributes.keep_warm_time] is None
        assert self.device.attributes[DeviceAttributes.top_temperature] is None
        assert self.device.attributes[DeviceAttributes.bottom_temperature] is None
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_toshiba_identity_builds_common_query(self) -> None:
        """Use the exact shared one-byte Toshiba EA query."""
        device = _build_toshiba_device()
        queries = device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], ToshibaMessageRequest)
        assert queries[0].body == b"\x00"
        assert queries[0].serialize() == bytes.fromhex(
            "55aacc330f0001ea0000000000000300003845",
        )
        assert device.build_query_fallback() == []

    @pytest.mark.parametrize("frame_type", _TOSHIBA_FRAME_TYPES)
    def test_toshiba_status_frame_generations(self, frame_type: int) -> None:
        """Decode legacy query, newer query, and notify frame identifiers."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_COURSE_OFFSET] = 0x02
        body[_TOSHIBA_REMAINING_MINUTES_OFFSET] = 0x34
        body[_TOSHIBA_REMAINING_HOURS_OFFSET] = 0x12
        body[_TOSHIBA_COOKING_STATE_OFFSET] = 0x0A

        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.EA, frame_type, body)),
        )

        assert status == {
            DeviceAttributes.cooking: True,
            DeviceAttributes.keep_warm: False,
            DeviceAttributes.mode: 0x02,
            DeviceAttributes.time_remaining: 12 * 60 + 34,
            DeviceAttributes.progress: "cooking",
        }
        assert device.attributes[DeviceAttributes.time_remaining] == 12 * 60 + 34

    def test_toshiba_fixed_newer_generation_status(self) -> None:
        """Decode the fixed newer-generation status frame from the Lua layout."""
        device = _build_toshiba_device()
        response = bytes.fromhex(
            "55aacc33270001ea0000000000000380"
            "00000000000000000000000000000000020000000030010a002522",
        )
        status = device.process_message(response)
        assert status[DeviceAttributes.mode] == 0x02
        assert status[DeviceAttributes.time_remaining] == 90
        assert status[DeviceAttributes.progress] == "cooking"

    @pytest.mark.parametrize(("raw_state", "expected"), _TOSHIBA_STATE_NAMES)
    def test_toshiba_cooking_state_mapping(
        self,
        raw_state: int,
        expected: str,
    ) -> None:
        """Map every Lua-documented Toshiba cooking state."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_COOKING_STATE_OFFSET] = raw_state
        frame = encode_toshiba_frame(DeviceType.EA, 0x0004, body)
        status = device.process_message(bytes(frame))
        assert status[DeviceAttributes.progress] == expected
        assert status[DeviceAttributes.cooking] is (raw_state == 0x0A)
        assert status[DeviceAttributes.keep_warm] is (raw_state == 0x07)

    def test_toshiba_requires_complete_base_status(self) -> None:
        """Accept exactly 25 bytes and reject the 24-byte truncated body."""
        device = _build_toshiba_device()
        complete = _toshiba_status_body()
        frame = encode_toshiba_frame(DeviceType.EA, 0x0003, complete)
        assert device.process_message(bytes(frame))[DeviceAttributes.mode] == 0

        truncated = complete[:-1]
        frame = encode_toshiba_frame(DeviceType.EA, 0x0003, truncated)
        assert device.process_message(bytes(frame)) == {}

    @pytest.mark.parametrize(
        ("frame_type", "body_type"),
        [
            (0x8002, 0x00),
            (0x0003, 0x01),
            (0x0004, 0x01),
        ],
    )
    def test_toshiba_rejects_unsupported_frame_body_combinations(
        self,
        frame_type: int,
        body_type: int,
    ) -> None:
        """Accept only documented Toshiba EA base-status combinations."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[0] = body_type
        frame = encode_toshiba_frame(DeviceType.EA, frame_type, body)
        assert device.process_message(bytes(frame)) == {}

    def test_toshiba_fallback_requires_valid_supported_status(self) -> None:
        """Select fallback framing only after a complete decoded EA status."""
        device = _build_toshiba_device(None)
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, ToshibaMessageRequest)

        body = _toshiba_status_body()
        invalid = encode_toshiba_frame(DeviceType.EA, 0x0003, body)
        invalid[-1] ^= 1
        assert device.process_message(bytes(invalid)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert device.toshiba_protocol is False

        wrong_type = encode_toshiba_frame(DeviceType.DB, 0x0003, body)
        assert device.process_message(bytes(wrong_type)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x01
        unsupported = encode_toshiba_frame(DeviceType.EA, 0x0003, body)
        assert device.process_message(bytes(unsupported)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x00
        valid = encode_toshiba_frame(DeviceType.EA, 0x0003, body)
        assert device.process_message(bytes(valid))[DeviceAttributes.mode] == 0
        assert device._is_query_response_valid(fallback) is True
        assert device.toshiba_protocol is True

    def test_explicit_non_toshiba_identity_skips_fallback(self) -> None:
        """Do not probe Toshiba framing for a known different manufacturer."""
        device = _build_toshiba_device("1234")
        assert device.build_query_fallback() == []
        assert isinstance(device.build_query()[0], MessageQuery)

    def test_toshiba_write_is_rejected_before_send(self) -> None:
        """Keep Toshiba EA writes disabled until hardware verification."""
        device = _build_toshiba_device()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.mode, 1)
        send.assert_not_called()

    def test_set_attribute_noop(self) -> None:
        """Test set attribute is a no-op for this device."""
        self.device.set_attribute(DeviceAttributes.mode.value, 1)

    def test_process_message_body1_set(self) -> None:
        """Test process message with a V0 set message parses EABody1."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [PROTOCOL_NONE] + [MessageType.set],
        )
        body = bytearray(30)
        body[5] = 0x16  # EABody1 marker
        body[6] = 2  # mode low byte -> cook_rice
        body[14] = 2  # progress Cooking
        body[18] = 90  # top temperature
        body[19] = 85  # bottom temperature
        body[22] = 1  # time remaining hours
        body[23] = 30  # time remaining minutes
        body[26] = 0  # keep warm time hours
        body[27] = 45  # keep warm time minutes
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.cooking] is True
        assert self.device.attributes[DeviceAttributes.keep_warm] is False
        assert self.device.attributes[DeviceAttributes.mode] == "cook_rice"
        assert self.device.attributes[DeviceAttributes.time_remaining] == 90
        assert self.device.attributes[DeviceAttributes.keep_warm_time] == 45
        assert self.device.attributes[DeviceAttributes.top_temperature] == 90
        assert self.device.attributes[DeviceAttributes.bottom_temperature] == 85
        assert self.device.attributes[DeviceAttributes.progress] == "cooking"
        assert new_status[DeviceAttributes.cooking.value] is True

    def test_process_message_body2_query(self) -> None:
        """Test process message with a V0 query message parses EABody2."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [PROTOCOL_NONE] + [MessageType.query],
        )
        body = bytearray(62)
        body[6] = 0x52  # EABody2 marker
        body[7] = 0xC3  # EABody2 marker
        body[9] = 3  # progress Keep-warm
        body[20] = 60  # bottom temperature
        body[21] = 70  # top temperature
        body[50] = 2  # time remaining hours
        body[51] = 0  # time remaining minutes
        body[54] = 1  # keep warm time hours
        body[55] = 5  # keep warm time minutes
        body[58] = 3  # mode low byte -> fast_cook_rice
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.cooking] is False
        assert self.device.attributes[DeviceAttributes.keep_warm] is True
        assert self.device.attributes[DeviceAttributes.mode] == "fast_cook_rice"
        assert self.device.attributes[DeviceAttributes.time_remaining] == 120
        assert self.device.attributes[DeviceAttributes.keep_warm_time] == 65
        assert self.device.attributes[DeviceAttributes.top_temperature] == 70
        assert self.device.attributes[DeviceAttributes.bottom_temperature] == 60
        assert self.device.attributes[DeviceAttributes.progress] == "keep_warm"

    def test_process_message_body1_query(self) -> None:
        """Test process message with a V0 query message parses EABody1."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [PROTOCOL_NONE] + [MessageType.query],
        )
        body = bytearray(30)
        body[5] = 0x3D  # EABody1 marker
        body[6] = 1  # mode low byte -> reserve
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.cooking] is False
        assert self.device.attributes[DeviceAttributes.keep_warm] is False
        assert self.device.attributes[DeviceAttributes.mode] == "reserve"
        assert self.device.attributes[DeviceAttributes.time_remaining] == 0
        assert self.device.attributes[DeviceAttributes.keep_warm_time] == 0
        assert self.device.attributes[DeviceAttributes.top_temperature] == 0
        assert self.device.attributes[DeviceAttributes.bottom_temperature] == 0
        assert self.device.attributes[DeviceAttributes.progress] == "idle"

    def test_process_message_body1_notify(self) -> None:
        """Test process message with a V0 notify1 message parses EABody1."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [PROTOCOL_NONE] + [MessageType.notify1],
        )
        body = bytearray(30)
        body[5] = 0x3D  # EABody1 marker
        body[14] = 4  # progress out of range
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.mode] == "smart"
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"

    @pytest.mark.parametrize(
        ("message_type", "body_type"),
        [
            (MessageType.set, 0x02),
            (MessageType.query, 0x03),
            (MessageType.notify1, 0x04),
        ],
    )
    def test_process_message_body3(
        self,
        message_type: MessageType,
        body_type: int,
    ) -> None:
        """Test process message with a V1 message parses EABody3."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
        )
        body = bytearray(26)
        body[3] = body_type
        body[4] = 3  # mode low byte -> fast_cook_rice
        body[8] = 2  # progress Cooking
        body[12] = 1  # time remaining hours
        body[13] = 10  # time remaining minutes
        body[20] = 95  # top temperature
        body[21] = 88  # bottom temperature
        body[22] = 0  # keep warm time hours
        body[23] = 30  # keep warm time minutes
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.cooking] is True
        assert self.device.attributes[DeviceAttributes.keep_warm] is False
        assert self.device.attributes[DeviceAttributes.mode] == "fast_cook_rice"
        assert self.device.attributes[DeviceAttributes.time_remaining] == 70
        assert self.device.attributes[DeviceAttributes.keep_warm_time] == 30
        assert self.device.attributes[DeviceAttributes.top_temperature] == 95
        assert self.device.attributes[DeviceAttributes.bottom_temperature] == 88
        assert self.device.attributes[DeviceAttributes.progress] == "cooking"

    def test_process_message_body3_cloud_mode(self) -> None:
        """Test process message maps out-of-range mode and progress values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(26)
        body[3] = 0x03
        body[4] = 44  # mode low byte
        body[5] = 1  # mode high byte -> 300, out of range
        body[8] = 9  # progress out of range
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.mode] == "cloud"
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"

    @pytest.mark.parametrize("sub_type", [2, 4, 6, 8, 10, 0x62])
    def test_process_message_new_body(self, sub_type: int) -> None:
        """Test process message with a notify1 message parses EABodyNew."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(64)
        body[3] = 0x01  # EABodyNew marker
        body[6] = sub_type
        body[7] = 1  # mode low byte -> reserve
        body[11] = 2  # progress Cooking
        body[16] = 1  # time remaining hours
        body[17] = 0  # time remaining minutes
        body[19] = 0  # keep warm time hours
        body[20] = 50  # keep warm time minutes
        body[60] = 99  # top temperature
        body[61] = 77  # bottom temperature
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.cooking] is True
        assert self.device.attributes[DeviceAttributes.keep_warm] is False
        assert self.device.attributes[DeviceAttributes.mode] == "reserve"
        assert self.device.attributes[DeviceAttributes.time_remaining] == 60
        assert self.device.attributes[DeviceAttributes.keep_warm_time] == 50
        assert self.device.attributes[DeviceAttributes.top_temperature] == 99
        assert self.device.attributes[DeviceAttributes.bottom_temperature] == 77
        assert self.device.attributes[DeviceAttributes.progress] == "cooking"

    def test_process_message_new_body_unknown_subtype(self) -> None:
        """Test process message with an unknown EABodyNew subtype updates nothing."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(64)
        body[3] = 0x01  # EABodyNew marker
        body[6] = 0  # unknown subtype
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

    def test_process_message_mode_only(self) -> None:
        """Test process message with a notify1 X06 message updates only mode."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(8)
        body[3] = 0x06  # mode-only marker
        body[4] = 2  # mode low byte -> cook_rice
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {DeviceAttributes.mode.value: "cook_rice"}
        assert self.device.attributes[DeviceAttributes.mode] == "cook_rice"
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"

    @pytest.mark.parametrize(
        ("protocol", "message_type"),
        [
            (PROTOCOL_NONE, MessageType.set),
            (PROTOCOL_NONE, MessageType.query),
            (PROTOCOL_NONE, MessageType.notify2),
            (ProtocolVersion.V1, MessageType.set),
            (ProtocolVersion.V1, MessageType.notify2),
        ],
    )
    def test_process_message_unhandled(
        self,
        protocol: int,
        message_type: MessageType,
    ) -> None:
        """Test process message with an unhandled message updates nothing."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [protocol] + [message_type],
        )
        body = bytearray(64)
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

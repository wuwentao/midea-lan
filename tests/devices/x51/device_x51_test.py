"""Test 0x51 device."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.x51 import DeviceAttributes, MideaX51Device
from midealan.devices.x51.message import (
    MessageQueryBase,
    MessageQueryPhoto,
    MessageQueryPhotoMode,
)
from midealan.message import MessageType, ToshibaMessageRequest, encode_toshiba_frame

# Lua-derived fixture layout, intentionally independent of production constants.
_BASE_STATUS_LENGTH = 12
_PHOTO_MODE_STATUS_LENGTH = 7
_BATTERY_OFFSET = 11
_BATTERY_STATES = (
    (0x01, "normal"),
    (0x02, "low"),
    (0x04, "replace"),
    (0x08, "high"),
    (0x10, "high_exception"),
    (0x20, "low_exception"),
    (0xFF, 0xFF),
)


def _build_device(manufacturer_code: str | None = "0008") -> MideaX51Device:
    """Create a 0x51 device without opening a socket."""
    identity = (
        {"manufacturer_code": manufacturer_code}
        if manufacturer_code is not None
        else {}
    )
    return MideaX51Device(
        name="0x51 Device",
        device_id=1,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="test",
        subtype=0,
        customize="",
        **identity,
    )


def _base_status() -> bytearray:
    """Build a minimum complete 0x51 base status."""
    return bytearray(_BASE_STATUS_LENGTH)


def _photo_mode_status() -> bytearray:
    """Build a complete 0x51 photo-mode status."""
    return bytearray(_PHOTO_MODE_STATUS_LENGTH)


class TestMideaX51Device:
    """Test the Midea 0x51 device wrapper."""

    def test_initial_attributes(self) -> None:
        """Initialize every exposed attribute as unknown."""
        device = _build_device()
        assert set(device.attributes) == set(DeviceAttributes)
        assert all(value is None for value in device.attributes.values())

    def test_query_function_groups(self) -> None:
        """Query every documented Toshiba 0x51 function group."""
        queries = _build_device().build_query()
        assert [type(query) for query in queries] == [
            MessageQueryBase,
            MessageQueryPhoto,
            MessageQueryPhotoMode,
        ]
        assert [query.body for query in queries] == [b"\x00", b"\x01", b"\x02"]
        assert queries[0].serialize() == bytes.fromhex(
            "55aacc330f00015100000000000003000013f7",
        )

    @pytest.mark.parametrize(
        "frame_type",
        [MessageType.set, MessageType.query, MessageType.notify1],
    )
    def test_base_status_frame_types(self, frame_type: MessageType) -> None:
        """Decode base status from every Lua-documented frame type."""
        device = _build_device()
        body = bytearray(
            [0x00, 30, 12, 19, 10, 0xEA, 0x07, 0x34, 0x12, 0x02, 0x01, 0x02],
        )
        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.X51, frame_type, body)),
        )
        assert status == {
            DeviceAttributes.time_minute: 30,
            DeviceAttributes.time_hour: 12,
            DeviceAttributes.time_day: 19,
            DeviceAttributes.time_month: 10,
            DeviceAttributes.time_year: 2026,
            DeviceAttributes.temperature: 0x1234,
            DeviceAttributes.light: 0x0102,
            DeviceAttributes.battery_status: "low",
        }

    @pytest.mark.parametrize(("raw", "expected"), _BATTERY_STATES)
    def test_battery_status_mapping(self, raw: int, expected: str | int) -> None:
        """Map every documented battery value and preserve unknown values."""
        device = _build_device()
        body = _base_status()
        body[_BATTERY_OFFSET] = raw
        frame = encode_toshiba_frame(DeviceType.X51, MessageType.query, body)
        status = device.process_message(bytes(frame))
        assert status[DeviceAttributes.battery_status] == expected

    @pytest.mark.parametrize("frame_type", [MessageType.set, MessageType.query])
    def test_full_photo_mode_status(self, frame_type: MessageType) -> None:
        """Decode full photo-mode status and schedule fields."""
        device = _build_device()
        body = bytearray([0x02, 0x01, 0x0F, 6, 15, 18, 45])
        frame = encode_toshiba_frame(DeviceType.X51, frame_type, body)
        status = device.process_message(bytes(frame))
        assert status[DeviceAttributes.shoot] is True
        assert status[DeviceAttributes.mode] == 0x0F
        assert status[DeviceAttributes.periodical_mode] is True
        assert status[DeviceAttributes.request_mode] is True
        assert status[DeviceAttributes.auto_mode] is True
        assert status[DeviceAttributes.direct_mode] is True
        assert status[DeviceAttributes.first_schedule_hour] == 6
        assert status[DeviceAttributes.first_schedule_minute] == 15
        assert status[DeviceAttributes.second_schedule_hour] == 18
        assert status[DeviceAttributes.second_schedule_minute] == 45

    def test_short_and_full_photo_mode_notifications(self) -> None:
        """Allow short notifications and publish schedules when present."""
        device = _build_device()
        short = encode_toshiba_frame(
            DeviceType.X51,
            MessageType.notify1,
            bytes((0x02, 0x00, 0x0A)),
        )
        status = device.process_message(bytes(short))
        assert status[DeviceAttributes.shoot] is False
        assert status[DeviceAttributes.periodical_mode] is False
        assert status[DeviceAttributes.request_mode] is True
        assert status[DeviceAttributes.auto_mode] is False
        assert status[DeviceAttributes.direct_mode] is True
        assert DeviceAttributes.first_schedule_hour not in status

        full = encode_toshiba_frame(
            DeviceType.X51,
            MessageType.notify1,
            bytes((0x02, 0x01, 0x01, 1, 2, 3, 4)),
        )
        status = device.process_message(bytes(full))
        assert status[DeviceAttributes.second_schedule_minute] == 4

    @pytest.mark.parametrize("frame_type", [MessageType.notify1, MessageType.exception])
    def test_error_status(self, frame_type: MessageType) -> None:
        """Decode error codes from notification and exception frames."""
        device = _build_device()
        frame = encode_toshiba_frame(
            DeviceType.X51,
            frame_type,
            bytes((0xFE, 0x34, 0x12)),
        )
        assert device.process_message(bytes(frame))[DeviceAttributes.error_code] == (
            0x1234
        )

    def test_photo_response_is_valid_without_attributes(self) -> None:
        """Treat the documented photo response as valid but attribute-free."""
        device = _build_device(None)
        fallback = device.build_query_fallback()
        assert [type(query) for query in fallback] == [
            MessageQueryBase,
            MessageQueryPhoto,
            MessageQueryPhotoMode,
        ]
        assert device.build_query() == []
        frame = encode_toshiba_frame(DeviceType.X51, MessageType.query, b"\x01")
        assert device.process_message(bytes(frame)) == {}
        assert device._is_query_response_valid(fallback[1]) is True
        assert device.toshiba_protocol is True
        assert len(device.build_query()) == 3

    def test_explicit_non_toshiba_identity_does_not_query(self) -> None:
        """Do not send Toshiba queries for a known different manufacturer."""
        device = _build_device("1234")
        assert device.build_query() == []
        assert device.build_query_fallback() == []

    def test_toshiba_fallback_requires_valid_supported_status(self) -> None:
        """Select Toshiba framing only after a valid supported 0x51 status."""
        device = _build_device(None)
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, ToshibaMessageRequest)
        body = _base_status()

        invalid = encode_toshiba_frame(DeviceType.X51, MessageType.query, body)
        invalid[-1] ^= 1
        assert device.process_message(bytes(invalid)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert device.toshiba_protocol is False

        wrong_type = encode_toshiba_frame(DeviceType.DB, MessageType.query, body)
        assert device.process_message(bytes(wrong_type)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0xFF
        unsupported = encode_toshiba_frame(DeviceType.X51, MessageType.query, body)
        assert device.process_message(bytes(unsupported)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x00
        valid = encode_toshiba_frame(DeviceType.X51, MessageType.query, body)
        assert device.process_message(bytes(valid))[DeviceAttributes.time_minute] == 0
        assert device.toshiba_protocol is True

    @pytest.mark.parametrize(
        ("frame_type", "body"),
        [
            (MessageType.query, b""),
            (MessageType.query, b"\x00" + bytes(_BASE_STATUS_LENGTH - 2)),
            (MessageType.query, b"\x02\x00\x00"),
            (MessageType.notify1, b"\x02\x00"),
            (MessageType.query, b"\xfe\x34\x12"),
            (MessageType.notify1, b"\xfe\x34"),
        ],
    )
    def test_rejects_incomplete_or_unsupported_status(
        self,
        frame_type: MessageType,
        body: bytes,
    ) -> None:
        """Reject bodies that do not match their function/frame contract."""
        device = _build_device()
        frame = encode_toshiba_frame(DeviceType.X51, frame_type, body)
        assert device.process_message(bytes(frame)) == {}

    def test_toshiba_write_is_rejected_before_send(self) -> None:
        """Keep Toshiba 0x51 writes disabled until hardware verification."""
        device = _build_device()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.mode, 1)
        send.assert_not_called()

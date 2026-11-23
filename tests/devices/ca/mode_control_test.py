"""Test Midea CA refrigerator mode control."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.ca import (
    CAModeWritePendingError,
    DeviceAttributes,
    MideaCADevice,
)
from midealan.devices.ca.message import (
    CA_MODE_BODY_LENGTH,
    MessageCAResponse,
    build_ca_mode_body,
)
from midealan.message import ListTypes, MessageBase, MessageQuestCustom, MessageType


def _device() -> MideaCADevice:
    """Build a verified Midea CA refrigerator fixture."""
    return MideaCADevice(
        name="CA refrigerator",
        device_id=1,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V3,
        model="310Z999Z",
        subtype=56,
        customize="",
        manufacturer_code="1234",
    )


def _status(
    mode: int = 0,
    message_type: MessageType = MessageType.query,
    body_type: ListTypes = ListTypes.X00,
) -> bytes:
    """Build a complete general-status response with a 61-byte payload."""
    body = bytearray(CA_MODE_BODY_LENGTH + 1)
    body[0] = body_type
    body[1] = mode
    body[2:] = bytes(range(2, CA_MODE_BODY_LENGTH + 1))
    header = bytearray(
        [0xAA, 0, 0, 0, 0, 0, 0, 0, ProtocolVersion.V3, message_type],
    )
    return bytes(header + body + bytearray([0]))


@pytest.mark.parametrize(
    ("attribute", "mask"),
    [
        (DeviceAttributes.storage_mode, 0x01),
        (DeviceAttributes.freezing_mode, 0x02),
        (DeviceAttributes.holiday_mode, 0x10),
    ],
)
def test_mode_set_changes_only_requested_bit(
    attribute: DeviceAttributes,
    mask: int,
) -> None:
    """Each mode uses its documented bit and preserves all other bytes."""
    original = bytes([0xA0, *range(1, CA_MODE_BODY_LENGTH)])
    changed = build_ca_mode_body(original, mask, True)
    assert len(changed) == CA_MODE_BODY_LENGTH
    assert changed[0] == original[0] | mask
    assert changed[1:] == original[1:]
    assert attribute.value in {"storage_mode", "freezing_mode", "holiday_mode"}


def test_body_length_is_strict() -> None:
    """Missing or extra bytes are rejected before a write."""
    with pytest.raises(ValueError, match="must contain 61 bytes"):
        build_ca_mode_body(bytes(CA_MODE_BODY_LENGTH - 1), 0x01, True)
    with pytest.raises(ValueError, match="must contain 61 bytes"):
        build_ca_mode_body(bytes(CA_MODE_BODY_LENGTH + 1), 0x01, True)


def test_missing_or_stale_status_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent and older-than-two-minutes status bodies cannot be written."""
    device = _device()
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_not_called()

        clock = [100.0]
        monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
        device.process_message(_status(0x00))
        clock[0] += 121.0
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_not_called()


def test_invalid_status_body_is_not_cached() -> None:
    """A short CA response does not create a writable status cache."""
    device = _device()
    short_body = bytes(
        [0xAA, 0, 0, 0, 0, 0, 0, 0, ProtocolVersion.V3, MessageType.query, 0, 0],
    )
    device.process_message(short_body)
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
        send.assert_not_called()


def test_set_requires_status_and_waits_for_next_status() -> None:
    """Writes require a fresh status and a later status releases the guard."""
    device = _device()
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_not_called()

        device.process_message(_status(0x00))
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_called_once()
        command = send.call_args.args[0]
        assert isinstance(command, MessageQuestCustom)
        assert command.body[0] == 0x01
        assert command.body[1:] == bytes(range(2, CA_MODE_BODY_LENGTH + 1))

        with pytest.raises(CAModeWritePendingError, match="waiting for a newer"):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x01))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


def test_notify02_general_status_is_a_valid_set_template() -> None:
    """General-status notifications preserve existing mode bits."""
    device = _device()
    device.process_message(_status(0x01, MessageType.notify1, ListTypes.X02))
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
    command = send.call_args.args[0]
    assert command.body[0] == 0x03


def test_status_received_before_set_does_not_clear_pending_guard() -> None:
    """A parsed pre-SET status cannot release the pending write."""
    device = _device()
    device.process_message(_status(0x00))
    with patch.object(device, "build_send") as send:
        device._message_received()
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        device.process_message(_status(0x00))
        with pytest.raises(CAModeWritePendingError):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1


def test_status_received_before_dispatch_hook_cannot_clear_pending_guard() -> None:
    """A receive reserved before SET keeps its pending guard after dispatch."""
    device = _device()
    device.process_message(_status(0x00))
    with patch.object(device, "build_send") as send:
        # Model recv() returning, then the receive callback being delayed while
        # the caller sends a SET. The reserved order must remain older than SET.
        device._message_receive_started()
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        device._message_received()
        device.process_message(_status(0x00))
        device._message_dispatch_complete()
        with pytest.raises(CAModeWritePendingError):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1


def test_status_freshness_uses_receive_time_when_dispatch_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delayed dispatch cannot make an old received status fresh again."""
    device = _device()
    clock = [100.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])

    device._message_received()
    clock[0] += 121.0
    device.process_message(_status(0x00))

    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
    send.assert_not_called()


def test_older_status_cannot_replace_newer_cached_status() -> None:
    """Out-of-order status processing preserves the newest cached body."""
    device = _device()
    newer = MessageCAResponse(_status(0x02))
    older = MessageCAResponse(_status(0x01))

    with patch("midealan.devices.ca.time.monotonic", return_value=200.0):
        device._remember_ca_mode_status(newer, event_order=2, received_at=200.0)
        device._remember_ca_mode_status(older, event_order=1, received_at=100.0)

        with patch.object(device, "build_send") as send:
            device.set_attribute(DeviceAttributes.holiday_mode.value, True)
    assert send.call_args.args[0].body[0] == 0x12


def test_failed_send_does_not_publish_state_or_leave_pending() -> None:
    """A failed transport does not update state or consume the status."""
    device = _device()
    device.process_message(_status(0x00))
    with (
        patch.object(device, "build_send", side_effect=OSError("offline")),
        pytest.raises(OSError, match="offline"),
    ):
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
    assert device.attributes[DeviceAttributes.holiday_mode] is False
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
        send.assert_called_once()


def test_framing_has_body_only_and_valid_checksum() -> None:
    """The custom request is framed once by the existing Midea path."""
    body = bytes(range(CA_MODE_BODY_LENGTH))
    command = MessageQuestCustom(
        DeviceType.CA,
        ProtocolVersion.V3,
        MessageType.set,
        bytearray(body),
    )
    serialized = bytes(command.serialize())
    assert serialized[10 : 10 + CA_MODE_BODY_LENGTH] == body
    assert len(serialized) == 10 + CA_MODE_BODY_LENGTH + 1
    assert serialized[-1] == MessageBase.checksum(serialized[1:-1])
    assert serialized[10] == 0


def test_toshiba_path_does_not_cache_or_write() -> None:
    """Toshiba CA remains on its existing read-only path."""
    device = _device()
    device._manufacturer_code = "0008"
    device._toshiba_protocol = True
    with pytest.raises(ValueError, match="hardware verification"):
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)

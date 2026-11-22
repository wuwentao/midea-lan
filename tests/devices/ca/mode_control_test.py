"""Test Midea CA refrigerator mode control."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ca import DeviceAttributes, MideaCADevice
from midealan.devices.ca.message import (
    CA_MODE_BODY_LENGTH,
    build_ca_mode_body,
)
from midealan.message import MessageBase, MessageQuestCustom, MessageType


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


def _status(mode: int = 0) -> bytes:
    """Build a complete general-status response with a 61-byte payload."""
    body = bytearray(CA_MODE_BODY_LENGTH + 1)
    body[0] = 0x00
    body[1] = mode
    body[2:] = bytes(range(2, CA_MODE_BODY_LENGTH + 1))
    header = bytearray(
        [0xAA, 0, 0, 0, 0, 0, 0, 0, ProtocolVersion.V3, MessageType.query],
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

        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x01))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


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
        0xCA,
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


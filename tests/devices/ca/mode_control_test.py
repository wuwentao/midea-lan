"""Test Midea CA refrigerator mode control."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.device import MessageResult, MideaDevice
from midealan.devices.ca import (
    CAModeWritePendingError,
    DeviceAttributes,
    MideaCADevice,
)
from midealan.devices.ca.message import (
    CA_MODE_BODY_LENGTH,
    MessageCAResponse,
    MessageQuery,
    build_ca_mode_body,
)
from midealan.exceptions import ValueWrongType
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


def _complete_send(*_args: object, **kwargs: object) -> None:
    """Run the transport acknowledgement used by synchronous send mocks."""
    on_sent = kwargs.get("on_sent")
    if callable(on_sent):
        on_sent()


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
    original = bytes([0, 0xA0, *range(2, CA_MODE_BODY_LENGTH)])
    changed = build_ca_mode_body(original, mask, True)
    assert len(changed) == CA_MODE_BODY_LENGTH
    assert changed[0] == 0
    assert changed[1] == original[1] | mask
    assert changed[2:] == original[2:]
    assert build_ca_mode_body(changed, mask, False) == original
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
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
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
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
        send.assert_not_called()


def test_parse_message_always_clears_receive_marker() -> None:
    """CA receipt metadata is scoped to one parsed transport frame."""
    device = _device()
    device._message_received()

    with patch.object(
        MideaDevice,
        "parse_message",
        return_value=MessageResult.SUCCESS,
    ) as parse:
        assert device.parse_message(b"frame") == MessageResult.SUCCESS

    parse.assert_called_once_with(b"frame")
    assert device._ca_mode_received_event_order is None
    assert device._ca_mode_received_at is None


def test_parse_message_clears_receive_marker_when_dispatch_fails() -> None:
    """Malformed input cannot leak receipt ordering into the next frame."""
    device = _device()
    device._message_received()

    with (
        patch.object(MideaDevice, "parse_message", side_effect=ValueError("bad")),
        pytest.raises(ValueError, match="bad"),
    ):
        device.parse_message(b"frame")

    assert device._ca_mode_received_event_order is None
    assert device._ca_mode_received_at is None


def test_unsupported_and_invalid_mode_writes_are_rejected() -> None:
    """Only boolean writes to verified mode attributes reach the transport."""
    device = _device()
    device.set_attribute("unknown", True)
    with pytest.raises(ValueWrongType, match="Expected bool"):
        device.set_attribute(DeviceAttributes.storage_mode.value, 1.0)


def test_toshiba_write_return_path_remains_a_no_op() -> None:
    """A Toshiba write cannot fall through into the Midea mode implementation."""
    device = _device()
    device._toshiba_protocol = True
    with patch.object(device, "reject_toshiba_write"):
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
    assert device._ca_mode_pending is None


def test_toshiba_query_path_is_preserved() -> None:
    """Toshiba devices continue to use their family-specific query builder."""
    device = _device()
    device._toshiba_protocol = True
    with patch.object(device, "build_toshiba_query", return_value=[]) as query:
        assert device.build_query() == []
    query.assert_called_once_with()


def test_midea_query_path_is_preserved() -> None:
    """Midea CA devices retain the normal MessageQuery request."""
    device = _device()
    queries = device.build_query()
    assert len(queries) == 1
    assert isinstance(queries[0], MessageQuery)


def test_flex_zone_status_derives_variable_mode() -> None:
    """The existing 310A2111 temperature-derived mode remains published."""
    device = _device()
    device._model = "310A2111"
    device._subtype = 56
    status = bytearray(_status())
    status[10 + 35] = 0x00
    with patch.object(
        device,
        "process_toshiba_message",
        return_value=None,
    ):
        result = device.process_message(bytes(status))
    assert DeviceAttributes.variable_mode in result


def test_toshiba_status_dispatch_returns_before_midea_parser() -> None:
    """Decoded Toshiba statuses bypass Midea CA mode status handling."""
    device = _device()
    expected = {"power": True}
    with patch.object(device, "process_toshiba_message", return_value=expected):
        assert device.process_message(b"frame") == expected


def test_toshiba_frame_status_is_still_decoded() -> None:
    """The CA Toshiba decoder remains available after mode-cache additions."""
    device = _device()
    device._toshiba_protocol = True
    with patch.object(device, "process_toshiba_message", return_value={"power": True}):
        assert device.process_message(b"frame") == {"power": True}


def test_set_requires_status_and_waits_for_next_status() -> None:
    """Writes require a fresh status and a later status releases the guard."""
    device = _device()
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_not_called()

        device.process_message(_status(0x00))
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        send.assert_called_once()
        command = send.call_args.args[0]
        assert isinstance(command, MessageQuestCustom)
        expected = bytes([0x00, 0x01, *range(2, 61)])
        assert command.serialize()[10:-1] == expected

        with pytest.raises(CAModeWritePendingError, match="waiting for device"):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x01))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


def test_notify02_general_status_is_a_valid_set_template() -> None:
    """General-status notifications preserve existing mode bits."""
    device = _device()
    device.process_message(_status(0x01, MessageType.notify1, ListTypes.X02))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
    command = send.call_args.args[0]
    assert command.serialize()[10:-1] == bytes([0x00, 0x03, *range(2, 61)])


def test_mismatched_status_notification_is_not_a_set_template() -> None:
    """Only query/X00 and notify1/X02 general statuses are writable templates."""
    device = _device()
    device.process_message(_status(0x01, MessageType.query, ListTypes.X02))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
    send.assert_not_called()


def test_non_status_message_type_is_not_a_set_template() -> None:
    """SET responses never become a read-modify-write status template."""
    device = _device()
    device.process_message(_status(0x01, MessageType.set, ListTypes.X00))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
    send.assert_not_called()


def test_unchanged_mode_does_not_send() -> None:
    """A requested mode value already reported by the device is a no-op."""
    device = _device()
    device.process_message(_status(0x01))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
    send.assert_not_called()


def test_post_set_rejection_releases_pending_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer status rejecting the requested bit permits a safe retry."""
    device = _device()
    clock = [100.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        clock[0] += 1.0
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        clock[0] += 1.0
        device.process_message(_status(0x00))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


def test_deferred_async_send_cannot_be_confirmed_before_stream_write() -> None:
    """A status handled before the queued write cannot release the SET guard."""
    device = _device()
    device.process_message(_status(0x00))
    writer = MagicMock()
    loop = MagicMock()
    device._device_protocol_version = ProtocolVersion.V2
    device._writer = writer
    device._stream_loop = loop

    device.set_attribute(DeviceAttributes.storage_mode.value, True)

    loop.call_soon_threadsafe.assert_called_once()
    writer.write.assert_not_called()
    assert device._ca_mode_pending is not None
    assert device._ca_mode_pending.sent_order is None

    device._message_received()
    device.process_message(_status(0x00))
    device._message_dispatch_complete()
    assert device._ca_mode_pending is not None
    assert device._ca_mode_pending.sent_order is None

    callback, *args = loop.call_soon_threadsafe.call_args.args
    callback(*args)
    writer.write.assert_called_once()
    pending_after_write = device._ca_mode_pending
    assert pending_after_write is not None
    assert pending_after_write.sent_order is not None

    device._message_received()
    device.process_message(_status(0x01))
    device._message_dispatch_complete()
    assert device._ca_mode_pending is None


@pytest.mark.asyncio
async def test_checked_probe_marks_receipt_before_dispatch() -> None:
    """The checked-probe read records receipt before parsing its frame."""
    device = _device()
    reader = AsyncMock()
    reader.read.return_value = b"frame"
    device._reader = reader
    events: list[str] = []

    def parse_message(_msg: bytes) -> MessageResult:
        events.append("parsed")
        return MessageResult.SUCCESS

    with (
        patch.object(
            device,
            "_message_received",
            side_effect=lambda: events.append("received"),
        ),
        patch.object(
            device,
            "parse_message",
            side_effect=parse_message,
        ),
    ):
        await device._await_query_reply()

    assert events == ["received", "parsed"]


@pytest.mark.asyncio
async def test_supervisor_marks_receipt_before_dispatch() -> None:
    """The normal service read records receipt before parsing its frame."""
    device = _device()
    reader = AsyncMock()
    reader.read.side_effect = [b"frame", b""]
    device._reader = reader
    device._is_run = True
    events: list[str] = []

    def parse_message(_msg: bytes) -> MessageResult:
        events.append("parsed")
        device._is_run = False
        return MessageResult.SUCCESS

    with (
        patch.object(device, "_connect_loop", new_callable=AsyncMock),
        patch.object(device, "_check_refresh", new_callable=AsyncMock),
        patch.object(device, "_check_heartbeat"),
        patch.object(
            device,
            "_message_received",
            side_effect=lambda: events.append("received"),
        ),
        patch.object(device, "parse_message", side_effect=parse_message),
    ):
        await device._supervise()

    assert events == ["received", "parsed"]


def test_pre_set_status_with_delayed_dispatch_does_not_clear_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frame received before SET cannot confirm it after delayed dispatch."""
    device = _device()
    clock = [90.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
    device.process_message(_status(0x00))
    clock[0] = 100.0
    device._message_received()
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        clock[0] = 101.0
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        clock[0] = 102.0
        device.process_message(_status(0x01))
        device._message_dispatch_complete()
        with pytest.raises(CAModeWritePendingError):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x01))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


def test_pre_set_receipt_with_later_order_does_not_clear_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-write receipt cannot release the guard due to later dispatch order."""
    device = _device()
    clock = [100.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send):
        device.set_attribute(DeviceAttributes.storage_mode.value, True)

    pending = device._ca_mode_pending
    assert pending is not None
    assert pending.sent_order is not None
    assert pending.sent_at == 100.0

    device._remember_ca_mode_status(
        MessageCAResponse(_status(0x01)),
        event_order=pending.sent_order + 1,
        received_at=99.0,
    )
    assert device._ca_mode_pending is pending

    device._remember_ca_mode_status(
        MessageCAResponse(_status(0x01)),
        event_order=pending.sent_order + 2,
        received_at=100.0,
    )
    assert device._ca_mode_pending is None


def test_confirming_status_clears_pending_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Receipt order confirms a write even when monotonic clock ticks are equal."""
    device = _device()
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: 100.0)
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        device.process_message(_status(0x01))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


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

    with patch.object(device, "build_send", side_effect=_complete_send) as send:
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

        with patch.object(device, "build_send", side_effect=_complete_send) as send:
            device.set_attribute(DeviceAttributes.holiday_mode.value, True)
    assert send.call_args.args[0].body[1] == 0x12


def test_pending_write_is_reported_after_status_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired cache does not turn a pending write into a silent no-op."""
    device = _device()
    clock = [100.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send):
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        clock[0] += 121.0
        with pytest.raises(CAModeWritePendingError, match="waiting for device"):
            device.set_attribute(DeviceAttributes.freezing_mode.value, True)


def test_pending_write_recovers_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreported write cannot block later writes indefinitely."""
    device = _device()
    clock = [100.0]
    monkeypatch.setattr("midealan.devices.ca.time.monotonic", lambda: clock[0])
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        clock[0] += 241.0
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x00))
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 2


def test_disconnect_clears_pending_write_and_cached_status() -> None:
    """Reconnect requires a new status and does not retain a pending write."""
    device = _device()
    device.process_message(_status(0x00))
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)
        device.close_socket()
        device.set_attribute(DeviceAttributes.freezing_mode.value, True)
        assert send.call_count == 1

        device.process_message(_status(0x00))
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
    with patch.object(device, "build_send", side_effect=_complete_send) as send:
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
        send.assert_called_once()


def test_failed_send_preserves_a_replaced_pending_write() -> None:
    """An older send failure cannot clear pending state installed concurrently."""
    device = _device()
    device.process_message(_status(0x00))
    replacement = MagicMock()

    def replace_pending_then_fail(*_args: object, **_kwargs: object) -> None:
        device._ca_mode_pending = replacement
        raise OSError("offline")

    with (
        patch.object(device, "build_send", side_effect=replace_pending_then_fail),
        pytest.raises(OSError, match="offline"),
    ):
        device.set_attribute(DeviceAttributes.holiday_mode.value, True)
    assert device._ca_mode_pending is replacement


def test_stale_send_callback_cannot_restore_cleared_pending_write() -> None:
    """A delayed acknowledgement from an old connection is ignored."""
    device = _device()
    device.process_message(_status(0x00))
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.storage_mode.value, True)

    on_sent = send.call_args.kwargs["on_sent"]
    device.close_socket()
    on_sent()
    assert device._ca_mode_pending is None


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

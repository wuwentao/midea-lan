"""DC parameter appointment regression tests from anonymous status bodies."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from midealan.devices.dc import MideaDCDevice
from midealan.devices.dc.message import ControlAttributes as Attr
from midealan.exceptions import ValueWrongType
from tests.devices.dc.controls_dc_test import BASE_ARGS, DC_BODY, dryer, frame

DC_RESERVED = bytes.fromhex(
    "0401080002000000000200000100a601015a0000dc3734730000200001010000"
    "0000000001000000000001",
)
NOW = datetime(2026, 10, 12, 15, 24, 30, tzinfo=UTC)


@pytest.mark.parametrize("value", [True, 1, "true"])
def test_reservation_requires_a_deadline(value: bool | int | str) -> None:
    """Enabling the flag alone cannot start an unscheduled automatic cycle."""
    device = dryer()
    before = dict(device.attributes)
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="Use appointment_finish"),
    ):
        device.set_attribute(Attr.appointment, value)
    send.assert_not_called()
    assert device.attributes == before


@pytest.mark.parametrize(
    ("report", "wait", "duration", "status"),
    [(DC_RESERVED, 422, 90, "delay")],
)
def test_app_reservations_and_start_state(
    report: bytes,
    wait: int,
    duration: int,
    status: str,
) -> None:
    """Real app reservations count as active and retain independent editing guards."""
    with patch("midealan.devices.dc.message.datetime") as clock:
        clock.now.return_value = NOW
        device = dryer(report)
    assert device.get_attribute(Attr.appointment) is True
    assert device.get_attribute("start") is True
    assert device.get_attribute("status") == status
    assert device.get_attribute("time_remaining") == duration
    assert device.get_attribute(Attr.parameter_controls_available) is False
    assert device.get_attribute(Attr.appointment_controls_available) is True
    finish_value = device.get_attribute(Attr.appointment_finish)
    assert isinstance(finish_value, str)
    finish = datetime.fromisoformat(finish_value)
    assert finish == NOW.replace(second=0) + timedelta(minutes=wait + duration)


def test_finish_time_subtracts_program_duration_and_is_not_optimistic() -> None:
    """Use a timezone-bearing deadline, not total minutes until completion."""
    device = dryer()
    assert device._controls is not None
    before = dict(device.attributes)
    target = (NOW.replace(second=0) + timedelta(hours=10)).isoformat()
    duration = device.get_attribute("time_remaining")
    assert isinstance(duration, int)
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        device.set_attribute(Attr.appointment_finish, target)
    body = send.call_args_list[0].args[0].body
    assert body[1] == 255
    assert body[2] == 1
    assert int.from_bytes(body[14:16], "little") == 600 - duration
    assert body[3:12] == device._controls.body[3:12]
    assert device.attributes == before
    assert send.call_args_list[1].args[0].body == b"\x03"
    assert len(body) == 22
    assert body[12] == 253
    assert body[13] == device._controls.body[13]


@pytest.mark.parametrize("report", [DC_RESERVED])
def test_cancel_pauses_and_clears_both_fields_without_starting(report: bytes) -> None:
    """Cancel pauses explicitly; clearing only the wait could start immediately."""
    device = dryer(report)
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.appointment, False)
    clear_index = 1
    assert send.call_args_list[0].args[0].body == bytes([2, 255, 0])
    body = send.call_args_list[clear_index].args[0].body
    assert body[1:3] == bytes([255, 255])
    assert body[14:16] == bytes(2)
    assert body[3:12] == report[3:12]
    assert body[12] == 252
    assert body[13] == report[13]
    assert device.get_attribute(Attr.appointment) is True
    cancelled = bytearray(report)
    cancelled[2], cancelled[14], cancelled[15] = (1, 0, 0)
    cancelled[12] &= ~3
    device.process_message(frame(cancelled))
    assert device.get_attribute(Attr.appointment) is False
    assert device.get_attribute(Attr.appointment_finish) is None
    assert device.get_attribute("start") is False


@pytest.mark.parametrize("value", [True, False, 0, 170.5, "bad", "2026-10-13T08:00:00"])
def test_invalid_completion_values_never_send(value: bool | float | str) -> None:
    """Reject invalid types, syntax and naive local timestamps before sending."""
    device = dryer()
    assert device._controls is not None
    with (
        patch.object(device, "build_send") as send,
        pytest.raises((ValueError, ValueWrongType)),
    ):
        device.set_attribute(Attr.appointment_finish, value)
    send.assert_not_called()


@pytest.mark.parametrize("offset", [-1, 0, 1, 60, 1500])
def test_too_early_past_and_over_24h_targets_never_send(offset: int) -> None:
    """Reject deadlines that cannot leave a positive safe wait."""
    device = dryer()
    assert device._controls is not None
    target = (NOW.replace(second=0) + timedelta(minutes=offset)).isoformat()
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        with pytest.raises(ValueError, match="Completion time"):
            device.set_attribute(Attr.appointment_finish, target)
    send.assert_not_called()


@pytest.mark.parametrize(("power", "status"), [(0, 1), (1, 2), (1, 3), (1, 7)])
def test_reservation_cannot_interrupt_running_paused_or_faulted_cycle(
    power: int,
    status: int,
) -> None:
    """Reservations cannot change a running or paused actual cycle."""
    device = dryer()
    assert device._controls is not None
    report = bytearray(device._controls.body)
    report[1], report[2] = (power, status)
    device.process_message(frame(report))
    assert device.get_attribute(Attr.appointment_controls_available) is False
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="standby"),
    ):
        device.set_attribute(Attr.appointment, False)
    send.assert_not_called()


@pytest.mark.parametrize(
    ("status", "active"),
    [(1, False), (2, True), (3, False), (6, False), (8, True), (9, False)],
)
def test_dryer_start_reflects_running_and_active_reservation_only(
    status: int,
    active: bool,
) -> None:
    """Scope the corrected start state to the verified dryer only."""
    report = bytearray(DC_RESERVED)
    report[2] = status
    assert dryer(report).get_attribute("start") is active
    legacy = MideaDCDevice(customize="", **BASE_ARGS)
    legacy.process_message(frame(report))
    assert legacy.get_attribute("start") is (status in (2, 6))


def test_dryer_resuming_reservation_keeps_wait_high_byte() -> None:
    """Resume preserves all sixteen bits of the queued delay."""
    device = dryer(DC_RESERVED)
    with patch.object(device, "build_send") as send:
        device.set_attribute("start", True)
    assert send.call_args.args[0].body[3:16] == DC_RESERVED[3:16]
    assert send.call_args.args[0].body[14:16] == (422).to_bytes(2, "little")


def test_dryer_can_edit_or_cancel_a_selected_but_not_started_reservation() -> None:
    """Status 6 occurs after setting only the flag/wait with start unchanged."""
    report = bytearray(DC_RESERVED)
    report[2] = 6
    device = dryer(report)
    assert device.get_attribute("start") is False
    assert device.get_attribute(Attr.parameter_controls_available) is False
    assert device.get_attribute(Attr.appointment_controls_available) is True
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.appointment, False)
    assert send.call_args_list[0].args[0].body[2] == 0
    assert send.call_args_list[1].args[0].body[12] == 252


def test_cancelled_dryer_with_retained_inactive_wait_has_no_deadline() -> None:
    """The dryer retains the last wait after cancellation until powered off."""
    report = bytearray(DC_RESERVED)
    report[2] = 1
    report[12] &= ~3
    device = dryer(report)
    assert device.get_attribute(Attr.appointment) is False
    assert device.get_attribute(Attr.appointment_finish) is None
    assert device.get_attribute("start") is False


def test_dryer_verified_duration_above_255_uses_minutes_not_hours() -> None:
    """Verified dryers report a sixteen-bit minute duration."""
    report = bytearray(DC_RESERVED)
    report[17:19] = (300).to_bytes(2, "little")
    assert dryer(report).get_attribute("time_remaining") == 300


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("retained_minutes", [0, 90, 300])
def test_power_off_clears_duration_until_power_returns(
    profile: bool,
    retained_minutes: int,
) -> None:
    """Off reports clear stale durations in both entity state and update events."""
    device = dryer() if profile else MideaDCDevice(customize="", **BASE_ARGS)
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[17:19] = (300).to_bytes(2, "little")
    powered_duration = 300 if profile else 104
    update = device.process_message(frame(report))
    assert device.get_attribute("time_remaining") == powered_duration
    assert update["time_remaining"] == powered_duration

    report[1] = 0
    report[17:19] = retained_minutes.to_bytes(2, "little")
    update = device.process_message(frame(report))
    assert device.get_attribute("power") is False
    assert device.get_attribute("time_remaining") is None
    assert update["time_remaining"] is None

    report[1] = 1
    report[17:19] = (300).to_bytes(2, "little")
    update = device.process_message(frame(report))
    assert device.get_attribute("time_remaining") == powered_duration
    assert update["time_remaining"] == powered_duration


def test_unsupported_reservation_flag_is_read_only() -> None:
    """Unknown reservation codes must not be treated as off."""
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[12] = 3
    device = dryer(report)
    assert device.get_attribute(Attr.appointment) is None
    assert device.get_attribute(Attr.appointment_controls_available) is False

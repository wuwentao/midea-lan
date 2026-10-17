"""DB parameter appointment regression tests from anonymous status bodies."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from midealan.devices.db.message import ControlAttributes as Attr
from midealan.exceptions import ValueWrongType
from tests.devices.db.controls_db_test import DB_BODY, frame, washer

DB_RESERVED = bytes.fromhex(
    "040106001f0540060303020400427a01208a0000db5933b10000003f0c080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
NOW = datetime(2026, 10, 12, 15, 24, 30, tzinfo=UTC)


@pytest.mark.parametrize("value", [True, 1, "true"])
def test_reservation_requires_a_deadline(value: bool | int | str) -> None:
    """Enabling the flag alone cannot start an unscheduled automatic cycle."""
    device = washer()
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
    [(DB_RESERVED, 378, 138, "delay")],
)
def test_app_reservations_and_start_state(
    report: bytes,
    wait: int,
    duration: int,
    status: str,
) -> None:
    """Real app reservations count as active and retain independent editing guards."""
    with patch("midealan.devices.db.message.datetime") as clock:
        clock.now.return_value = NOW
        device = washer(report)
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
    device = washer()
    assert device._controls is not None
    before = dict(device.attributes)
    target = (NOW.replace(second=0) + timedelta(hours=10)).isoformat()
    duration = device.get_attribute("time_remaining")
    assert isinstance(duration, int)
    with (
        patch("midealan.devices.db.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        device.set_attribute(Attr.appointment_finish, target)
    body = send.call_args_list[0].args[0].body
    assert body[1] == 255
    assert body[2] == 1
    assert int.from_bytes(body[14:16], "little") == 600 - duration
    assert body[3:12] == DB_BODY[3:12]
    assert device.attributes == before
    assert send.call_args_list[1].args[0].body == b"\x03"
    assert len(body) == 54
    assert body[13] == DB_BODY[13] | 2
    assert body[22] == 2
    assert body[35] == 247
    assert body[36:38] == DB_BODY[36:38]


@pytest.mark.parametrize("report", [DB_RESERVED])
def test_cancel_pauses_and_clears_both_fields_without_starting(report: bytes) -> None:
    """Cancel pauses explicitly; clearing only the wait could start immediately."""
    device = washer(report)
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.appointment, False)
    clear_index = 0
    body = send.call_args_list[clear_index].args[0].body
    assert body[1:3] == bytes([255, 0])
    assert body[14:16] == bytes(2)
    assert body[3:12] == report[3:12]
    assert body[13] == report[13] & ~2
    assert body[22] == 2
    assert body[35] == 243
    assert body[36:38] == report[36:38]
    assert device.get_attribute(Attr.appointment) is True
    cancelled = bytearray(report)
    cancelled[2], cancelled[14], cancelled[15] = (1, 0, 0)
    cancelled[13] &= ~2
    device.process_message(frame(cancelled))
    assert device.get_attribute(Attr.appointment) is False
    assert device.get_attribute(Attr.appointment_finish) is None
    assert device.get_attribute("start") is False


@pytest.mark.parametrize("value", [True, False, 0, 170.5, "bad", "2026-10-13T08:00:00"])
def test_invalid_completion_values_never_send(value: bool | float | str) -> None:
    """Reject invalid types, syntax and naive local timestamps before sending."""
    device = washer()
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
    device = washer()
    assert device._controls is not None
    target = (NOW.replace(second=0) + timedelta(minutes=offset)).isoformat()
    with (
        patch("midealan.devices.db.message.datetime") as clock,
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
    device = washer()
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


def test_short_v2_report_disables_reservations() -> None:
    """Reservations require the cloud-cycle fields to preserve parameters."""
    device = washer(DB_BODY[:31])
    assert device.get_attribute(Attr.appointment_controls_available) is False
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="standby"),
    ):
        device.set_attribute(Attr.appointment, False)
    send.assert_not_called()

"""Offline acceptance for exact-model grouped writes and their state context."""

import socket
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from typing import cast
from unittest.mock import patch

import pytest

from midealan.crc8 import calculate
from midealan.device import MideaDevice
from midealan.devices.ac import DeviceAttributes as A
from midealan.devices.ac import MideaACDevice
from midealan.devices.ac.message import PropertiesBody, PropertiesSet
from midealan.message import ListTypes, NewProtocolMessageBody
from tests.devices.ac.device_ac_test import MODEL_220F4047_C0_BODY
from tests.devices.ac.device_ac_test import TestMideaACDevice as _DeviceFixture

Controlled = tuple[MideaACDevice, list[PropertiesSet]]


@pytest.fixture(autouse=True)
def stable_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep exact deadline arithmetic independent of host clock precision."""
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)


class _InertSocket:
    """Witness the real socket lifecycle without opening a transport."""

    def __init__(self) -> None:
        """Keep only harmless shutdown and close markers."""
        self.calls: list[str] = []

    def shutdown(self, how: int) -> None:
        """Record the standard shutdown argument."""
        self.calls.append(f"shutdown:{how}")

    def close(self) -> None:
        """Record closing the inert object."""
        self.calls.append("close")


def core_response(
    power: bool = False,
    mode: int = 2,
    temperature: float = 27.5,
    fan: int = 102,
    extra: Sequence[tuple[int, bytes]] = (),
) -> bytes:
    """Produce the real five-byte RX TLV layout plus serial/body CRC."""
    properties = [(1, bytes([int(power), mode, round(temperature * 2), fan])), *extra]
    body = bytearray([ListTypes.B1, len(properties)])
    for tag, value in properties:
        body.extend(NewProtocolMessageBody.pack(tag, bytearray(value), pack_len=5))
    body.append(1)
    body.append(calculate(body))
    return _DeviceFixture._response(body)


@pytest.fixture(autouse=True)
def no_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[threading.Thread], None]:
    """Fail instead of touching a network or starting an appliance thread."""
    original_start = threading.Thread.start

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("OFFLINE_ONLY")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(threading.Thread, "start", forbidden)
    # Only the explicit lock-witness test uses this on inert worker threads.
    return original_start


@pytest.fixture
def controlled() -> Iterator[Controlled]:
    """Feed a real decoder and replace only the external send boundary."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(core_response())
    sent: list[PropertiesSet] = []
    with patch.object(device, "build_send", side_effect=sent.append):
        yield device, sent
    assert not device.is_alive()


def test_three_legacy_golden_messages(controlled: Controlled) -> None:
    """Each normal core call emits exactly one source-backed grouped body."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    device.set_attribute(A.mode, 2)
    device.set_attribute(A.power, False)
    assert [message._body.hex() for message in sent] == [
        "0101000401053766",
        "0101000401023766",
        "0101000400023766",
    ]
    assert device.attributes[A.power] is False  # Submitted state is not readback.


@pytest.mark.parametrize("temperature", [16, 16.5, 17, 27.5, 32])
def test_temperature_codec_preserves_off(
    controlled: Controlled,
    temperature: float,
) -> None:
    """Temperature-only writes preserve explicit off and half-degree precision."""
    device, sent = controlled
    device.set_target_temperature(temperature, None)
    assert sent[-1].mode_power == (False, 2, temperature, 102)
    assert sent[-1]._body[6] == round(temperature * 2)


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), 15.5, 32.5, 16.3])
def test_invalid_temperature_rejected_without_send(
    controlled: Controlled,
    temperature: float,
) -> None:
    """Invalid setpoints cannot reach the send boundary."""
    device, sent = controlled
    with pytest.raises(ValueError, match="Operating temperature"):
        device.set_target_temperature(temperature, None)
    assert not sent


@pytest.mark.parametrize("fan", [0, 40, 102])
def test_fan_zero_not_missing(controlled: Controlled, fan: int) -> None:
    """Zero fan speed is a supplied value, not an absent field."""
    device, sent = controlled
    device.set_attribute(A.fan_speed, fan)
    assert sent[-1].mode_power == (False, 2, 27.5, fan)


@pytest.mark.parametrize("fan", [-1, 103, 40.5])
def test_invalid_fan_rejected(controlled: Controlled, fan: float) -> None:
    """Out-of-domain or fractional fan values cannot be truncated or sent."""
    device, sent = controlled
    with pytest.raises(ValueError, match="Operating fan"):
        device.set_attribute(A.fan_speed, fan)
    assert not sent


def test_explicit_mode_zero_rejected_not_defaulted(controlled: Controlled) -> None:
    """An explicit zero mode is rejected instead of replaced with a default."""
    device, sent = controlled
    with pytest.raises(ValueError, match="Operating mode"):
        device.set_target_temperature(27.5, 0)
    assert not sent


@pytest.mark.parametrize("initial_power", [False, True])
def test_power_temperature_sequence(
    controlled: Controlled,
    initial_power: bool,
) -> None:
    """A following setpoint write preserves the previous power intent."""
    device, sent = controlled
    device.set_attribute(A.power, initial_power)
    device.set_target_temperature(17, None)
    assert sent[-1].mode_power == (initial_power, 2, 17, 102)


@pytest.mark.parametrize("order", ["temp_fan", "fan_temp", "mode_temp", "combined_off"])
def test_continuous_requests_keep_previous_intent(
    controlled: Controlled,
    order: str,
) -> None:
    """Both explicit and inherited fields survive consecutive setters."""
    device, sent = controlled
    if order == "temp_fan":
        device.set_target_temperature(17, None)
        device.set_attribute(A.fan_speed, 40)
        expected = (False, 2, 17, 40)
    elif order == "fan_temp":
        device.set_attribute(A.fan_speed, 40)
        device.set_target_temperature(17, None)
        expected = (False, 2, 17, 40)
    elif order == "mode_temp":
        device.set_attribute(A.mode, 5)
        device.set_target_temperature(17, None)
        expected = (True, 5, 17, 102)
    else:
        device.set_target_temperature(17, 5)
        device.set_attribute(A.power, False)
        expected = (False, 5, 17, 102)
    assert len(sent) == 2
    assert sent[-1].mode_power == expected


def test_late_c0_b1_cannot_revert_unconfirmed_control(controlled: Controlled) -> None:
    """Late readback cannot erase pending intent or the V007 target guard."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    device.process_message(core_response())  # Old B1 arrives after the command.
    device.process_message(_DeviceFixture._response(bytearray(MODEL_220F4047_C0_BODY)))
    device.set_target_temperature(17, None)
    assert sent[-1].mode_power == (True, 5, 17.0, 102)
    assert device.attributes[A.target_temperature] == 27.5  # V007 still guards C0.


def test_matching_b1_confirms_and_external_state_can_then_change(
    controlled: Controlled,
) -> None:
    """Matching observed state releases intent and accepts later external state."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    device.process_message(core_response(True, 5))
    assert device._pending_operating is None
    device.process_message(core_response(True, 2, 26, 40))
    device.set_attribute(A.power, False)
    assert sent[-1].mode_power == (False, 2, 26, 40)


def test_pending_timeout_fails_closed_then_fresh_b1_resynchronizes(
    controlled: Controlled,
) -> None:
    """Expired intent stops writes until a new complete B1 arrives."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    pending = device._pending_operating
    assert pending is not None
    last_time = pending[1]
    with patch(
        "midealan.devices.ac.time.monotonic",
        return_value=last_time + device._operating_timeout(),
    ):
        with pytest.raises(RuntimeError, match="complete B1"):
            device.set_target_temperature(17, None)
        assert len(sent) == 1
        device.process_message(core_response(False, 2, 26, 40))
        device.set_target_temperature(17, None)
    assert sent[-1].mode_power == (False, 2, 17, 40)


def test_timeout_with_late_mismatching_b1_is_bounded(controlled: Controlled) -> None:
    """Expired intent cannot override a subsequently observed complete state."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    pending = device._pending_operating
    assert pending is not None
    last_time = pending[1]
    with patch(
        "midealan.devices.ac.time.monotonic",
        return_value=last_time + device._operating_timeout(),
    ):
        device.process_message(core_response(False, 2, 26, 40))
        assert device._pending_operating is None
        device.set_attribute(A.power, False)
    assert sent[-1].mode_power == (False, 2, 26, 40)


def test_continuous_writes_cannot_renew_pending_deadline(
    controlled: Controlled,
) -> None:
    """Consecutive writes retain the first unconfirmed submission's expiry."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    assert device._pending_operating is not None
    first_sent_at = device._pending_operating[1]
    with patch(
        "midealan.devices.ac.time.monotonic",
        return_value=first_sent_at + 10,
    ):
        device.set_target_temperature(17, None)
    assert device._pending_operating is not None
    assert device._pending_operating[1] == first_sent_at
    with (
        patch(
            "midealan.devices.ac.time.monotonic",
            return_value=first_sent_at + device._operating_timeout(),
        ),
        pytest.raises(RuntimeError, match="complete B1"),
    ):
        device.set_attribute(A.fan_speed, 40)
    assert len(sent) == 2


def test_missing_baseline_does_not_guess_and_off_remains_available() -> None:
    """Missing core state refuses guessing but allows an independent safe off."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with patch.object(device, "build_send") as send:
        with pytest.raises(RuntimeError, match="complete B1"):
            device.set_attribute(A.mode, 2)
        with pytest.raises(RuntimeError, match="complete B1"):
            device.set_target_temperature(17, None)
        send.assert_not_called()
        device.set_attribute(A.power, False)
    assert send.call_args.args[0]._body.hex() == "0101000100"


def test_disconnect_drops_command_context(controlled: Controlled) -> None:
    """Unavailability invalidates both observed and pending command contexts."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    device.set_available(False)
    with pytest.raises(RuntimeError, match="complete B1"):
        device.set_attribute(A.fan_speed, 40)
    device.set_attribute(A.power, False)
    assert sent[-1]._body.hex() == "0101000100"


@pytest.mark.parametrize("running", [False, True])
def test_real_close_drops_context_and_ignores_late_frames(
    controlled: Controlled,
    running: bool,
) -> None:
    """The actual close entry refuses old-session state even without callbacks."""
    device, sent = controlled
    inert = _InertSocket()
    device._socket = cast("socket.socket", inert)
    device._is_run = running
    device.set_attribute(A.mode, 5)
    device.close()
    assert device._confirmed_operating is None
    assert device._pending_operating is None
    device.process_message(core_response(True, 5))
    with pytest.raises(RuntimeError, match="complete B1"):
        device.set_attribute(A.fan_speed, 40)
    assert len(sent) == 1
    if running:
        assert cast("socket.socket | None", device._socket) is None
        assert inert.calls == [f"shutdown:{socket.SHUT_RDWR}", "close"]
    else:
        # Preserve the base close() contract for a thread not running yet.
        assert cast("object", device._socket) is inert
        device.close_socket()
    assert not device.is_alive()


@pytest.mark.parametrize("running", [False, True])
def test_real_socket_close_invalidates_context_without_a_callback(
    controlled: Controlled,
    running: bool,
) -> None:
    """Direct active-socket closure invalidates both contexts for either run flag."""
    device, sent = controlled
    inert = _InertSocket()
    device._socket = cast("socket.socket", inert)
    device._is_run = running
    device.set_attribute(A.mode, 5)
    device.close_socket()
    assert cast("socket.socket | None", device._socket) is None
    assert inert.calls == [f"shutdown:{socket.SHUT_RDWR}", "close"]
    assert device._confirmed_operating is None
    assert device._pending_operating is None
    device.process_message(core_response(True, 5))
    with pytest.raises(RuntimeError, match="complete B1"):
        device.set_attribute(A.fan_speed, 40)
    assert len(sent) == 1
    device._is_run = False


def test_closing_old_socket_preserves_active_context(controlled: Controlled) -> None:
    """Retiring an old socket cannot disable the current connection's state."""
    device, sent = controlled
    active, old = _InertSocket(), _InertSocket()
    device._socket = cast("socket.socket", active)
    device.set_attribute(A.mode, 5)
    device.close_socket(cast("socket.socket", old))
    assert cast("object", device._socket) is active
    assert not active.calls
    assert old.calls == [f"shutdown:{socket.SHUT_RDWR}", "close"]
    device.set_attribute(A.fan_speed, 40)
    assert sent[-1].mode_power == (True, 5, 27.5, 40)
    device.close_socket()


def test_reconnect_requires_new_complete_b1_after_ready(controlled: Controlled) -> None:
    """Availability alone cannot revive old state or closed-session readback."""
    device, sent = controlled
    device.set_attribute(A.mode, 5)
    device.set_available(False)
    device.process_message(core_response(True, 5))
    assert device._confirmed_operating is None
    device.set_available(True)
    with pytest.raises(RuntimeError, match="complete B1"):
        device.set_attribute(A.fan_speed, 40)
    device.process_message(core_response(False, 2, 26, 102))
    device.set_attribute(A.fan_speed, 40)
    assert sent[-1].mode_power == (False, 2, 26, 40)


def test_failed_send_invalidates_both_contexts(controlled: Controlled) -> None:
    """A send exception must not leave reusable unconfirmed state."""
    device, sent = controlled
    with (
        patch.object(device, "build_send", side_effect=OSError("synthetic failure")),
        pytest.raises(OSError, match="synthetic failure"),
    ):
        device.set_attribute(A.mode, 5)
    assert device._pending_operating is None
    assert device._confirmed_operating is None
    assert not sent


@pytest.mark.parametrize(
    "fault",
    ["crc", "duplicate", "partial", "conflict", "b0", "truncated"],
)
def test_bad_core_frame_cannot_seed_command_context(fault: str) -> None:
    """Malformed, partial and conflicting core frames cannot seed commands."""
    extra = [(2, bytes([2]))]
    if fault == "duplicate":
        extra += [(2, bytes([2]))]
    if fault == "conflict":
        extra = [(2, bytes([5]))]
    frame = core_response(extra=extra)
    body = bytearray(frame[10:-1])
    if fault == "crc":
        body[-1] ^= 1
    elif fault == "partial":
        body = bytearray([ListTypes.B1, 1, 2, 0, 0, 1, 2, 1])
        body.append(calculate(body))
    elif fault == "b0":
        body[0] = ListTypes.B0
        body[-1] = calculate(body[:-1])
    elif fault == "truncated":
        body = body[:-3]
    assert PropertiesBody._validated_operating_snapshot(body) is None
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_DeviceFixture._response(body))
    with patch.object(device, "build_send") as send:
        with pytest.raises(RuntimeError, match="complete B1"):
            device.set_attribute(A.mode, 5)
        send.assert_not_called()


def test_grouped_and_independent_core_formats_are_mutually_exclusive() -> None:
    """One message cannot accidentally contain both core wire formats."""
    message = PropertiesSet(0)
    message.mode_power = (False, 2, 27.5, 102)
    message.operating_power = False
    with pytest.raises(ValueError, match="conflict"):
        _ = message._body


@pytest.mark.parametrize(("model", "subtype"), [("220F4047", 9), ("other", 8)])
def test_unrelated_model_keeps_legacy_general_path(model: str, subtype: int) -> None:
    """Exact model and subtype matching leaves unrelated controls untouched."""
    device = _DeviceFixture._make_device(model, subtype)
    with patch.object(device, "build_send") as send:
        device.set_attribute(A.mode, 2)
    message = send.call_args.args[0]
    assert not isinstance(message, PropertiesSet)
    assert message.mode == 2


def test_same_instance_serializes_reentrant_lock_use(controlled: Controlled) -> None:
    """Nested same-thread controls can reuse the lock without deadlocking."""
    device, sent = controlled
    with device._operating_lock:
        device.set_target_temperature(17, 5)
        device.set_attribute(A.power, False)
    assert len(sent) == 2
    assert sent[-1].mode_power == (False, 5, 17, 102)


@pytest.mark.parametrize("mode", [1, 6])
def test_supported_mode_bounds_remain_available(
    controlled: Controlled,
    mode: int,
) -> None:
    """The complete existing exact-model mode range remains writable."""
    device, sent = controlled
    device.set_attribute(A.mode, mode)
    assert sent[-1].mode_power == (True, mode, 27.5, 102)


def test_fractional_attribute_mode_is_not_truncated(controlled: Controlled) -> None:
    """A fractional attribute mode fails before forming a command."""
    device, sent = controlled
    with pytest.raises(ValueError, match="Operating mode must be an integer"):
        device.set_attribute(A.mode, 2.5)
    assert not sent


def test_confirmed_state_expires_without_pending_intent(controlled: Controlled) -> None:
    """Observed state alone cannot seed grouped writes indefinitely."""
    device, sent = controlled
    assert device._confirmed_operating is not None
    observed_at = device._confirmed_operating[1]
    with (
        patch(
            "midealan.devices.ac.time.monotonic",
            return_value=observed_at + device._operating_timeout(),
        ),
        pytest.raises(RuntimeError, match="complete B1"),
    ):
        device.set_attribute(A.mode, 5)
    assert not sent


def test_matching_readback_during_send_is_not_recreated_as_pending(
    controlled: Controlled,
) -> None:
    """Reentrant observed confirmation survives completion of the send call."""
    device, _ = controlled
    with patch.object(
        device,
        "build_send",
        side_effect=lambda _: device.process_message(core_response(True, 5)),
    ):
        device.set_attribute(A.mode, 5)
    assert device._pending_operating is None
    assert device._confirmed_operating is not None
    assert device._confirmed_operating[0] == (True, 5, 27.5, 102)


def test_disconnect_during_send_cannot_recreate_pending_context(
    controlled: Controlled,
) -> None:
    """A synchronous unavailability notification stays authoritative."""
    device, _ = controlled
    with patch.object(
        device,
        "build_send",
        side_effect=lambda _: device.set_available(False),
    ):
        device.set_attribute(A.mode, 5)
    assert device._pending_operating is None
    assert device._confirmed_operating is None


@pytest.mark.parametrize("fault", ["power", "mode", "temperature", "fan", "status"])
def test_invalid_core_domains_are_not_command_baselines(fault: str) -> None:
    """CRC validity cannot promote invalid domain values into control state."""
    body = bytearray(core_response()[10:-1])
    index, value = {
        "power": (6, 2),
        "mode": (7, 0),
        "temperature": (8, 31),
        "fan": (9, 103),
        "status": (4, 1),
    }[fault]
    body[index] = value
    body[-1] = calculate(body[:-1])
    assert PropertiesBody._validated_operating_snapshot(body) is None


@pytest.mark.parametrize(
    "body",
    [bytearray(), bytearray([ListTypes.B1]), bytearray([ListTypes.B1, 0])],
)
def test_short_core_frame_is_not_a_baseline(body: bytearray) -> None:
    """Short envelopes fail closed without indexing outside the frame."""
    assert PropertiesBody._validated_operating_snapshot(body) is None


def test_two_inert_workers_serialize_core_intents(
    controlled: Controlled,
    no_transport: Callable[[threading.Thread], None],
) -> None:
    """Two real test threads cannot interleave one appliance's core writes."""
    device, sent = controlled
    first_send = threading.Event()
    release_send = threading.Event()
    second_attempt = threading.Event()
    errors: list[Exception] = []

    def record(message: PropertiesSet) -> None:
        sent.append(message)
        if len(sent) == 1:
            first_send.set()
            if not release_send.wait(5):
                raise TimeoutError("synthetic send wait expired")

    def run(action: Callable[[], None]) -> None:
        try:
            action()
        except (RuntimeError, ValueError, OSError) as error:
            errors.append(error)

    def second_write() -> None:
        second_attempt.set()
        device.set_target_temperature(17, None)

    first = threading.Thread(
        target=run,
        args=(lambda: device.set_attribute(A.mode, 5),),
    )
    second = threading.Thread(target=run, args=(second_write,))
    with patch.object(device, "build_send", side_effect=record):
        try:
            no_transport(first)
            assert first_send.wait(5)
            no_transport(second)
            assert second_attempt.wait(5)
            acquired = device._operating_lock.acquire(blocking=False)
            if acquired:
                device._operating_lock.release()
            assert not acquired
            assert len(sent) == 1
        finally:
            release_send.set()
            first.join(5)
            if second.ident is not None:
                second.join(5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors
    assert [message.mode_power for message in sent] == [
        (True, 5, 27.5, 102),
        (True, 5, 17, 102),
    ]


def _property_response(
    properties: Sequence[tuple[int, bytes]],
    body_type: ListTypes = ListTypes.B1,
) -> bytes:
    """Build a valid response without opening transport."""
    body = bytearray([body_type, len(properties)])
    for tag, value in properties:
        body.extend(NewProtocolMessageBody.pack(tag, bytearray(value), pack_len=5))
    body.append(1)
    body.append(calculate(body))
    return _DeviceFixture._response(body)


def _written_properties(message: PropertiesSet) -> dict[int, bytes]:
    """Read the actual serialized TX properties, excluding device readback."""
    body = message._body
    cursor = 1
    result = {}
    for _ in range(body[0]):
        tag = body[cursor] | body[cursor + 1] << 8
        length = body[cursor + 2]
        cursor += 3
        result[tag] = bytes(body[cursor : cursor + length])
        cursor += length
    assert cursor == len(body)
    return result


def test_exact_model_has_independent_operating_and_person_queries() -> None:
    """Extra verified probes preserve the upstream dynamic-query mechanism."""
    from midealan.devices.ac.message import (  # noqa: PLC0415
        PropertiesCapsQuery,
        PropertiesDefaultQuery,
        PropertiesOperatingQuery,
        PropertiesPersonAvoidQuery,
        PropertiesPersonTowardQuery,
    )

    device = _DeviceFixture._make_device("220F4047", 8)
    device._capabilities["light_sensitive"] = True
    queries = device.build_query()
    classes = [type(query) for query in queries]
    assert PropertiesDefaultQuery in classes
    assert PropertiesCapsQuery in classes
    assert classes.count(PropertiesOperatingQuery) == 1
    assert classes.count(PropertiesPersonTowardQuery) == 1
    assert classes.count(PropertiesPersonAvoidQuery) == 1
    assert next(
        q for q in queries if type(q) is PropertiesOperatingQuery
    ).properties == (
        1,
        2,
        3,
        6,
    )
    assert next(
        q for q in queries if type(q) is PropertiesPersonTowardQuery
    ).properties == (0x0032,)
    assert next(
        q for q in queries if type(q) is PropertiesPersonAvoidQuery
    ).properties == (0x0033,)


@pytest.mark.parametrize(("model", "subtype"), [("220F4047", 9), ("other", 8)])
def test_person_controls_and_probes_are_exactly_gated(
    model: str,
    subtype: int,
) -> None:
    """Other model/subtype pairs keep their previous attributes and queries."""
    device = _DeviceFixture._make_device(model, subtype)
    assert A.wind_straight not in device.attributes
    assert A.wind_avoid not in device.attributes
    assert not any(
        type(q).__name__ == "PropertiesOperatingQuery" for q in device.build_query()
    )
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(NotImplementedError, match="unsupported"),
    ):
        device.set_person_airflow_mode("toward")
    send.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "toward", "avoid"),
    [
        ("toward", b"\x01", b"\x00"),
        ("avoid", b"\x00", b"\x01"),
    ],
)
def test_person_enabling_is_atomic_and_readback_stays_observed(
    mode: str,
    toward: bytes,
    avoid: bytes,
) -> None:
    """One write clears the opposite setting, without pretending it was observed."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x0032, b"\x00"), (0x0033, b"\x00")]))
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode(mode)
    assert send.call_count == 1
    properties = _written_properties(send.call_args.args[0])
    assert properties[0x0032] == toward
    assert properties[0x0033] == avoid
    assert device.attributes[A.wind_straight] is False
    assert device.attributes[A.wind_avoid] is False
    updated = device.process_message(
        _property_response([(0x0032, toward), (0x0033, avoid)]),
    )
    assert updated[A.wind_straight] is (toward == b"\x01")
    assert updated[A.wind_avoid] is (avoid == b"\x01")


@pytest.mark.parametrize(
    ("active", "expected"),
    [
        (0x0032, 0x0032),
        (0x0033, 0x0033),
    ],
)
def test_person_off_writes_only_observed_active_flag(
    active: int,
    expected: int,
) -> None:
    """Off follows the observed active feature, without a redundant all-off pair."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(
        _property_response(
            [
                (0x0032, bytes([int(active == 0x0032)])),
                (0x0033, bytes([int(active == 0x0033)])),
            ],
        ),
    )
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode("off")
    properties = _written_properties(send.call_args.args[0])
    assert properties[expected] == b"\x00"
    assert (0x0033 if expected == 0x0032 else 0x0032) not in properties
    assert (
        device.attributes[A.wind_straight if active == 0x0032 else A.wind_avoid] is True
    )


def test_person_already_off_is_noop_and_bad_mode_is_rejected() -> None:
    """Unknown/off state cannot manufacture a write; invalid modes are rejected."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x0032, b"\x00"), (0x0033, b"\x00")]))
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode("off")
        with pytest.raises(ValueError, match="Unsupported"):
            device.set_person_airflow_mode("invalid")
    send.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
def test_exact_screen_route_and_existing_boolean_light_encoding(enabled: bool) -> None:
    """Reuse screen/light codecs with the exact-model absolute display route."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with patch.object(device, "build_send") as send:
        device.set_attribute(A.screen_display, enabled)
        device.set_attribute(A.light_sensitive, enabled)
    assert send.call_count == 2
    screen, light = (item.args[0] for item in send.call_args_list)
    assert isinstance(screen, PropertiesSet)
    assert _written_properties(screen)[0x0017] == bytes([0x64 if enabled else 0])
    assert _written_properties(light)[0x0208] == bytes([3 if enabled else 0])
    update = device.process_message(
        _property_response([(0x0208, bytes([3 if enabled else 0]))]),
    )
    assert update[A.light_sensitive] is enabled


def test_valid_independent_b1_target_latches_precedence_and_invalid_does_not() -> None:
    """Only a valid B1 target supersedes the startup C0 source."""
    device = _DeviceFixture._make_device("220F4047", 8)
    c0 = _DeviceFixture._response(bytearray(MODEL_220F4047_C0_BODY))
    device.process_message(c0)
    fallback = device.attributes[A.target_temperature]
    device.process_message(_property_response([(3, b"\x00")]))
    assert device._prefer_core_target_temperature is False
    assert device.attributes[A.target_temperature] == fallback
    device.process_message(_property_response([(3, bytes([105]))]))  # 27.5 = (105-50)/2
    assert cast("bool", device._prefer_core_target_temperature) is True
    assert device.attributes[A.target_temperature] == 27.5
    device.process_message(c0)
    assert device.attributes[A.target_temperature] == 27.5


def test_b0_and_crc_invalid_b1_cannot_latch_target_source() -> None:
    """A set echo or corrupt query cannot disable the C0 startup source."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(3, bytes([105]))], ListTypes.B0))
    assert device._prefer_core_target_temperature is False
    frame = _property_response([(3, bytes([105]))])
    body = bytearray(frame[10:-1])
    body[-1] ^= 1
    device.process_message(_DeviceFixture._response(body))
    assert device._prefer_core_target_temperature is False


@pytest.mark.parametrize(("mode", "tag"), [("toward", 0x32), ("avoid", 0x33)])
def test_person_enable_then_off_keeps_last_intent(mode: str, tag: int) -> None:
    """A rapid off must supersede the last submitted, not yet observed enable."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode(mode)
        device.set_person_airflow_mode("off")
    assert send.call_count == 2
    written = _written_properties(send.call_args.args[0])
    assert written[tag] == b"\x00"
    assert (0x33 if tag == 0x32 else 0x32) not in written
    assert device.attributes[A.wind_straight] is False
    assert device.attributes[A.wind_avoid] is False


@pytest.mark.parametrize(
    ("attr", "tag"),
    [(A.wind_straight, 0x32), (A.wind_avoid, 0x33)],
)
def test_explicit_person_off_retains_target_in_conflicting_state(
    attr: str,
    tag: int,
) -> None:
    """An explicit off targets its own flag even during conflicting readback."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x32, b"\x01"), (0x33, b"\x01")]))
    with patch.object(device, "build_send") as send:
        with pytest.raises(RuntimeError, match="Conflicting"):
            device.set_person_airflow_mode("off")
        send.assert_not_called()
        device.set_attribute(attr, False)
    written = _written_properties(send.call_args.args[0])
    assert written[tag] == b"\x00"
    assert (0x33 if tag == 0x32 else 0x32) not in written


@pytest.mark.parametrize("loss", ["expired", "failed", "disconnected"])
def test_person_intent_loss_requires_new_readback(loss: str) -> None:
    """Expired, failed and lost-session intent cannot authorize a guessed off."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
    with patch.object(device, "build_send") as send:
        if loss == "failed":
            send.side_effect = OSError("partial send")
            with pytest.raises(OSError, match="partial send"):
                device.set_person_airflow_mode("toward")
            send.side_effect = None
        else:
            device.set_person_airflow_mode("toward")
        send.reset_mock()
        if loss == "disconnected":
            device.set_available(False)
        pending = device._pending_person_airflow
        expiry = (
            pending[1] + device._operating_timeout()
            if loss == "expired" and pending is not None
            else time.monotonic()
        )
        with (
            patch("midealan.devices.ac.time.monotonic", return_value=expiry),
            pytest.raises(RuntimeError, match="Fresh complete person"),
        ):
            device.set_person_airflow_mode("off")
        send.assert_not_called()
        device.set_available(True)
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x01")]))
        device.set_person_airflow_mode("off")
    assert _written_properties(send.call_args.args[0])[0x33] == b"\x00"


def test_person_matching_observation_releases_intent_for_external_changes() -> None:
    """After both flags are observed, later external state controls generic off."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode("toward")
        device.process_message(_property_response([(0x32, b"\x01"), (0x33, b"\x00")]))
        assert device._pending_person_airflow is None
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x01")]))
        device.set_person_airflow_mode("off")
    assert _written_properties(send.call_args.args[0])[0x33] == b"\x00"


@pytest.mark.parametrize("feature", [A.sleep_mode, A.eco_mode])
def test_adjacent_full_state_write_uses_pending_core(feature: str) -> None:
    """The actual serializer boundary shares the pending core for legacy extras."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(core_response())
    with patch.object(MideaDevice, "build_send") as send:
        device.set_attribute(A.mode, 5)
        device.set_attribute(feature, True)
    full_state = send.call_args.args[0]
    assert (
        full_state.power,
        full_state.mode,
        full_state.target_temperature,
        full_state.fan_speed,
    ) == (True, 5, 27.5, 102)
    assert getattr(full_state, feature) is True
    assert full_state.serialize()
    assert device.attributes[A.power] is False


def test_prebuilt_full_state_is_reconciled_immediately_before_serialization() -> None:
    """A full packet built before another command cannot replay its old core."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(core_response())
    old_message = device.make_message_set()
    with patch.object(MideaDevice, "build_send"):
        device.set_attribute(A.mode, 5)
        device.build_send(old_message)
    assert old_message.power is True
    assert old_message.mode == 5


@pytest.mark.parametrize("kind", ["set_echo", "corrupt_query"])
def test_person_off_uses_valid_query_values_not_echo_or_corrupt_state(
    kind: str,
) -> None:
    """Only valid queried flags can identify the target of a generic off."""
    device = _DeviceFixture._make_device("220F4047", 8)
    device.process_message(_property_response([(0x32, b"\x01"), (0x33, b"\x00")]))
    frame = _property_response(
        [(0x32, b"\x00"), (0x33, b"\x01")],
        ListTypes.B0 if kind == "set_echo" else ListTypes.B1,
    )
    if kind == "corrupt_query":
        body = bytearray(frame[10:-1])
        body[-1] ^= 1
        frame = _DeviceFixture._response(body)
    device.process_message(frame)
    with patch.object(device, "build_send") as send:
        device.set_person_airflow_mode("off")
    written = _written_properties(send.call_args.args[0])
    assert written[0x32] == b"\x00"
    assert 0x33 not in written


@pytest.mark.parametrize("loss", ["missing", "expired", "failed", "disconnected"])
def test_complete_state_writer_cannot_bypass_core_invalidation(loss: str) -> None:
    """Every complete-state writer refuses unknown or invalidated core fields."""
    device = _DeviceFixture._make_device("220F4047", 8)
    if loss != "missing":
        device.process_message(core_response())
    with patch.object(MideaDevice, "build_send") as send:
        if loss == "failed":
            send.side_effect = OSError("partial full-state send")
            with pytest.raises(OSError, match="partial full-state"):
                device.set_attribute(A.sleep_mode, True)
            send.side_effect = None
        if loss == "disconnected":
            device.set_available(False)
        send.reset_mock()
        confirmed = device._confirmed_operating
        expiry = (
            confirmed[1] + device._operating_timeout()
            if loss == "expired" and confirmed is not None
            else time.monotonic()
        )
        with (
            patch("midealan.devices.ac.time.monotonic", return_value=expiry),
            pytest.raises(RuntimeError, match="complete B1"),
        ):
            device.set_attribute(A.eco_mode, True)
        send.assert_not_called()


def test_expired_person_chain_cannot_expire_a_new_enable_before_its_off() -> None:
    """An explicit enable after expiry owns a new bounded chain, not the old one."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with (
        patch("midealan.devices.ac.time.monotonic", return_value=100.0) as clock,
        patch.object(device, "build_send") as send,
    ):
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
        device.set_person_airflow_mode("toward")
        clock.return_value = 120.0
        device.set_person_airflow_mode("avoid")
        pending = device._pending_person_airflow
        assert pending is not None
        assert pending[1] == 100.0  # An unexpired chain never renews on each write.
        clock.return_value = 134.0
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
        clock.return_value = 136.0
        device.set_person_airflow_mode("avoid")
        current = device._pending_person_airflow
        assert current is not None
        assert current[1] == 136.0
        before_off = send.call_count
        device.set_person_airflow_mode("off")
        assert send.call_count == before_off + 1
        written = _written_properties(send.call_args.args[0])
        assert written[0x33] == b"\x00"
        assert 0x32 not in written


def test_person_expiry_cannot_reuse_observation_before_latest_write() -> None:
    """A near-deadline enable cannot turn a later off into a silent no-op."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with (
        patch("midealan.devices.ac.time.monotonic", return_value=100.0) as clock,
        patch.object(device, "build_send") as send,
    ):
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
        device.set_person_airflow_mode("toward")
        clock.return_value = 133.0
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
        clock.return_value = 134.0
        device.set_person_airflow_mode("avoid")
        pending = device._pending_person_airflow
        assert pending is not None
        assert pending[1] == 100.0
        clock.return_value = 136.0
        before_off = send.call_count
        with pytest.raises(RuntimeError, match="Fresh complete person"):
            device.set_person_airflow_mode("off")
        assert send.call_count == before_off
        clock.return_value = 137.0
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x01")]))
        device.set_person_airflow_mode("off")
        assert send.call_count == before_off + 1
        assert _written_properties(send.call_args.args[0])[0x33] == b"\x00"


def test_person_confirmation_requires_both_flags_after_latest_write() -> None:
    """Even equal timestamps cannot combine a pre-write flag with new readback."""
    device = _DeviceFixture._make_device("220F4047", 8)
    with (
        patch("midealan.devices.ac.time.monotonic", return_value=100.0),
        patch.object(device, "build_send"),
    ):
        device.process_message(_property_response([(0x32, b"\x00"), (0x33, b"\x00")]))
        device.set_person_airflow_mode("toward")
        device.process_message(_property_response([(0x32, b"\x01")]))
        assert device._pending_person_airflow is not None
        device.process_message(_property_response([(0x33, b"\x00")]))
        assert device._pending_person_airflow is None


@pytest.mark.parametrize("source", ["aggregate", "standalone"])
def test_valid_model_target_wins_over_generic_7e_in_same_reply(source: str) -> None:
    """Generic extension values cannot replace validated model-specific state."""
    device = _DeviceFixture._make_device("220F4047", 8)
    generic = bytes(56)  # Generic target 12C, power/mode/fan zero.
    response = (
        core_response(True, 2, 27.5, 102, extra=[(0x7E, generic)])
        if source == "aggregate"
        else _property_response([(3, bytes([105])), (0x7E, generic)])
    )
    device.process_message(response)
    assert device.attributes[A.target_temperature] == 27.5
    assert device._prefer_core_target_temperature is True
    if source == "aggregate":
        assert device.attributes[A.power] is True
        assert device.attributes[A.mode] == 2
        assert device.attributes[A.fan_speed] == 102


@pytest.mark.parametrize("kind", ["generic_only", "bad_crc", "invalid_target"])
def test_generic_7e_target_cannot_latch_model_specific_source(kind: str) -> None:
    """Only validated model target evidence can disable the C0 fallback."""
    device = _DeviceFixture._make_device("220F4047", 8)
    properties = [(0x7E, bytes(56))]
    if kind != "generic_only":
        properties.append((3, bytes([105 if kind == "bad_crc" else 0])))
    response = _property_response(properties)
    if kind == "bad_crc":
        body = bytearray(response[10:-1])
        body[-1] ^= 1
        response = _DeviceFixture._response(body)
    device.process_message(response)
    assert device._prefer_core_target_temperature is False
    device.process_message(_DeviceFixture._response(bytearray(MODEL_220F4047_C0_BODY)))
    assert device.attributes[A.target_temperature] != 12.0

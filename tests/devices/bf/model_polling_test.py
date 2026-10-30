"""Offline regression for the verified model-specific BF behavior."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MessageResult
from midealan.devices.bf import MideaBFDevice


def oven(model: str = "700006B9", subtype: int = 5) -> MideaBFDevice:
    """Construct an offline instance with synthetic identity and credentials."""
    return MideaBFDevice(
        name="Offline oven",
        device_id=1,
        ip_address="127.0.0.1",
        port=12345,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model=model,
        subtype=subtype,
        customize="",
    )


@pytest.fixture(autouse=True)
def deny_network_and_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test tries to cross the offline boundary."""

    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("NETWORK_OR_THREAD_START_DENIED")

    monkeypatch.setattr("socket.socket", reject)
    monkeypatch.setattr("threading.Thread.start", reject)


@pytest.mark.parametrize(
    ("model", "subtype", "interval", "fast"),
    [
        ("700006B9", 5, 1, True),
        ("700006B9", 5, 30, False),
        ("700006B9", 5, 0, False),
        ("700006B9", 5, -1, False),
        ("other", 5, 1, False),
        ("700006B9", 1, 1, False),
    ],
)
def test_receive_gate(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    subtype: int,
    interval: int,
    fast: bool,
) -> None:
    """Retain the old receive timeout everywhere outside the exact fast path."""
    device = oven(model, subtype)
    device.set_refresh_interval(interval)
    device._previous_refresh = 100
    monkeypatch.setattr("midealan.device.time.time", lambda: 100.25)
    assert device._uses_deadline_polling() is fast
    assert device._receive_timeout() == (0.75 if fast else 10)


def loop(
    monkeypatch: pytest.MonkeyPatch,
    device: MideaBFDevice,
    duration: float,
    responses: bool,
    success_at: float | None = None,
    switch_interval: tuple[float, int] | None = None,
) -> SimpleNamespace:
    """Drive the production run method with a bounded virtual socket/clock."""
    state = SimpleNamespace(
        now=0.0,
        pending=False,
        queries=[],
        closed=None,
        replied=False,
        switched=False,
    )

    class FakeSocket:
        timeout = 10.0

        def settimeout(self, value: float) -> None:
            self.timeout = value

        def recv(self, size: int) -> bytes:
            assert size == 512
            if responses and state.pending:
                state.pending = False
                state.now += 0.02
                return b"synthetic-valid-report"
            if (
                success_at is not None
                and not state.replied
                and state.now + self.timeout >= success_at
            ):
                state.now = success_at
                state.replied = True
                return b"synthetic-valid-report"
            state.now += self.timeout
            if (
                switch_interval is not None
                and not state.switched
                and state.now >= switch_interval[0]
            ):
                device.set_refresh_interval(switch_interval[1])
                state.switched = True
            if state.now >= duration:
                device._is_run = False
                return b""
            raise TimeoutError

    def refresh() -> None:
        state.queries.append(state.now)
        state.pending = True

    def close() -> None:
        state.closed = state.now
        device._socket = None
        device._is_run = False

    monkeypatch.setattr("midealan.device.time.time", lambda: state.now)
    monkeypatch.setattr("midealan.device.time.monotonic", lambda: state.now)
    device._is_run = True
    monkeypatch.setattr(device, "_socket", FakeSocket())
    monkeypatch.setattr(device, "_connect_loop", Mock())
    monkeypatch.setattr(device, "refresh_status", refresh)
    monkeypatch.setattr(device, "send_heartbeat", Mock())
    monkeypatch.setattr(
        device,
        "parse_message",
        Mock(return_value=MessageResult.SUCCESS),
    )
    monkeypatch.setattr(device, "close_socket", close)
    device.run()
    return state


def test_real_loop_one_second_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the receive wakeup reaches real query scheduling, not just a helper."""
    device = oven()
    device.set_refresh_interval(1)
    state = loop(monkeypatch, device, 100, True)
    gaps = [b - a for a, b in zip(state.queries, state.queries[1:], strict=False)]
    assert len(gaps) >= 95
    assert all(0.99 <= gap <= 1.02 for gap in gaps)


@pytest.mark.parametrize("interval", [1, 30, 0])
def test_no_response_keeps_120_seconds(
    monkeypatch: pytest.MonkeyPatch,
    interval: int,
) -> None:
    """A one-second recv must not shrink the old connection allowance to 12s."""
    device = oven()
    device.set_refresh_interval(interval)
    state = loop(monkeypatch, device, 200, False)
    assert state.closed == pytest.approx(120, abs=0.02)
    if interval == 0:
        assert not state.queries


def test_valid_report_resets_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the full allowance after a parsed success at 60 seconds."""
    device = oven()
    device.set_refresh_interval(1)
    state = loop(monkeypatch, device, 250, False, success_at=60)
    assert state.replied
    assert state.closed == pytest.approx(180, abs=0.02)


def test_real_single_query_refresh_does_not_add_pacing_sleep() -> None:
    """The multi-query pacing policy does not delay one BF query."""
    device = oven()
    device._appliance_query = False
    with (
        patch.object(device, "build_send") as send,
        patch("midealan.device.time.sleep") as sleep,
    ):
        device.refresh_status()
        send.assert_called_once()
        sleep.assert_not_called()


@pytest.mark.parametrize(("initial", "updated"), [(1, 30), (1, 0), (30, 1)])
def test_interval_change_preserves_response_allowance(
    monkeypatch: pytest.MonkeyPatch,
    initial: int,
    updated: int,
) -> None:
    """Fast receive counts must never shorten the connection watchdog."""
    device = oven()
    device.set_refresh_interval(initial)
    state = loop(monkeypatch, device, 200, False, switch_interval=(20, updated))
    assert state.switched
    assert state.closed == pytest.approx(120, abs=0.02)

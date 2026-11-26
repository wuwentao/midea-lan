"""Test eb device."""

from collections.abc import Sequence
from threading import Event, RLock, Thread, get_ident
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.eb import DeviceAttributes, MideaEBDevice
from midealan.devices.eb.message import INNER_HEAD
from midealan.exceptions import SocketException, ValueOutOfRange, ValueWrongType
from midealan.message import MessageType


class _SignalingRLock:
    """Reentrant lock that signals before each acquisition attempt."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.attempted = Event()
        self._owner: int | None = None
        self._depth = 0

    def __enter__(self) -> None:
        self.attempted.set()
        self._lock.acquire()
        current_thread = get_ident()
        if self._owner == current_thread:
            self._depth += 1
        else:
            self._owner = current_thread
            self._depth = 1

    def __exit__(self, *_args: object) -> None:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
        self._lock.release()

    def owned_by_current_thread(self) -> bool:
        """Return whether the calling thread currently owns the lock."""
        return self._owner == get_ident()


def _report_frame(body: Sequence[int]) -> bytes:
    """Wrap a report body in a full eb query-reply frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0xEB, 0, 0, 0, 0, 0, 1, 0x03])
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body() -> list[int]:
    """Build a full 24-byte inner-frame status report body."""
    body = [0] * 24
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[2] = 0x02
    body[7] = 0x14
    body[8] = 0x27
    body[9] = 0x01
    body[10] = 3
    body[11] = 0x12
    body[12] = 0x34
    body[19] = 7
    body[23] = 9
    return body


class TestMideaEBDevice:
    """Test Midea eb device."""

    @pytest.fixture
    def device(self) -> MideaEBDevice:
        """Eb device on V3 transport."""
        return MideaEBDevice(
            name="eb",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="00" * 32,
            key="00" * 32,
            device_protocol=ProtocolVersion.V3,
            model="",
            subtype=0,
            customize="",
        )

    def test_initial_attributes(self, device: MideaEBDevice) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.function_num] is None

    def test_build_query(self, device: MideaEBDevice) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaEBDevice) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_status_body()))
        assert status["work_status"] == 3
        assert status["function_num"] == 0x1234
        assert status["fire_level"] == 7
        assert device.attributes[DeviceAttributes.error_code] == 9

    def test_process_message_short_no_update(self, device: MideaEBDevice) -> None:
        """A body shorter than the minimum carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_work_status(self, device: MideaEBDevice) -> None:
        """Setting work_status sends a control frame with it at body[11]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[11] == 1

    def test_set_function_num(self, device: MideaEBDevice) -> None:
        """Setting function_num sends it big-endian at body[9]/body[10]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.function_num, 0x1234)
        body = build_send.call_args[0][0].body
        assert body[9] == 0x12
        assert body[10] == 0x34

    def test_set_fire_level(self, device: MideaEBDevice) -> None:
        """Setting fire_level lands at body[14]."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.fire_level, 5)
        assert build_send.call_args[0][0].body[14] == 5

    def test_set_seeds_from_state(self, device: MideaEBDevice) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.function_num] = 0x55
        device._attributes[DeviceAttributes.fire_level] = 3
        device._attributes[DeviceAttributes.time_reserve_hr] = 2
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        body = build_send.call_args[0][0].body
        assert body[10] == 0x55  # seeded function_num lo
        assert body[11] == 1  # overridden work_status
        assert body[12] == 2  # seeded reserve hr
        assert body[14] == 3  # seeded fire_level

    def test_consecutive_sets_preserve_pending_values(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A rapid second write includes the first unconfirmed value."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
            device.set_attribute(DeviceAttributes.time_reserve_min, 30)
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[12] == 1
        assert second_body[13] == 30

    def test_stale_report_keeps_pending_value(self, device: MideaEBDevice) -> None:
        """A stale intervening report does not undo an unconfirmed write."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
            device.process_message(_report_frame(_status_body()))
            device.set_attribute(DeviceAttributes.time_reserve_min, 30)
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[12] == 1
        assert second_body[13] == 30

    def test_report_confirms_pending_value(self, device: MideaEBDevice) -> None:
        """A matching report clears the confirmed pending control."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
        body = _status_body()
        body[17] = 1
        device.process_message(_report_frame(body))
        assert DeviceAttributes.time_reserve_hr not in device._pending_controls

    def test_failed_send_does_not_add_pending_value(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A failed first send leaves no optimistic control value behind."""
        with (
            patch.object(device, "build_send", side_effect=SocketException),
            pytest.raises(SocketException),
        ):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
        assert device._pending_controls == {}

    def test_failed_replacement_restores_previous_pending_value(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A failed replacement keeps the last successfully sent value."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
        with (
            patch.object(device, "build_send", side_effect=SocketException),
            pytest.raises(SocketException),
        ):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 2)
        assert device._pending_controls[DeviceAttributes.time_reserve_hr] == 1

    def test_pending_replacement_uses_confirmation_lock(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A replacement cannot race a report's pending confirmation."""
        lock = _SignalingRLock()
        device._pending_controls_lock = lock  # type: ignore[assignment]
        completed = Event()

        def replace_pending() -> None:
            with patch.object(device, "build_send"):
                device.set_attribute(DeviceAttributes.time_reserve_hr, 2)
            completed.set()

        with lock:
            lock.attempted.clear()
            replace_thread = Thread(target=replace_pending)
            replace_thread.start()
            assert lock.attempted.wait(timeout=1)
            assert not completed.is_set()
        replace_thread.join(timeout=1)
        assert not replace_thread.is_alive()
        assert completed.is_set()

    def test_failed_replacement_does_not_restore_confirmed_value(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A report received during a failed send confirms the prior value."""
        lock = _SignalingRLock()
        device._pending_controls_lock = lock  # type: ignore[assignment]
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)

        send_started = Event()
        release_send = Event()
        report_completed = Event()
        send_errors: list[SocketException] = []

        def fail_send(_message: object) -> None:
            send_started.set()
            release_send.wait(timeout=1)
            raise SocketException

        def replace_pending() -> None:
            try:
                device.set_attribute(DeviceAttributes.time_reserve_hr, 2)
            except SocketException as error:
                send_errors.append(error)

        body = _status_body()
        body[17] = 1

        def confirm_previous() -> None:
            device.process_message(_report_frame(body))
            report_completed.set()

        with patch.object(device, "build_send", side_effect=fail_send):
            replace_thread = Thread(target=replace_pending)
            replace_thread.start()
            assert send_started.wait(timeout=1)
            lock.attempted.clear()
            report_thread = Thread(target=confirm_previous)
            report_thread.start()
            assert lock.attempted.wait(timeout=1)
            assert not report_completed.is_set()
            release_send.set()
            replace_thread.join(timeout=1)
            report_thread.join(timeout=1)

        assert not replace_thread.is_alive()
        assert not report_thread.is_alive()
        assert send_errors
        assert DeviceAttributes.time_reserve_hr not in device._pending_controls

    def test_report_update_is_atomic_with_control_build(
        self,
        device: MideaEBDevice,
    ) -> None:
        """A setter cannot build a frame from a partially applied report."""
        lock = _SignalingRLock()
        device._pending_controls_lock = lock  # type: ignore[assignment]
        field_updated = Event()
        continue_report = Event()
        set_completed = Event()
        unlocked_update = Event()

        class BlockingAttributes(dict[str, object]):
            """Pause the report after its first writable field update."""

            def __setitem__(self, key: str, value: object) -> None:
                super().__setitem__(key, value)
                if key == DeviceAttributes.work_status:
                    if not lock.owned_by_current_thread():
                        unlocked_update.set()
                    field_updated.set()
                    continue_report.wait(timeout=1)

        device._attributes = BlockingAttributes(device._attributes)

        def process_report() -> None:
            device.process_message(_report_frame(_status_body()))

        def set_fire_level() -> None:
            device.set_attribute(DeviceAttributes.fire_level, 5)
            set_completed.set()

        with patch.object(device, "build_send") as build_send:
            report_thread = Thread(target=process_report)
            report_thread.start()
            assert field_updated.wait(timeout=1)
            lock.attempted.clear()
            set_thread = Thread(target=set_fire_level)
            set_thread.start()
            assert lock.attempted.wait(timeout=1)
            assert not set_completed.is_set()
            continue_report.set()
            report_thread.join(timeout=1)
            set_thread.join(timeout=1)

        assert not report_thread.is_alive()
        assert not set_thread.is_alive()
        assert not unlocked_update.is_set()
        body = build_send.call_args.args[0].body
        assert body[9] == 0x12
        assert body[10] == 0x34

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.fire_level, 22),
            (DeviceAttributes.time_reserve_hr, 24),
            (DeviceAttributes.time_reserve_min, 60),
            (DeviceAttributes.definite_time_hr, -1),
            (DeviceAttributes.function_num, 0x10000),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaEBDevice,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaEBDevice) -> None:
        """A bool / non-number param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.fire_level, True)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, "on")

    def test_set_readonly_ignored(self, device: MideaEBDevice) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.time_running_hr, 2)
            device.set_attribute(DeviceAttributes.response, "response_normal")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaEBDevice) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaEBDevice) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaEBDevice) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaEBDevice) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaEBDevice) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

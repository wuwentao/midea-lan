"""Test e7 device."""

from collections.abc import Sequence
from threading import Event, RLock, Thread, get_ident
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.e7 import DeviceAttributes, MideaE7Device
from midealan.devices.e7.message import INNER_HEAD
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


def _report_frame(body: Sequence[int], message_type: int = MessageType.query) -> bytes:
    """Wrap a report body in a full e7 response frame."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, 0xE7, 0, 0, 0, 0, 0, 0, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _status_body_32() -> list[int]:
    """Build a full v3/v4 (32-bit function_num) status body."""
    body = [0] * 26
    body[0] = INNER_HEAD
    body[1] = 0x55
    body[7] = 0x14
    body[8] = 0x27
    body[9] = 1  # response normal
    body[10] = 2  # work_status
    body[11] = 0x00
    body[12] = 0x00
    body[13] = 0x12
    body[14] = 0x34  # function_num = 0x1234
    body[21] = 7  # fire level
    body[25] = 9  # error code
    return body


def _make_device(subtype: int) -> MideaE7Device:
    """Build an e7 device on V3 transport with the given subtype."""
    return MideaE7Device(
        name="e7",
        device_id=1,
        ip_address="192.168.1.1",
        port=6444,
        token="00" * 32,
        key="00" * 32,
        device_protocol=ProtocolVersion.V3,
        model="",
        subtype=subtype,
        customize="",
    )


class TestMideaE7Device32bit:
    """Test Midea e7 device on the 32-bit (subtype 8) layout."""

    @pytest.fixture
    def device(self) -> MideaE7Device:
        """E7 device with a 32-bit subtype."""
        return _make_device(8)

    def test_initial_attributes(self, device: MideaE7Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.function_num] is None

    def test_build_query(self, device: MideaE7Device) -> None:
        """Build a single status query with the inner query frame."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body[0] == INNER_HEAD

    def test_process_message(self, device: MideaE7Device) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_status_body_32()))
        assert status["work_status"] == 2
        assert status["function_num"] == 0x1234
        assert device.attributes[DeviceAttributes.error_code] == 9

    def test_process_message_short_no_update(self, device: MideaE7Device) -> None:
        """A body shorter than the minimum record carries no decoded state."""
        assert device.process_message(_report_frame([INNER_HEAD, 0x55])) == {}

    def test_set_function_num_32bit(self, device: MideaE7Device) -> None:
        """Setting a 32-bit function_num packs four big-endian bytes."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.function_num, 0x01020304)
        body = build_send.call_args[0][0].body
        assert body[9] == 0x01
        assert body[10] == 0x02
        assert body[11] == 0x03
        assert body[12] == 0x04

    def test_set_function_num_32bit_range(self, device: MideaE7Device) -> None:
        """A 32-bit layout accepts a value beyond the 16-bit range."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.function_num, 0x10000)
        assert build_send.called

    def test_set_work_status(self, device: MideaE7Device) -> None:
        """Setting work_status lands at body[13] in the 32-bit frame."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[13] == 1

    def test_set_fire_level(self, device: MideaE7Device) -> None:
        """Setting fire_level lands at body[16] in the 32-bit frame."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.fire_level, 7)
        assert build_send.call_args[0][0].body[16] == 7

    def test_set_seeds_from_state(self, device: MideaE7Device) -> None:
        """A single-field change keeps the other control fields from state."""
        device._attributes[DeviceAttributes.function_num] = 0x0A0B
        device._attributes[DeviceAttributes.fire_level] = 4
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        body = build_send.call_args[0][0].body
        assert body[11] == 0x0A  # seeded function_num bytes
        assert body[12] == 0x0B
        assert body[13] == 1  # new work_status
        assert body[16] == 4  # seeded fire_level

    def test_set_ignores_non_int_seed(self, device: MideaE7Device) -> None:
        """A stored bool / non-int field is not seeded into the control frame."""
        device._attributes[DeviceAttributes.fire_level] = True
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, 1)
        assert build_send.call_args[0][0].body[16] == 0

    def test_consecutive_sets_preserve_pending_values(
        self,
        device: MideaE7Device,
    ) -> None:
        """A rapid second write includes the first unconfirmed value."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
            device.set_attribute(DeviceAttributes.time_reserve_min, 30)
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[14] == 1
        assert second_body[15] == 30

    def test_stale_report_keeps_pending_value(self, device: MideaE7Device) -> None:
        """A stale intervening report does not undo an unconfirmed write."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
            device.process_message(_report_frame(_status_body_32()))
            device.set_attribute(DeviceAttributes.time_reserve_min, 30)
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[14] == 1
        assert second_body[15] == 30

    def test_report_confirms_pending_value(self, device: MideaE7Device) -> None:
        """A matching report clears the confirmed pending control."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.time_reserve_hr, 1)
        body = _status_body_32()
        body[19] = 1
        device.process_message(_report_frame(body))
        assert DeviceAttributes.time_reserve_hr not in device._pending_controls

    def test_failed_send_does_not_add_pending_value(
        self,
        device: MideaE7Device,
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
        device: MideaE7Device,
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
        device: MideaE7Device,
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
        device: MideaE7Device,
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

        body = _status_body_32()
        body[19] = 1

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
        device: MideaE7Device,
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
            device.process_message(_report_frame(_status_body_32()))

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
        assert body[11] == 0x12
        assert body[12] == 0x34

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.work_status, 6),
            (DeviceAttributes.time_reserve_hr, 24),
            (DeviceAttributes.time_reserve_min, 60),
            (DeviceAttributes.fire_level, 22),
            (DeviceAttributes.definite_time_hr, 24),
            (DeviceAttributes.function_num, 0x100000000),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaE7Device,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaE7Device) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.fire_level, True)
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.fire_level, "x")

    def test_set_readonly_ignored(self, device: MideaE7Device) -> None:
        """Report-only fields are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.error_code, 5)
            device.set_attribute(DeviceAttributes.time_running_hr, 2)
            device.set_attribute(DeviceAttributes.work_stage, 1)
            device.set_attribute(DeviceAttributes.response, "x")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaE7Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaE7Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaE7Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaE7Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaE7Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None


class TestMideaE7Device16bit:
    """Test Midea e7 device on the 16-bit (subtype 6) layout."""

    @pytest.fixture
    def device(self) -> MideaE7Device:
        """E7 device with the 16-bit subtype."""
        return _make_device(6)

    def test_set_function_num_16bit(self, device: MideaE7Device) -> None:
        """Setting a 16-bit function_num packs two big-endian bytes."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.function_num, 0x1234)
        body = build_send.call_args[0][0].body
        assert body[9] == 0x12
        assert body[10] == 0x34

    def test_set_function_num_16bit_out_of_range(self, device: MideaE7Device) -> None:
        """The 16-bit layout rejects a value beyond 0xFFFF."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(DeviceAttributes.function_num, 0x10000)

    def test_process_message_16bit(self, device: MideaE7Device) -> None:
        """A v1 query reply decodes with the 16-bit layout."""
        body = [0] * 24
        body[0] = INNER_HEAD
        body[1] = 0x55
        body[7] = 0x14
        body[8] = 0x27
        body[9] = 1
        body[10] = 1
        body[11] = 0x12
        body[12] = 0x34
        body[23] = 7
        status = device.process_message(_report_frame(body))
        assert status["function_num"] == 0x1234
        assert status["error_code"] == 7

"""Test b2 device."""

from collections.abc import Sequence
from threading import Event, RLock, Thread, get_ident
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.b2 import DeviceAttributes, MideaB2Device
from midealan.devices.b2.message import STATUS_STANDBY, STATUS_WORK, MessageSet
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


def _report_frame(
    body: Sequence[int],
    message_type: MessageType = MessageType.query,
) -> bytes:
    """Wrap a report body in a full b2 query-reply frame."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, 0xB2, 0, 0, 0, 0, 0, 3, message_type],
    )
    return bytes(header + bytearray(body) + bytearray([0x00]))


def _report_body() -> list[int]:
    """Build a full 17-byte report body."""
    body = [0] * 17
    body[0] = STATUS_WORK
    body[1] = 0x71  # vegetable
    body[2] = 2
    body[3] = 45
    body[4] = 90
    body[16] = 0x01  # lock
    return body


def _control_echo_body(message: MessageSet) -> list[int]:
    """Expand a 15-byte control body into its 17-byte echo layout."""
    control = message.body
    body = [0] * 17
    body[:5] = control[:5]
    body[16] = control[14]
    return body


class TestMideaB2Device:
    """Test Midea b2 device."""

    @pytest.fixture
    def device(self) -> MideaB2Device:
        """b2 device on V3 transport."""
        return MideaB2Device(
            name="b2",
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

    def test_initial_attributes(self, device: MideaB2Device) -> None:
        """Every attribute starts unset."""
        assert device.attributes[DeviceAttributes.work_status] is None
        assert device.attributes[DeviceAttributes.work_mode] is None

    def test_build_query(self, device: MideaB2Device) -> None:
        """Build a single status query with an empty body."""
        query = device.build_query()
        assert len(query) == 1
        assert query[0].body == bytearray([0x00])

    def test_process_message(self, device: MideaB2Device) -> None:
        """A query reply updates every decoded attribute."""
        status = device.process_message(_report_frame(_report_body()))
        assert status["work_status"] == "work"
        assert status["work_mode"] == "vegetable"
        assert status["temperature"] == 90
        assert device.attributes[DeviceAttributes.lock] is True

    def test_process_message_unknown_status_skipped(
        self,
        device: MideaB2Device,
    ) -> None:
        """An unknown status byte leaves work_status out of the update."""
        body = _report_body()
        body[0] = 0x55  # not a known work_status
        status = device.process_message(_report_frame(body))
        assert "work_status" not in status
        # Other decoded fields still land.
        assert status["temperature"] == 90

    def test_set_work_status(self, device: MideaB2Device) -> None:
        """Setting work_status sends it as the leading body byte."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "work")
        message = build_send.call_args[0][0]
        assert message.message_type == MessageType.set
        assert message.body[0] == STATUS_WORK

    def test_set_work_status_wrong(self, device: MideaB2Device) -> None:
        """An unknown / non-string work_status is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, "spin")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_status, 1)

    def test_set_work_mode(self, device: MideaB2Device) -> None:
        """Setting work_mode sends it at body offset 1."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_mode, "fish")
        assert build_send.call_args[0][0].body[1] == 0x03

    def test_set_work_mode_wrong(self, device: MideaB2Device) -> None:
        """An unknown / non-string work_mode is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_mode, "roast")
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.work_mode, 5)

    def test_set_temperature(self, device: MideaB2Device) -> None:
        """Setting temperature sends it at body offset 4."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 80)
        assert build_send.call_args[0][0].body[4] == 80

    def test_set_lock(self, device: MideaB2Device) -> None:
        """Setting lock sends it at the control body offset 14."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.lock, True)
        assert build_send.call_args[0][0].body[14] == 0x01

    def test_set_seeds_from_state(self, device: MideaB2Device) -> None:
        """A single-field change keeps the other fields from current state."""
        device._attributes[DeviceAttributes.work_status] = "standby"
        device._attributes[DeviceAttributes.work_mode] = "fish"
        device._attributes[DeviceAttributes.work_hour] = 1
        device._attributes[DeviceAttributes.work_minute] = 20
        device._attributes[DeviceAttributes.temperature] = 70
        device._attributes[DeviceAttributes.lock] = True
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "work")
        body = build_send.call_args[0][0].body
        assert body[0] == STATUS_WORK  # overridden
        assert body[1] == 0x03  # seeded mode fish
        assert body[2] == 1  # seeded hour
        assert body[3] == 20  # seeded minute
        assert body[4] == 70  # seeded temperature
        assert body[14] == 0x01  # seeded lock

    def test_consecutive_sets_preserve_pending_values(
        self,
        device: MideaB2Device,
    ) -> None:
        """A rapid second write includes the first unconfirmed value."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.set_attribute(DeviceAttributes.work_minute, 30)
            device.set_attribute(DeviceAttributes.work_status, "work")
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[2] == 1
        assert second_body[3] == 30
        third_body = build_send.call_args_list[2].args[0].body
        assert third_body[0] == STATUS_WORK
        assert third_body[2] == 1
        assert third_body[3] == 30

    def test_stale_report_keeps_pending_value(self, device: MideaB2Device) -> None:
        """A stale intervening report does not undo an unconfirmed write."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.process_message(_report_frame(_report_body()))
            device.set_attribute(DeviceAttributes.work_minute, 30)
        second_body = build_send.call_args_list[1].args[0].body
        assert second_body[2] == 1
        assert second_body[3] == 30

    def test_control_echo_confirms_pending_values(
        self,
        device: MideaB2Device,
    ) -> None:
        """A matching control echo clears each confirmed pending control."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_status, "work")
            device.set_attribute(DeviceAttributes.work_mode, "vegetable")
            device.set_attribute(DeviceAttributes.work_hour, 2)
            device.set_attribute(DeviceAttributes.work_minute, 45)
            device.set_attribute(DeviceAttributes.temperature, 90)
            device.set_attribute(DeviceAttributes.lock, True)
        message = build_send.call_args.args[0]
        device.process_message(
            _report_frame(_control_echo_body(message), MessageType.set),
        )
        assert device._pending_controls == {}
        assert not device._pending_control_frames

    def test_repeated_value_waits_for_ordered_confirmations(
        self,
        device: MideaB2Device,
    ) -> None:
        """A delayed first A report cannot confirm a later A in A-B-A writes."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.set_attribute(DeviceAttributes.work_hour, 2)
            device.set_attribute(DeviceAttributes.work_hour, 1)

        messages = [call.args[0] for call in build_send.call_args_list]
        device.process_message(
            _report_frame(_control_echo_body(messages[0]), MessageType.set),
        )
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [2, 1]

        device.process_message(
            _report_frame(_control_echo_body(messages[1]), MessageType.set),
        )
        device.process_message(
            _report_frame(_control_echo_body(messages[2]), MessageType.set),
        )
        assert DeviceAttributes.work_hour not in device._pending_controls

    def test_control_echo_confirms_skipped_pending_values(
        self,
        device: MideaB2Device,
    ) -> None:
        """A later control echo supersedes an omitted intermediate echo."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.set_attribute(DeviceAttributes.work_hour, 2)

        message = build_send.call_args.args[0]
        device.process_message(
            _report_frame(_control_echo_body(message), MessageType.set),
        )
        assert DeviceAttributes.work_hour not in device._pending_controls

    def test_unmatched_control_echo_keeps_pending_frame(
        self,
        device: MideaB2Device,
    ) -> None:
        """A control echo for an unknown frame cannot confirm a write."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)

        body = _control_echo_body(build_send.call_args.args[0])
        body[2] = 2
        device.process_message(_report_frame(body, MessageType.set))
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [1]
        assert len(device._pending_control_frames) == 1

    def test_short_control_ack_keeps_pending_frame(
        self,
        device: MideaB2Device,
    ) -> None:
        """A short set acknowledgment lacks the state needed to confirm."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.work_hour, 1)

        device.process_message(
            _report_frame([STATUS_WORK, 0x03, 1], MessageType.set),
        )
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [1]
        assert len(device._pending_control_frames) == 1

    @pytest.mark.parametrize("message_type", [MessageType.query, MessageType.notify1])
    def test_status_report_cannot_confirm_pending_value(
        self,
        device: MideaB2Device,
        message_type: MessageType,
    ) -> None:
        """A query or notify report cannot consume the pending queue."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.set_attribute(DeviceAttributes.work_hour, 2)

        body = _report_body()
        body[2] = 1
        device.process_message(_report_frame(body, message_type))
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [1, 2]

    def test_stale_query_does_not_shift_control_echo_order(
        self,
        device: MideaB2Device,
    ) -> None:
        """A delayed query cannot make an early echo confirm a later write."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.work_hour, 1)
            device.set_attribute(DeviceAttributes.work_minute, 30)
            device.set_attribute(DeviceAttributes.work_hour, 2)
            device.set_attribute(DeviceAttributes.work_hour, 1)

        messages = [call.args[0] for call in build_send.call_args_list]
        device.process_message(_report_frame(_control_echo_body(messages[0])))
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [1, 2, 1]

        device.process_message(
            _report_frame(_control_echo_body(messages[0]), MessageType.set),
        )
        assert list(pending) == [2, 1]
        device.process_message(
            _report_frame(_control_echo_body(messages[1]), MessageType.set),
        )
        assert list(pending) == [2, 1]
        assert DeviceAttributes.work_minute not in device._pending_controls
        device.process_message(
            _report_frame(_control_echo_body(messages[2]), MessageType.set),
        )
        assert list(pending) == [1]
        device.process_message(
            _report_frame(_control_echo_body(messages[3]), MessageType.set),
        )
        assert DeviceAttributes.work_hour not in device._pending_controls

    def test_reset_clears_pending_controls(self, device: MideaB2Device) -> None:
        """Connection invalidation discards controls from the old socket."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.work_hour, 1)
        device.reset_init_query()
        assert device._pending_controls == {}
        assert not device._pending_control_frames

    def test_failed_send_does_not_add_pending_value(
        self,
        device: MideaB2Device,
    ) -> None:
        """A failed first send leaves no optimistic control value behind."""
        with (
            patch.object(device, "build_send", side_effect=SocketException),
            pytest.raises(SocketException),
        ):
            device.set_attribute(DeviceAttributes.work_hour, 1)
        assert device._pending_controls == {}
        assert not device._pending_control_frames

    def test_failed_replacement_restores_previous_pending_value(
        self,
        device: MideaB2Device,
    ) -> None:
        """A failed replacement keeps the last successfully sent value."""
        with patch.object(device, "build_send"):
            device.set_attribute(DeviceAttributes.work_hour, 1)
        with (
            patch.object(device, "build_send", side_effect=SocketException),
            pytest.raises(SocketException),
        ):
            device.set_attribute(DeviceAttributes.work_hour, 2)
        pending = device._pending_controls[DeviceAttributes.work_hour]
        assert list(pending) == [1]
        assert len(device._pending_control_frames) == 1

    def test_report_update_is_atomic_with_control_build(
        self,
        device: MideaB2Device,
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
            device.process_message(_report_frame(_report_body()))

        def set_temperature() -> None:
            device.set_attribute(DeviceAttributes.temperature, 80)
            set_completed.set()

        with patch.object(device, "build_send") as build_send:
            report_thread = Thread(target=process_report)
            report_thread.start()
            assert field_updated.wait(timeout=1)
            lock.attempted.clear()
            set_thread = Thread(target=set_temperature)
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
        assert body[1] == 0x71
        assert body[2] == 2
        assert body[3] == 45
        assert body[4] == 80
        assert body[14] == 0x01

    def test_set_ignores_unknown_seed(self, device: MideaB2Device) -> None:
        """A stored status / mode not in the code map is not seeded."""
        device._attributes[DeviceAttributes.work_status] = "bogus"
        device._attributes[DeviceAttributes.work_mode] = "bogus"
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.temperature, 60)
        body = build_send.call_args[0][0].body
        assert body[0] == STATUS_STANDBY  # default work_status
        assert body[1] == 0  # default mode

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (DeviceAttributes.work_hour, 10),
            (DeviceAttributes.work_minute, 60),
            (DeviceAttributes.temperature, 40),
            (DeviceAttributes.temperature, 101),
        ],
    )
    def test_set_out_of_range(
        self,
        device: MideaB2Device,
        attr: str,
        value: int,
    ) -> None:
        """A numeric param outside its range is rejected."""
        with pytest.raises(ValueOutOfRange):
            device.set_attribute(attr, value)

    def test_set_wrong_type(self, device: MideaB2Device) -> None:
        """A bool / non-number numeric param is rejected."""
        with pytest.raises(ValueWrongType):
            device.set_attribute(DeviceAttributes.temperature, True)

    def test_set_readonly_ignored(self, device: MideaB2Device) -> None:
        """door/water/box state are read-only: nothing is sent."""
        with patch.object(device, "build_send") as build_send:
            device.set_attribute(DeviceAttributes.door_state, "open")
            device.set_attribute(DeviceAttributes.water_state, "empty")
            device.set_attribute(DeviceAttributes.box_state, "out")
        build_send.assert_not_called()

    def test_set_customize_refresh_interval(self, device: MideaB2Device) -> None:
        """JSON customize applies a valid refresh interval."""
        device.set_customize('{"refresh_interval": 45}')
        assert device._refresh_interval == 45

    def test_set_customize_invalid_refresh_type(self, device: MideaB2Device) -> None:
        """A non-numeric refresh interval is left unchanged."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "soon"}')
        assert device._refresh_interval == before

    def test_set_customize_without_refresh_key(self, device: MideaB2Device) -> None:
        """A non-empty customize lacking refresh_interval leaves it unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaB2Device) -> None:
        """Malformed customize JSON is caught and does not raise."""
        device.set_customize("{not json")
        assert device._refresh_interval is not None

    def test_set_customize_empty(self, device: MideaB2Device) -> None:
        """Empty customize is a no-op."""
        device.set_customize("")
        assert device.attributes[DeviceAttributes.work_status] is None

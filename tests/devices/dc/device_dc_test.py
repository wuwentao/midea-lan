"""Test DC device integration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MideaDeviceInitKwargs
from midealan.devices.dc import DeviceAttributes, MideaDCDevice
from midealan.devices.dc.message import ControlAttributes as Attr
from midealan.devices.dc.message import (
    MessagePower,
    MessageQuery,
    MessageStart,
)
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType

DC_BODY = bytes.fromhex(
    "03000000020000000002000000000000015a0000dc3734730000200001010000"
    "0000000001000000000001",
)
DC_RESERVED = bytes.fromhex(
    "0401080002000000000200000100a601015a0000dc3734730000200001010000"
    "0000000001000000000001",
)
NOW = datetime(2026, 10, 12, 15, 24, 30, tzinfo=UTC)
BASE_ARGS: MideaDeviceInitKwargs = {
    "name": "Test laundry appliance",
    "device_id": 1,
    "ip_address": "192.0.2.1",
    "port": 6444,
    "token": "00",
    "key": "00",
    "device_protocol": ProtocolVersion.V1,
    "model": "test",
    "subtype": 0,
}


def frame(
    body: bytes | bytearray,
    message_type: MessageType = MessageType.query,
) -> bytes:
    """Use an identity-free header; direct decoders do not validate its checksum."""
    return bytes([170] + [0] * 7 + [ProtocolVersion.V1, message_type]) + body + b"\x00"


def dryer(body: bytes | bytearray | None = None) -> MideaDCDevice:
    """Normalize operating state without altering the captured extended fields."""
    args = BASE_ARGS.copy()
    args["model"], args["subtype"] = ("38208801", 13367)
    device = MideaDCDevice(customize="", **args)
    if body is None:
        report = bytearray(DC_BODY)
        report[0:3] = bytes([3, 1, 1])
        report[4], report[9], report[11] = (43, 2, 1)
        report[12] = report[12] & ~12 | 4
        report[13] = report[13] & ~12 | 4
        report[36] = 1
    else:
        report = bytearray(body)
    device.process_message(frame(report))
    return device


class TestMideaDCDevice:
    """Test Midea DC Device."""

    device: MideaDCDevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea DC Device setup."""
        self.device = MideaDCDevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="test_model",
            subtype=1,
            customize="",
        )

    def test_initial_attributes(self) -> None:
        """Test initial attributes."""
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.start] is False
        assert self.device.attributes[DeviceAttributes.status] == "unknown"
        assert self.device.attributes[DeviceAttributes.program] == "none"
        assert self.device.attributes[DeviceAttributes.intensity] is None
        assert self.device.attributes[DeviceAttributes.dryness_level] is None
        assert self.device.attributes[DeviceAttributes.dry_temperature] is None
        assert self.device.attributes[DeviceAttributes.error_code] is None
        assert self.device.attributes[DeviceAttributes.door_warn] is None
        assert self.device.attributes[DeviceAttributes.ai_switch] is None
        assert self.device.attributes[DeviceAttributes.material] is None
        assert self.device.attributes[DeviceAttributes.water_box] is None
        assert self.device.attributes[DeviceAttributes.washing_data] == bytearray([])
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"
        assert self.device.attributes[DeviceAttributes.time_remaining] is None

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    @pytest.mark.parametrize(
        "message_type",
        [MessageType.query, MessageType.set],
    )
    def test_query_set_response(self, message_type: MessageType) -> None:
        """Test query/set response with mapped status and program."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
        )
        body = bytearray(30)
        body[0] = 0x03  # Body type
        body[1] = 0x01  # power
        body[2] = 0x02  # status start
        body[4] = 0x01  # program fiber
        body[9] = 0x03  # intensity
        body[10] = 0x04  # dryness level / dry temperature
        body[16] = 0x01  # progress
        body[17] = 30  # time remaining low byte
        body[18] = 1  # time remaining high byte
        body[24] = 0x05  # error code
        body[25] = 0x06  # door warn
        body[27] = 0x07  # ai switch
        body[28] = 0x08  # material
        body[29] = 0x09  # water box
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is True
        assert self.device.attributes[DeviceAttributes.start] is True
        assert self.device.attributes[DeviceAttributes.status] == "start"
        assert self.device.attributes[DeviceAttributes.program] == "fiber"
        assert self.device.attributes[DeviceAttributes.intensity] == 3
        assert self.device.attributes[DeviceAttributes.dryness_level] == 4
        assert self.device.attributes[DeviceAttributes.dry_temperature] == 4
        assert self.device.attributes[DeviceAttributes.error_code] == 5
        assert self.device.attributes[DeviceAttributes.door_warn] == 6
        assert self.device.attributes[DeviceAttributes.ai_switch] == 7
        assert self.device.attributes[DeviceAttributes.material] == 8
        assert self.device.attributes[DeviceAttributes.water_box] == 9
        assert self.device.attributes[DeviceAttributes.washing_data] == body[3:15]
        assert self.device.attributes[DeviceAttributes.progress] is None
        assert self.device.attributes[DeviceAttributes.time_remaining] == 286

    def test_query_set_response_mapped_progress(self) -> None:
        """Test query/set response with a valid progress bit set."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.query],
        )
        body = bytearray(30)
        body[0] = 0x03  # Body type
        body[16] = 0x02  # progress bit 1
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.progress] == "prog1"

    def test_notify1_response_unmapped_values(self) -> None:
        """Test notify1 response with unmapped status and program values."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(30)
        body[0] = 0x04  # Body type
        body[2] = 20  # unmapped status
        body[4] = 99  # unmapped program
        crc = bytearray([0x00])
        self.device.process_message(bytes(header + body + crc))
        assert self.device.attributes[DeviceAttributes.power] is False
        assert self.device.attributes[DeviceAttributes.start] is False
        assert self.device.attributes[DeviceAttributes.status] == 20
        assert self.device.attributes[DeviceAttributes.program] == 99
        assert self.device.attributes[DeviceAttributes.progress] is None
        assert self.device.attributes[DeviceAttributes.time_remaining] is None

    def test_unexpected_response(self) -> None:
        """Test notify1 response with unexpected body type updates no attribute."""
        header = bytearray(
            [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [MessageType.notify1],
        )
        body = bytearray(30)
        body[0] = 0x03  # unexpected body type for notify1
        crc = bytearray([0x00])
        new_status = self.device.process_message(bytes(header + body + crc))
        assert new_status == {}

    def test_set_attribute_power(self) -> None:
        """Test set attribute power sends a power message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessagePower)
            assert message.power is True

    def test_set_attribute_start(self) -> None:
        """Test set attribute start sends a start message."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.start.value, True)
            mock_build_send.assert_called_once()
            message = mock_build_send.call_args[0][0]
            assert isinstance(message, MessageStart)
            assert message.start is True
            assert message.washing_data == bytearray([])

    def test_set_attribute_not_supported(self) -> None:
        """Test set attribute with an unsupported attribute does not send."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.ai_switch.value, True)
            mock_build_send.assert_not_called()

    def test_set_attribute_wrong_type(self) -> None:
        """Test set attribute with a non-bool value raises and does not send."""
        with (
            patch.object(self.device, "build_send") as mock_build_send,
            pytest.raises(ValueWrongType),
        ):
            self.device.set_attribute(DeviceAttributes.power.value, 5)
        mock_build_send.assert_not_called()


@pytest.mark.parametrize(
    ("cls", "model", "subtype"),
    [(MideaDCDevice, "38208801", 13367)],
)
def test_profile_identity_and_legacy_isolation(
    cls: type,
    model: str,
    subtype: int,
) -> None:
    """Expose Lua-confirmed controls broadly and gate only profile extensions."""
    for wrong_model, wrong_subtype in [("other", subtype), (model, subtype + 1)]:
        device = cls(
            customize="",
            **dict(BASE_ARGS, model=wrong_model, subtype=wrong_subtype),
        )
        assert device.get_attribute(Attr.parameter_control_supported) is True
        assert len(device.get_parameter_options(Attr.program_control)) == 50
        assert Attr.temperature_control not in device.attributes
        assert Attr.dryness_control not in device.attributes
    device = cls(
        customize="",
        **dict(BASE_ARGS, model="marketing name", sn8=model, subtype=subtype),
    )
    assert device.get_attribute(Attr.parameter_control_supported) is True
    assert Attr.temperature_control in device.attributes
    assert Attr.dryness_control in device.attributes
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match=r"standby|unavailable|Timed extra"),
    ):
        device.set_attribute(Attr.program_control, "cotton")
    send.assert_not_called()


def test_generic_lua_controls_are_available_without_profile_identity() -> None:
    """Generic Lua fields use the complete protocol program table."""
    device = MideaDCDevice(customize="", **BASE_ARGS)
    report = bytearray(DC_BODY)
    report[0:3] = bytes([3, 1, 1])
    device.process_message(frame(report))
    assert device.get_parameter_options(Attr.program_control)[1] == "fiber"
    assert device.get_parameter_options(Attr.program_control)[49] == "sterilize"
    assert device.get_attribute(Attr.anti_wrinkle) is False
    assert device.get_attribute(Attr.sterilize) is False
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.program_control, "fiber")
    assert send.call_args_list[0].args[0].body[4] == 1


def test_missing_extended_fields_and_short_acknowledgements() -> None:
    """Acks preserve state; missing temperature fields disable writes."""
    device = dryer()
    before = dict(device.attributes)
    device.process_message(frame(bytes([2] + [255] * 32), MessageType.set))
    assert device.attributes == before
    device.process_message(frame(DC_BODY[:30]))
    assert device.get_attribute(Attr.temperature_control) is None


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


@pytest.mark.parametrize("minutes", [90, 270])
def test_finish_time_subtracts_program_duration_and_is_not_optimistic(
    minutes: int,
) -> None:
    """Use a timezone-bearing deadline, not total minutes until completion."""
    device = dryer()
    assert device._controls is not None
    report = bytearray(device._controls.body)
    report[17:19] = minutes.to_bytes(2, "little")
    device.process_message(frame(report))
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
    assert body[2] == 255
    assert int.from_bytes(body[14:16], "little") == 600 - duration
    assert body[3:12] == device._controls.body[3:12]
    assert device.attributes == before
    assert send.call_args_list[1].args[0].body == b"\x03"
    assert len(body) == 22
    assert body[12] == 5
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
    assert body[12] == report[12] & ~3
    assert body[13] == report[13]
    assert device.get_attribute(Attr.appointment) is True
    cancelled = bytearray(report)
    cancelled[2], cancelled[14], cancelled[15] = (1, 0, 0)
    cancelled[12] &= ~3
    device.process_message(frame(cancelled))
    assert device.get_attribute(Attr.appointment) is False
    assert device.get_attribute(Attr.appointment_finish) is None
    assert device.get_attribute("start") is False


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
    assert send.call_args_list[1].args[0].body[12] == report[12] & ~3


@pytest.mark.parametrize("profile", [False, True])
def test_reservation_starts_only_after_a_matching_query(profile: bool) -> None:
    """A prepare write cannot start a cycle before its real fields are confirmed."""
    device = dryer() if profile else MideaDCDevice(customize="", **BASE_ARGS)
    if not profile:
        report = bytearray(DC_BODY)
        report[1:3] = bytes([1, 1])
        device.process_message(frame(report))
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        target = (NOW.replace(second=0) + timedelta(hours=10)).isoformat()
        device.set_attribute(Attr.appointment_finish, target)
        assert len(send.call_args_list) == 2
        prepare = send.call_args_list[0].args[0].body
        assert prepare[1:3] == bytes([255, 255])
        assert prepare[12] == (5 if profile else 253)
        assert send.call_args_list[1].args[0].body == b"\x03"
        assert device._controls is not None
        report = bytearray(device._controls.body)
        report[0:3] = bytes([3, 1, 6])
        report[12] = report[12] & ~3 | 1
        report[14:16] = prepare[14:16]
        if not profile:
            # These extensions are not generic Lua fields or generic controls.
            report[36] += 1
            report[42] += 1
        device.process_message(frame(report))
        assert len(send.call_args_list) == 4
        started = send.call_args_list[2].args[0].body
        assert started[2] == 1
        assert started[3:16] == prepare[3:16]
        assert send.call_args_list[3].args[0].body == b"\x03"
        device.process_message(frame(report))
        assert len(send.call_args_list) == 4


@pytest.mark.parametrize(
    "response",
    ["ack", "notify", "stale", "wrong_wait", "zero_wait", "running"],
)
def test_unconfirmed_reservation_never_sends_start(response: str) -> None:
    """Acks, notifications and rejected/incorrect fields cannot authorize a start."""
    device = dryer()
    assert device._controls is not None
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        minutes = 91 if response == "zero_wait" else 600
        target = (NOW.replace(second=0) + timedelta(minutes=minutes)).isoformat()
        device.set_attribute(Attr.appointment_finish, target)
        prepare = send.call_args_list[0].args[0].body
        report = bytearray(device._controls.body)
        report[2] = 6
        report[12] = report[12] & ~3 | 1
        report[14:16] = prepare[14:16]
        if response == "ack":
            device.process_message(frame(bytes([2]) + bytes(21), MessageType.set))
        elif response == "notify":
            report[0] = 4
            device.process_message(frame(report, MessageType.notify1))
        else:
            if response == "stale":
                report[12] &= ~3
            elif response == "wrong_wait":
                report[14:16] = (100).to_bytes(2, "little")
            elif response == "zero_wait":
                report[14:16] = bytes(2)
            elif response == "running":
                report[2] = 2
            device.process_message(frame(report))
        assert len(send.call_args_list) == (3 if response == "notify" else 2)
        assert device._pending_appointment is not None
        if response == "notify":
            assert send.call_args_list[-1].args[0].body == b"\x03"


@pytest.mark.parametrize("offset", [4, 9, 12, 13, 17, 36, 42])
def test_parameter_change_aborts_pending_reservation(offset: int) -> None:
    """Do not start if another controller changes selected options or duration."""
    device = dryer()
    assert device._controls is not None
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        device.set_attribute(
            Attr.appointment_finish,
            (NOW.replace(second=0) + timedelta(hours=10)).isoformat(),
        )
        report = bytearray(device._controls.body)
        report[12] = report[12] & ~3 | 1
        report[14:16] = send.call_args_list[0].args[0].body[14:16]
        report[offset] += 4 if offset == 12 else 1
        device.process_message(frame(report))
        assert device._pending_appointment is None
        assert len(send.call_args_list) == 2


def test_reservation_confirmation_timeout_never_starts() -> None:
    """Even a matching delayed report cannot start an expired request."""
    device = dryer()
    assert device._controls is not None
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch("midealan.devices.dc.monotonic", return_value=100) as timer,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        device.set_attribute(
            Attr.appointment_finish,
            (NOW.replace(second=0) + timedelta(hours=10)).isoformat(),
        )
        report = bytearray(device._controls.body)
        report[12] = report[12] & ~3 | 1
        report[14:16] = send.call_args_list[0].args[0].body[14:16]
        timer.return_value = 115
        device.process_message(frame(report))
        assert device._pending_appointment is None
        assert len(send.call_args_list) == 2


@pytest.mark.parametrize("attribute", ["appointment", "power", "start"])
def test_cancel_or_stop_discards_pending_start(attribute: str) -> None:
    """Cancellation wins over a later otherwise valid query confirmation."""
    device = dryer()
    assert device._controls is not None
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        target = (NOW.replace(second=0) + timedelta(hours=10)).isoformat()
        device.set_attribute(Attr.appointment_finish, target)
        report = bytearray(device._controls.body)
        report[12] = report[12] & ~3 | 1
        report[14:16] = send.call_args_list[0].args[0].body[14:16]
        with pytest.raises(ValueError, match="Wait for reservation confirmation"):
            device.set_attribute(Attr.sterilize, False)
        device.set_attribute(attribute, False)
        count = len(send.call_args_list)
        device.process_message(frame(report))
        assert device._pending_appointment is None
        assert len(send.call_args_list) == count


def test_clock_change_before_confirmation_does_not_start_past_deadline() -> None:
    """Revalidation fails closed if the wall clock jumps beyond the deadline."""
    device = dryer()
    assert device._controls is not None
    with (
        patch("midealan.devices.dc.message.datetime") as clock,
        patch.object(device, "build_send") as send,
    ):
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        device.set_attribute(
            Attr.appointment_finish,
            (NOW.replace(second=0) + timedelta(hours=10)).isoformat(),
        )
        report = bytearray(device._controls.body)
        report[12] = report[12] & ~3 | 1
        report[14:16] = send.call_args_list[0].args[0].body[14:16]
        clock.now.return_value = NOW + timedelta(hours=11)
        device.process_message(frame(report))
        assert device._pending_appointment is None
        assert len(send.call_args_list) == 2


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize(
    ("raw_duration", "minutes"),
    [(b"\x0e\x01", 270), (b"\x2c\x01", 300)],
)
def test_duration_above_255_uses_little_endian_minutes(
    profile: bool,
    raw_duration: bytes,
    minutes: int,
) -> None:
    """The appliance-confirmed 0E01 duration is 270 minutes, not 74 minutes."""
    report = bytearray(DC_RESERVED if profile else DC_BODY)
    report[1:3] = bytes([1, 1])
    report[17:19] = raw_duration
    device = dryer(report) if profile else MideaDCDevice(customize="", **BASE_ARGS)
    if not profile:
        device.process_message(frame(report))
    assert device.get_attribute("time_remaining") == minutes


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
    update = device.process_message(frame(report))
    assert device.get_attribute("time_remaining") == 300
    assert update["time_remaining"] == 300

    report[1] = 0
    report[17:19] = retained_minutes.to_bytes(2, "little")
    update = device.process_message(frame(report))
    assert device.get_attribute("power") is False
    assert device.get_attribute("time_remaining") is None
    assert update["time_remaining"] is None

    report[1] = 1
    report[17:19] = (300).to_bytes(2, "little")
    update = device.process_message(frame(report))
    assert device.get_attribute("time_remaining") == 300
    assert update["time_remaining"] == 300

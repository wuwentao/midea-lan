"""Test DC message parsing and control encoding."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MideaDeviceInitKwargs
from midealan.devices.dc import MideaDCDevice
from midealan.devices.dc.message import ControlAttributes as Attr
from midealan.devices.dc.message import (
    DCControls,
    MessageDCBase,
    MessagePower,
    MessageQuery,
    MessageStart,
)
from midealan.exceptions import ValueWrongType
from midealan.message import ListTypes, MessageType

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


class TestMessageDCBase:
    """Test DC Message Base."""

    def test_body_not_implemented(self) -> None:
        """Test body not implemented."""
        msg = MessageDCBase(
            protocol_version=ProtocolVersion.V1,
            message_type=MessageType.query,
            body_type=ListTypes.X03,
        )
        with pytest.raises(NotImplementedError):
            _ = msg.body


class TestMessageQuery:
    """Test DC Message Query."""

    def test_query_body(self) -> None:
        """Test query body contains only the body type."""
        msg = MessageQuery(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x03])


class TestMessagePower:
    """Test DC Message Power."""

    def test_power_body_on(self) -> None:
        """Test power body with power on."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1)
        msg.power = True
        assert msg.body == bytearray([0x02, 0x01, 0xFF])

    def test_power_body_off(self) -> None:
        """Test power body with power off."""
        msg = MessagePower(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x02, 0x00, 0xFF])


class TestMessageStart:
    """Test DC Message Start."""

    def test_start_body(self) -> None:
        """Test start body with washing data."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1)
        msg.start = True
        msg.washing_data = bytearray([0x01, 0x02])
        assert msg.body == bytearray([0x02, 0xFF, 0x01, 0x01, 0x02])

    def test_stop_body(self) -> None:
        """Test stop body."""
        msg = MessageStart(protocol_version=ProtocolVersion.V1)
        assert msg.body == bytearray([0x02, 0xFF, 0x00])


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("flags", [0, 4, 0x54])
def test_reservation_flag_preserves_profile_neighbours(
    profile: bool,
    enabled: bool,
    flags: int,
) -> None:
    """Use the appliance's packed byte while retaining generic Lua selectors."""
    report = bytearray(DC_BODY)
    report[12] = flags | int(not enabled)
    controls = DCControls(profile=profile)
    controls.update(report)
    encoded = controls.encode_appointment(enabled=enabled, wait=600 if enabled else 0)
    assert encoded[12] == (flags | int(enabled) if profile else 253 if enabled else 252)
    assert encoded[3:12] == report[3:12]
    assert encoded[13] == report[13]


@pytest.mark.parametrize(
    ("attribute", "value"),
    [(Attr.temperature_control, "low"), (Attr.timed_extra, 10)],
)
def test_generic_profile_cannot_encode_unverified_extensions(
    attribute: Attr,
    value: str | int,
) -> None:
    """Generic encoders reject extensions even when called without device dispatch."""
    controls = DCControls(profile=False)
    controls.update(bytearray(DC_BODY))
    assert controls.options(attribute) == []
    with pytest.raises(ValueError, match="unavailable in the current profile"):
        controls.encode(attribute, value)


@pytest.mark.parametrize(
    ("attribute", "offset"),
    [(Attr.anti_wrinkle, 12), (Attr.sterilize, 13)],
)
def test_generic_feature_packets_follow_lua_bitfields(
    attribute: str,
    offset: int,
) -> None:
    """Generic feature writes use the Lua two-bit masks."""
    device = MideaDCDevice(customize="", **BASE_ARGS)
    report = bytearray(DC_BODY)
    report[0:3] = bytes([3, 1, 1])
    device.process_message(frame(report))
    with patch.object(device, "build_send") as send:
        device.set_attribute(attribute, True)
    body = send.call_args_list[0].args[0].body
    assert body[offset] == 247
    if attribute == Attr.sterilize:
        assert body[11] == 255


@pytest.mark.parametrize(
    ("attribute", "label", "offset", "raw"),
    [
        (Attr.program_control, "big_dry", 4, 43),
        (Attr.program_control, "hanfu_ming", 4, 88),
        (Attr.program_control, "pet_sterilize", 4, 114),
        (Attr.dryness_control, "ready_to_wear", 9, 2),
        (Attr.anti_wrinkle, False, 12, 243),
        (Attr.anti_wrinkle, True, 12, 247),
    ],
)
def test_dryer_parameter_packets(
    attribute: str,
    label: str | bool,
    offset: int,
    raw: int,
) -> None:
    """Program and feature writes preserve power and start."""
    device = dryer()
    with patch.object(device, "build_send") as send:
        device.set_attribute(attribute, label)
    expected = bytearray([2] + [255] * 21)
    expected[offset] = raw
    assert send.call_args_list[0].args[0].body == expected
    assert len(device.get_parameter_options(Attr.program_control)) == 36


@pytest.mark.parametrize(("enabled", "mode", "flag"), [(False, 0, 243), (True, 1, 247)])
def test_sterilize_mode_and_flag_are_written_together(
    enabled: bool,
    mode: int,
    flag: int,
) -> None:
    """Write both fields; the old flag alone did not change the app state."""
    device = dryer()
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.sterilize, enabled)
    expected = bytearray([2] + [255] * 21)
    expected[11], expected[13] = (mode, flag)
    if enabled:
        expected[9] = 2
    assert send.call_args_list[0].args[0].body == expected
    assert device.get_parameter_options(Attr.dryness_control) == ["ready_to_wear"]


def test_extended_temperature_preserves_anti_wrinkle_and_season() -> None:
    """The short temperature command reset anti-wrinkle; body[11] is sterilization."""
    device = dryer()
    before = dict(device.attributes)
    assert device.get_attribute(Attr.temperature_control) == "standard"
    assert device.get_attribute(Attr.sterilize) is True
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.temperature_control, "low")
    body = send.call_args_list[0].args[0].body
    assert len(body) == 33
    assert body[1:3] == b"\xff\xff"
    assert body[11] == 255
    assert (body[12], body[24], body[28], body[29]) == (247, 2, 0, DC_BODY[42])
    assert device.attributes == before


@pytest.mark.parametrize("extra", [0, 170])
def test_timed_extra_is_additional_time_not_total_duration(extra: int) -> None:
    """The device adds ten minutes to the requested 0..170 minute extension."""
    device = dryer()
    report = bytearray(DC_BODY)
    report[0:3] = bytes([3, 1, 1])
    report[4], report[5], report[6] = (26, 0, 0)
    device.process_message(frame(report))
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.timed_extra, extra)
    assert send.call_args_list[0].args[0].body[5:7] == extra.to_bytes(2, "little")
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match=r"standby|unavailable|Timed extra"),
    ):
        device.set_attribute(Attr.timed_extra, 180)
    send.assert_not_called()


@pytest.mark.parametrize("report", [b"", DC_BODY[:29], bytes([2]) + DC_BODY[1:]])
def test_invalid_reports_preserve_control_snapshot(report: bytes) -> None:
    """Truncated reports and acknowledgements cannot replace valid state."""
    controls = DCControls()
    before = controls.update(bytearray(DC_BODY))
    assert controls.update(bytearray(report)) == {}
    assert controls.body == DC_BODY
    assert controls.attributes == before


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        (Attr.program_control, True),
        (Attr.program_control, "unknown"),
        (Attr.dryness_control, "storage"),
        (Attr.temperature_control, "high"),
        (Attr.sterilize, "on"),
        (Attr.anti_wrinkle, 1),
    ],
)
def test_invalid_parameter_writes_never_send(
    attribute: str,
    value: bool | int | str,
) -> None:
    """Reject invalid types, options and dryness incompatible with sterilization."""
    device = dryer()
    before = dict(device.attributes)
    with (
        patch.object(device, "build_send") as send,
        pytest.raises((ValueError, ValueWrongType)),
    ):
        device.set_attribute(attribute, value)
    send.assert_not_called()
    assert device.attributes == before


def test_unknown_dryness_has_no_options_and_rejects_writes() -> None:
    """A new unsupported report must clear previously writable dryness."""
    device = dryer()
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[9] = 255
    device.process_message(frame(report))
    assert device.get_attribute(Attr.dryness_control) is None
    assert device.get_parameter_options(Attr.dryness_control) == []
    assert device.get_parameter_options(Attr.anti_wrinkle) == []
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="unavailable"),
    ):
        device.set_attribute(Attr.dryness_control, "storage")
    send.assert_not_called()


def test_storage_dryness_is_available_with_sterilization_off() -> None:
    """Only a real disabled sterilization report permits storage dryness."""
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    device = dryer(report)
    assert device.get_attribute(Attr.sterilize) is False
    assert device.get_parameter_options(Attr.dryness_control) == [
        "ready_to_wear",
        "storage",
    ]
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.dryness_control, "storage")
    expected = bytearray([2] + [255] * 21)
    expected[9] = 3
    assert send.call_args_list[0].args[0].body == expected


@pytest.mark.parametrize("extra", [True, "bad", -10, 10.5, 15, 180])
def test_invalid_timed_extension_never_sends(extra: bool | str | float) -> None:
    """Timed extensions must be integer multiples of ten within the range."""
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[4] = 26
    device = dryer(report)
    with (
        patch.object(device, "build_send") as send,
        pytest.raises((ValueError, ValueWrongType)),
    ):
        device.set_attribute(Attr.timed_extra, extra)
    send.assert_not_called()


def test_integral_float_extension_encodes_minutes() -> None:
    """Whole-number values from numeric clients retain the minute encoding."""
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[4] = 26
    device = dryer(report)
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.timed_extra, 10.0)
    expected = bytearray([2] + [255] * 21)
    expected[5:7] = bytes([10, 0])
    assert send.call_args_list[0].args[0].body == expected


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


def test_cancelled_dryer_with_retained_inactive_wait_has_no_deadline() -> None:
    """The dryer retains the last wait after cancellation until powered off."""
    report = bytearray(DC_RESERVED)
    report[2] = 1
    report[12] &= ~3
    device = dryer(report)
    assert device.get_attribute(Attr.appointment) is False
    assert device.get_attribute(Attr.appointment_finish) is None
    assert device.get_attribute("start") is False


def test_unsupported_reservation_flag_is_read_only() -> None:
    """Unknown reservation codes must not be treated as off."""
    report = bytearray(DC_BODY)
    report[1:3] = bytes([1, 1])
    report[12] = 3
    device = dryer(report)
    assert device.get_attribute(Attr.appointment) is None
    assert device.get_attribute(Attr.appointment_controls_available) is False

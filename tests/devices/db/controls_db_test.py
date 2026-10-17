"""DB parameter controls regression tests from anonymous status bodies."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.device import MideaDeviceInitKwargs
from midealan.devices.db import MideaDBDevice
from midealan.devices.db.message import ControlAttributes as Attr
from midealan.devices.db.message import DBControls
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType

DB_BODY = bytes.fromhex(
    "030101001f0520010300030400400000204f0000db5933b10000002d08080000"
    "02ffff000000ffffffffffffffff140101ffffffff01ff200000080000",
)
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


def washer(body: bytes | bytearray = DB_BODY) -> MideaDBDevice:
    """Create a verified model without opening a socket."""
    args = BASE_ARGS.copy()
    args["model"], args["subtype"] = ("38131140", 13145)
    device = MideaDBDevice(customize="", **args)
    device.process_message(frame(body))
    return device


@pytest.mark.parametrize(
    ("cls", "model", "subtype"),
    [(MideaDBDevice, "38131140", 13145)],
)
def test_profile_identity_and_legacy_isolation(
    cls: type,
    model: str,
    subtype: int,
) -> None:
    """Require model and subtype; unrelated devices keep legacy behavior."""
    for wrong_model, wrong_subtype in [("other", subtype), (model, subtype + 1)]:
        device = cls(
            customize="",
            **dict(BASE_ARGS, model=wrong_model, subtype=wrong_subtype),
        )
        assert Attr.parameter_control_supported not in device.attributes
        assert device.get_parameter_options(Attr.program_control) == []
    device = cls(
        customize="",
        **dict(BASE_ARGS, model="marketing name", sn8=model, subtype=subtype),
    )
    assert device.get_attribute(Attr.parameter_control_supported) is True
    assert device.get_attribute(Attr.parameter_controls_available) is False
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match=r"standby|unavailable|Timed extra"),
    ):
        device.set_attribute(Attr.program_control, "cotton")
    send.assert_not_called()


@pytest.mark.parametrize(
    ("attribute", "label", "offset", "raw"),
    [
        (Attr.program_control, "big", 4, 11),
        (Attr.program_control, "yoga", 4, 147),
        (Attr.program_control, "quick_drying_clothes", 4, 145),
        (Attr.temperature_control, "20", 7, 2),
        (Attr.spin_speed_control, "1000", 8, 4),
        (Attr.rinse_count, "3", 6, 63),
        (Attr.water_level_control, "l2", 5, 2),
        (Attr.detergent_control, "l4", 11, 5),
        (Attr.detergent_control, "smart", 11, 4),
    ],
)
def test_washer_single_parameter_packets(
    attribute: str,
    label: str,
    offset: int,
    raw: int,
) -> None:
    """Use independently measured byte offsets and keep power/start/mode untouched."""
    device = washer()
    before = dict(device.attributes)
    with patch.object(device, "build_send") as send:
        device.set_attribute(attribute, label)
    expected = bytearray([2] + [255] * 21)
    expected[offset] = raw
    assert send.call_args_list[0].args[0].body == expected
    assert send.call_args_list[1].args[0].body == b"\x03"
    assert device.attributes == before, (
        "Only a real response may change displayed state"
    )
    assert len(device.get_parameter_options(Attr.program_control)) == 30


@pytest.mark.parametrize(
    ("minutes", "request_code"),
    [(42, 4), (45, 0), (50, 1), (55, 2), (60, 3)],
)
def test_wash_actual_minutes_and_non_linear_requests(
    minutes: int,
    request_code: int,
) -> None:
    """Wash requests encode minus three or increasing five-minute steps."""
    body = bytearray(DB_BODY)
    body[9], body[27] = (4, 42)
    device = washer(body)
    assert device.get_parameter_options(Attr.wash_time_control) == [
        "42",
        "45",
        "50",
        "55",
        "60",
    ]
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.wash_time_control, str(minutes))
    assert send.call_args_list[0].args[0].body[9] == request_code
    body[7], body[9], body[27] = (3, 0, 14)
    device.process_message(frame(body))
    assert device.get_parameter_options(Attr.wash_time_control) == [
        "11",
        "14",
        "19",
        "24",
        "29",
    ]


@pytest.mark.parametrize(
    ("minutes", "request_code"),
    [(8, 3), (9, 4), (10, 0), (11, 1), (12, 2)],
)
def test_spin_actual_minutes_and_non_linear_requests(
    minutes: int,
    request_code: int,
) -> None:
    """Spin request zero is ten minutes; it is not the shortest option."""
    device = washer()
    assert device.get_parameter_options(Attr.spin_time_control) == [
        "8",
        "9",
        "10",
        "11",
        "12",
    ]
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.spin_time_control, str(minutes))
    assert send.call_args_list[0].args[0].body[10] == request_code


@pytest.mark.parametrize(("enabled", "raw"), [(False, 63), (True, 127)])
def test_forget_free_preserves_custom_times_and_cloud_program(
    enabled: bool,
    raw: int,
) -> None:
    """Regression: FF cloud-cycle fields used to reset temperature and time presets."""
    report = bytearray(DB_BODY)
    report[9], report[10], report[27], report[28] = (3, 2, 60, 12)
    device = washer(report)
    before = dict(device.attributes)
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.forget_free, enabled)
    body = send.call_args_list[0].args[0].body
    assert len(body) == 54
    assert body[1:3] == b"\xff\xff"
    assert body[3:16] == bytes.fromhex("001f0520010303020400400000")
    assert body[22] == 2
    assert body[24] == raw
    assert body[36:38] == b"\x00\x00"
    assert device.attributes == before


@pytest.mark.parametrize(
    ("status", "power", "mode"),
    [(2, 1, 0), (3, 1, 0), (6, 1, 0), (1, 0, 0), (1, 1, 1)],
)
def test_washer_rejects_running_off_or_service_mode(
    status: int,
    power: int,
    mode: int,
) -> None:
    """Parameter writes must not implicitly stop or start an appliance."""
    report = bytearray(DB_BODY)
    report[1], report[2], report[3] = (power, status, mode)
    device = washer(report)
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match=r"standby|unavailable|Timed extra"),
    ):
        device.set_attribute(Attr.temperature_control, "20")
    send.assert_not_called()


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        (Attr.temperature_control, True),
        (Attr.rinse_count, "0"),
        (Attr.spin_speed_control, "1600"),
        (Attr.wash_time_control, "99"),
        (Attr.forget_free, "on"),
    ],
)
def test_invalid_washer_options_never_send(attribute: str, value: str | bool) -> None:
    """Reject unsupported or incorrectly typed options before constructing any frame."""
    device = washer()
    with (
        patch.object(device, "build_send") as send,
        pytest.raises((ValueError, ValueWrongType)),
    ):
        device.set_attribute(attribute, value)
    send.assert_not_called()


def test_missing_extended_fields_disable_forget_free() -> None:
    """Short reports must not keep stale writable extended state."""
    device = washer()
    device.process_message(frame(DB_BODY[:31]))
    assert device.get_attribute(Attr.forget_free) is None
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="unavailable"),
    ):
        device.set_attribute(Attr.forget_free, True)
    send.assert_not_called()


def test_unverified_38132386_does_not_inherit_v2_controls() -> None:
    """DB v41 Lua does not establish compatibility with the verified DB v33 controls."""
    args = BASE_ARGS.copy()
    args["model"], args["subtype"] = "38132386", 0
    device = MideaDBDevice(customize="", **args)
    device.process_message(frame(DB_BODY))
    assert Attr.parameter_control_supported not in device.attributes
    assert Attr.appointment_control_supported not in device.attributes
    assert device.get_parameter_options(Attr.program_control) == []


def test_integral_numeric_select_encodes_without_decimal_suffix() -> None:
    """Numeric clients may supply whole-number selects as floats."""
    device = washer()
    with patch.object(device, "build_send") as send:
        device.set_attribute(Attr.temperature_control, 20.0)
    expected = bytearray([2] + [255] * 21)
    expected[7] = 2
    assert send.call_args_list[0].args[0].body == expected
    assert send.call_args_list[1].args[0].body == b"\x03"


@pytest.mark.parametrize("report", [b"", DB_BODY[:30], bytes([2]) + DB_BODY[1:]])
def test_invalid_reports_preserve_control_snapshot(report: bytes) -> None:
    """Truncated reports and acknowledgements cannot replace valid state."""
    controls = DBControls()
    before = controls.update(bytearray(DB_BODY))
    assert controls.update(bytearray(report)) == {}
    assert controls.body == DB_BODY
    assert controls.attributes == before


def test_options_before_first_report_do_not_invent_minutes() -> None:
    """Capabilities alone cannot provide writable time or temperature choices."""
    controls = DBControls()
    assert controls.options(Attr.wash_time_control) == []
    assert controls.options(Attr.spin_time_control) == []
    assert controls.options(Attr.temperature_control) == []
    assert controls.options(Attr.forget_free) == []


@pytest.mark.parametrize(
    ("request_code", "minutes"),
    [(5, 45), (255, 45), (0, 0), (0, 254), (0, 255), (0, 3)],
)
def test_invalid_minute_reports_disable_time_writes(
    request_code: int,
    minutes: int,
) -> None:
    """Unknown request codes, sentinels and nonpositive options stay read-only."""
    device = washer()
    report = bytearray(DB_BODY)
    report[9], report[27] = request_code, minutes
    device.process_message(frame(report))
    assert device.get_attribute(Attr.wash_time_control) is None
    assert device.get_parameter_options(Attr.wash_time_control) == []
    with (
        patch.object(device, "build_send") as send,
        pytest.raises(ValueError, match="unavailable"),
    ):
        device.set_attribute(Attr.wash_time_control, "45")
    send.assert_not_called()

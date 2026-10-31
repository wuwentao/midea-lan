"""Vendor Lua packets and a real 17100007 LAN query response."""

from collections.abc import Callable
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.c3 import DeviceAttributes as A
from midealan.devices.c3 import MideaC3Device
from midealan.devices.c3.message import C3Basic2010Body, MessageC3Response
from midealan.devices.c3.quintuple import (
    BASIC_SIZES,
    BasicTag,
    C3QuintupleBasicBody,
    MessageQuery2010,
    MessageSet2010,
)
from midealan.message import MessageType

# Query response received 57 ms after the vendor-generated query, 2026-10-30.
QUERY_REPLY = bytes.fromhex(
    "aa7cc300000000000003002010ff1cffff00ffff01ff0103014a7fff00f001e000ff"
    "00000000010101000000000001000000020202022600fa00fa0032022600fa00fa0032"
    "012c00aa025800c801b100010102ff010130000000002f000000000000000000000000"
    "000001005a0000ffff001a0a1f0022ffffffff006b",
)


def device() -> MideaC3Device:
    """Create an offline controller with no real credentials or connection."""
    return MideaC3Device(
        name="Test",
        device_id=1,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="17100007",
        subtype=195,
        customize="",
    )


def frame(body: bytes, kind: MessageType = MessageType.set) -> bytes:
    """Wrap a synthetic acknowledgement without making a network connection."""
    header = bytes((0xAA, 10 + len(body), 0xC3, 0, 0, 0, 0, 0, 0, kind))
    return header + body + bytes((-sum((header + body)[1:]) & 0xFF,))


def test_query_matches_vendor_lua() -> None:
    """The tested UART query must remain byte-for-byte vendor compatible."""
    assert (
        MessageQuery2010().serialize().hex()
        == "aa14c300000000000003002010ffffffff00fffffc"
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {BasicTag.DHW_TEMPERATURE: 48},
            "aa19c300000000000002002010ffffffff01ffff00070201e00d",
        ),
        (
            {BasicTag.DHW_TEMPERATURE: 48.5},
            "aa19c300000000000002002010ffffffff01ffff00070201e508",
        ),
        (
            {BasicTag.DHW_POWER: True},
            "aa18c300000000000002002010ffffffff01ffff00020101f4",
        ),
        (
            {BasicTag.DHW_POWER: False},
            "aa18c300000000000002002010ffffffff01ffff00020100f5",
        ),
        (
            {BasicTag.ZONE1_TEMPERATURE: 33},
            "aa19c300000000000002002010ffffffff01ffff000402014aa6",
        ),
        (
            {BasicTag.ZONE1_POWER: False},
            "aa18c300000000000002002010ffffffff01ffff00000100f7",
        ),
    ],
)
def test_set_matches_vendor_lua(values: dict, expected: str) -> None:
    """Literal packets were generated independently by the recovered vendor Lua."""
    assert MessageSet2010(values).serialize().hex() == expected


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), 3276.7, 3276.69])
def test_invalid_temperature(value: float) -> None:
    """Reject values that cannot represent a valid target."""
    with pytest.raises(ValueError, match="temperature"):
        MessageSet2010({BasicTag.DHW_TEMPERATURE: value})


@pytest.mark.parametrize(
    "values",
    [{}, {99: True}, {BasicTag.DHW_POWER: "false"}, {BasicTag.MODE: 99}],
)
def test_invalid_controls(values: dict) -> None:
    """Never silently coerce invalid controls into dangerous defaults."""
    with pytest.raises(ValueError, match=r"."):
        MessageSet2010(values)


def test_real_query_reply() -> None:
    """A synchronous query now exposes the actual controller state."""
    response = MessageC3Response(QUERY_REPLY, model="17100007")
    assert response.zone1_power is True
    assert not hasattr(response, "zone2_power")  # ff means invalid, not false.
    assert response.dhw_power is True
    assert response.mode == 3
    assert response.dhw_target_temp == 48
    assert response.room_target_temp == 24
    assert response.tank_actual_temperature == 43.3
    assert response.outdoor_temperature == 9
    assert response.dhw_temp_min == 20
    assert response.dhw_temp_max == 60
    assert response.quintuple_arrays["zone_target_temp"] == {0: 33}


def test_device_query_and_targets() -> None:
    """Translate water/room modes and limits into the existing HA-facing attributes."""
    d = device()
    assert len(d.build_query()) == 6
    status = d.process_message(QUERY_REPLY)
    assert status[A.target_temperature] == [33, 25]
    assert status[A.temperature_min][0] == 25
    assert status[A.temperature_max][0] == 55
    assert d.attributes[A.zone1_water_temp_mode] is True
    assert d.attributes[A.zone1_room_temp_mode] is False
    assert d._quintuple_ready is True


def test_controls_wait_for_status() -> None:
    """Prevent the old default room-temperature mode from selecting the wrong field."""
    d = device()
    with pytest.raises(ValueError, match="first 0x2010"):
        d.set_attribute(A.dhw_power, True)
    with pytest.raises(ValueError, match="first 0x2010"):
        d.set_target_temperature(33, None, 0)


@pytest.mark.parametrize(
    ("attr", "tag", "value"),
    [
        (A.zone1_power, BasicTag.ZONE1_POWER, False),
        (A.zone2_power, BasicTag.ZONE2_POWER, False),
        (A.dhw_power, BasicTag.DHW_POWER, True),
        (A.zone1_curve, BasicTag.ZONE1_CURVE, True),
        (A.zone2_curve, BasicTag.ZONE2_CURVE, False),
        (A.fast_dhw, BasicTag.FAST_DHW, True),
        (A.tbh, BasicTag.TANK_BOOSTER, False),
        (A.dhw_target_temp, BasicTag.DHW_TEMPERATURE, 48.5),
    ],
)
def test_attribute_routing(attr: A, tag: BasicTag, value: bool | float) -> None:
    """Every supported attribute writes only its own TLV."""
    d = device()
    d.process_message(QUERY_REPLY)
    d._attributes[A.double_zone] = True
    with patch.object(d, "build_send") as send:
        d.set_attribute(attr, value)
    assert (
        send.call_args.args[0].serialize() == MessageSet2010({tag: value}).serialize()
    )


def test_temperature_and_mode_routing() -> None:
    """Preserve half degrees and map HA auto (1) to vendor auto (5)."""
    d = device()
    d.process_message(QUERY_REPLY)
    d._attributes[A.double_zone] = True
    with patch.object(d, "build_send") as send:
        d.set_target_temperature(33.5, None, 0)
        assert (
            send.call_args.args[0].serialize()
            == MessageSet2010({BasicTag.ZONE1_TEMPERATURE: 33.5}).serialize()
        )
        d.set_mode(0, 1)
        assert (
            send.call_args.args[0].serialize()
            == MessageSet2010(
                {BasicTag.ZONE1_POWER: True, BasicTag.MODE: 5},
            ).serialize()
        )
        d.set_mode(0, 0)
        assert (
            send.call_args.args[0].serialize()
            == MessageSet2010(
                {BasicTag.ZONE1_POWER: False},
            ).serialize()
        )
        d.set_target_temperature(34, 3, 1)
        assert (
            send.call_args.args[0].serialize()
            == MessageSet2010(
                {
                    BasicTag.ZONE2_TEMPERATURE: 34,
                    BasicTag.ZONE2_POWER: True,
                    BasicTag.MODE: 3,
                },
            ).serialize()
        )
        d.set_target_temperature(34, 0, 1)
        assert (
            send.call_args.args[0].serialize()
            == MessageSet2010(
                {BasicTag.ZONE2_TEMPERATURE: 34, BasicTag.ZONE2_POWER: False},
            ).serialize()
        )


def test_sparse_ack_preserves_other_zone_and_refreshes_target() -> None:
    """A one-field reply must not reset other zones or power flags."""
    d = device()
    d.process_message(QUERY_REPLY)
    ack = frame(bytes.fromhex("002010ffffffff01ffff000402014f"))
    state = d.process_message(ack)
    assert state[A.target_temperature] == [33.5, 25]
    assert d.attributes[A.dhw_target_temp] == 48
    assert d.attributes[A.dhw_power] is True


def test_room_mode_and_cooling_limits() -> None:
    """Apply correct limits for cooling, auto and room-controlled zones."""
    d = device()
    d.process_message(QUERY_REPLY)
    d.process_message(frame(bytes.fromhex("002010ffffffff01ffff00030102")))
    assert d.attributes[A.temperature_max][0] == 25
    d.process_message(frame(bytes.fromhex("002010ffffffff01ffff00120101")))
    assert d.attributes[A.temperature_min][0] == 17
    assert d.attributes[A.temperature_max][0] == 30
    with patch.object(d, "build_send") as send:
        d.set_target_temperature(22.5, 1, 0)
    assert (
        send.call_args.args[0].serialize()
        == MessageSet2010(
            {
                BasicTag.ZONE1_TEMPERATURE: 22.5,
                BasicTag.ROOM_TEMPERATURE: 22.5,
                BasicTag.ZONE1_POWER: True,
                BasicTag.MODE: 5,
            },
        ).serialize()
    )


@pytest.mark.parametrize(
    "body",
    [
        b"",
        bytes(9),
        bytes.fromhex("002010ffffffff02ffff"),
        bytes.fromhex("002010ffffffff01ffff00"),
        bytes.fromhex("002010ffffffff01ffff00070201"),
        bytes.fromhex("002010ffffffff01ffff00070101"),
    ],
)
def test_malformed_bodies(body: bytes) -> None:
    """Malformed envelopes and TLVs cannot publish partial controls."""
    response = C3QuintupleBasicBody(bytearray(body))
    assert response.quintuple_basic is False
    assert not hasattr(response, "dhw_target_temp")


def test_unknown_tlv_and_invalid_temperature() -> None:
    """Skip unknown tags and unavailable probes without inventing values."""
    body = bytes.fromhex("002010ffffffff01ffff123401010007027fff000601ff")
    assert not C3QuintupleBasicBody(bytearray(body)).quintuple_basic
    body = bytes.fromhex("002010ffffffff01ffff123401010007027fff")
    response = C3QuintupleBasicBody(bytearray(body))
    assert response.quintuple_basic
    assert not hasattr(response, "dhw_target_temp")


def test_signed_temperature() -> None:
    """The Lua's Temp type is signed two's-complement tenths."""
    body = bytes.fromhex("002010ffffffff01ffff003402ffce")
    assert C3QuintupleBasicBody(bytearray(body)).outdoor_temperature == -5


@pytest.mark.parametrize(
    "operation",
    [
        lambda d: d.set_attribute("not_a_control", True),
        lambda d: d.set_attribute(A.dhw_power, "false"),
        lambda d: d.set_attribute(A.dhw_target_temp, 90),
        lambda d: d.set_target_temperature(80, None, 0),
        lambda d: d.set_target_temperature(30, None, 2),
        lambda d: d.set_target_temperature(30, 8, 0),
        lambda d: d.set_mode(2, 3),
        lambda d: d.set_mode(0, 8),
        lambda d: d.set_mode(1, 3),
        lambda d: d.set_target_temperature(34, None, 1),
        lambda d: d.set_attribute(A.zone2_power, True),
    ],
)
def test_rejected_controls_never_send(
    operation: Callable[[MideaC3Device], None],
) -> None:
    """Unsupported operations must never use the legacy whole-state command."""
    d = device()
    d.process_message(QUERY_REPLY)
    with patch.object(d, "build_send") as send, pytest.raises(ValueError, match=r"."):
        operation(d)
    send.assert_not_called()


def test_schema_reaches_outdoor_field() -> None:
    """Guard offsets across the ASCII fields before tag 52."""
    assert 10 + sum(BASIC_SIZES[:52]) == 97


def test_unknown_reply_preserves_ready_state() -> None:
    """Unrelated replies do not clear known targets or readiness."""
    d = device()
    d.process_message(QUERY_REPLY)
    assert d.process_message(frame(bytes.fromhex("00ffff"))) == {}
    assert d.attributes[A.target_temperature][0] == 33


def test_legacy_temperature_parser_remains_available() -> None:
    """Preserve the old parser's optional compatibility field for callers."""
    body = C3Basic2010Body(bytearray(QUERY_REPLY[10:-1]), include_idu_t1s1=True)
    assert body.idu_t1s1 == 33

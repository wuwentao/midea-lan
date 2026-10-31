"""Energy readings verified independently by the recovered vendor Lua."""

import pytest

from midealan.devices.c3 import DeviceAttributes as A
from midealan.devices.c3.message import MessageC3Response
from midealan.devices.c3.quintuple import (
    C3QuintupleEnergyBody,
    MessageQuery2F12,
)
from midealan.message import MessageType

from .quintuple_test import QUERY_REPLY, device, frame

ENERGY_REPLY = bytes.fromhex(
    "aa9bc300000000000003002f12ff1cffff00ffff02ffffffff0258020b006b00"
    "000230000364c000030ffc0002ed380000ad0c00008e30000001f60000000000"
    "0000000000000000000000000054c400003e8000001edc00000113000002bc00"
    "0001f40000012c000000e90000157c00001068000007d000000113000054c400"
    "003e8000001edc00000113000054c400003e8000001edc0000011312",
)
EXPECTED = {
    "instant_power0": 1070,
    "instant_renew_power0": 5230,
    "current_unit_capacity": 6,
    "total_energy_consumption": 443,
    "total_produced_energy": 2224,
}


def test_query_matches_vendor_lua() -> None:
    """The read-only query exactly matches vendor jsonToData output."""
    assert (
        MessageQuery2F12().serialize().hex()
        == "aa14c300000000000003002f12ffffffff00ffffeb"
    )


@pytest.mark.parametrize("kind", [MessageType.query, MessageType.notify1])
def test_real_energy_reply(kind: MessageType) -> None:
    """Live reply gives kW heat, watts electricity and kWh totals."""
    packet = bytearray(ENERGY_REPLY)
    packet[9] = kind
    response = MessageC3Response(packet, model="17100007")
    assert response.quintuple_energy is True
    for name, value in EXPECTED.items():
        assert getattr(response, name) == value
    d = device()
    status = d.process_message(packet)
    for name, value in EXPECTED.items():
        assert status[name] == value
        assert d.attributes[A(name)] == value
    assert d._quintuple_ready is False  # Energy is not basic control status.


@pytest.mark.parametrize(
    ("model", "kind"),
    [("17100003", MessageType.query), ("17100007", MessageType.set)],
)
def test_energy_dispatch_is_restricted(model: str, kind: MessageType) -> None:
    """Never reinterpret other models or control acknowledgements as energy."""
    response = MessageC3Response(frame(ENERGY_REPLY[10:-1], kind), model=model)
    assert not hasattr(response, "quintuple_energy")


@pytest.mark.parametrize(("fill", "expected"), [(0, 0), (255, None)])
def test_zero_and_unavailable(fill: int, expected: int | None) -> None:
    """Invalid counters clear the current state; genuine zeros remain numeric."""
    body = bytearray(ENERGY_REPLY[10:-1])
    body[10:] = bytes([fill]) * (len(body) - 10)
    response = C3QuintupleEnergyBody(body)
    for name in EXPECTED:
        assert getattr(response, name) == expected


def test_sparse_energy_and_malformed_tlv() -> None:
    """Partial updates preserve unrelated counters; malformed TLVs are atomic."""
    d = device()
    d.process_message(ENERGY_REPLY)
    envelope = bytes.fromhex("002f12ffffffff01ffff")
    d.process_message(
        frame(envelope + bytes.fromhex("0004020000"), MessageType.notify1),
    )
    assert d.attributes[A.instant_power0] == 0
    assert d.attributes[A.total_produced_energy] == 2224
    for tail in ["00", "00040200", "00040100", "000402006b00060200"]:
        parsed = C3QuintupleEnergyBody(bytearray(envelope + bytes.fromhex(tail)))
        assert parsed.quintuple_energy is False
        assert not hasattr(parsed, "instant_power0")
    unknown = C3QuintupleEnergyBody(bytearray(envelope + bytes.fromhex("ffff0100")))
    assert unknown.quintuple_energy is False


@pytest.mark.parametrize("length", [0, 9, 10, 48])
def test_truncated_energy(length: int) -> None:
    """Short sequential blocks must not produce plausible-looking power."""
    parsed = C3QuintupleEnergyBody(bytearray(ENERGY_REPLY[10:-1][:length]))
    assert parsed.quintuple_energy is False
    assert not hasattr(parsed, "instant_power0")


def test_minimum_energy_and_unknown_format() -> None:
    """A complete core block is enough; unsupported encodings are ignored."""
    body = bytearray(ENERGY_REPLY[10:-1][:49])
    assert C3QuintupleEnergyBody(body).instant_power0 == 1070
    body[7] = 2
    assert C3QuintupleEnergyBody(body).quintuple_energy is False


def test_other_telemetry_cannot_overwrite_energy() -> None:
    """Do not mix legacy raw counters/capacity with the authoritative 2F12 table."""
    d = device()
    d.process_message(QUERY_REPLY)
    d.process_message(ENERGY_REPLY)
    body = bytearray.fromhex("002f10ff1cffff00ffff") + bytearray(180)
    body[60:64] = bytes.fromhex("00000051")
    status = d.process_message(frame(body, MessageType.notify1))
    for name, value in EXPECTED.items():
        assert name not in status
        assert d.attributes[A(name)] == value
    assert "comp_run_freq" in status

"""Offline regression for the verified model-specific BF behavior."""

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.bf import DeviceAttributes as A
from midealan.devices.bf import MideaBFDevice
from midealan.message import MessageType


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


def frame(body: bytearray) -> bytes:
    """Wrap a synthetic body using the actual response header layout."""
    header = bytearray([0xAA, 0, 0xBF, 0, 0, 0, 0, 0, 1, MessageType.query])
    return bytes(header + body + b"\x00")


@pytest.fixture(autouse=True)
def deny_network_and_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test tries to cross the offline boundary."""

    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("NETWORK_OR_THREAD_START_DENIED")

    monkeypatch.setattr("socket.socket", reject)
    monkeypatch.setattr("threading.Thread.start", reject)


@pytest.mark.parametrize("length", [1, 8, 14, 16, 26, 28, 32])
def test_missing_readonly_fields_are_unknown(length: int) -> None:
    """A missing low byte or flag cannot become a fabricated zero/False."""
    device = oven()
    full = bytearray(60)
    full[0] = 1
    full[14], full[16], full[26], full[28], full[32] = 200, 180, 190, 175, 32
    device.process_message(frame(full))
    short = device.process_message(frame(full[:length]))
    for key, offset in [
        (A.temperature_above, 14),
        (A.temperature_underside, 16),
        (A.cur_temperature_above, 26),
        (A.cur_temperature_underside, 28),
        (A.work_mode, 8),
        (A.pre_heat, 32),
    ]:
        if length <= offset:
            assert device.get_attribute(key) is None
            assert short[key] is None


def test_full_values_and_other_bf_behavior() -> None:
    """Preserve complete readings including real zero and the other-model path."""
    body = bytearray(60)
    body[0], body[14], body[16], body[26], body[28], body[32] = (
        1,
        200,
        180,
        190,
        175,
        32,
    )
    device = oven()
    device.process_message(frame(body))
    assert [
        device.get_attribute(k)
        for k in (
            A.temperature_above,
            A.temperature_underside,
            A.cur_temperature_above,
            A.cur_temperature_underside,
            A.pre_heat,
        )
    ] == [200, 180, 190, 175, True]
    device.process_message(frame(bytearray([1]) + bytearray(59)))
    assert device.get_attribute(A.temperature_above) == 0
    assert device.get_attribute(A.pre_heat) is False
    other = oven("other")
    other.process_message(frame(bytearray([1])))
    assert other.get_attribute(A.temperature_above) == 0


@pytest.mark.parametrize(("model", "subtype"), [("other", 5), ("700006B9", 1)])
def test_other_identity_keeps_missing_byte_fallback(model: str, subtype: int) -> None:
    """Keep historical parsing for non-matching model/subtype pairs."""
    device = oven(model, subtype)
    device.process_message(frame(bytearray([1])))
    assert device.get_attribute(A.temperature_above) == 0
    assert device.get_attribute(A.pre_heat) is False

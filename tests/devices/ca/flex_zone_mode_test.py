"""Test model-specific CA preset interpretation at the attribute boundary."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.ca import DeviceAttributes, MideaCADevice
from midealan.message import MessageType


def make_device(model: str = "310A2111", subtype: int = 56) -> MideaCADevice:
    """Construct an isolated device without starting its transport."""
    return MideaCADevice(
        name="Test Refrigerator",
        device_id=456,
        ip_address="192.0.2.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V1,
        model=model,
        subtype=subtype,
        customize="",
    )


@pytest.mark.parametrize(
    ("temperature", "mode"),
    [(6, "baby"), (2, "treasure"), (0, "zero")],
)
def test_wire_temperature_overrides_generic_mode(temperature: int, mode: str) -> None:
    """Real response decoding reaches the derived attribute and status."""
    device = make_device()
    body = bytearray(32)
    body[3] = temperature + 19
    body[5] = 1  # Generic soft_freezing must not overwrite this model's preset.
    header = bytearray([0xAA] + [0] * 7 + [ProtocolVersion.V1, MessageType.query])
    status = device.process_message(bytes(header + body + bytearray([0])))
    assert status[DeviceAttributes.variable_mode] == mode
    assert device.get_attribute(DeviceAttributes.variable_mode) == mode
    assert status[DeviceAttributes.flex_zone_setting_temp] == temperature


@pytest.mark.parametrize("temperature", [6, 6.0, 2, 2.0, 0, 0.0])
def test_temperature_only_update(temperature: float) -> None:
    """A partial temperature update includes the canonical mode notification."""
    device = make_device()
    response = SimpleNamespace(flex_zone_setting_temp=temperature)
    with patch("midealan.devices.ca.MessageCAResponse", return_value=response):
        status = device.process_message(b"")
    expected = {6.0: "baby", 2.0: "treasure", 0.0: "zero"}[temperature]
    assert status[DeviceAttributes.variable_mode] == expected
    assert device.get_attribute(DeviceAttributes.variable_mode) == expected


@pytest.mark.parametrize(
    "temperature",
    [3, -1, None, "0", "2", "6", False, True, float("nan"), float("inf")],
)
def test_unknown_source_clears_previous_mode(temperature: object) -> None:
    """Unverified attribute values cannot leave a stale or guessed preset."""
    device = make_device()
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(flex_zone_setting_temp=2),
    ):
        device.process_message(b"")
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(
            flex_zone_setting_temp=temperature,
            variable_mode=1,
        ),
    ):
        status = device.process_message(b"")
    assert status[DeviceAttributes.variable_mode] is None
    assert device.get_attribute(DeviceAttributes.variable_mode) is None


@pytest.mark.parametrize(("model", "subtype"), [("other", 56), ("310A2111", 1)])
def test_other_devices_keep_generic_mode(model: str, subtype: int) -> None:
    """Model and subtype must both match to replace the generic mode."""
    device = make_device(model, subtype)
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(flex_zone_setting_temp=2, variable_mode=1),
    ):
        status = device.process_message(b"")
    assert status[DeviceAttributes.variable_mode] == "soft_freezing"


def test_partial_responses_and_read_only_contract() -> None:
    """Raw-only updates use cached temperature; unrelated replies do not emit mode."""
    device = make_device()
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(variable_mode=1),
    ):
        assert device.process_message(b"")[DeviceAttributes.variable_mode] is None
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(flex_zone_setting_temp=6),
    ):
        device.process_message(b"")
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(variable_mode=0),
    ):
        assert device.process_message(b"")[DeviceAttributes.variable_mode] == "baby"
    with patch(
        "midealan.devices.ca.MessageCAResponse",
        return_value=SimpleNamespace(refrigerator_door=True),
    ):
        assert DeviceAttributes.variable_mode not in device.process_message(b"")
    before = device.attributes.copy()
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.variable_mode, "treasure")
        send.assert_not_called()
    assert device.attributes == before

"""Person flags reuse ordinary properties and capability customization."""

import json
from unittest.mock import patch

import pytest

from midealan.devices.ac import DeviceAttributes as A
from midealan.devices.ac.message import (
    PropertiesBody,
    PropertiesCapsQuery,
    PropertiesSet,
)
from midealan.message import ListTypes, NewProtocolMessageBody
from tests.devices.ac.device_ac_test import TestMideaACDevice as Fixture


@pytest.mark.parametrize("enabled", [True, False])
def test_customization_controls_existing_capability_collector(enabled: bool) -> None:
    """The existing collector honors opt-in and explicit opt-out without queries."""
    device = Fixture._make_device("220F4047", 8)
    assert device.get_attribute(A.wind_straight) is None
    assert device.get_attribute(A.wind_avoid) is None
    assert not {0x32, 0x33}.intersection(
        PropertiesCapsQuery.collect_capability_properties(device.capabilities),
    )
    device.set_customize(
        json.dumps(
            {
                "capabilities": {
                    "wind_straight": enabled,
                    "wind_avoid": enabled,
                },
            },
        ),
    )
    collected = PropertiesCapsQuery.collect_capability_properties(device.capabilities)
    assert (0x32 in collected) is enabled
    assert (0x33 in collected) is enabled


@pytest.mark.parametrize(
    ("attribute", "tag"),
    [(A.wind_straight, 0x32), (A.wind_avoid, 0x33)],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_property_setter_uses_existing_packet(
    attribute: str,
    tag: int,
    enabled: bool,
) -> None:
    """Only an explicitly requested flag is written, without optimistic readback."""
    device = Fixture._make_device("220F4047", 8)
    with patch.object(device, "build_send") as send:
        device.set_attribute(attribute, enabled)
    message = send.call_args.args[0]
    assert isinstance(message, PropertiesSet)
    assert bytes([tag, 0, 1, int(enabled)]) in message._body
    assert device.get_attribute(attribute) is None


@pytest.mark.parametrize("kind", [ListTypes.B0, ListTypes.B1])
@pytest.mark.parametrize("raw", [0, 1, 2])
def test_live_flags_are_not_capability_advertisements(kind: int, raw: int) -> None:
    """Straight 02 is not straight-on; avoid follows its ordinary nonzero flag."""
    body = bytearray([kind, 2])
    for tag in (0x32, 0x33):
        body.extend(NewProtocolMessageBody.pack(tag, bytearray([raw]), pack_len=5))
    parsed = PropertiesBody(body)
    assert parsed.wind_straight is (raw == 1)
    assert parsed.wind_avoid is (raw > 0)
    device = Fixture._make_device("220F4047", 8)
    device.process_message(Fixture._response(body))
    assert device.get_attribute(A.wind_straight) is (raw == 1)
    assert device.get_attribute(A.wind_avoid) is (raw > 0)


def test_missing_flags_stay_unknown_and_b5_does_not_create_live_state() -> None:
    """No tag and a capability-only body cannot create a live boolean."""
    assert not hasattr(PropertiesBody(bytearray([ListTypes.B1, 0])), "wind_straight")
    body = bytearray([ListTypes.B5, 2, 0x32, 0, 1, 1, 0x33, 0, 1, 1])
    parsed = PropertiesBody(body)
    assert not hasattr(parsed, "wind_straight")
    assert not hasattr(parsed, "wind_avoid")

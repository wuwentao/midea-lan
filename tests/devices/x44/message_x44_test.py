"""Test imports used by existing x44 library and Home Assistant clients."""

import pytest

from midealan.devices import ac, x44
from midealan.devices.x44 import message, zkp_3inch01
from tests.devices.x44 import identity


def test_flat_imports() -> None:
    """Old imports resolve to the canonical model implementations."""
    assert x44.DeviceAttributes is zkp_3inch01.DeviceAttributes
    assert zkp_3inch01.DeviceAttributes.brightness == x44.BRIGHTNESS
    assert x44.MessageQuery is message.MessageQuery is zkp_3inch01.message.MessageQuery
    assert (
        x44.MessageX44Response
        is message.MessageX44Response
        is zkp_3inch01.message.ScreenResponse
    )
    assert message.MessageSetScreen is zkp_3inch01.message.MessageSetScreen
    assert isinstance(
        x44.MideaX44Device(customize="", **identity("115P0303")),
        ac.MideaAppliance,
    )
    assert isinstance(
        x44.MideaAppliance(customize="", **identity("404M0001")),
        zkp_3inch01.ZKP3Inch01Device,
    )


@pytest.mark.parametrize("name", ["_zkp", "missing"])
def test_unknown_import(name: str) -> None:
    """A missing or private compatibility name raises the normal lookup error."""
    with pytest.raises(AttributeError):
        getattr(x44, name)

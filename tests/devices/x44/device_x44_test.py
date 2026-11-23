"""Test model selection and isolation at the 0x44 entry point."""

from argparse import Namespace
from typing import get_type_hints, override
from unittest.mock import patch

import pytest

from midealan.cli import MideaCLI
from midealan.const import DeviceType, ProtocolVersion
from midealan.device import MideaDevice
from midealan.devices import ac, x44
from midealan.devices.x44 import MideaX44Device, X44ModelProfile, zkp_3inch01
from midealan.devices.x44.util import DriverFactory
from midealan.message import MessageType
from tests.devices.x44 import (
    AC_REPORT_VIA_90S,
    ZKP_QUERY,
    ZKP_REPORT,
    identity,
    select_device,
)


@pytest.mark.parametrize(
    ("model", "subtype", "sn8"),
    [
        ("404M0001", 0, None),
        ("404M0001", 747, "404M0001"),
        ("404m0001", 747, "00000000"),
        ("Unknown", 0, " 404M0001\x00"),
        ("ZKP-3INCH01", 0, "404M0001"),
    ],
)
def test_screen_identity(model: str, subtype: int, sn8: str | None) -> None:
    """Stored, LAN and cloud identities select the screen without changing metadata."""
    device = select_device(model, subtype, sn8)
    assert isinstance(device, zkp_3inch01.ZKP3Inch01Device)
    assert x44.resolve_profile(model, subtype, sn8) is device.profile
    assert device.profile.name == "ZKP-3INCH01"
    assert device.model == model
    assert device.subtype == subtype
    assert set(device.attributes) == set(zkp_3inch01.DeviceAttributes)
    assert device.build_query()[0].serialize() == ZKP_QUERY


def test_independent_model_routes() -> None:
    """Only the registered AC bridge routes out of the x44 family."""
    screen = select_device("404M0001")
    panel = select_device("115P0303")
    assert type(screen) is zkp_3inch01.ZKP3Inch01Device
    assert type(panel) is ac.MideaAppliance
    assert x44.resolve_driver("404M0001") is zkp_3inch01.ZKP3Inch01Device
    assert x44.resolve_driver("115P0303") is ac.MideaAppliance
    assert screen.device_type == DeviceType.X44
    assert panel.device_type == DeviceType.AC
    assert screen.process_message(AC_REPORT_VIA_90S) == {}
    assert screen.process_message(ZKP_REPORT)["voice_volume"] == 50
    assert "voice_volume" not in panel.attributes


def test_driver_return_type_is_resolvable() -> None:
    """Runtime introspection exposes the same factory contract as type checkers."""
    assert get_type_hints(x44.resolve_driver)["return"] is DriverFactory


@pytest.mark.parametrize(
    ("model", "sn8", "device_id"),
    [
        ("TEST0001", None, 1),
        ("", "00000000", 1),
        ("404M0001", "TEST0001", 1),
        ("404M0001", "115P0303", 1),
        ("TEST0001", "404M0001", 1),
        ("ZKP-3INCH01", None, 1),
        ("KJR-90S", None, 1),
        ("0000", None, 1),
        ("0000", "TEST0001", 0),
        ("TEST0001", None, 0),
        ("404M0001", "115P0303", 0),
    ],
)
def test_unregistered_model_is_inert(
    model: str,
    sn8: str | None,
    device_id: int,
) -> None:
    """The object remains usable without enabling a model's commands or poller."""
    device = select_device(model, sn8=sn8, device_id=device_id)
    assert isinstance(device, MideaX44Device)
    assert device.profile is None
    assert x44.resolve_profile(model, sn8=sn8) is None
    assert device.attributes == {}
    assert device.build_query() == []
    assert device.process_message(ZKP_REPORT) == {}
    with (
        patch.object(MideaDevice, "open") as start,
        patch.object(MideaDevice, "connect") as connect,
        patch.object(MideaDevice, "refresh_status") as refresh,
        patch.object(MideaDevice, "build_send") as send,
    ):
        device.open()
        assert not device.connect()
        device.refresh_status(check_protocol=True)
        device.set_attribute("brightness", 50)
        device.send_command(MessageType.set, bytearray())
        device.close()
    start.assert_not_called()
    connect.assert_not_called()
    refresh.assert_not_called()
    send.assert_not_called()


class _TestSensor(MideaX44Device):
    """Minimal third driver registered by subtype in the routing tests."""

    profile = X44ModelProfile(name="Test sensor", attributes=("level",))

    @override
    def process_message(self, msg: bytes) -> dict[str, int]:
        self._attributes["level"] = msg[0]
        return {"level": msg[0]}


def test_new_driver_per_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """A newly registered model owns a separate attribute store per device."""
    monkeypatch.setitem(x44._MODEL_DRIVERS, ("TEST0001", 1), _TestSensor)
    first = select_device("TEST0001", 1, device_id=1)
    second = select_device("TEST0001", 1, device_id=2)
    assert isinstance(first, _TestSensor)
    assert isinstance(second, _TestSensor)
    assert first.process_message(bytes([7])) == {"level": 7}
    assert second.attributes == {"level": None}
    assert second.process_message(bytes([3])) == {"level": 3}
    assert first.attributes == {"level": 7}


def test_subtype_driver_overrides_model_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact subtype overrides only that subtype of an already registered model."""
    monkeypatch.setitem(x44._MODEL_DRIVERS, ("TEST0001", 1), _TestSensor)
    monkeypatch.setitem(x44._MODEL_DRIVERS, ("404M0001", 7), _TestSensor)
    assert x44.resolve_profile("TEST0001", 2) is None
    assert isinstance(select_device("404M0001", 7), _TestSensor)
    assert x44.resolve_profile("404M0001", 7) is _TestSensor.profile
    screen = select_device("404M0001", 747)
    assert isinstance(screen.build_query()[0], zkp_3inch01.message.MessageQuery)
    assert (
        screen.process_message(ZKP_REPORT)[zkp_3inch01.DeviceAttributes.voice_volume]
        == 50
    )


def test_read_only_driver() -> None:
    """A directly constructed model can inherit read-only behavior."""
    sensor = _TestSensor(customize="", **identity("TEST0001"))
    assert sensor.build_query() == []
    with patch.object(sensor, "build_send") as send:
        sensor.set_attribute("level", 4)
    send.assert_not_called()


@pytest.mark.asyncio
async def test_cli_discovery_with_an_unknown_model() -> None:
    """Discovery only connects to the registered model."""
    cli = MideaCLI()
    cli.namespace = Namespace(host=None)
    row = {
        "type": DeviceType.X44,
        "protocol": ProtocolVersion.V2,
        "ip_address": "192.0.2.1",
        "port": 6444,
        "mac": None,
        "sn": "",
        "support": "supported",
    }
    devices = {
        1: {**row, "device_id": 1, "model": "TEST0001"},
        2: {**row, "device_id": 2, "model": "404M0001"},
    }
    with (
        patch("midealan.cli.discover", return_value=devices),
        patch.object(MideaDevice, "connect", return_value=True) as connect,
        patch.object(MideaDevice, "refresh_status") as refresh,
    ):
        assert [device.model for device in await cli.discover()] == ["404M0001"]
    connect.assert_called_once()
    refresh.assert_called_once()


@pytest.mark.parametrize("report", [ZKP_REPORT, AC_REPORT_VIA_90S])
def test_cli_decodes_only_screen_captures(
    report: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The model-less CLI decodes a known screen report and ignores other layouts."""
    expected = select_device("404M0001").process_message(report)
    cli = MideaCLI()
    cli.namespace = Namespace(message=report)
    with caplog.at_level("INFO"):
        cli.message()
    assert caplog.messages == [f"Parsed message: {expected}"]


def test_decoding_a_capture_keeps_the_device_unconfigured() -> None:
    """Reading a bare frame leaves the model, state and poller untouched."""
    device = select_device("0000", device_id=0)
    assert device.process_message(ZKP_REPORT)["voice_volume"] == 50
    assert device.model == "0000"
    assert device.attributes == {}
    assert device.build_query() == []
    assert not device.connect()

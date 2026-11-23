"""Identities and captured frames used to test the 0x44 family."""

import json
from pathlib import Path

from midealan.const import DeviceType, ProtocolVersion
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.devices import device_selector
from midealan.message import MessageBase

_captures = json.loads(
    (Path(__file__).resolve().parents[2] / "responses" / "x44-panels.json").read_text(
        encoding="utf-8",
    ),
)
ZKP_QUERY = bytes.fromhex(_captures["404M0001"]["query"])
ZKP_REPORT = bytes.fromhex(_captures["404M0001"]["report"])
AC_REPORT_VIA_90S = bytes.fromhex(_captures["115P0303"]["synthetic_ac_report"])


def identity(model: str, subtype: int = 0) -> MideaDeviceInitKwargs:
    """Build the standard constructor arguments for an offline panel."""
    return {
        "name": "panel",
        "device_id": 1,
        "ip_address": "192.0.2.1",
        "port": 6444,
        "token": "",
        "key": "",
        "device_protocol": ProtocolVersion.V3,
        "model": model,
        "subtype": subtype,
    }


def select_device(
    model: str,
    subtype: int = 0,
    sn8: str | None = None,
    *,
    device_id: int = 1,
) -> MideaDevice:
    """Create the driver through the public type selector."""
    kwargs = identity(model, subtype)
    kwargs["sn8"] = sn8
    kwargs["device_id"] = device_id
    return device_selector(device_type=DeviceType.X44, customize="", **kwargs)


def frame(message_type: int, body: bytes) -> bytearray:
    """Wrap a test payload in an appliance frame."""
    data = bytearray([0xAA, 0, 0x44, 0, 0, 0, 0, 0, 0, message_type]) + body
    data[1] = len(data)
    data.append(MessageBase.checksum(data[1:]))
    return data

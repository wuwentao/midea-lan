"""Select a model driver for appliances advertising type 0x44."""

import re
from typing import Any, override

from midealan.message import MessageRequest

from . import kjr_90s, message, zkp_3inch01
from .util import DelegatedModel, DriverFactory, MideaX44Device, X44ModelProfile

# An exact subtype takes precedence over the entry for the whole internal model.
type _Model = type[MideaX44Device] | DelegatedModel
_MODEL_DRIVERS: dict[tuple[str, int | None], _Model] = {
    ("404M0001", None): zkp_3inch01.ZKP3Inch01Device,
    ("115P0303", None): kjr_90s.MODEL,
}

MideaAppliance = MideaX44Device


class UnregisteredX44Device(MideaX44Device):
    """Keep discovery metadata available without operating an unknown device."""

    @override
    def connect(self, check_protocol: bool = False) -> bool:
        """Tell discovery clients there is no usable connection for this model."""
        return False

    @override
    def open(self) -> None:
        """Leave the poller stopped."""

    @override
    def refresh_status(self, check_protocol: bool = False) -> None:
        """Skip the transport's initial appliance query as well as periodic polls."""

    @override
    def process_message(self, msg: bytes) -> dict[str, int]:
        """Decode a bare capture only when there is no target device or model."""
        # The CLI uses device ID 0 and model "0000" for an offline capture.
        if (
            self.device_id == 0
            and self.model in {"", "0000", "00000000"}
            and self.sn8 is None
        ):
            return zkp_3inch01.message.decode_capture(msg)
        return {}

    @override
    def build_send(self, cmd: MessageRequest, query: bool = False) -> None:
        """Ignore raw commands from callers as well as attribute writes."""


def _match_model(
    model: str | None,
    subtype: int | None,
    sn8: str | None,
) -> _Model:
    """Match LAN model or cloud SN8, rejecting conflicting internal codes."""
    codes = set()
    for value in (model, sn8):
        code = (value or "").strip(" \t\r\n\x00").upper()
        if code != "00000000" and re.fullmatch(r"[A-Z0-9]{8}", code):
            codes.add(code)
    if len(codes) != 1:
        return UnregisteredX44Device
    code = codes.pop()
    return _MODEL_DRIVERS.get((code, subtype)) or _MODEL_DRIVERS.get(
        (code, None),
        UnregisteredX44Device,
    )


def resolve_driver(
    model: str | None,
    subtype: int | None = None,
    sn8: str | None = None,
) -> DriverFactory:
    """Return the driver that owns this device's connection, messages and state."""
    match = _match_model(model, subtype, sn8)
    return match.driver if isinstance(match, DelegatedModel) else match


def resolve_profile(
    model: str | None,
    subtype: int | None = None,
    sn8: str | None = None,
) -> X44ModelProfile | DelegatedModel | None:
    """Look up native capabilities or the delegated device type before connecting."""
    match = _match_model(model, subtype, sn8)
    return match if isinstance(match, DelegatedModel) else match.profile


# Existing Home Assistant entities import the screen enum from the family package.
DeviceAttributes = zkp_3inch01.DeviceAttributes

__all__ = [
    "DelegatedModel",
    "DeviceAttributes",
    "MideaAppliance",
    "MideaX44Device",
    "X44ModelProfile",
    "kjr_90s",
    "resolve_driver",
    "resolve_profile",
    "zkp_3inch01",
]
__all__ += [name for name in vars(message) if not name.startswith("_")]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Preserve the flat message imports used by older x44 clients."""
    if name.startswith("_"):
        raise AttributeError(name)
    return getattr(message, name)

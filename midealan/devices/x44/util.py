"""Shared device construction and profiles for the 0x44 family."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol, Unpack, cast, override

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs

if TYPE_CHECKING:
    from midealan.message import MessageRequest

_LOGGER = logging.getLogger(__name__)


class DriverFactory(Protocol):
    """Constructor shared by LAN appliance drivers, including delegated types."""

    def __call__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> MideaDevice:
        """Construct a device with its discovery identity and user options."""


@dataclass(frozen=True)
class X44ModelProfile:
    """Capabilities declared by a native x44 model."""

    name: str
    attributes: tuple[str, ...]
    writable: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DelegatedModel:
    """A recognized model whose capabilities and protocol belong to another driver."""

    name: str
    device_type: DeviceType
    driver: DriverFactory


class _X44DeviceFactory(type):
    """Keep the class constructor usable when the selected driver is outside x44."""

    def __call__(
        cls,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> MideaDevice:
        """Construct the selected driver with its own initializer exactly once."""
        if cls is MideaX44Device:
            # The family router imports this base while registering its models.
            from . import resolve_driver  # noqa: PLC0415

            driver = resolve_driver(
                kwargs["model"],
                kwargs["subtype"],
                kwargs.get("sn8"),
            )
            return driver(customize=customize, **kwargs)
        return cast("MideaDevice", super().__call__(customize=customize, **kwargs))


class MideaX44Device(MideaDevice, metaclass=_X44DeviceFactory):
    """Common entry point and LAN transport for native type 0x44 drivers."""

    profile: ClassVar[X44ModelProfile | None] = None

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize one transport and attribute store for the selected driver."""
        super().__init__(
            device_type=DeviceType.X44,
            attributes=dict.fromkeys(self.profile.attributes) if self.profile else {},
            **kwargs,
        )
        if self.profile is None and self.device_id:
            _LOGGER.info(
                "No 0x44 driver for model %r, subtype %s, SN8 %r",
                self.model,
                self.subtype,
                self.sn8,
            )

    @override
    def build_query(self) -> list[MessageRequest]:
        """Return no periodic queries unless the driver defines them."""
        return []

    @override
    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Read-only by default. Writable drivers implement their own controls."""

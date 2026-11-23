"""Device driver for the ZKP-3INCH01 smart screen (404M0001)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, override

from midealan.devices.x44.util import MideaX44Device, X44ModelProfile

from .message import (
    SCREEN_WRITABLE,
    DeviceAttributes,
    MessageQuery,
    MessageSetScreen,
    decode_report,
)

if TYPE_CHECKING:
    from midealan.message import MessageRequest


class ZKP3Inch01Device(MideaX44Device):
    """Screen settings for the ZKP-3INCH01 panel."""

    profile: ClassVar[X44ModelProfile] = X44ModelProfile(
        name="ZKP-3INCH01",
        attributes=tuple(DeviceAttributes),
        writable=SCREEN_WRITABLE,
    )

    @override
    def build_query(self) -> list[MessageRequest]:
        """Query the screen-status record."""
        return [MessageQuery(self._message_protocol_version)]

    @override
    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Update the screen fields present in this report."""
        status = {
            name: value
            for name, value in decode_report(msg).items()
            if name in self._attributes
        }
        self._attributes.update(status)
        return status

    @override
    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Send a control for one writable screen field."""
        if attr in self.profile.writable:
            self.build_send(
                MessageSetScreen.for_attribute(
                    self._message_protocol_version,
                    attr,
                    value,
                ),
            )

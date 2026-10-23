"""Toshiba 0x51 device messages."""

from midealan.const import DeviceType
from midealan.message import ToshibaMessageRequest


class MessageQueryBase(ToshibaMessageRequest):
    """Toshiba 0x51 base clock and sensor query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x00."""
        super().__init__(DeviceType.X51, protocol_version, b"\x00")


class MessageQueryReserved(ToshibaMessageRequest):
    """Toshiba 0x51 reserved function query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x01."""
        super().__init__(DeviceType.X51, protocol_version, b"\x01")


class MessageQuerySchedule(ToshibaMessageRequest):
    """Toshiba 0x51 schedule and mode query."""

    def __init__(self, protocol_version: int) -> None:
        """Query function type 0x02."""
        super().__init__(DeviceType.X51, protocol_version, b"\x02")

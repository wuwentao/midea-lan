"""Midea lan x70 device (seasoning / spice dispenser, 调味机)."""

import json
import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    MAX_BOXES,
    SEASONING_NUMBER_HIGH,
    SEASONING_NUMBER_LOW,
    SEASONING_VALUE_HIGH,
    SEASONING_VALUE_LOW,
    SUB_CMD_OUTPUT,
    SUB_CMD_SET,
    MessageQuery,
    MessageSetDispense,
    MessageSetType,
    MessageX70Response,
)

_LOGGER = logging.getLogger(__name__)


def _build_attribute_names() -> list[str]:
    """Build the flat read-only status attribute list (sub_cmd + 8 box records)."""
    names = ["sub_cmd", "control_result"]
    time_fields = (
        "add_time_year",
        "add_time_month",
        "add_time_day",
        "add_time_hour",
        "add_time_minute",
        "add_time_second",
        "clean_time_year",
        "clean_time_month",
        "clean_time_day",
        "clean_time_hour",
        "clean_time_minute",
        "clean_time_second",
    )
    for box in range(1, MAX_BOXES + 1):
        names.append(f"box{box}_type")
        names.append(f"box{box}_status")
        names.extend(f"box{box}_{field}" for field in time_fields)
    return names


ALL_ATTRIBUTES = _build_attribute_names()

# 0x70 reports up to 8 box records with 14 fields each; build the StrEnum from
# the decoder's attribute list via the functional API so the two stay in sync.
DeviceAttributes = StrEnum(  # type: ignore[misc]
    "DeviceAttributes",
    {name: name for name in ALL_ATTRIBUTES},
)


class MideaX70Device(MideaDevice):
    """Midea x70 device (seasoning / spice dispenser)."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea x70 device."""
        super().__init__(
            device_type=DeviceType.X70,
            **kwargs,
            attributes=dict.fromkeys(ALL_ATTRIBUTES),
        )
        self.set_customize(customize)

    def build_query(self) -> list[MessageQuery]:
        """Midea x70 device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea x70 device process message."""
        message = MessageX70Response(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                self._attributes[status] = value
                new_status[str(status)] = value
        return new_status

    def _build_structured_message(
        self,
        sub_cmd: int,
        number: int,
        values: list[int],
    ) -> MessageSetDispense:
        """Build a dispense / set-type control message.

        ``values`` holds the per-slot weight (dispense) or type (set) for slots
        1..number; values are range-checked against the Lua checkBoundary bounds.
        """
        if not SEASONING_NUMBER_LOW <= number <= SEASONING_NUMBER_HIGH:
            msg = (
                f"[x70] seasoning number must be in "
                f"[{SEASONING_NUMBER_LOW}, {SEASONING_NUMBER_HIGH}]"
            )
            raise ValueOutOfRange(msg)
        if len(values) < number:
            msg = f"[x70] expected at least {number} seasoning values"
            raise ValueWrongType(msg)
        for value in values[:number]:
            if isinstance(value, bool) or not isinstance(value, int):
                msg = "[x70] seasoning values must be integers"
                raise ValueWrongType(msg)
            if not SEASONING_VALUE_LOW <= value <= SEASONING_VALUE_HIGH:
                msg = (
                    f"[x70] seasoning value must be in "
                    f"[{SEASONING_VALUE_LOW}, {SEASONING_VALUE_HIGH}]"
                )
                raise ValueOutOfRange(msg)
        message = (
            MessageSetDispense(self._message_protocol_version)
            if sub_cmd == SUB_CMD_OUTPUT
            else MessageSetType(self._message_protocol_version)
        )
        message.number = number
        message.values = [*values[:number], *([0] * (MAX_BOXES - number))]
        return message

    def dispense(self, number: int, weights: list[int]) -> None:
        """Dispense ``number`` seasonings using the per-slot ``weights``."""
        message = self._build_structured_message(SUB_CMD_OUTPUT, number, weights)
        self.build_send(message)

    def set_box_types(self, number: int, types: list[int]) -> None:
        """Assign box ``types`` for the first ``number`` slots."""
        message = self._build_structured_message(SUB_CMD_SET, number, types)
        self.build_send(message)

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea x70 device set attribute.

        Every exposed attribute is a read-only status field; the seasoning
        dispenser's only controls are the structured ``dispense`` /
        ``set_box_types`` commands, so single-attribute writes are ignored.
        """

    def set_customize(self, customize: str) -> None:
        """Midea x70 device set customize (JSON, same style as other appliances)."""
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "refresh_interval" in params:
                    interval = params.get("refresh_interval")
                    if isinstance(interval, int | float):
                        self.set_refresh_interval(int(interval))
                    else:
                        _LOGGER.error(
                            "[%s] Invalid type for refresh_interval: %s",
                            self.device_id,
                            interval,
                        )
            except Exception:
                _LOGGER.exception("[%s] Set customize error", self.device_id)
        self.update_all({"refresh_interval": self._refresh_interval})


# Re-exported control classes for callers that need structured commands.
__all__ = [
    "DeviceAttributes",
    "MessageQuery",
    "MessageSetDispense",
    "MessageSetType",
    "MideaAppliance",
    "MideaX70Device",
]


class MideaAppliance(MideaX70Device):
    """Midea x70 appliance."""

"""Midea lan x9b device.

0x9B is a microwave + steam + convection combi oven (微蒸烤一体机). It reports a
rich status record (cooking mode, timers, oven/steam/probe temperatures, water
tank state, door/lock and maintenance flags) and accepts several command
groups: whole-appliance state controls, live parameter adjustment while a
program runs, structured start-cooking recipes and a system-time set.

The attribute list is derived from the message decoder (see
:data:`midealan.devices.x9b.message.ALL_ATTRIBUTES`) so it can never drift from
what the protocol actually reports.
"""

import logging
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import (
    ALL_ATTRIBUTES,
    PARAM_INT_ATTRIBUTES,
    STATE_INT_ATTRIBUTES,
    STATE_STR_ATTRIBUTES,
    MessageQuery,
    MessageSetParam,
    MessageSetState,
    MessageX9BResponse,
)

_LOGGER = logging.getLogger(__name__)

# Whole-appliance controls that map to a simple ``set_attribute`` call.
ATTR_POWER = "power"
ATTR_WORK_STATUS = "work_status"
ATTR_DOOR = "door"

# Build the StrEnum from the decoder's attribute list so the two stay in
# lock-step, matching the pattern used by the 0x9C device.
DeviceAttributes = StrEnum(  # type: ignore[misc]
    "DeviceAttributes",
    {name: name for name in ALL_ATTRIBUTES},
)


class MideaX9BDevice(MideaDevice):
    """Midea 0x9B microwave-steam-convection combi oven."""

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea 0x9B device."""
        super().__init__(
            device_type=DeviceType.X9B,
            **kwargs,
            attributes=dict.fromkeys(ALL_ATTRIBUTES),
        )

    def build_query(self) -> list[MessageQuery]:
        """Midea 0x9B device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea 0x9B device process message."""
        message = MessageX9BResponse(msg)
        self._message_protocol_version = message.protocol_version
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for name, value in message.attributes.items():
            if name not in self._attributes:
                continue
            self._attributes[name] = value
            new_status[name] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea 0x9B device set attribute.

        The single-value controls (power, child lock, oven light, door,
        hot-wind, screen brightness, volume and work status) plus the live
        parameter adjustments are exposed as plain ``set_attribute`` writes.
        Structured start-cooking recipes take multiple coordinated fields and
        are issued through :class:`~midealan.devices.x9b.message.MessageSetCooking`.
        """
        message: MessageSetState | MessageSetParam | None = self._build_state_message(
            attr,
            value,
        )
        if message is None:
            message = self._build_param_message(attr, value)
        if message is not None:
            self.build_send(message)

    def _build_state_message(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageSetState | None:
        """Build a state-control message for ``attr``, if it is one."""
        if attr == ATTR_POWER:
            message = MessageSetState(self._message_protocol_version)
            message.power = bool(value)
            return message
        if attr == ATTR_WORK_STATUS:
            message = MessageSetState(self._message_protocol_version)
            message.work_status = str(value)
            return message
        if attr == ATTR_DOOR:
            message = MessageSetState(self._message_protocol_version)
            message.door = str(value)
            return message
        if attr in STATE_STR_ATTRIBUTES:
            if not isinstance(value, bool):
                raise ValueWrongType(f"[x9b] {attr} expects a bool")
            message = MessageSetState(self._message_protocol_version)
            setattr(message, attr, value)
            return message
        if attr in STATE_INT_ATTRIBUTES:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueWrongType(f"[x9b] {attr} expects a number")
            message = MessageSetState(self._message_protocol_version)
            setattr(message, attr, int(value))
            return message
        return None

    def _build_param_message(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageSetParam | None:
        """Build a live-parameter message for ``attr``, if it is one."""
        if attr == "fire_power_set":
            message = MessageSetParam(self._message_protocol_version)
            message.fire_power_set = str(value)
            return message
        if attr in PARAM_INT_ATTRIBUTES:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueWrongType(f"[x9b] {attr} expects a number")
            message = MessageSetParam(self._message_protocol_version)
            setattr(message, attr, int(value))
            return message
        return None


# Re-exported control classes for callers that need structured commands.
__all__ = [
    "DeviceAttributes",
    "MideaAppliance",
    "MideaX9BDevice",
]


class MideaAppliance(MideaX9BDevice):
    """Midea 0x9B appliance."""

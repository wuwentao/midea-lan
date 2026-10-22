"""Midea lan 0x9C device.

0x9C is an integrated kitchen appliance (集成灶) that bundles several independent
sub-appliances behind one LAN connection: a range hood (``b6_*``), a gas hob with
left/right burners (``b7_left_*`` / ``b7_right_*``), upper/lower steam cabinets
(``b3_upstair_*`` / ``b3_downstair_*``), upper/lower steam-bake boxes (``b2_*``),
induction soup cookers (``e7_*``), warming plates (``sp_*``), an air conditioner
(``ac_*``) and a built-in oven (``bf_*``), plus a whole-appliance summary
(``total_*``).

Every module keeps its own state, so attributes are module-prefixed and controls
are routed to the matching module. The attribute list is derived from the message
decoder (see :data:`midealan.devices.x9c.message.ALL_ATTRIBUTES`) so it can never
drift from what the protocol actually reports.
"""

import logging
import math
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType

from .message import (
    ALL_ATTRIBUTES,
    VALUE_OFF,
    VALUE_ON,
    MessageQuery,
    MessageSetAc,
    MessageSetB2,
    MessageSetB3,
    MessageSetB6,
    MessageSetB7,
    MessageSetE7,
    MessageSetSp,
    MessageSetTotal,
    MessageX9CResponse,
)

_LOGGER = logging.getLogger(__name__)

# Attribute names that accept control commands, grouped by target module. Every
# other attribute in ``ALL_ATTRIBUTES`` is read-only status.
ATTR_TOTAL_POWER = "total_power"
ATTR_TOTAL_LOCK = "total_lock"
ATTR_AI_VOICE_MICROPHONE = "ai_voice_microphone"
ATTR_AI_VOICE_VOLUME = "ai_voice_volume"

# Accepted string states for the on/off style whole-appliance controls.
_ON_OFF_STATES = (VALUE_ON, VALUE_OFF)
# ai_voice_volume is encoded as a single byte.
_MAX_BYTE_VALUE = 0xFF

# 0x9C exposes ~370 attributes; build the StrEnum from the decoder's attribute
# list via the functional API so the two stay in lock-step.
DeviceAttributes = StrEnum(  # type: ignore[misc]
    "DeviceAttributes",
    {name: name for name in ALL_ATTRIBUTES},
)


class MideaX9CDevice(MideaDevice):
    """Midea 0x9C integrated kitchen appliance."""

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea 0x9C device."""
        super().__init__(
            device_type=DeviceType.X9C,
            **kwargs,
            attributes=dict.fromkeys(ALL_ATTRIBUTES),
        )

    def build_query(self) -> list[MessageQuery]:
        """Midea 0x9C device build query."""
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea 0x9C device process message."""
        message = MessageX9CResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status: dict[str, Any] = {}
        for name, value in message.attributes.items():
            if name not in self._attributes:
                continue
            self._attributes[name] = value
            new_status[name] = value
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea 0x9C device set attribute.

        Only the whole-appliance controls (power, child lock and the AI voice
        settings) are exposed as simple set operations. The individual cooking
        modules take structured multi-field commands that are issued through the
        dedicated ``MessageSet*`` classes rather than single-attribute writes.
        """
        message = self._build_total_message(attr, value)
        if message is not None:
            self.build_send(message)

    def _build_total_message(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageSetTotal | None:
        """Build a whole-appliance control message for ``attr``, if supported."""
        if attr == ATTR_TOTAL_POWER:
            if value not in _ON_OFF_STATES:
                raise ValueWrongType(
                    f"[x9c] total_power expects one of {_ON_OFF_STATES}",
                )
            message = MessageSetTotal(self._message_protocol_version)
            message.power = value
            return message
        if attr == ATTR_TOTAL_LOCK:
            if not isinstance(value, bool):
                raise ValueWrongType("[x9c] total_lock expects a bool")
            message = MessageSetTotal(self._message_protocol_version)
            message.lock = value
            return message
        if attr == ATTR_AI_VOICE_MICROPHONE:
            if value not in _ON_OFF_STATES:
                raise ValueWrongType(
                    f"[x9c] ai_voice_microphone expects one of {_ON_OFF_STATES}",
                )
            message = MessageSetTotal(self._message_protocol_version)
            message.ai_voice_microphone = value
            return message
        if attr == ATTR_AI_VOICE_VOLUME:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueWrongType("[x9c] ai_voice_volume expects a number")
            if not math.isfinite(value) or not 0 <= value <= _MAX_BYTE_VALUE:
                raise ValueWrongType(
                    f"[x9c] ai_voice_volume must be within 0-{_MAX_BYTE_VALUE}",
                )
            message = MessageSetTotal(self._message_protocol_version)
            message.ai_voice_volume = int(value)
            return message
        return None


# Re-exported control classes for callers that need structured module commands.
__all__ = [
    "ATTR_AI_VOICE_MICROPHONE",
    "ATTR_AI_VOICE_VOLUME",
    "ATTR_TOTAL_LOCK",
    "ATTR_TOTAL_POWER",
    "DeviceAttributes",
    "MessageQuery",
    "MessageSetAc",
    "MessageSetB2",
    "MessageSetB3",
    "MessageSetB6",
    "MessageSetB7",
    "MessageSetE7",
    "MessageSetSp",
    "MessageSetTotal",
    "MideaAppliance",
    "MideaX9CDevice",
]


class MideaAppliance(MideaX9CDevice):
    """Midea 0x9C appliance."""

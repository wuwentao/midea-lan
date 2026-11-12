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
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueOutOfRange, ValueWrongType

from .message import (
    ALL_ATTRIBUTES,
    BYTE_MIN,
    FIRE_POWER_MAP,
    PARAM_INT_ATTRIBUTES,
    PARAM_U16_ATTRIBUTES,
    SETTABLE_BYTE_MAX,
    STATE_INT_ATTRIBUTES,
    STATE_STR_ATTRIBUTES,
    U16_MAX,
    U16_MIN,
    WORK_STATUS_WRITE,
    MessageQuery,
    MessageQueryCameraOta,
    MessageSetParam,
    MessageSetState,
    MessageX9BResponse,
    X9BProfile,
)

_LOGGER = logging.getLogger(__name__)

# Whole-appliance controls that map to a simple ``set_attribute`` call.
ATTR_POWER = "power"
ATTR_WORK_STATUS = "work_status"
ATTR_DOOR = "door"
ATTR_FIRE_POWER = "fire_power"


@dataclass(frozen=True, slots=True)
class X9BProfileRule:
    """Map appliance identities to one shared wire-format profile.

    A rule represents byte-layout compatibility, not a single sellable model.
    Add a model/SN8/subtype to an existing rule when its query and response
    bytes have the same meanings. Add a new :class:`X9BProfile`, decoder path,
    and rule only when offsets or overlapping values mean something different.

    Rules are evaluated in order and the first matching selector wins. Model
    and SN8 are stronger identifiers and should be preferred. A subtype may be
    shared by unrelated products, so add subtype-only selectors only after a
    captured response proves that every device using it has this layout.
    """

    profile: X9BProfile
    sn8s: frozenset[str] = frozenset()
    models: frozenset[str] = frozenset()
    subtypes: frozenset[int] = frozenset()

    def match(self, *, sn8: str | None, model: str, subtype: int) -> str | None:
        """Return the matching selector description, or ``None``."""
        normalized_sn8 = sn8.upper() if sn8 else None
        normalized_model = model.upper()
        if normalized_sn8 in self.sn8s:
            return f"sn8={normalized_sn8}"
        if normalized_model in self.models:
            return f"model={normalized_model}"
        if subtype in self.subtypes:
            return f"subtype={subtype}"
        return None


# Keep specific/new layouts before broad/older ones. Multiple identities and
# verified subtypes can intentionally share one rule/profile; this is the only
# table that needs changing when a newly reported appliance reuses known bytes.
X9B_PROFILE_RULES: tuple[X9BProfileRule, ...] = (
    X9BProfileRule(
        profile=X9BProfile.CAMERA,
        sn8s=frozenset({"700ZG249"}),
        models=frozenset({"700ZG249", "S50E5"}),
    ),
    X9BProfileRule(
        profile=X9BProfile.EXTENDED,
        sn8s=frozenset({"70100277"}),
        models=frozenset({"70100277"}),
    ),
    X9BProfileRule(
        profile=X9BProfile.LEGACY,
        sn8s=frozenset({"0BS5053W"}),
        models=frozenset({"0BS5053W"}),
    ),
)

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
        self._profile, reason = self._select_profile()
        _LOGGER.debug(
            "[%s] Selected x9b profile %s (%s)",
            self.device_id,
            self._profile,
            reason,
        )

    @property
    def profile(self) -> X9BProfile:
        """Return the selected 0x9B wire-format profile."""
        return self._profile

    def _select_profile(self) -> tuple[X9BProfile, str]:
        """Select the first identity rule that matches this appliance."""
        for rule in X9B_PROFILE_RULES:
            reason = rule.match(sn8=self.sn8, model=self.model, subtype=self.subtype)
            if reason is not None:
                return rule.profile, reason
        return X9BProfile.UNKNOWN, "no verified identity rule"

    def build_query(self) -> list[MessageQuery | MessageQueryCameraOta]:
        """Build status queries, including a safe camera-profile probe.

        Known legacy/extended identities only receive their common status
        query. Camera identities receive the additional read-only 0x65 query.
        Unknown identities receive both during protocol probing: a valid 0x65
        response promotes them to the camera profile, while a silent query is
        recorded as unsupported without preventing the common status query
        from succeeding. This makes future compatible subtypes discoverable
        before they are added to :data:`X9B_PROFILE_RULES`.
        """
        queries: list[MessageQuery | MessageQueryCameraOta] = [
            MessageQuery(self._message_protocol_version),
        ]
        if self._profile in (X9BProfile.UNKNOWN, X9BProfile.CAMERA):
            queries.append(MessageQueryCameraOta(self._message_protocol_version))
        return queries

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea 0x9B device process message."""
        message = MessageX9BResponse(msg, profile=self._profile)
        if message.profile != self._profile:
            old_profile = self._profile
            self._profile = message.profile
            _LOGGER.info(
                "[%s] Promoted x9b profile from %s to %s after distinctive response",
                self.device_id,
                old_profile,
                self._profile,
            )
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
        if self._profile == X9BProfile.CAMERA:
            # The VALUE_VERSION=4 Lua defines controls, but issue #290 only
            # contains query/heartbeat traffic. Keep this profile read-only
            # until hardware feedback verifies command offsets and semantics.
            _LOGGER.warning(
                "[%s] Ignoring unverified x9b camera-profile control %s",
                self.device_id,
                attr,
            )
            return
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
            # screen_luminance and volume are encoded as a single byte whose
            # 0xFF sentinel means "leave unchanged", so 0xFF is not settable.
            coerced = self._coerce_int(attr, value, BYTE_MIN, SETTABLE_BYTE_MAX)
            message = MessageSetState(self._message_protocol_version)
            setattr(message, attr, coerced)
            return message
        return None

    def _build_param_message(
        self,
        attr: str,
        value: bool | float | str,
    ) -> MessageSetParam | None:
        """Build a live-parameter message for ``attr``, if it is one."""
        if attr == ATTR_FIRE_POWER:
            message = MessageSetParam(self._message_protocol_version)
            message.fire_power = str(value)
            return message
        if attr in PARAM_INT_ATTRIBUTES:
            if attr in PARAM_U16_ATTRIBUTES:
                coerced = self._coerce_int(attr, value, U16_MIN, U16_MAX)
            else:
                # Byte parameters (steam_quantity, hour/minute/second_set) use
                # the 0xFF "leave unchanged" sentinel, so 0xFF is not settable.
                coerced = self._coerce_int(attr, value, BYTE_MIN, SETTABLE_BYTE_MAX)
            message = MessageSetParam(self._message_protocol_version)
            setattr(message, attr, coerced)
            return message
        return None

    @staticmethod
    def _coerce_int(
        attr: str,
        value: bool | float | str,
        low: int,
        high: int,
    ) -> int:
        """Coerce ``value`` to an int in ``[low, high]`` or raise.

        Raises
        ------
        ValueWrongType
            If ``value`` is not a non-bool number, or is a non-integral float.
        ValueOutOfRange
            If the coerced integer falls outside ``[low, high]``.

        """
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueWrongType(f"[x9b] {attr} expects a number")
        # Reject fractional values rather than silently truncating (42.7 -> 42),
        # which would send a different control value than the caller asked for.
        if isinstance(value, float) and not value.is_integer():
            raise ValueWrongType(f"[x9b] {attr} must be a whole number")
        coerced = int(value)
        if not low <= coerced <= high:
            raise ValueOutOfRange(f"[x9b] {attr} must be in [{low}, {high}]")
        return coerced


# Re-exported control classes and option maps for callers that need structured
# commands or want to build UI option lists (e.g. the Home Assistant integration).
__all__ = [
    "FIRE_POWER_MAP",
    "WORK_STATUS_WRITE",
    "X9B_PROFILE_RULES",
    "DeviceAttributes",
    "MideaAppliance",
    "MideaX9BDevice",
    "X9BProfile",
    "X9BProfileRule",
]


class MideaAppliance(MideaX9BDevice):
    """Midea 0x9B appliance."""

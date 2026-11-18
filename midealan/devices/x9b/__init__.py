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
import time
from enum import StrEnum
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import (
    QUERY_TIMEOUT,
    SOCKET_TIMEOUT,
    MessageResult,
    MideaDevice,
    MideaDeviceInitKwargs,
    ResponseException,
)
from midealan.exceptions import SocketException, ValueOutOfRange, ValueWrongType
from midealan.message import MessageRequest, MessageType

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
    X9BProtocol,
)

_LOGGER = logging.getLogger(__name__)

# Whole-appliance controls that map to a simple ``set_attribute`` call.
ATTR_POWER = "power"
ATTR_WORK_STATUS = "work_status"
ATTR_DOOR = "door"
ATTR_FIRE_POWER = "fire_power"

# Build the StrEnum from the decoder's attribute list so the two stay in
# lock-step, matching the pattern used by the 0x9C device.
DeviceAttributes = StrEnum(  # type: ignore[misc]
    "DeviceAttributes",
    {name: name for name in ALL_ATTRIBUTES},
)

# Fields decoded by the V1/V2 layout but not present in VALUE_VERSION=4. Clear
# them if a response enables the V4 status layout after standard data was seen.
STATUS_V4_UNSUPPORTED_ATTRIBUTES = (
    DeviceAttributes("probe"),
    DeviceAttributes("turntable"),
    DeviceAttributes("probe_temperature"),
    DeviceAttributes("cur_probe_temperature"),
    DeviceAttributes("high_temperature_lock"),
    DeviceAttributes("high_temperature"),
    DeviceAttributes("probe_mode"),
    DeviceAttributes("ramadan"),
    DeviceAttributes("hot_wind"),
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
        self._protocol_flags = dict.fromkeys(X9BProtocol, False)
        self._last_response_protocol: X9BProtocol | None = None
        self._active_probe_protocol: X9BProtocol | None = None
        self._probe_response_protocols: set[X9BProtocol] = set()

    @property
    def protocol_flags(self) -> dict[X9BProtocol, bool]:
        """Return a copy of the response-detected protocol capabilities."""
        return self._protocol_flags.copy()

    def supports_protocol(self, protocol: X9BProtocol) -> bool:
        """Return whether a response has enabled ``protocol``."""
        return self._protocol_flags[protocol]

    def build_query(self) -> list[MessageQuery | MessageQueryCameraOta]:
        """Build probes from response-detected capabilities.

        An unidentified device receives every known query family, with the
        common ``01`` status query first so a silent optional extension cannot
        delay the first usable state. A complete status response stops unknown
        extension probes on later refreshes. Only a positive ``65 00 02``
        response keeps the camera OTA query recurring.

        To add another 0x9B wire protocol, add its query here, recognize its
        response in :class:`MessageX9BResponse`, and add one independent
        :class:`X9BProtocol` flag. No model, SN8 or subtype table is involved.
        """
        queries: list[MessageQuery | MessageQueryCameraOta] = [
            MessageQuery(self._message_protocol_version),
        ]
        status_detected = self.supports_protocol(X9BProtocol.STATUS)
        camera_ota_detected = self.supports_protocol(X9BProtocol.CAMERA_OTA)
        if not status_detected or camera_ota_detected:
            queries.append(MessageQueryCameraOta(self._message_protocol_version))
        return queries

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea 0x9B device process message."""
        message = MessageX9BResponse(
            msg,
            status_v4_protocol=self.supports_protocol(X9BProtocol.STATUS_V4),
        )
        new_status: dict[str, Any] = {}
        self._last_response_protocol = message.response_protocol
        self._probe_response_protocols.update(message.detected_protocols)
        status_v4_was_enabled = self.supports_protocol(X9BProtocol.STATUS_V4)
        for protocol in message.detected_protocols:
            if self.supports_protocol(protocol):
                continue
            self._protocol_flags[protocol] = True
            _LOGGER.debug(
                "[%s] Enabled x9b protocol flag %s from response: %s",
                self.device_id,
                protocol,
                message.protocol_evidence[protocol],
            )
        if not status_v4_was_enabled and self.supports_protocol(
            X9BProtocol.STATUS_V4,
        ):
            for attribute in STATUS_V4_UNSUPPORTED_ATTRIBUTES:
                self._attributes[attribute] = None
                new_status[attribute] = None
        self._message_protocol_version = message.protocol_version
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        for name, value in message.attributes.items():
            if name not in self._attributes:
                continue
            attribute = DeviceAttributes(name)
            self._attributes[attribute] = value
            new_status[attribute] = value
        return new_status

    def build_send(self, cmd: MessageRequest, query: bool = False) -> None:
        """Track probe replies and block unverified V4-layout controls."""
        if (
            self.supports_protocol(X9BProtocol.STATUS_V4)
            and cmd.message_type == MessageType.set
        ):
            _LOGGER.warning(
                "[%s] Ignoring unverified x9b VALUE_VERSION=4 command %s",
                self.device_id,
                cmd.__class__.__name__,
            )
            return
        if query:
            self._last_response_protocol = None
            self._probe_response_protocols.clear()
            if isinstance(cmd, MessageQueryCameraOta):
                self._active_probe_protocol = X9BProtocol.CAMERA_OTA
            elif isinstance(cmd, MessageQuery):
                self._active_probe_protocol = X9BProtocol.STATUS
            else:
                self._active_probe_protocol = None
            _LOGGER.debug(
                "[%s] Sending x9b protocol probe %s, AA frame: %s",
                self.device_id,
                cmd.__class__.__name__,
                cmd.serialize().hex(),
            )
        super().build_send(cmd, query=query)

    def _await_query_reply(self) -> None:
        """Keep reading a checked probe until its matching business reply arrives."""
        expected = self._active_probe_protocol
        if expected is None:
            super()._await_query_reply()
            return
        deadline = time.monotonic() + QUERY_TIMEOUT
        while True:
            if not self._socket:
                _LOGGER.debug("[%s] device socket is none", self.device_id)
                raise SocketException
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self._socket.settimeout(min(remaining, QUERY_TIMEOUT))
            msg = self._socket.recv(512)
            if len(msg) == 0:
                raise ConnectionResetError("Connection closed by peer.")
            result = self.parse_message(msg)
            if expected in self._probe_response_protocols:
                break
            if result in (MessageResult.PADDING, MessageResult.SUCCESS):
                continue
            raise ResponseException
        self._socket.settimeout(SOCKET_TIMEOUT)

    def _is_query_response_valid(self, cmd: MessageRequest) -> bool:
        """Require a matching x9b business response, not only a heartbeat."""
        expected: X9BProtocol | None = None
        if isinstance(cmd, MessageQueryCameraOta):
            expected = X9BProtocol.CAMERA_OTA
        elif isinstance(cmd, MessageQuery):
            expected = X9BProtocol.STATUS
        if expected is None:
            return super()._is_query_response_valid(cmd)
        valid = expected in self._probe_response_protocols
        if not valid:
            _LOGGER.debug(
                "[%s] x9b probe %s had no matching %s business response",
                self.device_id,
                cmd.__class__.__name__,
                expected,
            )
        return valid

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea 0x9B device set attribute.

        The single-value controls (power, child lock, oven light, door,
        hot-wind, screen brightness, volume and work status) plus the live
        parameter adjustments are exposed as plain ``set_attribute`` writes.
        Structured start-cooking recipes take multiple coordinated fields and
        are issued through :class:`~midealan.devices.x9b.message.MessageSetCooking`.
        """
        if self.supports_protocol(X9BProtocol.STATUS_V4):
            # The VALUE_VERSION=4 Lua defines controls, but issue #290 only
            # contains query/heartbeat traffic. Keep this protocol read-only
            # until hardware feedback verifies command offsets and semantics.
            _LOGGER.warning(
                "[%s] Ignoring unverified x9b VALUE_VERSION=4 control %s",
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
    "DeviceAttributes",
    "MideaAppliance",
    "MideaX9BDevice",
    "X9BProtocol",
]


class MideaAppliance(MideaX9BDevice):
    """Midea 0x9B appliance."""

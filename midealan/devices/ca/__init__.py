"""Midea lan CA device."""

import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MessageResult, MideaDevice, MideaDeviceInitKwargs
from midealan.exceptions import ValueWrongType
from midealan.message import (
    ListTypes,
    MessageQuestCustom,
    MessageRequest,
    MessageType,
    ToshibaFrame,
)

from .message import (
    CA_MODE_BODY_LENGTH,
    CA_MODE_MASKS,
    CA_MODE_MAX_AGE_SECONDS,
    CA_MODE_PENDING_TIMEOUT_SECONDS,
    MessageCAResponse,
    MessageQuery,
    build_ca_mode_body,
    decode_toshiba_ca_status,
)

_LOGGER = logging.getLogger(__name__)

SUBTYPE_310A2111 = 56
CA_MODE_MODEL = "310Z999Z"
CA_MODE_SUBTYPE = 56
TOSHIBA_SHIFTED_MODEL = "0000000D"
FLEX_ZONE_MODE_BY_TEMPERATURE: dict[float, str] = {
    6.0: "baby",
    2.0: "treasure",
    0.0: "zero",
}


class DeviceAttributes(StrEnum):
    """Midea CA device attributes."""

    mode = "mode"
    code_mode = "code_mode"
    storage_mode = "storage_mode"
    freezing_mode = "freezing_mode"
    smart_mode = "smart_mode"
    energy_saving_mode = "energy_saving_mode"
    holiday_mode = "holiday_mode"
    moisturize_mode = "moisturize_mode"
    preservation_mode = "preservation_mode"
    acme_freezing_mode = "acme_freezing_mode"
    flood_light = "flood_light"
    freezing_ice_machine_power = "freezing_ice_machine_power"
    energy_consumption = "energy_consumption"
    refrigerator_actual_temp = "refrigerator_actual_temp"
    freezer_actual_temp = "freezer_actual_temp"
    flex_zone_actual_temp = "flex_zone_actual_temp"
    right_flex_zone_actual_temp = "right_flex_zone_actual_temp"
    refrigerator_setting_temp = "refrigerator_setting_temp"
    freezer_setting_temp = "freezer_setting_temp"
    flex_zone_setting_temp = "flex_zone_setting_temp"
    right_flex_zone_setting_temp = "right_flex_zone_setting_temp"
    refrigerator_door_overtime = "refrigerator_door_overtime"
    freezer_door_overtime = "freezer_door_overtime"
    bar_door_overtime = "bar_door_overtime"
    flex_zone_door_overtime = "flex_zone_door_overtime"
    refrigerator_door = "refrigerator_door"
    freezer_door = "freezer_door"
    bar_door = "bar_door"
    flex_zone_door = "flex_zone_door"
    microcrystal_fresh = "microcrystal_fresh"
    electronic_smell = "electronic_smell"
    humidity = "humidity"
    variable_mode = "variable_mode"


@dataclass(frozen=True, slots=True)
class _CAModeStatus:
    """Last accepted Midea CA general status body."""

    body: bytes
    received_at: float
    event_order: int


@dataclass(frozen=True, slots=True)
class _PendingCAModeWrite:
    """Mode bit that must be confirmed by a later real status."""

    mask: int
    enabled: bool
    sent_order: int | None = None
    sent_at: float | None = None


class CAModeWritePendingError(RuntimeError):
    """A CA mode write is waiting for a newer real device status."""


class MideaCADevice(MideaDevice):
    """Midea CA device."""

    TOSHIBA_SUPPORTED = True
    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        (MessageType.query, MessageType.notify1),
    )

    _variable_mode: ClassVar[dict[int, str]] = {
        0x00: "none",
        0x01: "soft_freezing",
        0x02: "zero_fresh",
        0x03: "cold_drink",
        0x04: "fresh_product",
        0x05: "partial_freezing",
        0x06: "dry_zone",
        0x07: "freeze_warm",
        0x08: "partial_freezing",
    }

    _humidity: ClassVar[dict[int, str]] = {
        0x10: "high",
        0x20: "low",
    }

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea CA device."""
        super().__init__(
            device_type=DeviceType.CA,
            **kwargs,
            attributes={
                # Read-only parser values; None means no general status received.
                DeviceAttributes.mode: None,
                DeviceAttributes.code_mode: None,
                DeviceAttributes.storage_mode: None,
                DeviceAttributes.freezing_mode: None,
                DeviceAttributes.smart_mode: None,
                DeviceAttributes.energy_saving_mode: None,
                DeviceAttributes.holiday_mode: None,
                DeviceAttributes.moisturize_mode: None,
                DeviceAttributes.preservation_mode: None,
                DeviceAttributes.acme_freezing_mode: None,
                DeviceAttributes.flood_light: None,
                DeviceAttributes.freezing_ice_machine_power: None,
                DeviceAttributes.energy_consumption: None,
                DeviceAttributes.refrigerator_actual_temp: None,
                DeviceAttributes.freezer_actual_temp: None,
                DeviceAttributes.flex_zone_actual_temp: None,
                DeviceAttributes.right_flex_zone_actual_temp: None,
                DeviceAttributes.refrigerator_setting_temp: None,
                DeviceAttributes.freezer_setting_temp: None,
                DeviceAttributes.flex_zone_setting_temp: None,
                DeviceAttributes.right_flex_zone_setting_temp: None,
                DeviceAttributes.refrigerator_door_overtime: False,
                DeviceAttributes.freezer_door_overtime: False,
                DeviceAttributes.bar_door_overtime: False,
                DeviceAttributes.flex_zone_door_overtime: False,
                DeviceAttributes.refrigerator_door: False,
                DeviceAttributes.freezer_door: False,
                DeviceAttributes.bar_door: False,
                DeviceAttributes.flex_zone_door: False,
                DeviceAttributes.microcrystal_fresh: False,
                DeviceAttributes.electronic_smell: False,
                DeviceAttributes.humidity: None,
                DeviceAttributes.variable_mode: None,
            },
        )
        self._modes = [""]
        self._ca_mode_lock = threading.RLock()
        self._ca_mode_event_lock = threading.Lock()
        self._ca_mode_event_order = 0
        self._ca_mode_received_event_order: int | None = None
        self._ca_mode_received_at: float | None = None
        self._ca_mode_status: _CAModeStatus | None = None
        self._ca_mode_pending: _PendingCAModeWrite | None = None

    def build_query(self) -> list[MessageRequest]:
        """Midea CA device build query."""
        if self.toshiba_protocol:
            return self.build_toshiba_query()
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea CA device process message."""
        status = self.process_toshiba_message(msg)
        if status is not None:
            return status
        with self._ca_mode_lock:
            event_order = self._ca_mode_received_event_order
            received_at = self._ca_mode_received_at
        if event_order is None:
            event_order = self._next_ca_mode_event_order()
        if received_at is None:
            received_at = time.monotonic()
        message = MessageCAResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        self._remember_ca_mode_status(message, event_order, received_at)
        new_status = {}
        for attr in self._attributes:
            if hasattr(message, str(attr)):
                value = getattr(message, str(attr))
                # variable_mode
                if attr == DeviceAttributes.variable_mode:
                    self._attributes[attr] = MideaCADevice._variable_mode.get(value)
                # humidity
                elif attr == DeviceAttributes.humidity:
                    self._attributes[attr] = MideaCADevice._humidity.get(value)
                else:
                    self._attributes[attr] = value
                new_status[str(attr)] = self._attributes[attr]
        if (
            self.model == "310A2111"
            and self.subtype == SUBTYPE_310A2111
            and (
                DeviceAttributes.flex_zone_setting_temp in new_status
                or DeviceAttributes.variable_mode in new_status
            )
        ):
            # This model reports its preset through the setting temperature,
            # not the generic variable-mode byte. Emit the derived attribute
            # as well so consumers refresh on temperature-only updates.
            temperature = self._attributes[DeviceAttributes.flex_zone_setting_temp]
            mode = (
                FLEX_ZONE_MODE_BY_TEMPERATURE.get(temperature)
                if isinstance(temperature, (int, float))
                and not isinstance(temperature, bool)
                else None
            )
            self._attributes[DeviceAttributes.variable_mode] = mode
            new_status[DeviceAttributes.variable_mode] = mode
        return new_status

    def parse_message(self, msg: bytes) -> MessageResult:
        """Parse a frame and clear its CA receive marker after dispatch."""
        try:
            return super().parse_message(msg)
        finally:
            self._message_dispatch_complete()

    def _message_received(self) -> None:
        """Record when a socket frame arrives, before dispatch."""
        received_at = time.monotonic()
        event_order = self._next_ca_mode_event_order()
        with self._ca_mode_lock:
            self._ca_mode_received_event_order = event_order
            self._ca_mode_received_at = received_at

    def _message_dispatch_complete(self) -> None:
        """Clear the receive marker after the decoded batch is dispatched."""
        with self._ca_mode_lock:
            self._ca_mode_received_event_order = None
            self._ca_mode_received_at = None

    def close_socket(self) -> None:
        """Clear cached mode state when the transport is disconnected."""
        super().close_socket()
        with self._ca_mode_lock:
            self._ca_mode_received_event_order = None
            self._ca_mode_received_at = None
            self._ca_mode_status = None
            self._ca_mode_pending = None

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode and publish a Toshiba CA base status."""
        status = decode_toshiba_ca_status(
            frame,
            shifted=self.model == TOSHIBA_SHIFTED_MODEL,
        )
        if status is None:
            return None
        self._attributes.update(status)
        return dict(status)

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea CA device set attribute."""
        if self.toshiba_protocol:
            del attr, value
            self.reject_toshiba_write()
            return
        mask = CA_MODE_MASKS.get(attr)
        if (
            mask is None
            or self.model != CA_MODE_MODEL
            or self.subtype != CA_MODE_SUBTYPE
        ):
            return
        if not isinstance(value, bool):
            raise ValueWrongType("[ca] Expected bool")

        with self._ca_mode_lock:
            pending = self._ca_mode_pending
            if pending is not None:
                pending_expired = (
                    pending.sent_at is not None
                    and time.monotonic() - pending.sent_at
                    > CA_MODE_PENDING_TIMEOUT_SECONDS
                )
                if pending_expired:
                    self._ca_mode_pending = None
                else:
                    raise CAModeWritePendingError(
                        "[ca] mode write refused: waiting for device status",
                    )
            status = self._fresh_ca_mode_status()
            if status is None:
                return
            if bool(status.body[1] & mask) == value:
                return
            body = build_ca_mode_body(status.body, mask, value)
            command = MessageQuestCustom(
                DeviceType.CA,
                self._message_protocol_version,
                MessageType.set,
                bytearray(body),
            )
            pending = _PendingCAModeWrite(mask=mask, enabled=value)
            self._ca_mode_pending = pending
            try:
                self.build_send(
                    command,
                    on_sent=lambda: self._ca_mode_write_sent(pending),
                )
            except Exception:
                if self._ca_mode_pending is pending:
                    self._ca_mode_pending = None
                raise

    def _ca_mode_write_sent(self, pending: _PendingCAModeWrite) -> None:
        """Record the mode SET only after its stream write runs on the device loop."""
        sent_at = time.monotonic()
        sent_order = self._next_ca_mode_event_order()
        with self._ca_mode_lock:
            if self._ca_mode_pending is pending:
                self._ca_mode_pending = _PendingCAModeWrite(
                    mask=pending.mask,
                    enabled=pending.enabled,
                    sent_order=sent_order,
                    sent_at=sent_at,
                )

    def _remember_ca_mode_status(
        self,
        message: MessageCAResponse,
        event_order: int,
        received_at: float,
    ) -> None:
        """Store only a complete Midea general status body for later SETs."""
        if (
            self.model != CA_MODE_MODEL
            or self.subtype != CA_MODE_SUBTYPE
            or getattr(message, "message_type", None)
            not in (MessageType.query, MessageType.notify1)
        ):
            return
        message_type = getattr(message, "message_type", None)
        body_type = getattr(message, "body_type", None)
        if (message_type, body_type) not in (
            (MessageType.query, ListTypes.X00),
            (MessageType.notify1, ListTypes.X02),
        ):
            return
        body = getattr(message, "body", bytearray())
        if len(body) < CA_MODE_BODY_LENGTH:
            return
        raw_body = bytes(body[:CA_MODE_BODY_LENGTH])
        with self._ca_mode_lock:
            current = self._ca_mode_status
            if current is not None and event_order < current.event_order:
                return
            self._ca_mode_status = _CAModeStatus(
                body=raw_body,
                received_at=received_at,
                event_order=event_order,
            )
            pending = self._ca_mode_pending
            # Require both receipt time and dispatch order to follow the wire write.
            if (
                pending is not None
                and pending.sent_order is not None
                and pending.sent_at is not None
                and received_at >= pending.sent_at
                and event_order > pending.sent_order
            ):
                if bool(raw_body[1] & pending.mask) != pending.enabled:
                    _LOGGER.debug(
                        "[%s] CA mode write was not confirmed by device status",
                        self.device_id,
                    )
                self._ca_mode_pending = None

    def _next_ca_mode_event_order(self) -> int:
        """Return an ordering point assigned at actual receipt or completed SET."""
        with self._ca_mode_event_lock:
            self._ca_mode_event_order += 1
            return self._ca_mode_event_order

    def _fresh_ca_mode_status(self) -> _CAModeStatus | None:
        """Return a recent complete status body, if one is available."""
        status = self._ca_mode_status
        if status is None:
            return None
        if time.monotonic() - status.received_at > CA_MODE_MAX_AGE_SECONDS:
            return None
        return status


class MideaAppliance(MideaCADevice):
    """Midea CA appliance."""

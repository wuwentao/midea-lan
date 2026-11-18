"""Midea lan x10 message.

Protocol layout follows Meiju Lua ``T_0000_10_3`` (minimal power-only
appliance). The device exposes a single on/off ``power`` state.

- Query: message type 0x03, body ``[0x01]`` (single command byte).
- Control: message type 0x02, body ``[power]`` where ``power`` is 0x00/0x01.
- Report (query reply 0x03 / notify 0x04): the Lua ``binToModel`` reads the
  power byte from ``messageBytes[1]`` -- i.e. the **second** body byte
  (``body[1]``), not the first.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

QUERY_PAYLOAD = 0x01  # lua: query bodyBytes[0] = 0x01
POWER_OFF = 0x00  # lua: BYTE_POWER_OFF
POWER_ON = 0x01  # lua: BYTE_POWER_ON

# Lua binToModel reads powerValue from messageBytes[1] (the second body byte).
POWER_BYTE = 1
REPORT_MIN_LEN = 2  # need body[0] and body[1]


class Message10Base(MessageRequest):
    """x10 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize x10 message base."""
        super().__init__(
            device_type=DeviceType.X10,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(Message10Base):
    """x10 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x10 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # Lua query body is the single command byte 0x01.
            body_type=ListTypes(QUERY_PAYLOAD),
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessagePower(Message10Base):
    """x10 message power (the only control).

    The Lua places the power value as the single body byte, which maps to the
    generic ``body_type`` byte in this framework. Set it eagerly via the
    ``power`` property so it is in place before ``MessageRequest.body`` reads
    ``body_type`` (that read happens before ``_body`` is evaluated).
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize x10 message power."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            # Lua control body is a single byte carrying the power value.
            body_type=ListTypes(POWER_OFF),
        )
        self._power = False

    @property
    def power(self) -> bool:
        """Power state carried by this control."""
        return self._power

    @power.setter
    def power(self, value: bool) -> None:
        self._power = value
        self.body_type = ListTypes(POWER_ON if value else POWER_OFF)

    @property
    def _body(self) -> bytearray:
        # body_type byte already carries the power value; no extra payload.
        return bytearray([])


class X10GeneralMessageBody(MessageBody):
    """x10 status body (Lua binToModel)."""

    power: bool

    def __init__(self, body: bytearray) -> None:
        """Initialize x10 message general body."""
        super().__init__(body)
        self.power = MessageBody.read_byte(body, POWER_BYTE) == POWER_ON


class Message10Response(MessageResponse):
    """x10 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize x10 message response."""
        super().__init__(bytearray(message))
        if (
            self.message_type in (MessageType.query, MessageType.notify1)
            and len(super().body) >= REPORT_MIN_LEN
        ):
            self.set_body(X10GeneralMessageBody(super().body))
        self.set_attr()

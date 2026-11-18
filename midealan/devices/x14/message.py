"""Midea lan x14 message.

Protocol layout follows Meiju Lua ``T_0000_14_79700Z76`` (electric curtain /
blind motor, 电动窗帘).

The body is a fixed-offset record preceded by a ``cmdType`` byte:

- ``body[0]`` cmdType (always ``0x01`` for this profile)
- ``body[1]`` software_version
- ``body[2]`` curtain_status: 0 close, 1 open, 2 stop
- ``body[3]`` curtain_position: 0..100 (%)
- ``body[4]`` curtain_direction: 0 positive, 1 reverse
- ``body[5]`` error_code

Messages:

- Query: message type 0x03, body ``[0x01]``.
- Control: message type 0x02, body ``[0x01, sw, status, position, direction,
  error]`` where any unchanged field is sent as ``0xFF`` (the Lua
  "not present / invalid" sentinel).
- Report: message type 0x04 (nack) or 0x05 (ack); fields decoded only when the
  byte is not ``0xFF``.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Report/ack message types unique to this device (Lua BYTE_REPORT_*).
REPORT_NACK = 0x04  # lua: BYTE_REPORT_NACK
REPORT_ACK = 0x05  # lua: BYTE_REPORT_ACK

# cmdType sub-command (Lua cmdType). Only 0x01 is defined.
CMD_TYPE = 0x01

# "field not present / invalid" sentinel (Lua 0xFF initialization).
VALUE_INVALID = 0xFF

QUERY_PAYLOAD = 0x01  # lua: query bodyBytes[0] = 0x01

# Body offsets (Lua updateGlobalPropertyValueByByte messageBytes[n]).
CMD_TYPE_BYTE = 0
SOFTWARE_VERSION_BYTE = 1
STATUS_BYTE = 2
POSITION_BYTE = 3
DIRECTION_BYTE = 4
ERROR_BYTE = 5
REPORT_MIN_LEN = 6  # last decoded offset is body[5]

# curtain_status codes (Lua VALUE_CLOSE/OPEN/STOP).
STATUS_CLOSE = 0x00
STATUS_OPEN = 0x01
STATUS_STOP = 0x02
STATUS_NAMES: dict[int, str] = {
    STATUS_CLOSE: "close",
    STATUS_OPEN: "open",
    STATUS_STOP: "stop",
}
STATUS_CODES: dict[str, int] = {name: code for code, name in STATUS_NAMES.items()}

# curtain_direction codes (Lua VALUE_POSITIVE/REVERSE).
DIRECTION_POSITIVE = 0x00
DIRECTION_REVERSE = 0x01
DIRECTION_NAMES: dict[int, str] = {
    DIRECTION_POSITIVE: "positive",
    DIRECTION_REVERSE: "reverse",
}
DIRECTION_CODES: dict[str, int] = {n: c for c, n in DIRECTION_NAMES.items()}

POSITION_MIN = 0
POSITION_MAX = 100


class Message14Base(MessageRequest):
    """x14 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize x14 message base."""
        super().__init__(
            device_type=DeviceType.X14,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(Message14Base):
    """x14 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x14 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(QUERY_PAYLOAD),
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageSet(Message14Base):
    """x14 control: curtain status / position / direction.

    The body carries the full fixed-offset record; any field left as
    ``VALUE_INVALID`` (0xFF) is treated by the device as "no change".
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize x14 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CMD_TYPE),
        )
        self.software_version = VALUE_INVALID
        self.status = VALUE_INVALID
        self.position = VALUE_INVALID
        self.direction = VALUE_INVALID
        self.error_code = VALUE_INVALID

    @property
    def _body(self) -> bytearray:
        # body_type byte is cmdType (0x01); the remaining five bytes follow.
        return bytearray(
            [
                self.software_version,
                self.status,
                self.position,
                self.direction,
                self.error_code,
            ],
        )


class X14GeneralMessageBody(MessageBody):
    """x14 status body (Lua updateGlobalPropertyValueByByte).

    A field is only exposed when its byte is not the 0xFF invalid sentinel.
    """

    software_version: int
    curtain_status: str
    curtain_position: int
    curtain_direction: str
    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize x14 message general body."""
        super().__init__(body)
        sw = MessageBody.read_byte(body, SOFTWARE_VERSION_BYTE, VALUE_INVALID)
        if sw != VALUE_INVALID:
            self.software_version = sw
        status = MessageBody.read_byte(body, STATUS_BYTE, VALUE_INVALID)
        if status in STATUS_NAMES:
            self.curtain_status = STATUS_NAMES[status]
        position = MessageBody.read_byte(body, POSITION_BYTE, VALUE_INVALID)
        if position != VALUE_INVALID:
            self.curtain_position = position
        direction = MessageBody.read_byte(body, DIRECTION_BYTE, VALUE_INVALID)
        if direction in DIRECTION_NAMES:
            self.curtain_direction = DIRECTION_NAMES[direction]
        error = MessageBody.read_byte(body, ERROR_BYTE, VALUE_INVALID)
        if error != VALUE_INVALID:
            self.error_code = error


class Message14Response(MessageResponse):
    """x14 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize x14 message response."""
        super().__init__(bytearray(message))
        body = super().body
        # Decode query replies (0x03) and device reports (0x04 notify1 / 0x05
        # notify2 == Lua REPORT_NACK/REPORT_ACK); the Lua only populates state
        # for cmdType 0x01 records of sufficient length.
        if (
            self.message_type
            in (MessageType.query, MessageType.notify1, MessageType.notify2)
            and len(body) >= REPORT_MIN_LEN
            and MessageBody.read_byte(body, CMD_TYPE_BYTE) == CMD_TYPE
        ):
            self.set_body(X14GeneralMessageBody(body))
        self.set_attr()

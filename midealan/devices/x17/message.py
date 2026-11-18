"""Midea lan x17 message.

Protocol layout follows Meiju Lua ``T_0000_17_2`` (electric ceiling-mounted
clothes-drying rack / 电动晾衣机):

- Query: message type 0x03, body ``[0x03]`` (single command byte, no payload).
- Control: message type 0x02, body ``[0x00, selector, value, 0*7]``. The first
  body byte is a fixed 0x00 command byte; ``selector`` (Lua ``byte1``) picks the
  function and ``value`` (Lua ``byte2``) is its argument.
- Report (query reply 0x03 / notify 0x04): the body carries the state bytes
  directly with **no leading command byte** -- ``body[0]`` is already the power
  byte (Lua ``binToModel`` reads ``messageBytes[0..3]`` from the body start).
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# --- Control selectors (Lua jsonToData ``byte1``) -------------------------
# Each distinct control sends the same frame shape: a 0x00 command byte, then
# this selector, then its value. Values below follow the Lua *_ON/*_OFF bytes.
SELECTOR_UPDOWN = 0x01  # lua: KEY_UPDOWN
SELECTOR_LIGHT = 0x02  # lua: KEY_LIGHT
SELECTOR_STERILIZE = 0x03  # lua: KEY_STERILIZE
SELECTOR_DRY = 0x04  # lua: KEY_DRY
SELECTOR_POWER = 0x05  # lua: KEY_POWER
SELECTOR_ANION = 0x06  # lua: KEY_ANION
SELECTOR_BAKING = 0x07  # lua: KEY_BAKING

VALUE_OFF = 0x00  # lua: *_OFF / POWER_OFF
VALUE_ON = 0x01  # lua: *_ON / POWER_ON

# updown is tri-state rather than on/off (Lua UPDOWN_PAUSE/UP/DOWN).
UPDOWN_PAUSE = 0x00  # lua: UPDOWN_PAUSE
UPDOWN_UP = 0x01  # lua: UPDOWN_UP
UPDOWN_DOWN = 0x02  # lua: UPDOWN_DOWN

UPDOWN_NAMES: dict[int, str] = {
    UPDOWN_PAUSE: "pause",
    UPDOWN_UP: "up",
    UPDOWN_DOWN: "down",
}
UPDOWN_CODES: dict[str, int] = {name: code for code, name in UPDOWN_NAMES.items()}

# Query command byte (Lua query bodyBytes[0] = 0x03).
QUERY_COMMAND = 0x03
# Control command byte (Lua control bodyBytes[0] = 0x00).
CONTROL_COMMAND = 0x00
# Control payload is padded to a fixed 9-byte body after the command byte
# (Lua assembleUart builds a 10-byte body: command + selector + value + 7 zeros).
CONTROL_PAD_BYTES = 7

# --- Report body offsets (Lua binToModel ``messageBytes[n]``) --------------
POWER_BYTE = 0  # lua: messageBytes[0] -> power
UPDOWN_BYTE = 1  # lua: messageBytes[1] -> updown
FLAGS_BYTE = 2  # lua: messageBytes[2] -> packed toggle bits
ERROR_BYTE = 3  # lua: messageBytes[3] -> error_code
REPORT_MIN_LEN = 4  # last fixed-offset read is body[3]

# Packed toggle bits inside FLAGS_BYTE (Lua bit.band(byte2, mask)).
LIGHT_BIT = 0x01  # lua: KEY_LIGHT
STERILIZE_BIT = 0x02  # lua: KEY_STERILIZE
DRY_BIT = 0x04  # lua: KEY_DRY
BAKING_BIT = 0x08  # lua: KEY_BAKING
ANION_BIT = 0x10  # lua: KEY_ANION


class Message17Base(MessageRequest):
    """x17 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize x17 message base."""
        super().__init__(
            device_type=DeviceType.X17,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(Message17Base):
    """x17 message query (full status)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x17 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # Lua query body is the single command byte 0x03 (no payload after).
            body_type=ListTypes(QUERY_COMMAND),
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageSet(Message17Base):
    """x17 single-function control.

    Every control shares one frame shape (Lua jsonToData control branch): a
    fixed 0x00 command byte, a function ``selector``, its ``value``, then zero
    padding. ``set_attribute`` fills ``selector``/``value`` for the requested
    function.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize x17 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CONTROL_COMMAND),
        )
        self.selector = SELECTOR_POWER
        self.value = VALUE_OFF

    @property
    def _body(self) -> bytearray:
        return bytearray([self.selector, self.value, *([0] * CONTROL_PAD_BYTES)])


class X17GeneralMessageBody(MessageBody):
    """x17 status body (Lua binToModel + assembleJsonByGlobalProperty).

    Unlike most devices the report body has no leading command byte, so the
    state bytes start at ``body[0]``.
    """

    power: bool
    updown: str
    light: bool
    sterilize: bool
    dry: bool
    baking: bool
    anion: bool
    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize x17 message general body."""
        super().__init__(body)
        self.power = MessageBody.read_byte(body, POWER_BYTE) == VALUE_ON
        updown_byte = MessageBody.read_byte(body, UPDOWN_BYTE)
        self.updown = UPDOWN_NAMES.get(updown_byte, "pause")
        flags = MessageBody.read_byte(body, FLAGS_BYTE)
        self.light = (flags & LIGHT_BIT) != 0
        self.sterilize = (flags & STERILIZE_BIT) != 0
        self.dry = (flags & DRY_BIT) != 0
        self.baking = (flags & BAKING_BIT) != 0
        self.anion = (flags & ANION_BIT) != 0
        self.error_code = MessageBody.read_byte(body, ERROR_BYTE)


class Message17Response(MessageResponse):
    """x17 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize x17 message response."""
        super().__init__(bytearray(message))
        # Lua binToModel decodes only query replies (0x03) and notifies (0x04);
        # it ignores the set echo (0x02). The report body carries state bytes
        # directly, so require enough bytes for every fixed offset read.
        if (
            self.message_type in (MessageType.query, MessageType.notify1)
            and len(super().body) >= REPORT_MIN_LEN
        ):
            self.set_body(X17GeneralMessageBody(super().body))
        self.set_attr()

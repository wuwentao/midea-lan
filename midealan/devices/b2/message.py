"""Midea lan b2 message.

Protocol layout follows Meiju Lua ``T_0000_B2_3`` (steam box / steam oven,
蒸箱). The body is a flat fixed-offset record with no sub-command prefix, so the
first body byte (``work_status``) maps to the generic ``body_type`` byte in this
framework and every Lua ``messageBytes[n]`` offset is the response body offset
``body[n]`` directly.

- Query: message type 0x03, empty body.
- Control: message type 0x02, 15-byte body
  ``[work_status, work_mode, work_hour, work_minute, temperature, 0,0,0,0,0,
  0,0,0,0, lock]``.
- Report (query reply 0x03 / notify 0x04): ``binToModel`` reads work_status,
  work_mode, hour, minute, temperature, the packed box/water/door state byte at
  body[6], and lock at body[16].
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# "field not present" sentinel (Lua BYTE_NONE) and lock bytes.
VALUE_NONE = 0xFF
LOCK_ON = 0x01
LOCK_OFF = 0x00

# Body offsets (Lua binToModel messageBytes[n] / jsonToData bodyBytes[n]).
WORK_STATUS_BYTE = 0
WORK_MODE_BYTE = 1
WORK_HOUR_BYTE = 2
WORK_MINUTE_BYTE = 3
TEMPERATURE_BYTE = 4
STATE_BYTE = 6  # packed box / water / door state
LOCK_BYTE = 16
# Control body length (Lua bodyLength = 15, incl. body[0]).
CONTROL_BODY_LEN = 15
# Report must reach at least the lock offset to decode fully.
REPORT_MIN_LEN = LOCK_BYTE + 1

# Packed state masks (Lua bit.band on messageBytes[6]).
BOX_STATE_MASK = 0x01  # 0 -> in, else out
WATER_STATE_MASK = 0x02  # 0 -> full, else empty
DOOR_STATE_MASK = 0x07  # 0 -> close, else open

# work_status codes (Lua BYTE_* status values).
STATUS_STANDBY = 0x01
STATUS_WORK = 0x02
STATUS_PAUSE = 0x03
STATUS_FINISH = 0x04
STATUS_RESERVATION = 0x06
STATUS_SAVE_POWER = 0x07
STATUS_NONE = 0xFF
WORK_STATUS_NAMES: dict[int, str] = {
    STATUS_STANDBY: "standby",
    STATUS_WORK: "work",
    STATUS_PAUSE: "pause",
    STATUS_FINISH: "work_finish",
    STATUS_RESERVATION: "reservation",
    STATUS_SAVE_POWER: "save_power",
    STATUS_NONE: "none",
}
# Settable work_status labels (Lua jsonToModel accepted values).
WORK_STATUS_CODES: dict[str, int] = {
    "standby": STATUS_STANDBY,
    "work": STATUS_WORK,
    "pause": STATUS_PAUSE,
    "save_power": STATUS_SAVE_POWER,
    "reservation": STATUS_RESERVATION,
    "none": STATUS_NONE,
}

# work_mode codes (Lua BYTE_MODE_* values).
MODE_NAMES: dict[int, str] = {
    0x01: "unfreeze",
    0x02: "keep_warm",
    0x03: "fish",
    0x04: "meat",
    0x05: "egg",
    0x06: "seafood",
    0x07: "steam_clean",
    0x08: "common",
    0x09: "grain",
    0x0A: "rice",
    0x0D: "zymosis",
    0x0E: "heat",
    0x0F: "furring_clean",
    0x10: "disinfect",
    0x71: "vegetable",
    0x72: "chop",
}
MODE_CODES: dict[str, int] = {name: code for code, name in MODE_NAMES.items()}

# door / water / box state labels (Lua VALUE_STATE_*).
DOOR_STATE_NAMES = {0: "close", 1: "open"}
WATER_STATE_NAMES = {0: "full", 1: "empty"}
BOX_STATE_NAMES = {0: "in", 1: "out"}

# Parameter ranges (Lua checkBoundary bounds).
TEMPERATURE_MIN = 50
TEMPERATURE_MAX = 100
WORK_HOUR_MIN = 0
WORK_HOUR_MAX = 9
WORK_MINUTE_MIN = 0
WORK_MINUTE_MAX = 59


class MessageB2Base(MessageRequest):
    """b2 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize b2 message base."""
        super().__init__(
            device_type=DeviceType.B2,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageB2Base):
    """b2 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize b2 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # The Lua query body is empty; body_type carries the leading 0x00.
            body_type=ListTypes(0x00),
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageSet(MessageB2Base):
    """b2 control: work_status / mode / time / temperature / lock.

    ``work_status`` is the first body byte, which maps to the generic
    ``body_type`` byte; it is set eagerly through its property so it is in place
    before ``MessageRequest.body`` reads ``body_type`` (that read happens before
    ``_body`` is evaluated).
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize b2 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(STATUS_STANDBY),
        )
        self._work_status = STATUS_STANDBY
        self.work_mode = 0
        self.work_hour = 0
        self.work_minute = 0
        self.temperature = 0
        self.lock = LOCK_OFF

    @property
    def work_status(self) -> int:
        """work_status carried by this control (the leading body byte)."""
        return self._work_status

    @work_status.setter
    def work_status(self, value: int) -> None:
        self._work_status = value
        self.body_type = ListTypes(value)

    @property
    def _body(self) -> bytearray:
        # body_type byte already carries work_status (body[0]); body[1..14]
        # follow, with the packed state bytes left zero.
        return bytearray(
            [
                self.work_mode,
                self.work_hour,
                self.work_minute,
                self.temperature,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                self.lock,
            ],
        )


class B2GeneralMessageBody(MessageBody):
    """b2 status body (Lua binToModel)."""

    work_status: str
    work_mode: str
    work_hour: int
    work_minute: int
    temperature: int
    door_state: str
    water_state: str
    box_state: str
    lock: bool

    def __init__(self, body: bytearray) -> None:
        """Initialize b2 message general body."""
        super().__init__(body)
        status = MessageBody.read_byte(body, WORK_STATUS_BYTE)
        if status in WORK_STATUS_NAMES:
            self.work_status = WORK_STATUS_NAMES[status]
        mode = MessageBody.read_byte(body, WORK_MODE_BYTE)
        if mode in MODE_NAMES:
            self.work_mode = MODE_NAMES[mode]
        self.work_hour = MessageBody.read_byte(body, WORK_HOUR_BYTE)
        self.work_minute = MessageBody.read_byte(body, WORK_MINUTE_BYTE)
        self.temperature = MessageBody.read_byte(body, TEMPERATURE_BYTE)
        state = MessageBody.read_byte(body, STATE_BYTE)
        # Lua compares each packed field against 0x00: zero -> first label.
        self.box_state = BOX_STATE_NAMES[1 if state & BOX_STATE_MASK else 0]
        self.water_state = WATER_STATE_NAMES[1 if state & WATER_STATE_MASK else 0]
        self.door_state = DOOR_STATE_NAMES[1 if state & DOOR_STATE_MASK else 0]
        self.lock = MessageBody.read_byte(body, LOCK_BYTE) == LOCK_ON


class MessageB2Response(MessageResponse):
    """b2 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize b2 message response."""
        super().__init__(bytearray(message))
        if (
            self.message_type
            in (MessageType.set, MessageType.query, MessageType.notify1)
            and len(super().body) >= REPORT_MIN_LEN
        ):
            self.set_body(B2GeneralMessageBody(super().body))
        self.set_attr()

"""Midea lan b7 message.

Protocol layout follows Meiju Lua ``T_0000_B7_14`` (智能燃气灶, dual-burner smart
gas stove / cooktop).

The Lua ``jsonToData`` hand-builds a self-contained Midea application frame
``0xAA <len> 0xB7 ... <frame-type> <command> <payload> <checkSum>``. That is the
same AA frame this framework already produces: the 10-byte framework header
carries flag/length/device-type/.../device-protocol/frame-type (Lua byte offsets
0..9), and the device ``body`` is everything after it. So the Lua ``bytecmd[9]``
(frame type: 0x03 query-echo, 0x04 notify, 0x02 fail) is the framework
``message_type``, the Lua ``bytecmd[10]`` (command: 0x31/0x41 status, 0x32 error)
is the device ``body[0]`` / ``body_type``, and every later Lua ``bytecmd[n]`` maps
to device ``body[n - 10]``.

Implemented scope (read-only status + simple per-burner controls):

- Query 0x31 (status) and 0x32 (error): fixed request frames from the Lua.
- Report 0x31/0x41 (status): left/right status, gears, surplus h/m, work h/m/s,
  work_mode, packed lock/menu_mark/gas_warn/smart_bl bits, and left/right temp.
- Report 0x32 (error): error_code / tips_code bitmaps (first set bit wins).
- Control for one burner: on/off (function_control 1), gear (3), temperature
  (11..14), and the panel lock (burner selector 3).

Out of scope (see the package docstring FUTURE list): the variable-length
``pots[]`` bound-induction-pot array, BT enumeration (0x37/0x47), menu download
(0xCA, cloud-only) and MAC bind (0x27).
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Inner frame head (Lua tdlist[0]); also the framework frame flag.
INNER_HEAD = 0xAA

# Commands carried at device body[0] (Lua bytecmd[10]).
CMD_STATUS_QUERY = 0x31  # query / query-echo status
CMD_STATUS_NOTIFY = 0x41  # notify status
CMD_ERROR = 0x32  # error / tips bitmap report

# Fail-response marker: message_type set (0x02) with body[1] == 0xFE.
FAIL_MARKER = 0xFE

# --- status report body offsets (Lua bytecmd[n] -> body[n - 10]) ---
LEFT_STATUS_BYTE = 1
RIGHT_STATUS_BYTE = 2
LEFT_SURPLUS_HOURS_BYTE = 3
LEFT_SURPLUS_MINUTES_BYTE = 4
LEFT_WORK_HOURS_BYTE = 5
LEFT_WORK_MINUTES_BYTE = 6
LEFT_WORK_SECONDS_BYTE = 7
RIGHT_SURPLUS_HOURS_BYTE = 8
RIGHT_SURPLUS_MINUTES_BYTE = 9
RIGHT_WORK_HOURS_BYTE = 10
RIGHT_WORK_MINUTES_BYTE = 11
RIGHT_WORK_SECONDS_BYTE = 12
LEFT_GEAR_BYTE = 13
RIGHT_GEAR_BYTE = 14
LEFT_WORK_MODE_BYTE = 15
RIGHT_WORK_MODE_BYTE = 16
PACKED_FLAGS_BYTE = 17
# Temperatures are 16-bit big-endian pairs that only appear in the long frame.
LEFT_TEMP_HI_BYTE = 37
LEFT_TEMP_LO_BYTE = 38
RIGHT_TEMP_HI_BYTE = 39
RIGHT_TEMP_LO_BYTE = 40
# Status decode needs at least up to the packed-flags byte; temps need body[40].
STATUS_MIN_LEN = PACKED_FLAGS_BYTE + 1
STATUS_TEMP_MIN_LEN = RIGHT_TEMP_LO_BYTE + 1

# Packed-flags bit positions in body[17] (Lua getBit(bytecmd[27], n)).
LOCK_BIT = 0
MENU_MARK_BIT = 1
GAS_WARN_BIT = 3
RIGHT_SMART_BL_BIT = 4
LEFT_SMART_BL_BIT = 5

TEMP_SHIFT = 8  # high byte << 8 | low byte

# --- error report (Lua: only when bytecmd[11] == 0x03, i.e. body[1] == 0x03) ---
ERROR_SUBTYPE_BYTE = 1
ERROR_SUBTYPE_VALUE = 0x03
ERROR_GROUP0_BYTE = 2  # bits 0..7 -> error_code 1..8
ERROR_GROUP1_BYTE = 3  # bits 0..7 -> error_code 9..16
TIPS_GROUP0_BYTE = 4  # bits 0..5 -> tips_code 1..6
TIPS_GROUP1_BYTE = 5  # bits 0..1 -> tips_code 7..8
ERROR_GROUP0_BITS = 8
ERROR_GROUP1_BITS = 8
ERROR_GROUP1_BASE = 9
TIPS_GROUP0_BITS = 6
TIPS_GROUP1_BITS = 2
TIPS_GROUP1_BASE = 7
ERROR_MIN_LEN = TIPS_GROUP1_BYTE + 1

# Fail-response reason offset (Lua bytecmd[13] -> body[3]).
FAIL_REASON_BYTE = 3
FAIL_MIN_LEN = FAIL_REASON_BYTE + 1

# --- control frame (Lua switch_mode per work_burner_control) ---
# The framework header already emits body[0..9]; the device body here starts at
# the command byte (body[0] = 0x21 control opcode, Lua tdlist[10]) and the Lua
# tdlist[11..] become body[1..].
CONTROL_OPCODE = 0x21  # Lua tdlist[10] for control
BURNER_LEFT = 0x01  # work_burner_control 1 -> body[1]
BURNER_RIGHT = 0x02  # work_burner_control 2 -> body[1]
BURNER_LOCK = 0x03  # work_burner_control 3 -> body[1]

# function_control values (Lua control.function_control at body[2]).
FUNCTION_POWER = 0x01  # on/off
FUNCTION_GEAR = 0x03  # gear -> body[5]
FUNCTION_SURPLUS = 0x04  # surplus timer -> body[3]/body[4]
FUNCTION_TEMP_MIN = 0x0B  # 11..14 temperature set
FUNCTION_TEMP_MAX = 0x0E

# Lock values written to body[2] when burner selector is BURNER_LOCK.
LOCK_OFF = 0x07
LOCK_ON = 0x08

# Control body offsets (device body[n] = Lua tdlist[n + 10]).
CTRL_BURNER_BYTE = 1  # Lua tdlist[11]
CTRL_FUNCTION_BYTE = 2  # Lua tdlist[12]
CTRL_SURPLUS_HOURS_BYTE = 3  # Lua tdlist[13]
CTRL_SURPLUS_MINUTES_BYTE = 4  # Lua tdlist[14]
CTRL_GEAR_BYTE = 5  # Lua tdlist[15]
CTRL_LEFT_TEMP_HI_BYTE = 6  # Lua tdlist[16]
CTRL_LEFT_TEMP_LO_BYTE = 7  # Lua tdlist[17]
CTRL_RIGHT_TEMP_HI_BYTE = 8  # Lua tdlist[18]
CTRL_RIGHT_TEMP_LO_BYTE = 9  # Lua tdlist[19]
# The Lua control body spans tdlist[11..21] -> body[1..11].
CONTROL_BODY_LEN = 11

TEMP_LOW_MASK = 0xFF

# function_control = 1 (FUNCTION_POWER) is the momentary ignite/toggle command;
# the protocol carries no separate on/off value.

# Parameter ranges (inclusive). Gears/temps are byte-wide fields.
GEAR_MIN = 0
GEAR_MAX = 0xFF
TEMP_MIN = 0
TEMP_MAX = 0xFFFF


def _bit(value: int, index: int) -> int:
    """Return bit ``index`` of ``value`` (0 or 1)."""
    return (value >> index) & 1


class MessageB7Base(MessageRequest):
    """b7 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize b7 message base."""
        super().__init__(
            device_type=DeviceType.B7,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQueryStatus(MessageB7Base):
    """b7 status query (Lua query_type 31 -> AA0BB7...033109)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize b7 status query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(CMD_STATUS_QUERY),
        )

    @property
    def _body(self) -> bytearray:
        # body[0] (command 0x31) is carried by body_type; the Lua trailing 0x09
        # is that frame's inner checksum, regenerated by the framework serializer.
        return bytearray([])


class MessageQueryError(MessageB7Base):
    """b7 error query (Lua query_type 32 -> AA0CB7...0103320304)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize b7 error query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(CMD_ERROR),
        )

    @property
    def _body(self) -> bytearray:
        # body[0] (command 0x32) is body_type; body[1] = 0x03 error sub-type.
        return bytearray([ERROR_SUBTYPE_VALUE])


class MessageSet(MessageB7Base):
    """b7 control for a single burner (on/off, gear, temperature) or the lock.

    The control opcode (Lua tdlist[10] = 0x21) maps to ``body_type``; the Lua
    ``tdlist[11..21]`` become ``body[1..11]``.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize b7 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CONTROL_OPCODE),
        )
        self.burner = BURNER_LEFT
        self.function_control = 0
        self.gear = 0
        self.surplus_hours = 0
        self.surplus_minutes = 0
        self.left_temp = 0
        self.right_temp = 0

    @property
    def _body(self) -> bytearray:
        body = bytearray(CONTROL_BODY_LEN)
        body[CTRL_BURNER_BYTE - 1] = self.burner
        body[CTRL_FUNCTION_BYTE - 1] = self.function_control
        if self.function_control == FUNCTION_GEAR:
            body[CTRL_GEAR_BYTE - 1] = self.gear
        elif self.function_control == FUNCTION_SURPLUS:
            body[CTRL_SURPLUS_HOURS_BYTE - 1] = self.surplus_hours
            body[CTRL_SURPLUS_MINUTES_BYTE - 1] = self.surplus_minutes
        elif FUNCTION_TEMP_MIN <= self.function_control <= FUNCTION_TEMP_MAX:
            if self.burner == BURNER_LEFT:
                body[CTRL_LEFT_TEMP_HI_BYTE - 1] = (
                    self.left_temp >> TEMP_SHIFT
                ) & TEMP_LOW_MASK
                body[CTRL_LEFT_TEMP_LO_BYTE - 1] = self.left_temp & TEMP_LOW_MASK
            else:
                body[CTRL_RIGHT_TEMP_HI_BYTE - 1] = (
                    self.right_temp >> TEMP_SHIFT
                ) & TEMP_LOW_MASK
                body[CTRL_RIGHT_TEMP_LO_BYTE - 1] = self.right_temp & TEMP_LOW_MASK
        return body


class MessageSetLock(MessageB7Base):
    """b7 panel-lock control (Lua work_burner_control 3)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize b7 lock set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CONTROL_OPCODE),
        )
        self.lock = False

    @property
    def _body(self) -> bytearray:
        body = bytearray(CONTROL_BODY_LEN)
        body[CTRL_BURNER_BYTE - 1] = BURNER_LOCK
        body[CTRL_FUNCTION_BYTE - 1] = LOCK_ON if self.lock else LOCK_OFF
        return body


class B7StatusMessageBody(MessageBody):
    """b7 status body (Lua dataToJson 0x31 / 0x41 branch)."""

    left_status: int
    right_status: int
    left_surplus_hours: int
    left_surplus_minutes: int
    right_surplus_hours: int
    right_surplus_minutes: int
    left_work_hours: int
    left_work_minutes: int
    left_work_seconds: int
    right_work_hours: int
    right_work_minutes: int
    right_work_seconds: int
    left_gear: int
    right_gear: int
    left_work_mode: int
    right_work_mode: int
    lock: bool
    menu_mark: bool
    gas_warn: bool
    left_smart_bl: bool
    right_smart_bl: bool
    left_temp: int
    right_temp: int

    def __init__(self, body: bytearray) -> None:
        """Initialize b7 status body."""
        super().__init__(body)
        self.left_status = MessageBody.read_byte(body, LEFT_STATUS_BYTE)
        self.right_status = MessageBody.read_byte(body, RIGHT_STATUS_BYTE)
        self.left_surplus_hours = MessageBody.read_byte(
            body,
            LEFT_SURPLUS_HOURS_BYTE,
        )
        self.left_surplus_minutes = MessageBody.read_byte(
            body,
            LEFT_SURPLUS_MINUTES_BYTE,
        )
        self.left_work_hours = MessageBody.read_byte(body, LEFT_WORK_HOURS_BYTE)
        self.left_work_minutes = MessageBody.read_byte(
            body,
            LEFT_WORK_MINUTES_BYTE,
        )
        self.left_work_seconds = MessageBody.read_byte(
            body,
            LEFT_WORK_SECONDS_BYTE,
        )
        self.right_surplus_hours = MessageBody.read_byte(
            body,
            RIGHT_SURPLUS_HOURS_BYTE,
        )
        self.right_surplus_minutes = MessageBody.read_byte(
            body,
            RIGHT_SURPLUS_MINUTES_BYTE,
        )
        self.right_work_hours = MessageBody.read_byte(body, RIGHT_WORK_HOURS_BYTE)
        self.right_work_minutes = MessageBody.read_byte(
            body,
            RIGHT_WORK_MINUTES_BYTE,
        )
        self.right_work_seconds = MessageBody.read_byte(
            body,
            RIGHT_WORK_SECONDS_BYTE,
        )
        self.left_gear = MessageBody.read_byte(body, LEFT_GEAR_BYTE)
        self.right_gear = MessageBody.read_byte(body, RIGHT_GEAR_BYTE)
        self.left_work_mode = MessageBody.read_byte(body, LEFT_WORK_MODE_BYTE)
        self.right_work_mode = MessageBody.read_byte(body, RIGHT_WORK_MODE_BYTE)
        flags = MessageBody.read_byte(body, PACKED_FLAGS_BYTE)
        self.lock = _bit(flags, LOCK_BIT) == 1
        self.menu_mark = _bit(flags, MENU_MARK_BIT) == 1
        self.gas_warn = _bit(flags, GAS_WARN_BIT) == 1
        self.left_smart_bl = _bit(flags, LEFT_SMART_BL_BIT) == 1
        self.right_smart_bl = _bit(flags, RIGHT_SMART_BL_BIT) == 1
        # Temperatures only exist in the long frame (Lua `if bytecmd[50]`).
        if len(body) >= STATUS_TEMP_MIN_LEN:
            self.left_temp = (
                MessageBody.read_byte(body, LEFT_TEMP_HI_BYTE) << TEMP_SHIFT
            ) + MessageBody.read_byte(body, LEFT_TEMP_LO_BYTE)
            self.right_temp = (
                MessageBody.read_byte(body, RIGHT_TEMP_HI_BYTE) << TEMP_SHIFT
            ) + MessageBody.read_byte(body, RIGHT_TEMP_LO_BYTE)


class B7ErrorMessageBody(MessageBody):
    """b7 error / tips body (Lua dataToJson 0x32 branch)."""

    error_code: int
    tips_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize b7 error body."""
        super().__init__(body)
        self.error_code = 0
        self.tips_code = 0
        if MessageBody.read_byte(body, ERROR_SUBTYPE_BYTE) != ERROR_SUBTYPE_VALUE:
            return
        group0 = MessageBody.read_byte(body, ERROR_GROUP0_BYTE)
        for i in range(ERROR_GROUP0_BITS):
            if _bit(group0, i) == 1:
                self.error_code = i + 1
                return
        group1 = MessageBody.read_byte(body, ERROR_GROUP1_BYTE)
        for i in range(ERROR_GROUP1_BITS):
            if _bit(group1, i) == 1:
                self.error_code = i + ERROR_GROUP1_BASE
                return
        tips0 = MessageBody.read_byte(body, TIPS_GROUP0_BYTE)
        for i in range(TIPS_GROUP0_BITS):
            if _bit(tips0, i) == 1:
                self.tips_code = i + 1
                return
        tips1 = MessageBody.read_byte(body, TIPS_GROUP1_BYTE)
        for i in range(TIPS_GROUP1_BITS):
            if _bit(tips1, i) == 1:
                self.tips_code = i + TIPS_GROUP1_BASE
                return


class B7FailMessageBody(MessageBody):
    """b7 fail-response body (Lua dataToJson bytecmd[9] == 0x02 branch)."""

    fail_resp_reason: int

    def __init__(self, body: bytearray) -> None:
        """Initialize b7 fail body."""
        super().__init__(body)
        if MessageBody.read_byte(body, LEFT_STATUS_BYTE) == FAIL_MARKER:
            self.fail_resp_reason = MessageBody.read_byte(body, FAIL_REASON_BYTE)


class MessageB7Response(MessageResponse):
    """b7 message response."""

    # Fields copied off the decoded body classes by ``set_attr``; declared here
    # so static type-checking sees them on the response.
    left_status: int
    right_status: int
    left_surplus_hours: int
    left_surplus_minutes: int
    right_surplus_hours: int
    right_surplus_minutes: int
    left_work_hours: int
    left_work_minutes: int
    left_work_seconds: int
    right_work_hours: int
    right_work_minutes: int
    right_work_seconds: int
    left_gear: int
    right_gear: int
    left_work_mode: int
    right_work_mode: int
    lock: bool
    menu_mark: bool
    gas_warn: bool
    left_smart_bl: bool
    right_smart_bl: bool
    left_temp: int
    right_temp: int
    error_code: int
    tips_code: int
    fail_resp_reason: int

    def __init__(self, message: bytes) -> None:
        """Initialize b7 message response."""
        super().__init__(bytearray(message))
        body = super().body
        command = self.body_type
        if (
            command in (CMD_STATUS_QUERY, CMD_STATUS_NOTIFY)
            and len(body) >= STATUS_MIN_LEN
        ):
            self.set_body(B7StatusMessageBody(body))
        elif command == CMD_ERROR and len(body) >= ERROR_MIN_LEN:
            self.set_body(B7ErrorMessageBody(body))
        elif self.message_type == MessageType.set and len(body) >= FAIL_MIN_LEN:
            self.set_body(B7FailMessageBody(body))
        self.set_attr()

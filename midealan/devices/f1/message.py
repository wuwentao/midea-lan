"""Midea lan f1 message.

Protocol layout follows Meiju Lua ``T_0000_F1_2`` (tea / beverage brewer). The
Midea body wraps an inner ``0xAA 0x55 ...`` application sub-frame, so the first
body byte (``0xAA``) maps to the generic ``body_type`` byte in this framework
and every Lua ``messageBytes[n]`` offset is the response body offset ``body[n]``.

- Query: message type 0x03, 8-byte inner frame with the 0x31 query selector.
- Control: message type 0x02, 25-byte inner frame with the 0x20 selector,
  carrying work_mode (little-endian 32-bit), code_id, power, appoint/work/warm
  times, warm/work temperatures and speed.
- Report (0x02 / 0x03 / 0x04) decodes the full status record.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Inner application sub-frame markers (Lua bodyBytes[0..1] and selectors).
INNER_HEAD = 0xAA  # bodyBytes[0]
INNER_HEAD2 = 0x55  # bodyBytes[1]
INNER_HEAD_BYTE = 0  # position of bodyBytes[0] in the response body
INNER_HEAD2_BYTE = 1  # position of bodyBytes[1] in the response body
SELECTOR_QUERY = 0x31  # bodyBytes[3] for a query
SELECTOR_CONTROL = 0x20  # bodyBytes[3] for a control

# power bytes (Lua BYTE_POWER_*).
POWER_ON = 0x01
POWER_OFF = 0x00

# Report body offsets (Lua binToModel messageBytes[n]).
MODE_B0_BYTE = 4
MODE_B1_BYTE = 5
MODE_B2_BYTE = 6
MODE_B3_BYTE = 7
ERROR_CODE_BYTE = 8
RESPONSE_TYPE_BYTE = 9
WORK_STATUS_BYTE = 10
STEP_STATUS_BYTE = 11
WORK_STEP_BYTE = 12
LID_STATUS_BYTE = 13
CUP_STATUS_BYTE = 14
CUR_WORK_TIME_LO_BYTE = 15
CUR_WORK_TIME_HI_BYTE = 16
CUR_TEMPERATURE_BYTE = 17
SPEED_BYTE = 18
SET_WORK_TEMP_BYTE = 19
SET_WARM_TEMP_BYTE = 20
APPOINT_TIME_LO_BYTE = 21
APPOINT_TIME_HI_BYTE = 22
SET_WORK_TIME_LO_BYTE = 23
SET_WORK_TIME_HI_BYTE = 24
SET_WARM_TIME_BYTE = 25
CODE_ID_BYTE = 26
# Lua binToModel requires at least 11 body bytes; the full record needs body[26].
REPORT_MIN_LEN = 11
STATUS_REPORT_MIN_LEN = CODE_ID_BYTE + 1

# Control body offsets (Lua jsonToData bodyBytes[n]).
CTRL_MODE_B0_BYTE = 4
CTRL_CODE_ID_BYTE = 8
CTRL_POWER_BYTE = 9
CTRL_APPOINT_TIME_LO_BYTE = 10
CTRL_SET_WORK_TIME_LO_BYTE = 12
CTRL_SET_WARM_TIME_BYTE = 14
CTRL_SET_WARM_TEMP_BYTE = 15
CTRL_SET_WORK_TEMP_BYTE = 16
CTRL_SPEED_BYTE = 17

BYTE_SHIFT = 8
BYTE_MASK = 0xFF
MODE_SHIFT_2 = 16
MODE_SHIFT_3 = 24

# response type (Lua BYTE_RESPONSE_*).
RESPONSE_FAIL = 0x00
RESPONSE_SUCCESS = 0x01
RESPONSE_NAMES: dict[int, str] = {
    RESPONSE_SUCCESS: "success",
    RESPONSE_FAIL: "fail",
}

# lid_status labels (Lua VALUE_HAVE_CUP / VALUE_NO_CUP).
LID_STATUS_NAMES: dict[int, str] = {0x00: "have_cup", 0x01: "no_cup"}
# cup_status labels (Lua VALUE_DEFAULT / VALUE_HOT_CUP / VALUE_COLD_CUP).
CUP_STATUS_NAMES: dict[int, str] = {
    0x00: "default",
    0x01: "hot_cup",
    0x02: "cold_cup",
}

# Parameter ranges (Lua checkBoundary bounds; temps are single pass-through bytes).
CODE_ID_LOW = 0
CODE_ID_HIGH = 255
TIME_16_LOW = 0
TIME_16_HIGH = 65535
WARM_TIME_LOW = 0
WARM_TIME_HIGH = 59
SPEED_LOW = 0
SPEED_HIGH = 8
MODE_LOW = 0
MODE_HIGH = 0xFFFFFFFF
TEMP_LOW = 0
TEMP_HIGH = 255


class MessageF1Base(MessageRequest):
    """f1 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize f1 message base."""
        super().__init__(
            device_type=DeviceType.F1,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageF1Base):
    """f1 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize f1 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(INNER_HEAD),
        )

    @property
    def _body(self) -> bytearray:
        # The inner query frame; body_type already carries body[0] (0xAA).
        return bytearray([INNER_HEAD2, 0x00, SELECTOR_QUERY, 0x00, 0x00, 0x00, 0x00])


class MessageSet(MessageF1Base):
    """f1 control: work_mode / power / time / temperature / speed."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize f1 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(INNER_HEAD),
        )
        self.work_mode = 0
        self.code_id = 0
        self.power = False
        self.appoint_time = 0
        self.set_work_time = 0
        self.set_keep_warm_time = 0
        self.set_keep_warm_temp = 0
        self.set_work_temp = 0
        self.speed = 0

    @property
    def _body(self) -> bytearray:
        # The inner control frame; body_type already carries body[0] (0xAA).
        return bytearray(
            [
                INNER_HEAD2,
                0x00,
                SELECTOR_CONTROL,
                self.work_mode & BYTE_MASK,
                (self.work_mode >> BYTE_SHIFT) & BYTE_MASK,
                (self.work_mode >> MODE_SHIFT_2) & BYTE_MASK,
                (self.work_mode >> MODE_SHIFT_3) & BYTE_MASK,
                self.code_id,
                POWER_ON if self.power else POWER_OFF,
                self.appoint_time & BYTE_MASK,
                (self.appoint_time >> BYTE_SHIFT) & BYTE_MASK,
                self.set_work_time & BYTE_MASK,
                (self.set_work_time >> BYTE_SHIFT) & BYTE_MASK,
                self.set_keep_warm_time,
                self.set_keep_warm_temp,
                self.set_work_temp,
                self.speed,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class F1GeneralMessageBody(MessageBody):
    """f1 status body (Lua binToModel)."""

    work_mode: int
    error_code: int
    response_type: str
    work_status: int
    step_status: int
    work_stage: int
    lid_status: str
    cup_status: str
    current_time: int
    current_temp: int
    speed: int
    set_work_temp: int
    set_keep_warm_temp: int
    appoint_time: int
    set_work_time: int
    set_keep_warm_time: int
    code_id: int

    def __init__(self, body: bytearray) -> None:
        """Initialize f1 message general body."""
        super().__init__(body)
        self.work_mode = (
            MessageBody.read_byte(body, MODE_B0_BYTE)
            + (MessageBody.read_byte(body, MODE_B1_BYTE) << BYTE_SHIFT)
            + (MessageBody.read_byte(body, MODE_B2_BYTE) << MODE_SHIFT_2)
            + (MessageBody.read_byte(body, MODE_B3_BYTE) << MODE_SHIFT_3)
        )
        self.error_code = MessageBody.read_byte(body, ERROR_CODE_BYTE)
        response = MessageBody.read_byte(body, RESPONSE_TYPE_BYTE)
        if response in RESPONSE_NAMES:
            self.response_type = RESPONSE_NAMES[response]
        self.work_status = MessageBody.read_byte(body, WORK_STATUS_BYTE)
        self.step_status = MessageBody.read_byte(body, STEP_STATUS_BYTE)
        self.work_stage = MessageBody.read_byte(body, WORK_STEP_BYTE)
        lid = MessageBody.read_byte(body, LID_STATUS_BYTE)
        if lid in LID_STATUS_NAMES:
            self.lid_status = LID_STATUS_NAMES[lid]
        cup = MessageBody.read_byte(body, CUP_STATUS_BYTE)
        if cup in CUP_STATUS_NAMES:
            self.cup_status = CUP_STATUS_NAMES[cup]
        self.current_time = MessageBody.read_byte(
            body,
            CUR_WORK_TIME_LO_BYTE,
        ) + (MessageBody.read_byte(body, CUR_WORK_TIME_HI_BYTE) << BYTE_SHIFT)
        self.current_temp = MessageBody.read_byte(body, CUR_TEMPERATURE_BYTE)
        self.speed = MessageBody.read_byte(body, SPEED_BYTE)
        self.set_work_temp = MessageBody.read_byte(body, SET_WORK_TEMP_BYTE)
        self.set_keep_warm_temp = MessageBody.read_byte(body, SET_WARM_TEMP_BYTE)
        self.appoint_time = MessageBody.read_byte(
            body,
            APPOINT_TIME_LO_BYTE,
        ) + (MessageBody.read_byte(body, APPOINT_TIME_HI_BYTE) << BYTE_SHIFT)
        self.set_work_time = MessageBody.read_byte(
            body,
            SET_WORK_TIME_LO_BYTE,
        ) + (MessageBody.read_byte(body, SET_WORK_TIME_HI_BYTE) << BYTE_SHIFT)
        self.set_keep_warm_time = MessageBody.read_byte(body, SET_WARM_TIME_BYTE)
        self.code_id = MessageBody.read_byte(body, CODE_ID_BYTE)


class MessageF1Response(MessageResponse):
    """f1 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize f1 message response."""
        super().__init__(bytearray(message))
        body = super().body
        # Only decode a frame that is a full status record AND carries the
        # inner 0xAA 0x55 application-frame markers (Lua bodyBytes[0..1]); a
        # control echo / notify with a different inner selector must not be
        # reinterpreted as status and overwrite attributes with garbage.
        if (
            self.message_type
            in (MessageType.set, MessageType.query, MessageType.notify1)
            and len(body) >= STATUS_REPORT_MIN_LEN
            and body[INNER_HEAD_BYTE] == INNER_HEAD
            and body[INNER_HEAD2_BYTE] == INNER_HEAD2
        ):
            self.set_body(F1GeneralMessageBody(body))
        self.set_attr()

"""Midea lan ef message.

Protocol layout follows Meiju Lua ``T_0000_EF_3`` (beverage / drink maker). The
Midea body wraps an inner ``0xAA 0x55 ...`` application sub-frame, so the first
body byte (``0xAA``) maps to the generic ``body_type`` byte in this framework
and every Lua ``messageBytes[n]`` offset is the response body offset ``body[n]``.

- Query: message type 0x03, 8-byte inner frame with the 0x31 query selector.
- Control: message type 0x02, 20-byte inner frame with the 0x20 selector,
  carrying cmd_code, cmd_id, a packed reserve/warm/drink_style flag byte,
  reserve time, warm time and temperature_setting.
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
SELECTOR_QUERY = 0x31  # bodyBytes[3] for a query
SELECTOR_CONTROL = 0x20  # bodyBytes[3] for a control

# Packed flag bits in body[12] / control body[9] (Lua bit.band masks).
RESERVE_MASK = 0x01  # reserve on
WARM_MASK = 0x02  # warm on
DRINK_STYLE_MASK = 0x04  # 0x04 -> warm_drink, 0 -> hot_drink

# Report body offsets (Lua binToModel messageBytes[n]).
CMD_CODE_LO_BYTE = 4
CMD_CODE_HI_BYTE = 5
WORK_STATUS_BYTE = 8
ERROR_CODE_BYTE = 9
RESPONSE_TYPE_BYTE = 10
CMD_ID_BYTE = 11
FLAG_BYTE = 12
WORK_STEP_BYTE = 13
PROCESS_STATUS_BYTE = 14
TIME_WORK_HR_BYTE = 15
TIME_WORK_MIN_BYTE = 16
TIME_MAX_BYTE = 17
TEMPERATURE_SETTING_BYTE = 18
TEMPERATURE_CURRENT_BYTE = 19
# Lua binToModel requires at least 11 body bytes; the full record needs body[19].
REPORT_MIN_LEN = 11
STATUS_REPORT_MIN_LEN = TEMPERATURE_CURRENT_BYTE + 1

# Control body offsets (Lua jsonToData bodyBytes[n]).
CTRL_CMD_CODE_LO_BYTE = 4
CTRL_CMD_CODE_HI_BYTE = 5
CTRL_CMD_ID_BYTE = 8
CTRL_FLAG_BYTE = 9
CTRL_TIME_RESERVE_HR_BYTE = 10
CTRL_TIME_RESERVE_MIN_BYTE = 11
CTRL_TIME_WARM_HR_BYTE = 12
CTRL_TIME_WARM_MIN_BYTE = 13
CTRL_TEMPERATURE_SETTING_BYTE = 14

# response type (Lua BYTE_RESPONSE_*).
RESPONSE_ERROR = 0x00
RESPONSE_NORMAL = 0x01
RESPONSE_NAMES: dict[int, str] = {
    RESPONSE_NORMAL: "response_normal",
    RESPONSE_ERROR: "response_error",
}

# drink_style labels (Lua VALUE_WARM_DRINK / VALUE_HOT_DRINK).
DRINK_WARM = "warm_drink"
DRINK_HOT = "hot_drink"

CMD_CODE_SHIFT = 8
CMD_CODE_LOW_MASK = 0xFF

# Parameter ranges (Lua checkBoundary bounds).
CMD_ID_LOW = 0
CMD_ID_HIGH = 255
TIME_HR_LOW = 0
TIME_HR_HIGH = 23
TIME_MIN_LOW = 0
TIME_MIN_HIGH = 59
TEMPERATURE_LOW = 0
TEMPERATURE_HIGH = 98
CMD_CODE_LOW = 0
CMD_CODE_HIGH = 0xFFFF


class MessageEFBase(MessageRequest):
    """ef message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize ef message base."""
        super().__init__(
            device_type=DeviceType.EF,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageEFBase):
    """ef message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize ef message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(INNER_HEAD),
        )

    @property
    def _body(self) -> bytearray:
        # The inner query frame; body_type already carries body[0] (0xAA).
        return bytearray([INNER_HEAD2, 0x00, SELECTOR_QUERY, 0x00, 0x00, 0x00, 0x00])


class MessageSet(MessageEFBase):
    """ef control: cmd_code / cmd_id / flags / time / temperature_setting."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize ef message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(INNER_HEAD),
        )
        self.cmd_code = 0
        self.cmd_id = 0
        self.reserve = False
        self.warm = False
        self.drink_style = DRINK_HOT
        self.time_reserve_hr = 0
        self.time_reserve_min = 0
        self.time_warm_hr = 0
        self.time_warm_min = 0
        self.temperature_setting = 0

    @property
    def _flag_byte(self) -> int:
        """Pack reserve / warm / drink_style into the Lua flag byte."""
        flag = 0
        if self.reserve:
            flag |= RESERVE_MASK
        if self.warm:
            flag |= WARM_MASK
        if self.drink_style == DRINK_WARM:
            flag |= DRINK_STYLE_MASK
        return flag

    @property
    def _body(self) -> bytearray:
        # The inner control frame; body_type already carries body[0] (0xAA).
        return bytearray(
            [
                INNER_HEAD2,
                0x00,
                SELECTOR_CONTROL,
                self.cmd_code & CMD_CODE_LOW_MASK,
                (self.cmd_code >> CMD_CODE_SHIFT) & CMD_CODE_LOW_MASK,
                0x00,
                0x00,
                self.cmd_id,
                self._flag_byte,
                self.time_reserve_hr,
                self.time_reserve_min,
                self.time_warm_hr,
                self.time_warm_min,
                self.temperature_setting,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class EFGeneralMessageBody(MessageBody):
    """ef status body (Lua binToModel)."""

    cmd_code: int
    work_status: int
    error_code: int
    response_type: str
    cmd_id: int
    reserve: bool
    warm: bool
    drink_style: str
    work_step: int
    process_status: int
    time_work_hr: int
    time_work_min: int
    time_max: int
    temperature_setting: int
    temperature_current: int

    def __init__(self, body: bytearray) -> None:
        """Initialize ef message general body."""
        super().__init__(body)
        self.cmd_code = (
            MessageBody.read_byte(body, CMD_CODE_HI_BYTE) << CMD_CODE_SHIFT
        ) + MessageBody.read_byte(body, CMD_CODE_LO_BYTE)
        self.work_status = MessageBody.read_byte(body, WORK_STATUS_BYTE)
        self.error_code = MessageBody.read_byte(body, ERROR_CODE_BYTE)
        response = MessageBody.read_byte(body, RESPONSE_TYPE_BYTE)
        if response in RESPONSE_NAMES:
            self.response_type = RESPONSE_NAMES[response]
        self.cmd_id = MessageBody.read_byte(body, CMD_ID_BYTE)
        flag = MessageBody.read_byte(body, FLAG_BYTE)
        self.reserve = bool(flag & RESERVE_MASK)
        self.warm = bool(flag & WARM_MASK)
        self.drink_style = DRINK_WARM if flag & DRINK_STYLE_MASK else DRINK_HOT
        self.work_step = MessageBody.read_byte(body, WORK_STEP_BYTE)
        self.process_status = MessageBody.read_byte(body, PROCESS_STATUS_BYTE)
        self.time_work_hr = MessageBody.read_byte(body, TIME_WORK_HR_BYTE)
        self.time_work_min = MessageBody.read_byte(body, TIME_WORK_MIN_BYTE)
        self.time_max = MessageBody.read_byte(body, TIME_MAX_BYTE)
        self.temperature_setting = MessageBody.read_byte(
            body,
            TEMPERATURE_SETTING_BYTE,
        )
        self.temperature_current = MessageBody.read_byte(
            body,
            TEMPERATURE_CURRENT_BYTE,
        )


class MessageEFResponse(MessageResponse):
    """ef message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize ef message response."""
        super().__init__(bytearray(message))
        body = super().body
        if (
            self.message_type
            in (MessageType.set, MessageType.query, MessageType.notify1)
            and len(body) >= STATUS_REPORT_MIN_LEN
        ):
            self.set_body(EFGeneralMessageBody(body))
        self.set_attr()

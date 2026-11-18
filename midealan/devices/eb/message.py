"""Midea lan eb message.

Protocol layout follows Meiju Lua ``T_0000_EB_3`` (steam / warming cooking
appliance). The Midea body wraps an inner ``0xAA 0x55 ...`` application
sub-frame, so the first body byte (``0xAA``) maps to the generic ``body_type``
byte in this framework and every Lua ``messageBytes[n]`` offset is the response
body offset ``body[n]`` directly.

- Query: message type 0x03, 15-byte inner frame carrying cmd code 0xC353.
- Control: message type 0x02, 17-byte inner frame carrying cmd code 0x2711 with
  function_no, work_status, reserve time, fire_level and definite time.
- Report (0x02 / 0x03, or 0x04 with cmd 0x2714 / 0x2716) decodes the status
  record; 0x2716 carries only error_code.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Inner application sub-frame markers (Lua bodyBytes[0..2]).
INNER_HEAD = 0xAA  # bodyBytes[0]
INNER_HEAD2 = 0x55  # bodyBytes[1]
PRODUCT_TYPE = 0x02  # BYTE_PRODUCT_TYPE
ATTR_FROM_APP = 0x82  # BYTE_ATTRIBUTE_TYPE_FROM_APP
CMD_WORD = 0xA0  # BYTE_CMD_WORD

# Inner body lengths (Lua BYTE_BODY_LENGTH_*).
BODY_LENGTH_QUERY = 0x0F
BODY_LENGTH_CONTROL = 0x11

# cmd codes, low/high (Lua BYTE_CMD_CODE_*).
CMD_QUERY_LOW = 0x53
CMD_QUERY_HIGH = 0xC3
CMD_CONTROL_LOW = 0x11
CMD_CONTROL_HIGH = 0x27
# Report cmd codes carried at body[7]/body[8] for notify (0x04) frames.
CMD_REPORT_STATUS_LOW = 0x14
CMD_REPORT_ERROR_LOW = 0x16
CMD_REPORT_HIGH = 0x27

# response type (Lua BYTE_RESPONSE_*).
RESPONSE_ERROR = 0x00
RESPONSE_NORMAL = 0x01
RESPONSE_NAMES: dict[int, str] = {
    RESPONSE_NORMAL: "response_normal",
    RESPONSE_ERROR: "response_error",
}

# Report body offsets (Lua binToModel messageBytes[n]).
CMD_CODE_LOW_BYTE = 7
CMD_CODE_HIGH_BYTE = 8
RESPONSE_BYTE = 9
WORK_STATUS_BYTE = 10
FUNCTION_NO_HI_BYTE = 11
FUNCTION_NO_LO_BYTE = 12
TIME_RUNNING_HR_BYTE = 13
TIME_RUNNING_MIN_BYTE = 14
TIME_SURPLUS_HR_BYTE = 15
TIME_SURPLUS_MIN_BYTE = 16
TIME_RESERVE_HR_BYTE = 17
TIME_RESERVE_MIN_BYTE = 18
FIRE_LEVEL_BYTE = 19
DEFINITE_TIME_HR_BYTE = 20
DEFINITE_TIME_MIN_BYTE = 21
WORK_STAGE_BYTE = 22
ERROR_CODE_BYTE = 23
# Lua binToModel requires at least 11 body bytes; the full status record needs
# up to body[23].
REPORT_MIN_LEN = 11
STATUS_REPORT_MIN_LEN = ERROR_CODE_BYTE + 1
# Error-only notify (0x2716) carries error_code at body[10].
ERROR_ONLY_CODE_BYTE = 10

FUNCTION_NO_SHIFT = 8
FUNCTION_NO_LOW_MASK = 0xFF

# Parameter ranges (Lua checkBoundary bounds).
TIME_MIN_LOW = 0
TIME_MIN_HIGH = 59
TIME_HR_LOW = 0
TIME_HR_HIGH = 23
FIRE_LEVEL_LOW = 0
FIRE_LEVEL_HIGH = 21


class MessageEBBase(MessageRequest):
    """eb message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize eb message base."""
        super().__init__(
            device_type=DeviceType.EB,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageEBBase):
    """eb message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize eb message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # body[0] is the inner 0xAA frame head.
            body_type=ListTypes(INNER_HEAD),
        )

    @property
    def _body(self) -> bytearray:
        # The inner query frame; body_type already carries body[0] (0xAA).
        return bytearray(
            [
                INNER_HEAD2,
                PRODUCT_TYPE,
                0x00,
                BODY_LENGTH_QUERY,
                ATTR_FROM_APP,
                CMD_WORD,
                CMD_QUERY_LOW,
                CMD_QUERY_HIGH,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class MessageSet(MessageEBBase):
    """eb control: function_no / work_status / time / fire_level."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize eb message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(INNER_HEAD),
        )
        self.function_no = 0
        self.work_status = 0
        self.time_reserve_hr = 0
        self.time_reserve_min = 0
        self.fire_level = 0
        self.definite_time_hr = 0
        self.definite_time_min = 0

    @property
    def _body(self) -> bytearray:
        # The inner control frame; body_type already carries body[0] (0xAA).
        return bytearray(
            [
                INNER_HEAD2,
                PRODUCT_TYPE,
                0x00,
                BODY_LENGTH_CONTROL,
                ATTR_FROM_APP,
                CMD_WORD,
                CMD_CONTROL_LOW,
                CMD_CONTROL_HIGH,
                (self.function_no >> FUNCTION_NO_SHIFT) & FUNCTION_NO_LOW_MASK,
                self.function_no & FUNCTION_NO_LOW_MASK,
                self.work_status,
                self.time_reserve_hr,
                self.time_reserve_min,
                self.fire_level,
                self.definite_time_hr,
                self.definite_time_min,
            ],
        )


class EBGeneralMessageBody(MessageBody):
    """eb status body (Lua binToModel full status record)."""

    response: str
    work_status: int
    function_no: int
    time_running_hr: int
    time_running_min: int
    time_surplus_hr: int
    time_surplus_min: int
    time_reserve_hr: int
    time_reserve_min: int
    fire_level: int
    definite_time_hr: int
    definite_time_min: int
    work_stage: int
    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize eb message general body."""
        super().__init__(body)
        response = MessageBody.read_byte(body, RESPONSE_BYTE)
        if response in RESPONSE_NAMES:
            self.response = RESPONSE_NAMES[response]
        self.work_status = MessageBody.read_byte(body, WORK_STATUS_BYTE)
        self.function_no = (
            MessageBody.read_byte(body, FUNCTION_NO_HI_BYTE) << FUNCTION_NO_SHIFT
        ) + MessageBody.read_byte(body, FUNCTION_NO_LO_BYTE)
        self.time_running_hr = MessageBody.read_byte(body, TIME_RUNNING_HR_BYTE)
        self.time_running_min = MessageBody.read_byte(body, TIME_RUNNING_MIN_BYTE)
        self.time_surplus_hr = MessageBody.read_byte(body, TIME_SURPLUS_HR_BYTE)
        self.time_surplus_min = MessageBody.read_byte(body, TIME_SURPLUS_MIN_BYTE)
        self.time_reserve_hr = MessageBody.read_byte(body, TIME_RESERVE_HR_BYTE)
        self.time_reserve_min = MessageBody.read_byte(body, TIME_RESERVE_MIN_BYTE)
        self.fire_level = MessageBody.read_byte(body, FIRE_LEVEL_BYTE)
        self.definite_time_hr = MessageBody.read_byte(body, DEFINITE_TIME_HR_BYTE)
        self.definite_time_min = MessageBody.read_byte(body, DEFINITE_TIME_MIN_BYTE)
        self.work_stage = MessageBody.read_byte(body, WORK_STAGE_BYTE)
        self.error_code = MessageBody.read_byte(body, ERROR_CODE_BYTE)


class EBErrorMessageBody(MessageBody):
    """eb error-only notify body (Lua cmd 0x2716)."""

    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize eb error-only body."""
        super().__init__(body)
        self.error_code = MessageBody.read_byte(body, ERROR_ONLY_CODE_BYTE)


class MessageEBResponse(MessageResponse):
    """eb message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize eb message response."""
        super().__init__(bytearray(message))
        body = super().body
        if len(body) < REPORT_MIN_LEN:
            self.set_attr()
            return
        if (
            self.message_type in (MessageType.set, MessageType.query)
            and len(body) >= STATUS_REPORT_MIN_LEN
        ):
            self.set_body(EBGeneralMessageBody(body))
        elif self.message_type == MessageType.notify1:
            cmd_low = MessageBody.read_byte(body, CMD_CODE_LOW_BYTE)
            cmd_high = MessageBody.read_byte(body, CMD_CODE_HIGH_BYTE)
            if (
                cmd_low == CMD_REPORT_STATUS_LOW
                and cmd_high == CMD_REPORT_HIGH
                and len(body) >= STATUS_REPORT_MIN_LEN
            ):
                self.set_body(EBGeneralMessageBody(body))
            elif cmd_low == CMD_REPORT_ERROR_LOW and cmd_high == CMD_REPORT_HIGH:
                self.set_body(EBErrorMessageBody(body))
        self.set_attr()

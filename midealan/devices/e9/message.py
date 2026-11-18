"""Midea lan e9 message.

Protocol layout follows Meiju Lua ``T_0000_E9_3`` (bread / baking machine). The
Midea body wraps an inner ``0xAA 0x55 ...`` application sub-frame, so the first
body byte (``0xAA``) maps to the generic ``body_type`` byte in this framework
and every Lua ``messageBytes[n]`` offset is the response body offset ``body[n]``
directly.

- Query: message type 0x03, 9-byte inner frame carrying cmd code 0x52/0xC3
  (query status) and a trailing inner checksum byte.
- Control: message type 0x02, 19-byte inner frame carrying control_cmd_code,
  volume, color, dosing, work_status, cuisine time, reserve time and
  bake_temperature, plus a trailing inner checksum byte.
- Report decodes two layouts: the control-echo / notify record (data type
  0x02 / 0x04) places control_cmd_code at body[6]; the query-status response
  (data type 0x03, cmd low 0x52) shifts the same payload two bytes later
  because body[6]/body[7] hold the query cmd code. Query cmd low 0x50 carries
  only an error code and 0x51 carries the product volume.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Inner application sub-frame markers (Lua bodyBytes[0..2] / BYTE_TASK_TYPE).
INNER_HEAD = 0xAA  # bodyBytes[0]
INNER_HEAD2 = 0x55  # bodyBytes[1]
INNER_FLAG = 0x04  # bodyBytes[2]
TASK_TYPE_SETTING = 0x02  # BYTE_TASK_TYPE_SETTING, bodyBytes[5]

# Inner body lengths (Lua BYTE_BODY_LENGTH_*).
BODY_LENGTH_QUERY = 0x09
BODY_LENGTH_CONTROL = 0x13

# Query cmd code bytes (Lua BYTE_QUERY_CMD_CODE_*).
QUERY_CMD_STATUS = 0x52  # BYTE_QUERY_CMD_CODE_STATUS
QUERY_CMD_ERROR = 0x50  # BYTE_QUERY_CMD_CODE_ERROR
QUERY_CMD_INFO = 0x51  # BYTE_QUERY_CMD_CODE_INFO
QUERY_CMD_HIGH = 0xC3  # BYTE_QUERY_CMD_CODE_LOW (the high byte on the wire)

# response type (Lua BYTE_RESPONSE_*).
RESPONSE_NORMAL = 0x01
RESPONSE_ERROR_E2 = 0x0A
RESPONSE_NAMES: dict[int, str] = {
    RESPONSE_NORMAL: "response_normal",
    RESPONSE_ERROR_E2: "response_error_e2",
}

# Control body offsets (Lua jsonToData control bodyBytes[n]).
CTRL_CMD_CODE_LO_BYTE = 6
CTRL_CMD_CODE_HI_BYTE = 7
CTRL_VOLUME_BYTE = 8
CTRL_COLOR_BYTE = 9
CTRL_DOSING_BYTE = 10
CTRL_WORK_STATUS_BYTE = 11
CTRL_TIME_CUISINE_MIN_BYTE = 12
CTRL_TIME_CUISINE_HR_BYTE = 13
CTRL_TIME_RESERVE_MIN_BYTE = 14
CTRL_TIME_RESERVE_HR_BYTE = 15
CTRL_BAKE_TEMPERATURE_BYTE = 16

# Report body offsets relative to the control_cmd_code low byte (Lua
# binToModel). The control-echo / notify record starts at body[6]; the
# query-status record starts at body[8] (the two query cmd bytes precede it).
REPORT_BASE_PUSH = 6
REPORT_BASE_QUERY = 8
# Offsets from the base (shared by both layouts).
OFFSET_CMD_CODE_LO = 0
OFFSET_CMD_CODE_HI = 1
OFFSET_RESPONSE = 2
OFFSET_VOLUME = 3
OFFSET_COLOR = 4
OFFSET_DOSING = 5
OFFSET_WORK_STATUS = 6
OFFSET_WORK_STAGE = 7
OFFSET_BOTTOM_TEMPERATURE = 8
OFFSET_TIME_RESERVE_MIN = 9
OFFSET_TIME_RESERVE_HR = 10
OFFSET_TIME_WORK_MIN = 11
OFFSET_TIME_WORK_HR = 12
OFFSET_TIME_WARM_MIN = 13
OFFSET_TIME_WARM_HR = 14
OFFSET_ERROR_CODE = 15

# Query cmd code position in a query-status response (body[6]/body[7]).
QUERY_CMD_LOW_BYTE = 6
QUERY_CMD_HIGH_BYTE = 7
# Query error response (cmd low 0x50): body[8]/body[9].
QUERY_ERROR_RESPONSE_BYTE = 8
QUERY_ERROR_CODE_BYTE = 9
# Query info response (cmd low 0x51): body[8] response, body[15] product volume.
QUERY_INFO_RESPONSE_BYTE = 8
QUERY_INFO_PRODUCT_VOLUME_BYTE = 15

# Lua binToModel requires at least 11 body bytes before decoding anything.
REPORT_MIN_LEN = 11
# A full status record needs body[base + OFFSET_ERROR_CODE].
PUSH_REPORT_MIN_LEN = REPORT_BASE_PUSH + OFFSET_ERROR_CODE + 1
QUERY_STATUS_MIN_LEN = REPORT_BASE_QUERY + OFFSET_ERROR_CODE + 1
QUERY_ERROR_MIN_LEN = QUERY_ERROR_CODE_BYTE + 1
QUERY_INFO_MIN_LEN = QUERY_INFO_PRODUCT_VOLUME_BYTE + 1

CMD_CODE_SHIFT = 8
CMD_CODE_LOW_MASK = 0xFF
INNER_CHECKSUM_MOD = 256

# Parameter ranges. volume / color / dosing / work_status are raw bytes in this
# protocol version; the documented Lua enums bound their accepted values.
CMD_CODE_LOW = 0
CMD_CODE_HIGH = 0xFFFF
VOLUME_LOW = 0  # BYTE_VOLUME_NO
VOLUME_HIGH = 3  # BYTE_VOLUME_1000
COLOR_LOW = 0  # BYTE_COLOR_NO
COLOR_HIGH = 3  # BYTE_COLOR_DARK
DOSING_LOW = 0  # BYTE_DOSING_NO
DOSING_HIGH = 3  # BYTE_DOSING_YEAST_AND_FRUIT
WORK_STATUS_LOW = 0  # BYTE_STATUS_STANDBY
WORK_STATUS_HIGH = 4  # BYTE_STATUS_WARM
TIME_MIN_LOW = 0
TIME_MIN_HIGH = 59
TIME_HR_LOW = 0
TIME_HR_HIGH = 23
BAKE_TEMPERATURE_LOW = 0
BAKE_TEMPERATURE_HIGH = 255


def _inner_checksum(frame: list[int]) -> int:
    """Return the Lua makeSum two's-complement checksum over ``frame``."""
    total = sum(frame) & CMD_CODE_LOW_MASK
    return (INNER_CHECKSUM_MOD - total) & CMD_CODE_LOW_MASK


class MessageE9Base(MessageRequest):
    """e9 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize e9 message base."""
        super().__init__(
            device_type=DeviceType.E9,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageE9Base):
    """e9 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize e9 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # body[0] is the inner 0xAA frame head.
            body_type=ListTypes(INNER_HEAD),
        )

    @property
    def _body(self) -> bytearray:
        # Full inner frame including the head so the checksum covers body[0..7];
        # body_type already carries body[0] (0xAA), so return frame[1:].
        frame = [
            INNER_HEAD,
            INNER_HEAD2,
            INNER_FLAG,
            0x00,
            BODY_LENGTH_QUERY,
            TASK_TYPE_SETTING,
            QUERY_CMD_STATUS,
            QUERY_CMD_HIGH,
        ]
        frame.append(_inner_checksum(frame))
        return bytearray(frame[1:])


class MessageSet(MessageE9Base):
    """e9 control: recipe / volume / color / dosing / time / bake temperature."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize e9 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(INNER_HEAD),
        )
        self.control_cmd_code = 0
        self.volume = 0
        self.color = 0
        self.dosing = 0
        self.work_status = 0
        self.time_cuisine_min = 0
        self.time_cuisine_hr = 0
        self.time_reserve_min = 0
        self.time_reserve_hr = 0
        self.bake_temperature = 0

    @property
    def _body(self) -> bytearray:
        # Full inner frame including the head so the checksum covers body[0..17];
        # body_type already carries body[0] (0xAA), so return frame[1:].
        frame = [
            INNER_HEAD,
            INNER_HEAD2,
            INNER_FLAG,
            0x00,
            BODY_LENGTH_CONTROL,
            TASK_TYPE_SETTING,
            self.control_cmd_code & CMD_CODE_LOW_MASK,
            (self.control_cmd_code >> CMD_CODE_SHIFT) & CMD_CODE_LOW_MASK,
            self.volume,
            self.color,
            self.dosing,
            self.work_status,
            self.time_cuisine_min,
            self.time_cuisine_hr,
            self.time_reserve_min,
            self.time_reserve_hr,
            self.bake_temperature,
            0x00,
        ]
        frame.append(_inner_checksum(frame))
        return bytearray(frame[1:])


class E9GeneralMessageBody(MessageBody):
    """e9 status body (Lua binToModel full status record)."""

    control_cmd_code: int
    response_type: str
    volume: int
    color: int
    dosing: int
    work_status: int
    work_stage: int
    bottom_temperature: int
    time_reserve_min: int
    time_reserve_hr: int
    time_work_min: int
    time_work_hr: int
    time_warm_min: int
    time_warm_hr: int
    error_code: int

    def __init__(self, body: bytearray, base: int) -> None:
        """Initialize e9 message general body at the given payload base offset."""
        super().__init__(body)
        self.control_cmd_code = (
            MessageBody.read_byte(body, base + OFFSET_CMD_CODE_HI) << CMD_CODE_SHIFT
        ) + MessageBody.read_byte(body, base + OFFSET_CMD_CODE_LO)
        response = MessageBody.read_byte(body, base + OFFSET_RESPONSE)
        if response in RESPONSE_NAMES:
            self.response_type = RESPONSE_NAMES[response]
        self.volume = MessageBody.read_byte(body, base + OFFSET_VOLUME)
        self.color = MessageBody.read_byte(body, base + OFFSET_COLOR)
        self.dosing = MessageBody.read_byte(body, base + OFFSET_DOSING)
        self.work_status = MessageBody.read_byte(body, base + OFFSET_WORK_STATUS)
        self.work_stage = MessageBody.read_byte(body, base + OFFSET_WORK_STAGE)
        self.bottom_temperature = MessageBody.read_byte(
            body,
            base + OFFSET_BOTTOM_TEMPERATURE,
        )
        self.time_reserve_min = MessageBody.read_byte(
            body,
            base + OFFSET_TIME_RESERVE_MIN,
        )
        self.time_reserve_hr = MessageBody.read_byte(
            body,
            base + OFFSET_TIME_RESERVE_HR,
        )
        self.time_work_min = MessageBody.read_byte(body, base + OFFSET_TIME_WORK_MIN)
        # The Lua query-status branch mislabels this slot as timeWarmHr; the
        # control-echo branch reads it as timeWorkHr, which is the intent.
        self.time_work_hr = MessageBody.read_byte(body, base + OFFSET_TIME_WORK_HR)
        self.time_warm_min = MessageBody.read_byte(body, base + OFFSET_TIME_WARM_MIN)
        self.time_warm_hr = MessageBody.read_byte(body, base + OFFSET_TIME_WARM_HR)
        self.error_code = MessageBody.read_byte(body, base + OFFSET_ERROR_CODE)


class E9ErrorMessageBody(MessageBody):
    """e9 query error response body (Lua cmd low 0x50)."""

    response_type: str
    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize e9 query error body."""
        super().__init__(body)
        response = MessageBody.read_byte(body, QUERY_ERROR_RESPONSE_BYTE)
        if response in RESPONSE_NAMES:
            self.response_type = RESPONSE_NAMES[response]
        self.error_code = MessageBody.read_byte(body, QUERY_ERROR_CODE_BYTE)


class E9InfoMessageBody(MessageBody):
    """e9 query info response body (Lua cmd low 0x51)."""

    response_type: str
    product_volume: int

    def __init__(self, body: bytearray) -> None:
        """Initialize e9 query info body."""
        super().__init__(body)
        response = MessageBody.read_byte(body, QUERY_INFO_RESPONSE_BYTE)
        if response in RESPONSE_NAMES:
            self.response_type = RESPONSE_NAMES[response]
        self.product_volume = MessageBody.read_byte(
            body,
            QUERY_INFO_PRODUCT_VOLUME_BYTE,
        )


class MessageE9Response(MessageResponse):
    """e9 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize e9 message response."""
        super().__init__(bytearray(message))
        body = super().body
        if len(body) < REPORT_MIN_LEN:
            self.set_attr()
            return
        if self.message_type in (MessageType.set, MessageType.notify1):
            if len(body) >= PUSH_REPORT_MIN_LEN:
                self.set_body(E9GeneralMessageBody(body, REPORT_BASE_PUSH))
        elif self.message_type == MessageType.query:
            self._decode_query(body)
        self.set_attr()

    def _decode_query(self, body: bytearray) -> None:
        """Dispatch a query response on its cmd low byte (Lua dataType 0x03)."""
        cmd_low = MessageBody.read_byte(body, QUERY_CMD_LOW_BYTE)
        if cmd_low == QUERY_CMD_STATUS and len(body) >= QUERY_STATUS_MIN_LEN:
            self.set_body(E9GeneralMessageBody(body, REPORT_BASE_QUERY))
        elif cmd_low == QUERY_CMD_ERROR and len(body) >= QUERY_ERROR_MIN_LEN:
            self.set_body(E9ErrorMessageBody(body))
        elif cmd_low == QUERY_CMD_INFO and len(body) >= QUERY_INFO_MIN_LEN:
            self.set_body(E9InfoMessageBody(body))

"""Midea lan e7 message.

Protocol layout follows Meiju Lua ``T_0000_E7_5`` (steam / warming cooking
appliance, a sibling of the 0xEB family). The Midea body wraps an inner
``0xAA 0x55 ...`` application sub-frame, so the first body byte (``0xAA``) maps
to the generic ``body_type`` byte and every Lua ``messageBytes[n]`` offset is
the response body offset ``body[n]`` directly.

The frame layout depends on the device soft version, which the Lua derives from
``deviceSubType`` (``getSoftVersion``): subtype 6 -> v1 (16-bit function_no),
subtype 10 -> v3 and subtypes 8/9 -> v4 (both 32-bit function_no). The soft
version number is also written into the frame's device-protocol-version byte
(header byte[8]). v3 and v4 build byte-identical frames, so only two concrete
layouts exist: a 16-bit one (v1) and a 32-bit one (v3/v4).

- Query: message type 0x03, 15-byte inner frame carrying cmd code 0xC353
  (identical across all versions).
- Control: message type 0x02, carrying cmd code 0x2711 with function_no,
  work_status, reserve time, fire_level and definite time. The 16-bit frame is
  17 bytes; the 32-bit frame is 19 bytes.
- Report (0x02 / 0x03, or 0x04 with cmd 0x2714 / 0x2716) decodes the status
  record; the v1 0x2716 notify carries only error_code at body[10].
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Inner application sub-frame markers (Lua bodyBytes[0..2] / [5] / [6]).
INNER_HEAD = 0xAA  # bodyBytes[0]
INNER_HEAD2 = 0x55  # bodyBytes[1]
PRODUCT_TYPE = 0x02  # bodyBytes[2]
ATTR_FROM_APP = 0x82  # bodyBytes[5]
CMD_WORD = 0xA0  # bodyBytes[6]

# Inner body lengths (Lua BYTE bodyBytes[4]).
BODY_LENGTH_QUERY = 0x0F
BODY_LENGTH_CONTROL_16 = 0x11
BODY_LENGTH_CONTROL_32 = 0x13

# cmd codes, low/high (Lua BYTE_CMD_CODE_*).
CMD_QUERY_LOW = 0x53
CMD_QUERY_HIGH = 0xC3
CMD_CONTROL_LOW = 0x11
CMD_CONTROL_HIGH = 0x27
# Report cmd codes carried at body[7]/body[8] for notify (0x04) frames.
CMD_REPORT_STATUS_LOW = 0x14
CMD_REPORT_ERROR_LOW = 0x16
CMD_REPORT_HIGH = 0x27

# Soft version per deviceSubType (Lua getSoftVersion). v3 and v4 are
# byte-identical 32-bit frames; v1 is the legacy 16-bit frame.
SOFT_VERSION_V1 = 1
SOFT_VERSION_V3 = 3
SOFT_VERSION_V4 = 4
SOFT_VERSION_BY_SUBTYPE: dict[int, int] = {
    6: SOFT_VERSION_V1,
    10: SOFT_VERSION_V3,
    8: SOFT_VERSION_V4,
    9: SOFT_VERSION_V4,
}
# Lua maps an unlisted subtype to soft version 0 (no frame built). Modern e7
# appliances use the 32-bit layout, so default an unknown subtype to v3 to keep
# the device controllable instead of mute.
DEFAULT_SOFT_VERSION = SOFT_VERSION_V3
_SOFT_VERSIONS_32BIT = frozenset({SOFT_VERSION_V3, SOFT_VERSION_V4})


def soft_version_for_subtype(subtype: int) -> int:
    """Return the soft version for a device subtype (Lua getSoftVersion)."""
    return SOFT_VERSION_BY_SUBTYPE.get(subtype, DEFAULT_SOFT_VERSION)


def is_32bit_layout(soft_version: int) -> bool:
    """Whether a soft version uses the 32-bit function_no frame layout."""
    return soft_version in _SOFT_VERSIONS_32BIT


# response type (Lua BYTE_RESPONSE_*).
RESPONSE_ERROR = 0x00
RESPONSE_NORMAL = 0x01
RESPONSE_NAMES: dict[int, str] = {
    RESPONSE_NORMAL: "response_normal",
    RESPONSE_ERROR: "response_error",
}

# Report body offsets shared by both layouts (Lua binToModel messageBytes[n]).
CMD_CODE_LOW_BYTE = 7
CMD_CODE_HIGH_BYTE = 8
RESPONSE_BYTE = 9
WORK_STATUS_BYTE = 10
FUNCTION_NO_BYTE = 11  # start of the big-endian function_no field
# The trailing status fields start right after the function_no field, whose
# width depends on the layout (2 bytes for v1, 4 bytes for v3/v4).
FUNCTION_NO_WIDTH_16 = 2
FUNCTION_NO_WIDTH_32 = 4
# Offsets of the trailing fields measured from the first byte after function_no.
OFFSET_TIME_RUNNING_HR = 0
OFFSET_TIME_RUNNING_MIN = 1
OFFSET_TIME_SURPLUS_HR = 2
OFFSET_TIME_SURPLUS_MIN = 3
OFFSET_TIME_RESERVE_HR = 4
OFFSET_TIME_RESERVE_MIN = 5
OFFSET_FIRE_LEVEL = 6
OFFSET_DEFINITE_TIME_HR = 7
OFFSET_DEFINITE_TIME_MIN = 8
OFFSET_WORK_STAGE = 9
OFFSET_ERROR_CODE = 10
# Error-only notify (0x2716, v1) carries error_code at body[10].
ERROR_ONLY_CODE_BYTE = 10

# Lua binToModel requires at least 11 body bytes before decoding anything.
REPORT_MIN_LEN = 11

BYTE_MASK = 0xFF
BYTE_SHIFT = 8


def _status_min_len(*, is_32bit: bool) -> int:
    """Minimum body length to hold a full status record for a layout."""
    width = FUNCTION_NO_WIDTH_32 if is_32bit else FUNCTION_NO_WIDTH_16
    return FUNCTION_NO_BYTE + width + OFFSET_ERROR_CODE + 1


STATUS_MIN_LEN_16 = _status_min_len(is_32bit=False)
STATUS_MIN_LEN_32 = _status_min_len(is_32bit=True)

# Parameter ranges (Lua checkBoundary bounds).
TIME_MIN_LOW = 0
TIME_MIN_HIGH = 59
TIME_HR_LOW = 0
TIME_HR_HIGH = 23
FIRE_LEVEL_LOW = 0
FIRE_LEVEL_HIGH = 21
# function_no / work_status are raw (Lua string2Int, no boundary); bound
# function_no by the frame width so a value cannot silently truncate.
FUNCTION_NO_LOW = 0
FUNCTION_NO_HIGH_16 = 0xFFFF
FUNCTION_NO_HIGH_32 = 0xFFFFFFFF
WORK_STATUS_LOW = 0
WORK_STATUS_HIGH = 5  # BYTE_STATUS_POWER_OFF


class MessageE7Base(MessageRequest):
    """e7 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize e7 message base.

        ``protocol_version`` is the device soft version (1/3/4); it is written
        into the frame's device-protocol-version byte to mirror the Lua
        ``getSoftVersion`` value.
        """
        super().__init__(
            device_type=DeviceType.E7,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageE7Base):
    """e7 message query (identical content across soft versions)."""

    def __init__(self, soft_version: int) -> None:
        """Initialize e7 message query."""
        super().__init__(
            protocol_version=soft_version,
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


class MessageSet(MessageE7Base):
    """e7 control: function_no / work_status / time / fire_level."""

    def __init__(self, soft_version: int) -> None:
        """Initialize e7 message set."""
        super().__init__(
            protocol_version=soft_version,
            message_type=MessageType.set,
            body_type=ListTypes(INNER_HEAD),
        )
        self._is_32bit = is_32bit_layout(soft_version)
        self.function_no = 0
        self.work_status = 0
        self.time_reserve_hr = 0
        self.time_reserve_min = 0
        self.fire_level = 0
        self.definite_time_hr = 0
        self.definite_time_min = 0

    @property
    def _function_no_bytes(self) -> list[int]:
        """Big-endian function_no bytes for the active layout."""
        if self._is_32bit:
            return [
                (self.function_no >> 24) & BYTE_MASK,
                (self.function_no >> 16) & BYTE_MASK,
                (self.function_no >> BYTE_SHIFT) & BYTE_MASK,
                self.function_no & BYTE_MASK,
            ]
        return [
            (self.function_no >> BYTE_SHIFT) & BYTE_MASK,
            self.function_no & BYTE_MASK,
        ]

    @property
    def _body(self) -> bytearray:
        # The inner control frame; body_type already carries body[0] (0xAA).
        body_length = (
            BODY_LENGTH_CONTROL_32 if self._is_32bit else BODY_LENGTH_CONTROL_16
        )
        return bytearray(
            [
                INNER_HEAD2,
                PRODUCT_TYPE,
                0x00,
                body_length,
                ATTR_FROM_APP,
                CMD_WORD,
                CMD_CONTROL_LOW,
                CMD_CONTROL_HIGH,
                *self._function_no_bytes,
                self.work_status,
                self.time_reserve_hr,
                self.time_reserve_min,
                self.fire_level,
                self.definite_time_hr,
                self.definite_time_min,
            ],
        )


class E7GeneralMessageBody(MessageBody):
    """e7 status body (Lua binToModel full status record)."""

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

    def __init__(self, body: bytearray, *, is_32bit: bool) -> None:
        """Initialize e7 message general body for the given layout width."""
        super().__init__(body)
        response = MessageBody.read_byte(body, RESPONSE_BYTE)
        if response in RESPONSE_NAMES:
            self.response = RESPONSE_NAMES[response]
        self.work_status = MessageBody.read_byte(body, WORK_STATUS_BYTE)
        if is_32bit:
            self.function_no = (
                (MessageBody.read_byte(body, FUNCTION_NO_BYTE) << 24)
                + (MessageBody.read_byte(body, FUNCTION_NO_BYTE + 1) << 16)
                + (MessageBody.read_byte(body, FUNCTION_NO_BYTE + 2) << BYTE_SHIFT)
                + MessageBody.read_byte(body, FUNCTION_NO_BYTE + 3)
            )
            tail = FUNCTION_NO_BYTE + FUNCTION_NO_WIDTH_32
        else:
            self.function_no = (
                MessageBody.read_byte(body, FUNCTION_NO_BYTE) << BYTE_SHIFT
            ) + MessageBody.read_byte(body, FUNCTION_NO_BYTE + 1)
            tail = FUNCTION_NO_BYTE + FUNCTION_NO_WIDTH_16
        self.time_running_hr = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_RUNNING_HR,
        )
        self.time_running_min = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_RUNNING_MIN,
        )
        self.time_surplus_hr = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_SURPLUS_HR,
        )
        self.time_surplus_min = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_SURPLUS_MIN,
        )
        self.time_reserve_hr = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_RESERVE_HR,
        )
        self.time_reserve_min = MessageBody.read_byte(
            body,
            tail + OFFSET_TIME_RESERVE_MIN,
        )
        self.fire_level = MessageBody.read_byte(body, tail + OFFSET_FIRE_LEVEL)
        self.definite_time_hr = MessageBody.read_byte(
            body,
            tail + OFFSET_DEFINITE_TIME_HR,
        )
        self.definite_time_min = MessageBody.read_byte(
            body,
            tail + OFFSET_DEFINITE_TIME_MIN,
        )
        self.work_stage = MessageBody.read_byte(body, tail + OFFSET_WORK_STAGE)
        self.error_code = MessageBody.read_byte(body, tail + OFFSET_ERROR_CODE)


class E7ErrorMessageBody(MessageBody):
    """e7 error-only notify body (Lua v1 cmd 0x2716)."""

    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize e7 error-only body."""
        super().__init__(body)
        self.error_code = MessageBody.read_byte(body, ERROR_ONLY_CODE_BYTE)


class MessageE7Response(MessageResponse):
    """e7 message response."""

    def __init__(self, message: bytes, soft_version: int) -> None:
        """Initialize e7 message response for the device soft version."""
        super().__init__(bytearray(message))
        body = super().body
        if len(body) < REPORT_MIN_LEN:
            self.set_attr()
            return
        is_32bit = is_32bit_layout(soft_version)
        min_len = STATUS_MIN_LEN_32 if is_32bit else STATUS_MIN_LEN_16
        if self.message_type in (MessageType.set, MessageType.query):
            if len(body) >= min_len:
                self.set_body(E7GeneralMessageBody(body, is_32bit=is_32bit))
        elif self.message_type == MessageType.notify1:
            self._decode_notify(body, is_32bit=is_32bit, min_len=min_len)
        self.set_attr()

    def _decode_notify(
        self,
        body: bytearray,
        *,
        is_32bit: bool,
        min_len: int,
    ) -> None:
        """Dispatch a notify (0x04) frame on its cmd code (Lua binToModel)."""
        cmd_low = MessageBody.read_byte(body, CMD_CODE_LOW_BYTE)
        cmd_high = MessageBody.read_byte(body, CMD_CODE_HIGH_BYTE)
        if (
            cmd_low == CMD_REPORT_STATUS_LOW
            and cmd_high == CMD_REPORT_HIGH
            and len(body) >= min_len
        ):
            self.set_body(E7GeneralMessageBody(body, is_32bit=is_32bit))
        elif (
            cmd_low == CMD_REPORT_ERROR_LOW
            and cmd_high == CMD_REPORT_HIGH
            and not is_32bit
        ):
            # Only the v1 (16-bit) protocol defines the error-only notify.
            self.set_body(E7ErrorMessageBody(body))

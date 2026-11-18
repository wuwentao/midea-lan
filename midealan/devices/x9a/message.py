"""Midea lan x9a message.

Protocol layout follows Meiju Lua ``T_0000_9A_1`` (microwave / steam-bake
oven, 微波炉/电烤箱). The body is a sub-command record whose first byte selects
the frame family:

- Query request: message type 0x03, body ``[0x31]``.
- Query reply (0x03, body[0] == 0x31): fixed-offset status record.
- Control request (0x02) has two forms distinguished by ``body[1]``:
  - ``[0x22, 0x02, power, lock, furnace_light]`` -- power / lock / light, any
    unchanged field sent as ``0xFF``.
  - ``[0x22, 0x01, 0, 0, 0, 0, 0, hour, minutes, second, mode, temp_hi,
    temp_lo, 0, 0, watt, weight/10, 0xFF]`` -- a cook setting.
- Control echo (0x02, body[0] == 0x22) mirrors the request shape.

In this framework the leading sub-command byte (``0x31`` / ``0x22``) maps to
the generic ``body_type`` byte, so every Lua ``messageBytes[n]`` offset is the
response body offset ``body[n]`` directly.
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# Sub-command (Lua body[0]) selecting the frame family.
QUERY_CMD = 0x31  # lua query/report body[0]
CONTROL_CMD = 0x22  # lua control body[0]

# Control sub-form (Lua body[1]).
FORM_STATUS = 0x02  # power / lock / furnace_light
FORM_COOK = 0x01  # mode / time / temperature / watt / weight

# "field unchanged / invalid" sentinel (Lua 0xff).
VALUE_INVALID = 0xFF

# Query-reply body offsets (Lua updateGlobalPropertyValueByByte messageBytes[n]
# for dataType == query, body[0] == 0x31).
QUERY_WORK_STATUS_BYTE = 1
QUERY_HOUR_BYTE = 6
QUERY_MINUTES_BYTE = 7
QUERY_SECOND_BYTE = 8
QUERY_MODE_BYTE = 9
QUERY_CUR_TEMP_HI_BYTE = 10
QUERY_CUR_TEMP_LO_BYTE = 11
QUERY_WATT_BYTE = 14
QUERY_WEIGHT_BYTE = 15
QUERY_LOCK_BYTE = 16
QUERY_LIGHT_BYTE = 17
QUERY_TEMP_HI_BYTE = 18
QUERY_TEMP_LO_BYTE = 19
# Last decoded offset is body[19] (target temperature low byte).
QUERY_REPORT_MIN_LEN = 20

# Control-echo body offsets (Lua dataType == control, body[0] == 0x22).
ECHO_STATUS_WORK_STATUS_BYTE = 2
ECHO_STATUS_LOCK_BYTE = 3
ECHO_STATUS_LIGHT_BYTE = 4
ECHO_COOK_HOUR_BYTE = 7
ECHO_COOK_MINUTES_BYTE = 8
ECHO_COOK_SECOND_BYTE = 9
ECHO_COOK_MODE_BYTE = 10
ECHO_COOK_TEMP_HI_BYTE = 11
ECHO_COOK_TEMP_LO_BYTE = 12
ECHO_COOK_WATT_BYTE = 15
ECHO_COOK_WEIGHT_BYTE = 16
ECHO_STATUS_MIN_LEN = 5  # body[0..4]
ECHO_COOK_MIN_LEN = 17  # body[0..16]

# work_status / power decode (Lua VALUE_WORK_STATUS_* and power mapping).
WORK_STATUS_POWER_OFF = 0x01  # workstatus == 0x01 -> power off
WORK_STATUS_CANCEL = 0x02
WORK_STATUS_WORK = 0x03
WORK_STATUS_END = 0x04
WORK_STATUS_APPOINTMENT = 0x05
WORK_STATUS_PAUSE = 0x06
WORK_STATUS_NAMES: dict[int, str] = {
    WORK_STATUS_CANCEL: "cancel",
    WORK_STATUS_WORK: "work",
    WORK_STATUS_PAUSE: "pause",
    WORK_STATUS_END: "end",
    WORK_STATUS_APPOINTMENT: "appointment",
}
# Settable work_status values (Lua jsonToData FORM_STATUS branch).
WORK_STATUS_CODES: dict[str, int] = {
    "cancel": WORK_STATUS_CANCEL,
    "work": WORK_STATUS_WORK,
    "pause": WORK_STATUS_PAUSE,
}

# power control bytes (Lua VALUE_ON/VALUE_OFF -> 0x02 / 0x01).
POWER_ON = 0x02
POWER_OFF = 0x01

# lock / furnace_light control bytes (Lua VALUE_ON/VALUE_OFF -> 0x01 / 0x00).
FLAG_ON = 0x01
FLAG_OFF = 0x00

# lock / furnace_light decode masks (Lua bit.band on query reply).
LOCK_MASK = 0x01  # body[16] & 0x01
LIGHT_MASK = 0x04  # body[17] & 0x04

# mode code <-> name (Lua KEY_MODE mapping).
MODE_NAMES: dict[int, str] = {
    0xD0: "keep_warm",
    0x44: "stero_baking",
    0x47: "whole_baking",
    0x4C: "up_down_baking",
    0xA0: "unfreeze",
    0x71: "hot_air_convection",
    0x4D: "power_saving",
    0x76: "center_baking",
    0x4E: "rotary_baking",
    0xB0: "fermentation",
    0xC4: "stoving",
    0x49: "down_baking",
    0xB1: "pizza",
    0x81: "up_infrared_fan",
    0x01: "microwave",
}
MODE_CODES: dict[str, int] = {name: code for code, name in MODE_NAMES.items()}

# Cook-form body length (Lua bodyLength = 19, incl. the 0x22 sub-command byte).
COOK_BODY_LEN = 19
# Weight is reported/sent in units of 10 g (Lua weight = messageBytes[15] * 10).
WEIGHT_UNIT = 10
# Target temperature is a big-endian 16-bit value.
TEMP_BYTE_SHIFT = 8
TEMP_LOW_MASK = 0xFF


class Message9aBase(MessageRequest):
    """x9a message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize x9a message base."""
        super().__init__(
            device_type=DeviceType.X9A,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(Message9aBase):
    """x9a message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x9a message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            # Lua query body is the single sub-command byte 0x31.
            body_type=ListTypes(QUERY_CMD),
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageStatusSet(Message9aBase):
    """x9a control: power / lock / furnace_light (Lua FORM_STATUS 0x22 0x02).

    Any field left as ``VALUE_INVALID`` (0xFF) is treated as "no change".
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize x9a status set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CONTROL_CMD),
        )
        self.work_status = VALUE_INVALID
        self.lock = VALUE_INVALID
        self.furnace_light = VALUE_INVALID

    @property
    def _body(self) -> bytearray:
        # body_type byte is the 0x22 sub-command; FORM_STATUS record follows.
        return bytearray(
            [FORM_STATUS, self.work_status, self.lock, self.furnace_light],
        )


class MessageCookSet(Message9aBase):
    """x9a control: mode / time / temperature / watt / weight (Lua FORM_COOK)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x9a cook set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(CONTROL_CMD),
        )
        self.hour = 0
        self.minutes = 0
        self.second = 0
        self.mode = 0
        self.temperature = 0
        self.watt = VALUE_INVALID
        # weight is stored in grams; None means "unchanged" and only maps to the
        # 0xFF wire sentinel at serialization, so a real 255 g is not dropped.
        self.weight: int | None = None

    @property
    def _body(self) -> bytearray:
        # body_type byte is the 0x22 sub-command; the 18-byte FORM_COOK record
        # (Lua bodyBytes[1..18]) follows. weight is sent in units of 10 g.
        weight = VALUE_INVALID if self.weight is None else self.weight // WEIGHT_UNIT
        return bytearray(
            [
                FORM_COOK,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                self.hour,
                self.minutes,
                self.second,
                self.mode,
                (self.temperature >> TEMP_BYTE_SHIFT) & TEMP_LOW_MASK,
                self.temperature & TEMP_LOW_MASK,
                0x00,
                0x00,
                self.watt,
                weight,
                VALUE_INVALID,
            ],
        )


def _decode_work_status(raw: int) -> tuple[bool, str | None]:
    """Decode the raw work_status byte into (power, work_status label)."""
    power = raw != WORK_STATUS_POWER_OFF
    return power, WORK_STATUS_NAMES.get(raw)


class X9aQueryBody(MessageBody):
    """x9a query-reply status body (Lua query branch, body[0] == 0x31)."""

    power: bool
    work_status: str
    mode: str
    hour: int
    minutes: int
    second: int
    current_temperature: int
    temperature: int
    lock: bool
    furnace_light: bool
    watt: int
    weight: int
    error_code: int

    def __init__(self, body: bytearray) -> None:
        """Initialize x9a query body."""
        super().__init__(body)
        raw_status = MessageBody.read_byte(body, QUERY_WORK_STATUS_BYTE)
        self.power, work_status = _decode_work_status(raw_status)
        if work_status is not None:
            self.work_status = work_status
        mode = MessageBody.read_byte(body, QUERY_MODE_BYTE)
        if mode in MODE_NAMES:
            self.mode = MODE_NAMES[mode]
        self.hour = MessageBody.read_byte(body, QUERY_HOUR_BYTE)
        self.minutes = MessageBody.read_byte(body, QUERY_MINUTES_BYTE)
        self.second = MessageBody.read_byte(body, QUERY_SECOND_BYTE)
        self.current_temperature = (
            MessageBody.read_byte(body, QUERY_CUR_TEMP_HI_BYTE) << TEMP_BYTE_SHIFT
        ) + MessageBody.read_byte(body, QUERY_CUR_TEMP_LO_BYTE)
        self.temperature = (
            MessageBody.read_byte(body, QUERY_TEMP_HI_BYTE) << TEMP_BYTE_SHIFT
        ) + MessageBody.read_byte(body, QUERY_TEMP_LO_BYTE)
        self.lock = (
            MessageBody.read_byte(body, QUERY_LOCK_BYTE) & LOCK_MASK
        ) == LOCK_MASK
        self.furnace_light = (
            MessageBody.read_byte(body, QUERY_LIGHT_BYTE) & LIGHT_MASK
        ) == LIGHT_MASK
        self.watt = MessageBody.read_byte(body, QUERY_WATT_BYTE)
        self.weight = MessageBody.read_byte(body, QUERY_WEIGHT_BYTE) * WEIGHT_UNIT
        # Lua always reports errorCode 0 on a query reply.
        self.error_code = 0


class X9aControlEchoBody(MessageBody):
    """x9a control-echo body (Lua control branch, body[0] == 0x22).

    The echo mirrors whichever FORM the request used (``body[1]``).
    """

    power: bool
    work_status: str
    lock: bool
    furnace_light: bool
    hour: int
    minutes: int
    second: int
    mode: str
    temperature: int
    watt: int
    weight: int

    def __init__(self, body: bytearray) -> None:
        """Initialize x9a control-echo body."""
        super().__init__(body)
        form = MessageBody.read_byte(body, 1)
        if form == FORM_STATUS and len(body) >= ECHO_STATUS_MIN_LEN:
            raw_status = MessageBody.read_byte(body, ECHO_STATUS_WORK_STATUS_BYTE)
            self.power, work_status = _decode_work_status(raw_status)
            if work_status is not None:
                self.work_status = work_status
            self.lock = (
                MessageBody.read_byte(body, ECHO_STATUS_LOCK_BYTE) & LOCK_MASK
            ) == LOCK_MASK
            self.furnace_light = (
                MessageBody.read_byte(body, ECHO_STATUS_LIGHT_BYTE) == FLAG_ON
            )
        elif form == FORM_COOK and len(body) >= ECHO_COOK_MIN_LEN:
            self.hour = MessageBody.read_byte(body, ECHO_COOK_HOUR_BYTE)
            self.minutes = MessageBody.read_byte(body, ECHO_COOK_MINUTES_BYTE)
            self.second = MessageBody.read_byte(body, ECHO_COOK_SECOND_BYTE)
            mode = MessageBody.read_byte(body, ECHO_COOK_MODE_BYTE)
            if mode in MODE_NAMES:
                self.mode = MODE_NAMES[mode]
            self.temperature = (
                MessageBody.read_byte(body, ECHO_COOK_TEMP_HI_BYTE) << TEMP_BYTE_SHIFT
            ) + MessageBody.read_byte(body, ECHO_COOK_TEMP_LO_BYTE)
            self.watt = MessageBody.read_byte(body, ECHO_COOK_WATT_BYTE)
            self.weight = (
                MessageBody.read_byte(body, ECHO_COOK_WEIGHT_BYTE) * WEIGHT_UNIT
            )


class Message9aResponse(MessageResponse):
    """x9a message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize x9a message response."""
        super().__init__(bytearray(message))
        body = super().body
        body_cmd = self.body_type
        if (
            self.message_type in (MessageType.query, MessageType.notify1)
            and body_cmd == QUERY_CMD
            and len(body) >= QUERY_REPORT_MIN_LEN
        ):
            self.set_body(X9aQueryBody(body))
        elif (
            self.message_type in (MessageType.set, MessageType.notify2)
            and body_cmd == CONTROL_CMD
            and len(body) >= ECHO_STATUS_MIN_LEN
        ):
            self.set_body(X9aControlEchoBody(body))
        self.set_attr()

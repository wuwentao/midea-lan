"""Midea lan x44 message.

Lua: vendor/midea-lua/lua/0x44/T_0000_44_404M0001_2025121601.lua
The panel query is message type 0x03 with body ``08`` plus a function byte.
Function ``02`` is the screen-status record decoded by ``toScnJson``.
"""

from __future__ import annotations

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

BODY_TYPE = ListTypes.X08  # lua: bodyBytes[0] = 0x08
SCREEN_FUNC = 0x02  # lua: queryType / funcType 0x02, toScnJson
UNCHANGED = 0xFF  # lua: getBodyBytes fill; cmdTValue ignores 0xFF
SCREEN_PAYLOAD_LENGTH = 20  # lua: bodyBytes[1] through bodyBytes[20]

FUNC_BYTE = 1
HAS_TOKEN_BYTE = 2  # lua: "hasToken"
STATUS_BYTE = 3  # lua: "status"
ERROR_CODE_BYTE = 4  # lua: "errorCode"
BUTTON_BYTE = 5  # lua: leftButton, midButton, rightButton
SWITCH_BYTE = 6  # lua: shwBtnNamSw, clsTBrightSw, sleepMdSw, slpMdMuteSw
AUTO_OFF_BYTE = 7  # lua: "auOffScrnType"
THEME_BYTE = 8  # lua: "theme"
NIGHT_VOLUME_BYTE = 9  # lua: "nightVolume"
VOICE_VOLUME_BYTE = 10  # lua: "voiceVolume"
SLEEP_START_HOUR_BYTE = 11  # lua: "slpMdStartH"
SLEEP_START_MINUTE_BYTE = 12  # lua: "slpMdStartM"
SLEEP_DURATION_HOUR_BYTE = 13  # lua: "slpMdH"
SLEEP_DURATION_MINUTE_BYTE = 14  # lua: "slpMdM"
KEEP_BYTE = 15  # lua: left/middle/rightButtonKeepState
MODE_BYTE = 16  # lua: voiceCtrlSw, sleepMode, screenState
BRIGHTNESS_BYTE = 17  # lua: "brightness"
LEFT_WORK_MODE_BYTE = 18  # lua: "leftButtonWorkMode"
MIDDLE_WORK_MODE_BYTE = 19  # lua: "middleButtonWorkMode"
RIGHT_WORK_MODE_BYTE = 20  # lua: "rightButtonWorkMode"

LOW_MASK = 0x03
FIELD2_MASK = 0x0C
FIELD3_MASK = 0x30
FIELD4_MASK = 0xC0
FIELD2_ON = 0x04
FIELD2_OTHER = 0x08
FIELD3_ON = 0x10
FIELD3_OTHER = 0x20
FIELD4_ON = 0x40
FIELD4_OTHER = 0x80
FLAG_OFF = 0x00
FLAG_ON = 0x01
OTHER_VALUE = 2  # lua: bitTValue stores 2 for the middle pattern of each pair

HAS_TOKEN = "has_token"  # noqa: S105
PANEL_STATUS = "panel_status"
ERROR_CODE = "error_code"
LEFT_BUTTON = "left_button"
MIDDLE_BUTTON = "middle_button"
RIGHT_BUTTON = "right_button"
SHOW_BUTTON_NAME = "show_button_name"
CLOSE_SCREEN_BRIGHT = "close_screen_bright"
SLEEP_MODE_SWITCH = "sleep_mode_switch"
SLEEP_MODE_MUTE = "sleep_mode_mute"
AUTO_OFF_SCREEN_TYPE = "auto_off_screen_type"
THEME = "theme"
NIGHT_VOLUME = "night_volume"
VOICE_VOLUME = "voice_volume"
SLEEP_START_HOUR = "sleep_start_hour"
SLEEP_START_MINUTE = "sleep_start_minute"
SLEEP_DURATION_HOUR = "sleep_duration_hour"
SLEEP_DURATION_MINUTE = "sleep_duration_minute"
LEFT_BUTTON_KEEP = "left_button_keep"
MIDDLE_BUTTON_KEEP = "middle_button_keep"
RIGHT_BUTTON_KEEP = "right_button_keep"
VOICE_CONTROL = "voice_control"
SLEEP_MODE = "sleep_mode"
SCREEN_STATE = "screen_state"
BRIGHTNESS = "brightness"
LEFT_WORK_MODE = "left_button_work_mode"
MIDDLE_WORK_MODE = "middle_button_work_mode"
RIGHT_WORK_MODE = "right_button_work_mode"

_BitNames = tuple[str | None, str | None, str | None, str | None]
_BIT_GROUPS: tuple[tuple[int, _BitNames], ...] = (
    (BUTTON_BYTE, (LEFT_BUTTON, MIDDLE_BUTTON, RIGHT_BUTTON, None)),
    (
        SWITCH_BYTE,
        (SHOW_BUTTON_NAME, CLOSE_SCREEN_BRIGHT, SLEEP_MODE_SWITCH, SLEEP_MODE_MUTE),
    ),
    (KEEP_BYTE, (LEFT_BUTTON_KEEP, MIDDLE_BUTTON_KEEP, RIGHT_BUTTON_KEEP, None)),
    (MODE_BYTE, (VOICE_CONTROL, SLEEP_MODE, SCREEN_STATE, None)),
)
_BYTE_FIELDS: tuple[tuple[int, str], ...] = (
    (HAS_TOKEN_BYTE, HAS_TOKEN),
    (STATUS_BYTE, PANEL_STATUS),
    (ERROR_CODE_BYTE, ERROR_CODE),
    (AUTO_OFF_BYTE, AUTO_OFF_SCREEN_TYPE),
    (THEME_BYTE, THEME),
    (NIGHT_VOLUME_BYTE, NIGHT_VOLUME),
    (VOICE_VOLUME_BYTE, VOICE_VOLUME),
    (SLEEP_START_HOUR_BYTE, SLEEP_START_HOUR),
    (SLEEP_START_MINUTE_BYTE, SLEEP_START_MINUTE),
    (SLEEP_DURATION_HOUR_BYTE, SLEEP_DURATION_HOUR),
    (SLEEP_DURATION_MINUTE_BYTE, SLEEP_DURATION_MINUTE),
    (BRIGHTNESS_BYTE, BRIGHTNESS),
    (LEFT_WORK_MODE_BYTE, LEFT_WORK_MODE),
    (MIDDLE_WORK_MODE_BYTE, MIDDLE_WORK_MODE),
    (RIGHT_WORK_MODE_BYTE, RIGHT_WORK_MODE),
)
_FIELD_MASKS = (LOW_MASK, FIELD2_MASK, FIELD3_MASK, FIELD4_MASK)
_FIELD_ON = (FLAG_ON, FIELD2_ON, FIELD3_ON, FIELD4_ON)
_FIELD_OTHER = (FIELD2_OTHER, FIELD3_OTHER, FIELD4_OTHER)


def _decode_low(value: int) -> int | None:
    field = value & LOW_MASK
    if field == LOW_MASK:
        return None
    return field


def _decode_shifted(value: int, mask: int, on_bits: int, other_bits: int) -> int | None:
    field = value & mask
    if field == FLAG_OFF:
        return FLAG_OFF
    if field == on_bits:
        return FLAG_ON
    if field == other_bits:
        return OTHER_VALUE
    return None


def _decode_bits(value: int, names: tuple[str | None, ...]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    low_name = names[0]
    low = _decode_low(value)
    if low_name is not None and low is not None:
        parsed[low_name] = low
    for index, name in enumerate(names[1:], start=1):
        if name is None:
            continue
        decoded = _decode_shifted(
            value,
            _FIELD_MASKS[index],
            _FIELD_ON[index],
            _FIELD_OTHER[index - 1],
        )
        if decoded is not None:
            parsed[name] = decoded
    return parsed


def _encode_bits(values: dict[str, int], names: tuple[str | None, ...]) -> int:
    encoded = 0
    for index, name in enumerate(names):
        mask = _FIELD_MASKS[index]
        if name is None or name not in values:
            encoded |= mask
            continue
        if values[name] == FLAG_ON:
            encoded |= _FIELD_ON[index]
    return encoded


def _read_byte(body: bytearray, index: int) -> int | None:
    if len(body) <= index or body[index] == UNCHANGED:
        return None
    return body[index]


def parse_screen(body: bytearray) -> dict[str, int]:
    """Parse a function-0x02 screen body, including its leading 0x08."""
    attributes: dict[str, int] = {}
    for index, name in _BYTE_FIELDS:
        value = _read_byte(body, index)
        if value is not None:
            attributes[name] = value
    for index, names in _BIT_GROUPS:
        value = _read_byte(body, index)
        if value is not None:
            attributes.update(_decode_bits(value, names))
    return attributes


class MessageX44Base(MessageRequest):
    """X44 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize X44 message base."""
        super().__init__(
            device_type=DeviceType.X44,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageX44Base):
    """Query the screen-status record."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the screen query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=BODY_TYPE,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([SCREEN_FUNC])


class MessageSetScreen(MessageX44Base):
    """Set one or more screen fields. Unset bytes stay 0xFF."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize a screen set command."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=BODY_TYPE,
        )
        self.values: dict[str, int] = {}

    @property
    def _body(self) -> bytearray:
        payload = bytearray([UNCHANGED] * SCREEN_PAYLOAD_LENGTH)
        payload[FUNC_BYTE - 1] = SCREEN_FUNC
        for index, names in _BIT_GROUPS:
            payload[index - 1] = _encode_bits(self.values, names)
        for index, name in _BYTE_FIELDS:
            if name in self.values:
                payload[index - 1] = self.values[name]
        return payload


class X44ScreenBody(MessageBody):
    """Screen-status body."""

    def __init__(self, body: bytearray) -> None:
        """Parse a screen body when the function byte is 0x02."""
        super().__init__(body)
        self.attributes: dict[str, int] = {}
        if len(body) > FUNC_BYTE and body[FUNC_BYTE] == SCREEN_FUNC:
            self.attributes = parse_screen(body)


class MessageX44Response(MessageResponse):
    """X44 response."""

    def __init__(self, message: bytearray) -> None:
        """Initialize X44 response."""
        super().__init__(message)
        self.attributes: dict[str, int] = {}
        if (
            self.message_type
            in {
                MessageType.query,
                MessageType.set,
                MessageType.notify1,
            }
            and self.body_type == BODY_TYPE
        ):
            screen = X44ScreenBody(self.body)
            self.set_body(screen)
            self.attributes = screen.attributes
        self.set_attr()

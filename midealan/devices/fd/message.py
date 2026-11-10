"""Midea lan FD message."""

from midealan.const import DeviceType
from midealan.crc8 import calculate
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

DISINFECT_A0_BODY_LENGTH = 29
DISINFECT_C8_BODY_LENGTH = 36
FD_LUA_PROTOCOL_DEFAULT = ""
FD_LUA_PROTOCOL_25 = "25"
FD_LUA_PROTOCOL_25_MODELS = frozenset({"20200012"})
FD_LUA_PROTOCOL_2024110101 = "2024110101"
FD_LUA_PROTOCOL_2024110101_MODELS = frozenset({"202Z3119"})
SCREEN_DISPLAY_DIM_CODE = 6
SCREEN_DISPLAY_OFF_CODE = 7
FD_LUA_25_AUTO_FAN_SPEED = 101
FD_LUA_25_DISPLAY_STATUS_INDEX = 43
FD_LUA_25_DISPLAY_STATUS_OFF = 0x01
FD_LUA_25_DISPLAY_STATUS_ON = 0x02
FD_LUA_25_FAN_SPEED_SET_INDEX = 2
FD_LUA_25_FAN_SPEEDS = {
    1: "lowest",
    39: "low",
    59: "medium",
    80: "high",
    101: "auto",
}
FD_LUA_25_MANUAL_FAN_SPEEDS = frozenset({1, 39, 59, 80})
FD_LUA_25_MODE_AUTO = 0x02
FD_LUA_25_MODE_MANUAL = 0x01
FD_LUA_25_MODE_SET_INDEX = 10
FD_LUA_25_MODE_STATUS_INDEX = 13
FD_LUA_25_DISPLAY_SET_INDEX = 14
FD_LUA_25_DISPLAY_SET_OFF = 0x40
FD_LUA_25_DISPLAY_SET_ON = 0x80
FD_LUA_25_SCREEN_DISPLAYS = {0: "bright", SCREEN_DISPLAY_OFF_CODE: "off"}
FD_LUA_25_SET_BODY_LENGTH = 21
FD_LUA_25_TARGET_HUMIDITY_SET_INDEX = 6
FD_LUA_2024110101_AIR_DRY_OFF = 0x02
FD_LUA_2024110101_AIR_DRY_ON = 0x01
FD_LUA_2024110101_AIR_DRY_SET_INDEX = 20
FD_LUA_2024110101_AIR_DRY_STATUS_INDEX = 42
FD_LUA_2024110101_AIR_DRY_STATUS_MASK = 0x30
FD_LUA_2024110101_AIR_DRY_STATUS_SHIFT = 4
FD_LUA_2024110101_CONTROL_FLAGS = 0x42
FD_LUA_2024110101_DISINFECT_SET_INDEX = 14
FD_LUA_2024110101_FAN_SPEED_SET_INDEX = 2
FD_LUA_2024110101_FAN_SPEEDS = {39: "low", 59: "medium", 80: "high"}
FD_LUA_2024110101_MODE_SET_INDEX = 10
FD_LUA_2024110101_MODE_STATUS_INDEX = 13
FD_LUA_2024110101_MODES = {1: "manual", 7: "sleep", 8: "moist_skin"}
FD_LUA_2024110101_PROMPT_TONE_SET_INDEX = 9
FD_LUA_2024110101_PROMPT_TONE_STATUS_INDEX = 19
FD_LUA_2024110101_PROMPT_TONE_STATUS_MASK = 0x80
FD_LUA_2024110101_SCREEN_DISPLAY_SET_INDEX = 8
FD_LUA_2024110101_SCREEN_DISPLAY_STATUS_INDEX = 9
FD_LUA_2024110101_SCREEN_DISPLAYS = {
    0: "bright",
    SCREEN_DISPLAY_DIM_CODE: "dim",
    SCREEN_DISPLAY_OFF_CODE: "off",
}
FD_LUA_2024110101_SET_BODY_LENGTH = 24
FD_LUA_2024110101_TARGET_HUMIDITY_SET_INDEX = 6
MAX_FAN_SPEED = 5
MAX_MSG_SERIAL_NUM = 254


def get_fd_lua_protocol_hint(model: str) -> str:
    """Return an initial FD Lua protocol hint for a known model."""
    if model in FD_LUA_PROTOCOL_25_MODELS:
        return FD_LUA_PROTOCOL_25
    if model in FD_LUA_PROTOCOL_2024110101_MODELS:
        return FD_LUA_PROTOCOL_2024110101
    return FD_LUA_PROTOCOL_DEFAULT


def detect_fd_lua_protocol(body: bytearray) -> str:
    """Detect an FD Lua protocol from distinctive C8 status fields."""
    if len(body) > FD_LUA_2024110101_AIR_DRY_STATUS_INDEX:
        air_dry = (
            body[FD_LUA_2024110101_AIR_DRY_STATUS_INDEX]
            & FD_LUA_2024110101_AIR_DRY_STATUS_MASK
        ) >> FD_LUA_2024110101_AIR_DRY_STATUS_SHIFT
        if air_dry in {
            FD_LUA_2024110101_AIR_DRY_ON,
            FD_LUA_2024110101_AIR_DRY_OFF,
        }:
            return FD_LUA_PROTOCOL_2024110101
    if len(body) > FD_LUA_25_DISPLAY_STATUS_INDEX and body[
        FD_LUA_25_DISPLAY_STATUS_INDEX
    ] in {FD_LUA_25_DISPLAY_STATUS_OFF, FD_LUA_25_DISPLAY_STATUS_ON}:
        return FD_LUA_PROTOCOL_25
    return FD_LUA_PROTOCOL_DEFAULT


class MessageFDBase(MessageRequest):
    """FD message base."""

    _message_serial = 0

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize FD message base."""
        super().__init__(
            device_type=DeviceType.FD,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )
        MessageFDBase._message_serial += 1
        if MessageFDBase._message_serial >= MAX_MSG_SERIAL_NUM:
            MessageFDBase._message_serial = 1
        self._message_id = MessageFDBase._message_serial

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError

    @property
    def body(self) -> bytearray:
        """FD message base body."""
        body = bytearray([self.body_type]) + self._body + bytearray([self._message_id])
        body.append(calculate(body))
        return body


class MessageQuery(MessageFDBase):
    """FD message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize FD message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X41,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray(
            [
                0x81,
                0x00,
                0xFF,
                0x03,
                0x00,
                0x00,
                0x02,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class MessageSet(MessageFDBase):
    """FD message set."""

    def __init__(
        self,
        protocol_version: int,
        lua_protocol: str = FD_LUA_PROTOCOL_DEFAULT,
    ) -> None:
        """Initialize FD message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X48,
        )
        self.power = False
        self.fan_speed = 0
        self.target_humidity = 50
        self.prompt_tone = False
        self.screen_display: int | None = 0x07
        self.mode = 0x01
        self.disinfect: bool | None = None
        self.wet_pad_dry: bool | None = None
        self._lua_protocol = lua_protocol

    @property
    def _body(self) -> bytearray:
        power = 0x01 if self.power else 0x00
        prompt_tone = 0x40 if self.prompt_tone else 0x00
        disinfect = 0 if self.disinfect is None else (1 if self.disinfect else 2)
        if self._lua_protocol == FD_LUA_PROTOCOL_25:
            screen_display_code = self.screen_display
            if screen_display_code == 0:
                screen_display = FD_LUA_25_DISPLAY_SET_ON
            elif screen_display_code in {
                SCREEN_DISPLAY_DIM_CODE,
                SCREEN_DISPLAY_OFF_CODE,
            }:
                screen_display = FD_LUA_25_DISPLAY_SET_OFF
            else:
                screen_display = 0
            fan_speed = (
                self.fan_speed
                if self.mode == FD_LUA_25_MODE_MANUAL
                and self.fan_speed in FD_LUA_25_MANUAL_FAN_SPEEDS
                else 0
            )
            body = bytearray(FD_LUA_25_SET_BODY_LENGTH)
            body[0] = power | prompt_tone | 0x02
            body[FD_LUA_25_FAN_SPEED_SET_INDEX] = fan_speed
            body[FD_LUA_25_TARGET_HUMIDITY_SET_INDEX] = self.target_humidity
            body[FD_LUA_25_MODE_SET_INDEX] = self.mode
            body[FD_LUA_25_DISPLAY_SET_INDEX] = screen_display
            return body
        if self._lua_protocol == FD_LUA_PROTOCOL_2024110101:
            body = bytearray(FD_LUA_2024110101_SET_BODY_LENGTH)
            body[0] = power | FD_LUA_2024110101_CONTROL_FLAGS
            body[FD_LUA_2024110101_FAN_SPEED_SET_INDEX] = self.fan_speed
            body[FD_LUA_2024110101_TARGET_HUMIDITY_SET_INDEX] = self.target_humidity
            body[FD_LUA_2024110101_SCREEN_DISPLAY_SET_INDEX] = (
                self.screen_display if self.screen_display is not None else 0
            )
            body[FD_LUA_2024110101_PROMPT_TONE_SET_INDEX] = prompt_tone
            body[FD_LUA_2024110101_MODE_SET_INDEX] = self.mode
            body[FD_LUA_2024110101_DISINFECT_SET_INDEX] = disinfect
            if self.wet_pad_dry is not None:
                body[FD_LUA_2024110101_AIR_DRY_SET_INDEX] = (
                    FD_LUA_2024110101_AIR_DRY_ON
                    if self.wet_pad_dry
                    else FD_LUA_2024110101_AIR_DRY_OFF
                )
            return body
        return bytearray(
            [
                power | prompt_tone | 0x02,
                0x00,
                self.fan_speed,
                0x00,
                0x00,
                0x00,
                self.target_humidity,
                0x00,
                self.screen_display if self.screen_display is not None else 0,
                self.mode,
                0x00,
                0x00,
                0x00,
                0x00,
                disinfect,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class FDC8MessageBody(MessageBody):
    """FD message C8 body."""

    def __init__(
        self,
        body: bytearray,
        lua_protocol: str = FD_LUA_PROTOCOL_DEFAULT,
    ) -> None:
        """Initialize FD message C8 body."""
        super().__init__(body)
        self.lua_protocol = lua_protocol or detect_fd_lua_protocol(body)
        self.power = (body[1] & 0x01) > 0
        self.fan_speed = body[3] & 0x7F
        self.target_humidity = body[7]
        self.current_humidity = body[16]
        self.current_temperature = (body[17] - 50) / 2
        self.tank = body[10]
        if (
            self.lua_protocol == FD_LUA_PROTOCOL_25
            and len(body) > FD_LUA_25_DISPLAY_STATUS_INDEX
        ):
            self.mode = body[FD_LUA_25_MODE_STATUS_INDEX]
            if self.mode == FD_LUA_25_MODE_AUTO:
                self.fan_speed = FD_LUA_25_AUTO_FAN_SPEED
            display = body[FD_LUA_25_DISPLAY_STATUS_INDEX]
            if display == FD_LUA_25_DISPLAY_STATUS_ON:
                self.screen_display = 0
            elif display == FD_LUA_25_DISPLAY_STATUS_OFF:
                self.screen_display = SCREEN_DISPLAY_OFF_CODE
            else:
                self.screen_display = display
        elif (
            self.lua_protocol == FD_LUA_PROTOCOL_2024110101
            and len(body) > FD_LUA_2024110101_PROMPT_TONE_STATUS_INDEX
        ):
            self.mode = body[FD_LUA_2024110101_MODE_STATUS_INDEX]
            self.screen_display = (
                body[FD_LUA_2024110101_SCREEN_DISPLAY_STATUS_INDEX] & 0x07
            )
            self.prompt_tone = (
                body[FD_LUA_2024110101_PROMPT_TONE_STATUS_INDEX]
                & FD_LUA_2024110101_PROMPT_TONE_STATUS_MASK
            ) > 0
            if len(body) > FD_LUA_2024110101_AIR_DRY_STATUS_INDEX:
                air_dry = (
                    body[FD_LUA_2024110101_AIR_DRY_STATUS_INDEX]
                    & FD_LUA_2024110101_AIR_DRY_STATUS_MASK
                ) >> FD_LUA_2024110101_AIR_DRY_STATUS_SHIFT
                if air_dry:
                    self.wet_pad_dry = air_dry == FD_LUA_2024110101_AIR_DRY_ON
        else:
            self.mode = (body[8] & 0x70) >> 4
            self.screen_display = body[9] & 0x07
        if len(body) > DISINFECT_C8_BODY_LENGTH:
            disinfect = body[34] & 0x03
            if disinfect:
                self.disinfect = disinfect == 1


class FDA0MessageBody(MessageBody):
    """FD message A0 body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize FD message A0 body."""
        super().__init__(body)
        self.power = (body[1] & 0x01) > 0
        self.fan_speed = body[3] & 0x7F
        self.target_humidity = body[7]
        self.current_humidity = body[16]
        self.current_temperature = (body[17] - 50) / 2
        self.tank = body[10]
        self.mode = body[10] & 0x07
        self.screen_display = body[9] & 0x07
        if len(body) > DISINFECT_A0_BODY_LENGTH:
            disinfect = body[27] & 0x03
            if disinfect:
                self.disinfect = disinfect == 1


class MessageFDResponse(MessageResponse):
    """FD message response."""

    def __init__(
        self,
        message: bytes,
        lua_protocol: str = FD_LUA_PROTOCOL_DEFAULT,
    ) -> None:
        """Initialize FD message response."""
        super().__init__(bytearray(message))
        if self.message_type in [
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        ]:
            if self.body_type in [0xB0, 0xB1]:
                pass
            elif self.body_type == ListTypes.A0:
                self.set_body(FDA0MessageBody(super().body))
            elif self.body_type == ListTypes.C8:
                self.set_body(FDC8MessageBody(super().body, lua_protocol))
        self.set_attr()
        fan_speed = getattr(self, "fan_speed", None)
        if fan_speed is not None and fan_speed < MAX_FAN_SPEED:
            self.fan_speed = 1

"""Midea lan x13 device."""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

MAX_EFFECT = 5
MIN_FAN_SPEED = 1
MAX_FAN_SPEED = 100
# Fan-light models expect a six-byte set payload; the legacy layout uses four
# and the appliance silently ignores the shorter one (verified on M0200008).
FAN_LIGHT_PAYLOAD_LENGTH = 6
# A4 status body offsets. Fan-light models report the light power in a
# different byte and append the fan state to the same report.
LIGHT_POWER_BYTE = 8
LIGHT_POWER_BYTE_FAN_LIGHT = 5
FAN_SPEED_BYTE = 6
FAN_POWER_BYTE = 10


class Message13Base(MessageRequest):
    """X13 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize X13 message base."""
        super().__init__(
            device_type=DeviceType.X13,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(Message13Base):
    """X13 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize X13 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X24,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([0x00, 0x00, 0x00, 0x00])


class MessageSet(Message13Base):
    """X13 message set."""

    def __init__(
        self,
        protocol_version: int,
        fan_light: bool = False,
    ) -> None:
        """Initialize X13 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X00,
        )
        self.fan_light = fan_light
        self.brightness: int | None = None
        self.color_temperature: int | None = None
        self.effect: int | None = None
        self.power: bool | None = None
        self.fan_power: bool | None = None
        self.fan_speed: int | None = None

    @property
    def _body(self) -> bytearray:
        body_byte = 0x00
        if self.power is not None:
            self.body_type = ListTypes.X01
            body_byte = 0x01 if self.power else 0x00
        elif self.effect is not None and self.effect in range(1, 6):
            self.body_type = ListTypes.X01
            body_byte = self.effect + 1
        elif self.color_temperature is not None:
            self.body_type = ListTypes.X03
            body_byte = self.color_temperature
        elif self.brightness is not None:
            self.body_type = ListTypes.X04
            body_byte = self.brightness
        elif self.fan_power is not None:
            self.body_type = ListTypes.X31
            body_byte = 0x01 if self.fan_power else 0x00
        elif self.fan_speed is not None:
            self.body_type = ListTypes.X34
            body_byte = self.fan_speed
        body = bytearray([body_byte, 0x00, 0x00, 0x00])
        if self.fan_light:
            body += bytearray(FAN_LIGHT_PAYLOAD_LENGTH - len(body))
        return body


class MessageMainLightBody(MessageBody):
    """X13 message main light body."""

    def __init__(self, body: bytearray, fan_light: bool = False) -> None:
        """Initialize X13 message main light body."""
        super().__init__(body)
        self.brightness = self.read_byte(body, 1)
        self.color_temperature = self.read_byte(body, 2)
        self.effect = self.read_byte(body, 3) - 1
        if self.effect > MAX_EFFECT:
            self.effect = 1
        power_byte = LIGHT_POWER_BYTE_FAN_LIGHT if fan_light else LIGHT_POWER_BYTE
        self.power = self.read_byte(body, power_byte) > 0
        # Fan-light models append the fan state to the report; other X13
        # lights do not report a fan at all.
        self.fan_speed = self.read_byte(body, FAN_SPEED_BYTE) if fan_light else None
        self.fan_power = (
            self.read_byte(body, FAN_POWER_BYTE) > 0 if fan_light else False
        )


class MessageMainLightResponseBody(MessageBody):
    """X13 message main light response body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize X13 message main light response body."""
        super().__init__(body)
        self.control_success: bool = body[1] > 0


class Message13Response(MessageResponse):
    """X13 message response."""

    def __init__(self, message: bytes, fan_light: bool = False) -> None:
        """Initialize X13 message response."""
        super().__init__(bytearray(message))
        if self.body_type == ListTypes.A4:
            self.set_body(MessageMainLightBody(super().body, fan_light))
        elif self.message_type == MessageType.set and self.body_type > ListTypes.X80:
            self.set_body(MessageMainLightResponseBody(super().body))
        self.control_success: bool
        self.set_attr()

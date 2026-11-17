"""Midea lan A1 device message."""

from enum import IntEnum

from midealan.const import DeviceType, ProtocolVersion
from midealan.crc8 import calculate
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
    NewProtocolMessageBody,
)

MAX_MSG_SERIAL_NUM = 100
MIN_TARGET_HUMIDITY = 35
MIN_FAN_SPEED = 5

# This undocumented group is absent from the vendor Lua, but the device log in
# https://github.com/wuwentao/midea_ac_lan/issues/1230 confirms the query and
# response signature on model 00000Q1A. The response uses C8, so the complete
# prefix must be checked before falling back to the ordinary A1 C8 decoder.
GROUP_ONE_QUERY_BODY = (0x21, 0x01, 0x41, 0x00, 0x01)
GROUP_ONE_RESPONSE_PREFIX = bytes((0xC8, 0x21, 0x01, 0xC1))
GROUP_ONE_COMPRESSOR_INDEX = 4
GROUP_ONE_COMPRESSOR_RUNNING = 0x32
GROUP_ONE_EVAPORATOR_TEMPERATURE_INDEX = 11
GROUP_ONE_TEMPERATURE_OFFSET = 50
GROUP_ONE_TEMPERATURE_DIVISOR = 2
GROUP_ONE_MIN_LENGTH = GROUP_ONE_EVAPORATOR_TEMPERATURE_INDEX + 1


class NewProtocolTags(IntEnum):
    """New protocol tags."""

    light = 0x005B


class MessageA1Base(MessageRequest):
    """Message A1 Base."""

    _message_serial = 0

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize message A1 base."""
        super().__init__(
            device_type=DeviceType.A1,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )
        MessageA1Base._message_serial += 1
        if MessageA1Base._message_serial >= MAX_MSG_SERIAL_NUM:
            MessageA1Base._message_serial = 1
        self._message_id = MessageA1Base._message_serial

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError

    @property
    def body(self) -> bytearray:
        """Message A1 base body."""
        body = bytearray([self.body_type]) + self._body + bytearray([self._message_id])
        body.append(calculate(body))
        return body


class MessageQuery(MessageA1Base):
    """Message A1 query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize message A1 query."""
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
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class GroupOneQuery(MessageA1Base):
    """Query the verified A1 compressor and evaporator group."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the A1 group-one query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.X41,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray(GROUP_ONE_QUERY_BODY)


class NewProtocolQuery(MessageA1Base):
    """Message A1 new protocol query."""

    def __init__(self, protocol_version: ProtocolVersion) -> None:
        """Initialize message A1 new protocol query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes.B1,
        )

    @property
    def _body(self) -> bytearray:
        query_params = [NewProtocolTags.light]
        _body = bytearray([len(query_params)])
        for param in query_params:
            _body.extend([param & 0xFF, param >> 8])
        return _body


class MessageSet(MessageA1Base):
    """Message A1 set."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize message A1 set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X48,
        )
        self.power = False
        self.prompt_tone = False
        self.mode = 1
        self.fan_speed = 40
        self.child_lock = False
        self.target_humidity = 40
        self.swing = False
        self.anion = False
        self.pump = False
        self.pump_enable = False
        self.water_level_set = 50

    @property
    def _body(self) -> bytearray:
        # byte1, power, prompt_tone
        power = 0x01 if self.power else 0x00
        prompt_tone = 0x40 if self.prompt_tone else 0x00
        # byte2 mode
        mode = self.mode
        # byte3 fan_speed
        fan_speed = self.fan_speed
        # byte7 target_humidity
        target_humidity = self.target_humidity
        # byte8 child_lock
        child_lock = 0x80 if self.child_lock else 0x00
        # byte9 anion, pump, pump enable
        anion = 0x40 if self.anion else 0x00
        pump = 0x08 if self.pump else 0x00
        pump_enable = 0x10 if self.pump_enable else 0x00
        # byte10 swing
        swing = 0x08 if self.swing else 0x00
        # byte 13 water_level_set
        water_level_set = self.water_level_set
        return bytearray(
            [
                power | prompt_tone | 0x02,
                mode,
                fan_speed,
                0x00,
                0x00,
                0x00,
                target_humidity,
                child_lock,
                anion | pump | pump_enable,
                swing,
                0x00,
                0x00,
                water_level_set,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class NewProtocolSet(MessageA1Base):
    """Message A1 new protocol set."""

    def __init__(self, protocol_version: ProtocolVersion) -> None:
        """Initialize message A1 new protocol set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.B0,
        )
        self.light: bool | None = None

    @property
    def _body(self) -> bytearray:
        pack_count = 0
        payload = bytearray([0x00])
        if self.light is not None:
            pack_count += 1
            payload.extend(
                NewProtocolMessageBody.pack(
                    param=NewProtocolTags.light,
                    value=bytearray([0x01 if self.light else 0x00]),
                ),
            )
        payload[0] = pack_count
        return payload


class A1GeneralMessageBody(MessageBody):
    """A1 general message body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize A1 general message body."""
        super().__init__(body)
        self.power = (body[1] & 0x01) > 0
        self.mode = body[2] & 0x0F
        self.fan_speed = body[3] & 0x7F
        self.target_humidity = max(body[7], MIN_TARGET_HUMIDITY)
        self.child_lock = (body[8] & 0x80) > 0
        self.anion = (body[9] & 0x40) > 0
        self.pump = (body[9] & 0x08) > 0
        self.pump_enable = (body[9] & 0x10) > 0
        self.tank = body[10] & 0x7F
        self.water_level_set = body[15]
        self.current_humidity = body[16]
        self.current_temperature = (body[17] - 50) / 2
        self.swing = (body[19] & 0x20) > 0
        if self.fan_speed < MIN_FAN_SPEED:
            self.fan_speed = 1

        # add filter cleaning reminder attribute
        self.filter_cleaning_reminder = (body[9] & 0x80) > 0


class A1GroupOneMessageBody(MessageBody):
    """A1 compressor and evaporator group response body."""

    def __init__(self, body: bytearray) -> None:
        """Decode fields verified against the issue debug capture."""
        super().__init__(body)
        self.compressor = (
            body[GROUP_ONE_COMPRESSOR_INDEX] == GROUP_ONE_COMPRESSOR_RUNNING
        )
        self.evaporator_temperature = (
            body[GROUP_ONE_EVAPORATOR_TEMPERATURE_INDEX] - GROUP_ONE_TEMPERATURE_OFFSET
        ) / GROUP_ONE_TEMPERATURE_DIVISOR


class A1NewProtocolMessageBody(NewProtocolMessageBody):
    """A1 new protocol message body."""

    def __init__(self, body: bytearray) -> None:
        """Initialize A1 new protocol message body."""
        super().__init__(body)
        params = self.parse()
        if NewProtocolTags.light in params:
            self.light = params[NewProtocolTags.light][0] > 0


class MessageA1Response(MessageResponse):
    """A1 message response."""

    # Populated dynamically by MessageResponse.set_attr().
    compressor: bool
    evaporator_temperature: float

    def __init__(self, message: bytearray) -> None:
        """Initialize A1 message response."""
        super().__init__(message)
        body = super().body
        if self.message_type in [
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        ]:
            if (
                self.message_type == MessageType.query
                and body[: len(GROUP_ONE_RESPONSE_PREFIX)] == GROUP_ONE_RESPONSE_PREFIX
            ):
                if len(body) >= GROUP_ONE_MIN_LENGTH:
                    self.set_body(A1GroupOneMessageBody(body))
            elif self.body_type in [ListTypes.B0, ListTypes.B1, ListTypes.B5]:
                self.set_body(A1NewProtocolMessageBody(body))
            else:
                self.set_body(A1GeneralMessageBody(body))
        elif (
            self.message_type == MessageType.notify2 and self.body_type == ListTypes.A0
        ):
            self.set_body(A1GeneralMessageBody(body))
        self.set_attr()

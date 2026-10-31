"""COLMO microclimate air controls for verified model/subtype pairs."""

from typing import ClassVar

from midealan.message import ListTypes, MessageType, NewProtocolMessageBody

from .message import MessageACBase

COLMO_AIR_DEVICES = frozenset({("22019023", 44204)})
HUMIDIFY_TAG = 0x0235
FRESH_AIR_TAG = 0x0233
PURIFY_TAG = 0x0232
AIR_RECORD_LENGTHS = {PURIFY_TAG: 9, FRESH_AIR_TAG: 10, HUMIDIFY_TAG: 7}
AIR_POWER_OFF = 1
AIR_POWER_ON = 2
AIR_SPEEDS = {40: "low", 60: "medium", 80: "high", 100: "full"}
AIR_POWER_ATTRIBUTES = {
    "humidify": HUMIDIFY_TAG,
    "fresh_air_power": FRESH_AIR_TAG,
    "purify": PURIFY_TAG,
}
MESSAGE_HEADER_LENGTH = 10
MESSAGE_TYPE_INDEX = 9


class ColmoAirQuery(MessageACBase):
    """Independent query for the three shared-blower air functions."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize a COLMO air query."""
        super().__init__(protocol_version, MessageType.query, ListTypes.B1)

    @property
    def _body(self) -> bytearray:
        body = bytearray([len(AIR_RECORD_LENGTHS)])
        for tag in AIR_RECORD_LENGTHS:
            body.extend(tag.to_bytes(2, "little"))
        return body


class ColmoAirSet(MessageACBase):
    """Single-property command preserving the device's remaining fields."""

    def __init__(self, protocol_version: int, tag: int, record: bytearray) -> None:
        """Initialize a COLMO air command from its last confirmed record."""
        super().__init__(protocol_version, MessageType.set, ListTypes.B0)
        self._tag = tag
        self._record = bytearray(record)

    @property
    def _body(self) -> bytearray:
        return bytearray([1]) + NewProtocolMessageBody.pack(
            param=self._tag,
            value=self._record,
        )


class ColmoAirState:
    """Readback-driven switches and one shared auxiliary fan speed."""

    controls: ClassVar[frozenset[str]] = frozenset(
        {
            *AIR_POWER_ATTRIBUTES,
            "auxiliary_fan_mode",
            "fresh_air_mode",
            "fresh_air_fan_speed",
        },
    )

    def __init__(self) -> None:
        """Initialize an unknown state without assuming the switches are off."""
        self._records: dict[int, bytearray] = {}
        self._speed: int | None = None

    def process_message(self, message: bytes) -> dict[str, bool | int | str]:
        """Decode only valid live records, never a B5 capability response."""
        if len(message) <= MESSAGE_HEADER_LENGTH:
            return {}
        body_type = message[MESSAGE_HEADER_LENGTH]
        message_type = message[MESSAGE_TYPE_INDEX]
        if body_type not in {ListTypes.B0, ListTypes.B1, ListTypes.B5}:
            return {}
        if body_type == ListTypes.B5 and message_type == MessageType.query:
            return {}
        try:
            body = bytearray(message[MESSAGE_HEADER_LENGTH:-1])
            params = NewProtocolMessageBody(body).parse()
        except (IndexError, ValueError):
            return {}
        changed = False
        for tag, length in AIR_RECORD_LENGTHS.items():
            record = params.get(tag)
            if (
                record is None
                or len(record) != length
                or record[0] not in {AIR_POWER_OFF, AIR_POWER_ON}
                or record[1] not in AIR_SPEEDS
            ):
                continue
            self._records[tag] = bytearray(record)
            self._speed = record[1]
            changed = True
        if not changed or self._speed is None:
            return {}
        for record in self._records.values():
            record[1] = self._speed
        state: dict[str, bool | int | str] = {
            name: self._records[tag][0] == AIR_POWER_ON
            for name, tag in AIR_POWER_ATTRIBUTES.items()
            if tag in self._records
        }
        state["auxiliary_fan_mode"] = AIR_SPEEDS[self._speed]
        state["fresh_air_fan_speed"] = self._speed
        fresh_air_on = self._records.get(FRESH_AIR_TAG, bytearray([AIR_POWER_OFF]))[0]
        state["fresh_air_mode"] = (
            AIR_SPEEDS[self._speed] if fresh_air_on == AIR_POWER_ON else "off"
        )
        return state

    def make_command(
        self,
        protocol_version: int,
        attribute: str,
        value: bool | float | str,
    ) -> ColmoAirSet:
        """Build a validated command without guessing another switch's state."""
        if self._speed is None:
            raise ValueError("Air control state has not been reported")
        if attribute in AIR_POWER_ATTRIBUTES:
            if not isinstance(value, bool):
                raise ValueError("Air switch value must be boolean")
            tag = AIR_POWER_ATTRIBUTES[attribute]
            power = AIR_POWER_ON if value else AIR_POWER_OFF
            speed = self._speed
        else:
            if attribute == "fresh_air_mode" and value == "off":
                return self.make_command(protocol_version, "fresh_air_power", False)
            if attribute == "fresh_air_fan_speed":
                if isinstance(value, bool) or value not in AIR_SPEEDS:
                    raise ValueError("Unsupported auxiliary fan speed")
                speed = int(value)
            else:
                speed = next(
                    (speed for speed, name in AIR_SPEEDS.items() if name == value),
                    0,
                )
                if not speed:
                    raise ValueError("Unsupported auxiliary fan mode")
            if attribute == "auxiliary_fan_mode":
                tag = next(
                    (
                        tag
                        for tag, record in self._records.items()
                        if record[0] == AIR_POWER_ON
                    ),
                    HUMIDIFY_TAG,
                )
                if tag not in self._records:
                    raise ValueError("Air control state has not been reported")
                power = self._records[tag][0]
            else:
                tag = FRESH_AIR_TAG
                power = AIR_POWER_ON
        if tag not in self._records:
            raise ValueError("Air switch state has not been reported")
        record = bytearray(self._records[tag])
        record[0], record[1] = power, speed
        return ColmoAirSet(protocol_version, tag, record)

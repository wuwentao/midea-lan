"""Midea lan x70 message.

Protocol layout follows Meiju Lua ``T_0000_70_1`` (seasoning / spice dispenser,
调味机). Unlike the oven family (e7/e9/eb/ef) this device uses a *plain* body:
the standard 10-byte Midea header carries ``dataType`` in header byte[9] (the
framework ``message_type``) and the application payload starts right after the
header, so the first body byte (Lua ``bodyBytes[0]`` / ``messageBytes[0]``) is
the ``sub_cmd`` selector and maps onto the generic ``body_type`` byte. The Lua
``makeSum`` (``255 - sum + 1``) is identical to the framework checksum, so no
inner sub-frame or custom checksum is needed.

- Query (message type 0x03): a single ``0x01`` body byte.
- Status report (message type 0x03): ``sub_cmd`` then 1-8 fixed 14-byte box
  records (type, status, add-time Y/M/D/H/M/S, clean-time Y/M/D/H/M/S).
- Control (message type 0x02): ``sub_cmd`` (0x01 dispense / 0x02 set type),
  the seasoning count and ``(slot, value)`` pairs for slots 1..count.
- Control response (message type 0x02): ``sub_cmd`` then a control result byte.
- Auto report (message type 0x04): ``sub_cmd`` only (dispense complete / clean).
"""

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

# sub_cmd selectors (Lua paramTable["subCmd"] / body[0]).
SUB_CMD_OUTPUT = 0x01  # VALUE_SEASONING_OUTPUT (dispense by weight)
SUB_CMD_SET = 0x02  # VALUE_SEASONING_SET (assign box type)
# Query selector byte placed in the query body (Lua bodyBytes[0] = 0x01).
QUERY_SELECTOR = 0x01

# Body offsets, all measured from body[0] = sub_cmd (Lua messageBytes[n]).
SUB_CMD_BYTE = 0
CONTROL_RESULT_BYTE = 1  # set-response body[1]
# Box status record: first record starts at body[1], each record is 14 bytes.
BOX_RECORD_BASE = 1
BOX_RECORD_SIZE = 14
MAX_BOXES = 8
# Field offsets within one 14-byte box record.
BOX_TYPE_OFFSET = 0
BOX_STATUS_OFFSET = 1
BOX_ADD_YEAR_OFFSET = 2
BOX_ADD_MONTH_OFFSET = 3
BOX_ADD_DAY_OFFSET = 4
BOX_ADD_HOUR_OFFSET = 5
BOX_ADD_MINUTE_OFFSET = 6
BOX_ADD_SECOND_OFFSET = 7
BOX_CLEAN_YEAR_OFFSET = 8
BOX_CLEAN_MONTH_OFFSET = 9
BOX_CLEAN_DAY_OFFSET = 10
BOX_CLEAN_HOUR_OFFSET = 11
BOX_CLEAN_MINUTE_OFFSET = 12
BOX_CLEAN_SECOND_OFFSET = 13
# A query report needs at least one complete box record (body[0..14]).
STATUS_REPORT_MIN_LEN = BOX_RECORD_BASE + BOX_RECORD_SIZE
# A control report needs the sub_cmd plus the control-result byte.
CONTROL_REPORT_MIN_LEN = CONTROL_RESULT_BYTE + 1

# box_status labels (Lua: 0x01 -> "missing", 0x00 -> "no").
BOX_STATUS_NO = 0x00
BOX_STATUS_MISSING = 0x01
BOX_STATUS_NAMES: dict[int, str] = {
    BOX_STATUS_NO: "no",
    BOX_STATUS_MISSING: "missing",
}

# sub_cmd labels per dataType (Lua VALUE_* strings).
QUERY_SUB_CMD_NAMES: dict[int, str] = {
    SUB_CMD_OUTPUT: "query_device",
}
CONTROL_SUB_CMD_NAMES: dict[int, str] = {
    SUB_CMD_OUTPUT: "seasoning_output",
    SUB_CMD_SET: "seasoning_set",
}
NOTIFY_SUB_CMD_NAMES: dict[int, str] = {
    SUB_CMD_OUTPUT: "seasoning_complete",
    SUB_CMD_SET: "box_clean",
}

# control_result labels (Lua VALUE_SUCCESS / VALUE_DATA_OVERFLOW / VALUE_EXECUTION).
CONTROL_RESULT_SUCCESS = 0x00
CONTROL_RESULT_OVERFLOW = 0x01
CONTROL_RESULT_EXECUTION = 0x02
CONTROL_RESULT_NAMES: dict[int, str] = {
    CONTROL_RESULT_SUCCESS: "success",
    CONTROL_RESULT_OVERFLOW: "data_overflow",
    CONTROL_RESULT_EXECUTION: "execution",
}

# Parameter ranges (Lua checkBoundary bounds).
SEASONING_NUMBER_LOW = 1
SEASONING_NUMBER_HIGH = 8
SEASONING_VALUE_LOW = 1  # weight or type
SEASONING_VALUE_HIGH = 255

# Field name fragments used to build the per-box attribute names.
_BOX_ADD_FIELDS = (
    ("add_time_year", BOX_ADD_YEAR_OFFSET),
    ("add_time_month", BOX_ADD_MONTH_OFFSET),
    ("add_time_day", BOX_ADD_DAY_OFFSET),
    ("add_time_hour", BOX_ADD_HOUR_OFFSET),
    ("add_time_minute", BOX_ADD_MINUTE_OFFSET),
    ("add_time_second", BOX_ADD_SECOND_OFFSET),
)
_BOX_CLEAN_FIELDS = (
    ("clean_time_year", BOX_CLEAN_YEAR_OFFSET),
    ("clean_time_month", BOX_CLEAN_MONTH_OFFSET),
    ("clean_time_day", BOX_CLEAN_DAY_OFFSET),
    ("clean_time_hour", BOX_CLEAN_HOUR_OFFSET),
    ("clean_time_minute", BOX_CLEAN_MINUTE_OFFSET),
    ("clean_time_second", BOX_CLEAN_SECOND_OFFSET),
)


class MessageX70Base(MessageRequest):
    """x70 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize x70 message base."""
        super().__init__(
            device_type=DeviceType.X70,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageX70Base):
    """x70 message query."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize x70 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=ListTypes(QUERY_SELECTOR),
        )

    @property
    def _body(self) -> bytearray:
        # The whole query body is the single 0x01 selector, already carried by
        # body_type; there are no further payload bytes.
        return bytearray()


class MessageSetDispense(MessageX70Base):
    """x70 control: dispense seasonings 1..number by weight (sub_cmd 0x01)."""

    _sub_cmd: int = SUB_CMD_OUTPUT

    def __init__(self, protocol_version: int) -> None:
        """Initialize x70 dispense control."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes(self._sub_cmd),
        )
        self.number = SEASONING_NUMBER_LOW
        # Per-slot payload values (weights for dispense, types for set).
        self.values = [0] * MAX_BOXES

    @property
    def _body(self) -> bytearray:
        # body[0] (sub_cmd) is carried by body_type; emit the seasoning count
        # then a (slot, value) pair for each active slot 1..number.
        count = max(SEASONING_NUMBER_LOW, min(self.number, SEASONING_NUMBER_HIGH))
        body = bytearray([count])
        for slot in range(1, count + 1):
            body.append(slot)
            body.append(self.values[slot - 1])
        return body


class MessageSetType(MessageSetDispense):
    """x70 control: assign box types for slots 1..number (sub_cmd 0x02)."""

    _sub_cmd: int = SUB_CMD_SET


def _box_status_label(value: int) -> str | int:
    """Map a raw box status byte to its label, keeping the raw value if unknown."""
    return BOX_STATUS_NAMES.get(value, value)


class X70StatusBody(MessageBody):
    """x70 query status body (Lua binToModel, dataType 0x03).

    0x70 reports up to eight homogeneous 14-byte box records, so (like 0x9C)
    decoded values are collected into an ``attributes`` dict keyed by the Lua
    field name rather than as fixed instance attributes.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize x70 status body."""
        super().__init__(body)
        self.attributes: dict[str, object] = {
            "sub_cmd": QUERY_SUB_CMD_NAMES.get(
                MessageBody.read_byte(body, SUB_CMD_BYTE),
            ),
        }
        # Decode each complete 14-byte box record present in the body.
        for box in range(1, MAX_BOXES + 1):
            base = BOX_RECORD_BASE + BOX_RECORD_SIZE * (box - 1)
            if len(body) < base + BOX_RECORD_SIZE:
                break
            self._set_box(body, box, base)

    def _set_box(self, body: bytearray, box: int, base: int) -> None:
        """Decode one box record starting at ``base`` into box{N}_* attributes."""
        self.attributes[f"box{box}_type"] = MessageBody.read_byte(
            body,
            base + BOX_TYPE_OFFSET,
        )
        self.attributes[f"box{box}_status"] = _box_status_label(
            MessageBody.read_byte(body, base + BOX_STATUS_OFFSET),
        )
        for name, offset in (*_BOX_ADD_FIELDS, *_BOX_CLEAN_FIELDS):
            self.attributes[f"box{box}_{name}"] = MessageBody.read_byte(
                body,
                base + offset,
            )


class X70ControlResultBody(MessageBody):
    """x70 control-response body (Lua binToModel, dataType 0x02)."""

    def __init__(self, body: bytearray) -> None:
        """Initialize x70 control-result body."""
        super().__init__(body)
        result = MessageBody.read_byte(body, CONTROL_RESULT_BYTE)
        self.attributes: dict[str, object] = {
            "sub_cmd": CONTROL_SUB_CMD_NAMES.get(
                MessageBody.read_byte(body, SUB_CMD_BYTE),
            ),
            "control_result": CONTROL_RESULT_NAMES.get(result, result),
        }


class X70NotifyBody(MessageBody):
    """x70 auto-report body (Lua dataType 0x04): sub_cmd label only."""

    def __init__(self, body: bytearray) -> None:
        """Initialize x70 notify body."""
        super().__init__(body)
        self.attributes: dict[str, object] = {
            "sub_cmd": NOTIFY_SUB_CMD_NAMES.get(
                MessageBody.read_byte(body, SUB_CMD_BYTE),
            ),
        }


class MessageX70Response(MessageResponse):
    """x70 message response."""

    def __init__(self, message: bytes) -> None:
        """Initialize x70 message response."""
        super().__init__(bytearray(message))
        self.attributes: dict[str, object] = {}
        body = super().body
        parsed: MessageBody | None = None
        if (
            self.message_type == MessageType.query
            and len(body) >= STATUS_REPORT_MIN_LEN
        ):
            parsed = X70StatusBody(body)
        elif (
            self.message_type == MessageType.set and len(body) >= CONTROL_REPORT_MIN_LEN
        ):
            parsed = X70ControlResultBody(body)
        elif self.message_type == MessageType.notify1 and len(body) >= 1:
            parsed = X70NotifyBody(body)
        if parsed is not None:
            self.set_body(parsed)
            self.attributes = parsed.attributes  # type: ignore[attr-defined]
        self.set_attr()

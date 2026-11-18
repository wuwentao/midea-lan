"""Test x70 message."""

from collections.abc import Sequence

from midealan.const import DeviceType
from midealan.devices.x70.message import (
    MAX_BOXES,
    SUB_CMD_OUTPUT,
    SUB_CMD_SET,
    MessageQuery,
    MessageSetDispense,
    MessageSetType,
    MessageX70Response,
    X70ControlResultBody,
    X70NotifyBody,
    X70StatusBody,
)
from midealan.message import MessageBase, MessageType


def _frame(body: Sequence[int], message_type: int) -> bytes:
    """Wrap a body in a full x70 response frame (plain body, framework checksum)."""
    header = bytearray(
        [0xAA, 10 + len(body) + 1, DeviceType.X70, 0, 0, 0, 0, 0, 2, message_type],
    )
    stream = header + bytearray(body)
    stream.append(MessageBase.checksum(stream[1:]))
    return bytes(stream)


def _box_record(base: int) -> list[int]:
    """Return a 14-byte box record whose bytes carry recognizable values."""
    return [base + i for i in range(14)]


class TestMessageQuery:
    """Test x70 query encode."""

    def test_query_frame(self) -> None:
        """Query carries the single 0x01 selector and a valid checksum."""
        frame = MessageQuery(2).serialize()
        assert frame[0] == 0xAA
        assert frame[2] == DeviceType.X70
        assert frame[9] == MessageType.query
        # body is just body[0] = 0x01 (carried by body_type).
        assert list(frame[10:-1]) == [0x01]
        assert frame[-1] == MessageBase.checksum(frame[1:-1])


class TestMessageSet:
    """Test x70 control encode."""

    def test_dispense_pairs(self) -> None:
        """Dispense emits sub_cmd, count and (slot, weight) pairs."""
        message = MessageSetDispense(2)
        message.number = 3
        message.values = [10, 20, 30, 0, 0, 0, 0, 0]
        frame = message.serialize()
        assert frame[9] == MessageType.set
        assert list(frame[10:-1]) == [SUB_CMD_OUTPUT, 3, 1, 10, 2, 20, 3, 30]
        assert frame[-1] == MessageBase.checksum(frame[1:-1])

    def test_set_type_pairs(self) -> None:
        """Set-type uses the 0x02 sub_cmd with (slot, type) pairs."""
        message = MessageSetType(2)
        message.number = 2
        message.values = [5, 6, 0, 0, 0, 0, 0, 0]
        frame = message.serialize()
        assert list(frame[10:-1]) == [SUB_CMD_SET, 2, 1, 5, 2, 6]

    def test_number_clamped_to_bounds(self) -> None:
        """An out-of-range number is clamped to the 1..8 Lua bounds."""
        low = MessageSetDispense(2)
        low.number = 0
        assert low.serialize()[10:-1][1] == 1  # count byte clamped up to 1
        high = MessageSetDispense(2)
        high.number = 99
        high.values = list(range(1, MAX_BOXES + 1))
        body = list(high.serialize()[10:-1])
        assert body[1] == MAX_BOXES


class TestX70StatusBody:
    """Test x70 status body decode."""

    def test_single_box(self) -> None:
        """A one-record body decodes box1 and stops there."""
        body = bytearray([SUB_CMD_OUTPUT, *_box_record(1)])
        attrs = X70StatusBody(body).attributes
        assert attrs["sub_cmd"] == "query_device"
        assert attrs["box1_type"] == 1  # record[0]
        # record[1] == 2 is an unknown status byte and is kept as a raw int.
        assert attrs["box1_status"] == 2
        assert attrs["box1_add_time_year"] == 3  # record[2]
        assert attrs["box1_clean_time_second"] == 14  # record[13]
        assert "box2_type" not in attrs

    def test_status_labels_and_unknown(self) -> None:
        """box_status maps 0/1 to labels and keeps unknown raw values."""
        # status byte 0 -> "no"
        body_no = bytearray([SUB_CMD_OUTPUT, 7, 0, *([0] * 12)])
        assert X70StatusBody(body_no).attributes["box1_status"] == "no"
        # status byte 1 -> "missing"
        body_missing = bytearray([SUB_CMD_OUTPUT, 7, 1, *([0] * 12)])
        assert X70StatusBody(body_missing).attributes["box1_status"] == "missing"
        # unknown status byte kept as raw int
        body_raw = bytearray([SUB_CMD_OUTPUT, 7, 9, *([0] * 12)])
        assert X70StatusBody(body_raw).attributes["box1_status"] == 9

    def test_all_boxes(self) -> None:
        """A full 8-record body decodes every box."""
        body = [SUB_CMD_OUTPUT]
        for box in range(MAX_BOXES):
            body.extend(_box_record(box * 20 + 1))
        attrs = X70StatusBody(bytearray(body)).attributes
        assert attrs["box8_type"] == 7 * 20 + 1
        assert attrs["box8_clean_time_second"] == 7 * 20 + 14

    def test_unknown_sub_cmd(self) -> None:
        """An unrecognized sub_cmd decodes to None."""
        body = bytearray([0x09, *_box_record(1)])
        assert X70StatusBody(body).attributes["sub_cmd"] is None


class TestX70ControlResultBody:
    """Test x70 control-response decode."""

    def test_results(self) -> None:
        """Each control result byte maps to its label."""
        success = X70ControlResultBody(bytearray([SUB_CMD_OUTPUT, 0])).attributes
        assert success["control_result"] == "success"
        assert success["sub_cmd"] == "seasoning_output"
        overflow = X70ControlResultBody(bytearray([SUB_CMD_SET, 1])).attributes
        assert overflow["control_result"] == "data_overflow"
        execution = X70ControlResultBody(bytearray([SUB_CMD_OUTPUT, 2])).attributes
        assert execution["control_result"] == "execution"

    def test_unknown_result_and_sub_cmd(self) -> None:
        """Unknown result/sub_cmd keep raw / None."""
        attrs = X70ControlResultBody(bytearray([0x09, 0x7F])).attributes
        assert attrs["control_result"] == 0x7F
        assert attrs["sub_cmd"] is None


class TestX70NotifyBody:
    """Test x70 auto-report decode."""

    def test_labels(self) -> None:
        """Notify sub_cmd maps 0x01/0x02 to complete / clean."""
        complete = X70NotifyBody(bytearray([SUB_CMD_OUTPUT])).attributes
        assert complete["sub_cmd"] == "seasoning_complete"
        assert X70NotifyBody(bytearray([SUB_CMD_SET])).attributes["sub_cmd"] == (
            "box_clean"
        )
        assert X70NotifyBody(bytearray([0x09])).attributes["sub_cmd"] is None


class TestMessageX70Response:
    """Test x70 response dispatch."""

    def test_query_report(self) -> None:
        """A query reply builds a status body."""
        frame = _frame([SUB_CMD_OUTPUT, *_box_record(1)], MessageType.query)
        response = MessageX70Response(frame)
        assert response.attributes["box1_type"] == 1
        assert response.attributes["sub_cmd"] == "query_device"

    def test_control_report(self) -> None:
        """A control reply builds a control-result body."""
        frame = _frame([SUB_CMD_SET, 0], MessageType.set)
        response = MessageX70Response(frame)
        assert response.attributes["control_result"] == "success"

    def test_notify_report(self) -> None:
        """A notify builds a notify body."""
        frame = _frame([SUB_CMD_OUTPUT], MessageType.notify1)
        response = MessageX70Response(frame)
        assert response.attributes["sub_cmd"] == "seasoning_complete"

    def test_short_query_not_decoded(self) -> None:
        """A query body shorter than one box record is not decoded."""
        frame = _frame([SUB_CMD_OUTPUT, 1, 2], MessageType.query)
        response = MessageX70Response(frame)
        assert response.attributes == {}

    def test_other_message_type_not_decoded(self) -> None:
        """A notify2 message is not decoded by any branch."""
        frame = _frame([SUB_CMD_OUTPUT, *_box_record(1)], MessageType.notify2)
        response = MessageX70Response(frame)
        assert response.attributes == {}

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
        parsed = X70StatusBody(body)
        assert parsed.sub_cmd == "query_device"
        assert parsed.box1_type == 1  # record[0]
        # record[1] == 2 is an unknown status byte and is kept as a raw int.
        assert parsed.box1_status == 2
        assert parsed.box1_add_time_year == 3  # record[2]
        assert parsed.box1_clean_time_second == 14  # record[13]
        assert not hasattr(parsed, "box2_type")

    def test_status_labels_and_unknown(self) -> None:
        """box_status maps 0/1 to labels and keeps unknown raw values."""
        # status byte 0 -> "no"
        body_no = bytearray([SUB_CMD_OUTPUT, 7, 0, *([0] * 12)])
        assert X70StatusBody(body_no).box1_status == "no"
        # status byte 1 -> "missing"
        body_missing = bytearray([SUB_CMD_OUTPUT, 7, 1, *([0] * 12)])
        assert X70StatusBody(body_missing).box1_status == "missing"
        # unknown status byte kept as raw int
        body_raw = bytearray([SUB_CMD_OUTPUT, 7, 9, *([0] * 12)])
        assert X70StatusBody(body_raw).box1_status == 9

    def test_all_boxes(self) -> None:
        """A full 8-record body decodes every box."""
        body = [SUB_CMD_OUTPUT]
        for box in range(MAX_BOXES):
            body.extend(_box_record(box * 20 + 1))
        parsed = X70StatusBody(bytearray(body))
        assert parsed.box8_type == 7 * 20 + 1
        assert parsed.box8_clean_time_second == 7 * 20 + 14

    def test_unknown_sub_cmd(self) -> None:
        """An unrecognized sub_cmd decodes to None."""
        body = bytearray([0x09, *_box_record(1)])
        assert X70StatusBody(body).sub_cmd is None


class TestX70ControlResultBody:
    """Test x70 control-response decode."""

    def test_results(self) -> None:
        """Each control result byte maps to its label."""
        assert X70ControlResultBody(bytearray([SUB_CMD_OUTPUT, 0])).control_result == (
            "success"
        )
        assert X70ControlResultBody(bytearray([SUB_CMD_SET, 1])).control_result == (
            "data_overflow"
        )
        assert X70ControlResultBody(bytearray([SUB_CMD_OUTPUT, 2])).control_result == (
            "execution"
        )
        assert X70ControlResultBody(bytearray([SUB_CMD_OUTPUT, 0])).sub_cmd == (
            "seasoning_output"
        )

    def test_unknown_result_and_sub_cmd(self) -> None:
        """Unknown result/sub_cmd keep raw / None."""
        parsed = X70ControlResultBody(bytearray([0x09, 0x7F]))
        assert parsed.control_result == 0x7F
        assert parsed.sub_cmd is None


class TestX70NotifyBody:
    """Test x70 auto-report decode."""

    def test_labels(self) -> None:
        """Notify sub_cmd maps 0x01/0x02 to complete / clean."""
        assert X70NotifyBody(bytearray([SUB_CMD_OUTPUT])).sub_cmd == "seasoning_complete"
        assert X70NotifyBody(bytearray([SUB_CMD_SET])).sub_cmd == "box_clean"
        assert X70NotifyBody(bytearray([0x09])).sub_cmd is None


class TestMessageX70Response:
    """Test x70 response dispatch."""

    def test_query_report(self) -> None:
        """A query reply builds a status body."""
        frame = _frame([SUB_CMD_OUTPUT, *_box_record(1)], MessageType.query)
        response = MessageX70Response(frame)
        assert getattr(response, "box1_type") == 1  # noqa: B009
        assert getattr(response, "sub_cmd") == "query_device"  # noqa: B009

    def test_control_report(self) -> None:
        """A control reply builds a control-result body."""
        frame = _frame([SUB_CMD_SET, 0], MessageType.set)
        response = MessageX70Response(frame)
        assert getattr(response, "control_result") == "success"  # noqa: B009

    def test_notify_report(self) -> None:
        """A notify builds a notify body."""
        frame = _frame([SUB_CMD_OUTPUT], MessageType.notify1)
        response = MessageX70Response(frame)
        assert getattr(response, "sub_cmd") == "seasoning_complete"  # noqa: B009

    def test_short_query_not_decoded(self) -> None:
        """A query body shorter than one box record is not decoded."""
        frame = _frame([SUB_CMD_OUTPUT, 1, 2], MessageType.query)
        response = MessageX70Response(frame)
        assert not hasattr(response, "box1_type")

    def test_other_message_type_not_decoded(self) -> None:
        """A notify2 message is not decoded by any branch."""
        frame = _frame([SUB_CMD_OUTPUT, *_box_record(1)], MessageType.notify2)
        response = MessageX70Response(frame)
        assert not hasattr(response, "box1_type")

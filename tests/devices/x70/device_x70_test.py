"""Test x70 device."""

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.x70 import (
    ALL_ATTRIBUTES,
    MideaX70Device,
)
from midealan.devices.x70.message import (
    MAX_BOXES,
    SUB_CMD_OUTPUT,
    SUB_CMD_SET,
    MessageSetDispense,
    MessageSetType,
)
from midealan.exceptions import ValueOutOfRange, ValueWrongType
from midealan.message import MessageBase, MessageType


def _frame(body: Sequence[int], message_type: int) -> bytes:
    """Wrap a body in a full x70 response frame."""
    header = bytearray([0xAA, 10 + len(body) + 1, 0x70, 0, 0, 0, 0, 0, 2, message_type])
    stream = header + bytearray(body)
    stream.append(MessageBase.checksum(stream[1:]))
    return bytes(stream)


def _status_body() -> list[int]:
    """Build a one-record status body."""
    return [SUB_CMD_OUTPUT, 3, 0, 24, 1, 2, 3, 4, 5, 20, 6, 7, 8, 9, 10]


class TestMideaX70Device:
    """Test Midea x70 device."""

    @pytest.fixture
    def device(self) -> MideaX70Device:
        """x70 device on V3 transport."""
        return MideaX70Device(
            name="x70",
            device_id=1,
            ip_address="192.168.1.1",
            port=6444,
            token="00" * 32,
            key="00" * 32,
            device_protocol=ProtocolVersion.V3,
            model="",
            subtype=0,
            customize="",
        )

    def test_initial_attributes(self, device: MideaX70Device) -> None:
        """Every attribute starts unset."""
        assert len(device.attributes) == len(ALL_ATTRIBUTES)
        assert device.attributes["box1_type"] is None
        assert device.attributes["sub_cmd"] is None

    def test_build_query(self, device: MideaX70Device) -> None:
        """build_query returns a single MessageQuery."""
        queries = device.build_query()
        assert len(queries) == 1
        assert queries[0].serialize()[9] == MessageType.query

    def test_process_message(self, device: MideaX70Device) -> None:
        """A status report updates the box attributes."""
        new_status = device.process_message(_frame(_status_body(), MessageType.query))
        assert new_status["box1_type"] == 3
        assert new_status["box1_status"] == "no"
        assert device.attributes["box1_add_time_year"] == 24
        assert device.attributes["box1_clean_time_second"] == 10

    def test_process_control_report(self, device: MideaX70Device) -> None:
        """A control reply updates sub_cmd and control_result."""
        new_status = device.process_message(_frame([SUB_CMD_SET, 0], MessageType.set))
        assert new_status["control_result"] == "success"
        assert device.attributes["sub_cmd"] == "seasoning_set"

    def test_process_message_ignores_unknown_key(
        self,
        device: MideaX70Device,
    ) -> None:
        """A decoded key not in the attribute map is skipped."""
        with patch(
            "midealan.devices.x70.MessageX70Response",
        ) as response_cls:
            response_cls.return_value.attributes = {"not_an_attr": 1, "sub_cmd": "x"}
            new_status = device.process_message(b"")
        assert "not_an_attr" not in new_status
        assert new_status == {"sub_cmd": "x"}

    def test_dispense(self, device: MideaX70Device) -> None:
        """Dispense builds and sends a MessageSetDispense."""
        with patch.object(device, "build_send") as send:
            device.dispense(2, [10, 20])
        assert send.call_count == 1
        message = send.call_args[0][0]
        assert isinstance(message, MessageSetDispense)
        assert list(message.serialize()[10:-1]) == [SUB_CMD_OUTPUT, 2, 1, 10, 2, 20]

    def test_set_box_types(self, device: MideaX70Device) -> None:
        """set_box_types builds and sends a MessageSetType."""
        with patch.object(device, "build_send") as send:
            device.set_box_types(3, [5, 6, 7])
        message = send.call_args[0][0]
        assert isinstance(message, MessageSetType)
        assert list(message.serialize()[10:-1]) == [SUB_CMD_SET, 3, 1, 5, 2, 6, 3, 7]

    def test_dispense_pads_values(self, device: MideaX70Device) -> None:
        """Extra values beyond number are ignored and the slot list is padded."""
        with patch.object(device, "build_send") as send:
            device.dispense(1, [11, 22, 33])
        message = send.call_args[0][0]
        assert len(message.values) == MAX_BOXES
        assert list(message.serialize()[10:-1]) == [SUB_CMD_OUTPUT, 1, 1, 11]

    def test_number_out_of_range(self, device: MideaX70Device) -> None:
        """A number outside 1..8 raises ValueOutOfRange."""
        with pytest.raises(ValueOutOfRange):
            device.dispense(0, [])
        with pytest.raises(ValueOutOfRange):
            device.dispense(9, list(range(1, 10)))

    def test_too_few_values(self, device: MideaX70Device) -> None:
        """Fewer values than number raises ValueWrongType."""
        with pytest.raises(ValueWrongType):
            device.dispense(3, [10, 20])

    def test_non_integer_value(self, device: MideaX70Device) -> None:
        """A non-integer value raises ValueWrongType."""
        with pytest.raises(ValueWrongType):
            device.dispense(1, [True])

    def test_value_out_of_range(self, device: MideaX70Device) -> None:
        """A per-slot value outside 1..255 raises ValueOutOfRange."""
        with pytest.raises(ValueOutOfRange):
            device.dispense(1, [0])
        with pytest.raises(ValueOutOfRange):
            device.dispense(1, [256])

    def test_set_attribute_is_noop(self, device: MideaX70Device) -> None:
        """set_attribute never sends a frame (all attributes are read-only)."""
        with patch.object(device, "build_send") as send:
            device.set_attribute("box1_type", 5)
        assert send.call_count == 0

    def test_set_customize_refresh_interval(self, device: MideaX70Device) -> None:
        """A valid refresh_interval customize updates the refresh interval."""
        device.set_customize('{"refresh_interval": 15}')
        assert device._refresh_interval == 15

    def test_set_customize_invalid_type(self, device: MideaX70Device) -> None:
        """A non-numeric refresh_interval is logged and ignored."""
        before = device._refresh_interval
        device.set_customize('{"refresh_interval": "bad"}')
        assert device._refresh_interval == before

    def test_set_customize_invalid_json(self, device: MideaX70Device) -> None:
        """Malformed customize JSON is caught and ignored."""
        device.set_customize("{not json}")

    def test_set_customize_empty(self, device: MideaX70Device) -> None:
        """An empty customize string is a no-op."""
        device.set_customize("")

    def test_set_customize_without_interval(self, device: MideaX70Device) -> None:
        """Valid JSON lacking refresh_interval leaves the interval unchanged."""
        before = device._refresh_interval
        device.set_customize('{"other": 1}')
        assert device._refresh_interval == before

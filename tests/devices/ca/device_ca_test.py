"""Test CA Device."""

from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.ca import DeviceAttributes, MideaCADevice
from midealan.devices.ca.message import MessageQuery
from midealan.message import (
    MessageType,
    ToshibaMessageRequest,
    encode_toshiba_frame,
)

# Lua-derived fixture layout, intentionally independent of production constants.
_TOSHIBA_NORMAL_STATUS_LENGTH = 13
_TOSHIBA_SHIFTED_STATUS_LENGTH = 16
_TOSHIBA_POWER_FLAGS_OFFSET = 1
_TOSHIBA_NORMAL_MODE_OFFSET = 2
_TOSHIBA_NORMAL_DOOR_OFFSET = 8
_TOSHIBA_NORMAL_ENERGY_OFFSET = 11
_TOSHIBA_SHIFTED_MODE_OFFSET = 4
_TOSHIBA_SHIFTED_DOOR_OFFSET = 11
_TOSHIBA_SHIFTED_ENERGY_OFFSET = 14
_TOSHIBA_REFRIGERATOR_DOOR_MASK = 0x01
_TOSHIBA_FREEZER_DOOR_MASK = 0x02
_TOSHIBA_BAR_DOOR_MASK = 0x04
_TOSHIBA_FLEX_ZONE_DOOR_MASK = 0x08
_TOSHIBA_ALL_DOORS_MASK = 0x0F
_TOSHIBA_SHIFTED_MODEL = "0000000D"

DIAGNOSTIC_FLAGS = (
    (DeviceAttributes.code_mode, 1, 0x01),
    (DeviceAttributes.freezing_mode, 1, 0x02),
    (DeviceAttributes.smart_mode, 1, 0x04),
    (DeviceAttributes.energy_saving_mode, 1, 0x08),
    (DeviceAttributes.holiday_mode, 1, 0x10),
    (DeviceAttributes.moisturize_mode, 1, 0x20),
    (DeviceAttributes.preservation_mode, 1, 0x40),
    (DeviceAttributes.acme_freezing_mode, 1, 0x80),
    (DeviceAttributes.flood_light, 7, 0x10),
    (DeviceAttributes.freezing_ice_machine_power, 8, 0x80),
)


def _build_message(message_type: MessageType, body: bytearray) -> bytes:
    """Build a full CA response message."""
    header = bytearray(
        [0xAA] + ([0x0] * 7) + [ProtocolVersion.V1] + [message_type],
    )
    return bytes(header + body + bytearray([0x00]))


def _general_body(length: int) -> bytearray:
    """Build a CA general body with representative values."""
    body = bytearray(length)
    body[0] = 0x00
    body[2] = 0x35  # refrigerator 5, freezer -15
    body[3] = 5  # flex zone -14
    body[4] = 50  # right flex zone -20
    body[5] = 0x01  # variable mode soft_freezing
    body[12] = 0x10
    body[13] = 0x01  # energy consumption 272
    body[17] = 110  # refrigerator actual 5.0
    body[18] = 90  # freezer actual -5.0
    body[19] = 100  # flex actual 0.0
    body[20] = 120  # right flex actual 10.0
    return body


def _build_toshiba_device(
    manufacturer_code: str | None = "0008",
    *,
    model: str = "test_model",
) -> MideaCADevice:
    """Build a CA device with optional manufacturer identity."""
    identity = (
        {"manufacturer_code": manufacturer_code}
        if manufacturer_code is not None
        else {}
    )
    return MideaCADevice(
        name="Toshiba CA Device",
        device_id=2,
        ip_address="192.0.2.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model=model,
        subtype=1,
        customize="",
        **identity,
    )


def _toshiba_status_body(*, shifted: bool = False) -> bytearray:
    """Build a minimum complete Toshiba CA base-status body."""
    length = (
        _TOSHIBA_SHIFTED_STATUS_LENGTH if shifted else _TOSHIBA_NORMAL_STATUS_LENGTH
    )
    return bytearray(length)


class TestMideaCADevice:
    """Test Midea CA Device."""

    device: MideaCADevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea CA Device setup."""
        self.device = MideaCADevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.1",
            port=12345,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V1,
            model="test_model",
            subtype=1,
            customize="",
        )

    def test_initial_attributes(self) -> None:
        """Test initial attributes."""
        assert self.device.attributes[DeviceAttributes.mode] is None
        for attribute, _, _ in DIAGNOSTIC_FLAGS:
            assert self.device.attributes[attribute] is None
        assert self.device.attributes[DeviceAttributes.energy_consumption] is None
        assert self.device.attributes[DeviceAttributes.refrigerator_actual_temp] is None
        assert self.device.attributes[DeviceAttributes.freezer_actual_temp] is None
        assert self.device.attributes[DeviceAttributes.flex_zone_actual_temp] is None
        assert (
            self.device.attributes[DeviceAttributes.right_flex_zone_actual_temp] is None
        )
        assert (
            self.device.attributes[DeviceAttributes.refrigerator_setting_temp] is None
        )
        assert self.device.attributes[DeviceAttributes.freezer_setting_temp] is None
        assert self.device.attributes[DeviceAttributes.flex_zone_setting_temp] is None
        assert (
            self.device.attributes[DeviceAttributes.right_flex_zone_setting_temp]
            is None
        )
        assert (
            self.device.attributes[DeviceAttributes.refrigerator_door_overtime] is False
        )
        assert self.device.attributes[DeviceAttributes.freezer_door_overtime] is False
        assert self.device.attributes[DeviceAttributes.bar_door_overtime] is False
        assert self.device.attributes[DeviceAttributes.flex_zone_door_overtime] is False
        assert self.device.attributes[DeviceAttributes.refrigerator_door] is False
        assert self.device.attributes[DeviceAttributes.freezer_door] is False
        assert self.device.attributes[DeviceAttributes.bar_door] is False
        assert self.device.attributes[DeviceAttributes.flex_zone_door] is False
        assert self.device.attributes[DeviceAttributes.microcrystal_fresh] is False
        assert self.device.attributes[DeviceAttributes.electronic_smell] is False
        assert self.device.attributes[DeviceAttributes.humidity] is None
        assert self.device.attributes[DeviceAttributes.variable_mode] is None

    def test_build_query(self) -> None:
        """Test build query."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

    def test_toshiba_identity_builds_common_query(self) -> None:
        """Use the shared one-byte Toshiba CA query for manufacturer 0008."""
        device = _build_toshiba_device()
        queries = device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], ToshibaMessageRequest)
        assert queries[0].body == b"\x00"
        assert device.build_query_fallback() == []

    @pytest.mark.parametrize("frame_type", [MessageType.query, MessageType.notify1])
    def test_toshiba_normal_query_and_notify_base_status(
        self,
        frame_type: MessageType,
    ) -> None:
        """Decode the normal Toshiba CA layout for query and notify frames."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_POWER_FLAGS_OFFSET] = 0x01
        body[_TOSHIBA_NORMAL_MODE_OFFSET] = 0x02
        body[_TOSHIBA_NORMAL_MODE_OFFSET + 1] = 0x05
        body[_TOSHIBA_NORMAL_MODE_OFFSET + 2] = 0x03
        body[_TOSHIBA_NORMAL_DOOR_OFFSET] = _TOSHIBA_ALL_DOORS_MASK
        body[_TOSHIBA_NORMAL_ENERGY_OFFSET : _TOSHIBA_NORMAL_ENERGY_OFFSET + 2] = (
            0x6443
        ).to_bytes(2, "little")

        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.CA, frame_type, body)),
        )

        assert status == {
            DeviceAttributes.mode: 0x02,
            DeviceAttributes.energy_saving_mode: True,
            DeviceAttributes.refrigerator_actual_temp: 0x05,
            DeviceAttributes.freezer_actual_temp: 0x03,
            DeviceAttributes.refrigerator_door: True,
            DeviceAttributes.freezer_door: True,
            DeviceAttributes.bar_door: True,
            DeviceAttributes.flex_zone_door: True,
            DeviceAttributes.energy_consumption: 0x6443,
        }
        assert device.attributes[DeviceAttributes.energy_consumption] == 0x6443

    @pytest.mark.parametrize("frame_type", [MessageType.query, MessageType.notify1])
    def test_toshiba_shifted_query_and_notify_base_status(
        self,
        frame_type: MessageType,
    ) -> None:
        """Decode model 0000000D with its shifted CA status offsets."""
        device = _build_toshiba_device(model=_TOSHIBA_SHIFTED_MODEL)
        body = _toshiba_status_body(shifted=True)
        body[_TOSHIBA_SHIFTED_MODE_OFFSET] = 0x02
        body[_TOSHIBA_SHIFTED_MODE_OFFSET + 1] = 0x05
        body[_TOSHIBA_SHIFTED_MODE_OFFSET + 2] = 0x03
        body[_TOSHIBA_SHIFTED_DOOR_OFFSET] = _TOSHIBA_ALL_DOORS_MASK
        body[_TOSHIBA_SHIFTED_ENERGY_OFFSET : _TOSHIBA_SHIFTED_ENERGY_OFFSET + 2] = (
            0x4364
        ).to_bytes(2, "little")

        status = device.process_message(
            bytes(encode_toshiba_frame(DeviceType.CA, frame_type, body)),
        )

        assert status[DeviceAttributes.mode] == 0x02
        assert status[DeviceAttributes.refrigerator_actual_temp] == 0x05
        assert status[DeviceAttributes.freezer_actual_temp] == 0x03
        assert status[DeviceAttributes.energy_consumption] == 0x4364
        assert status[DeviceAttributes.energy_saving_mode] is False

    @pytest.mark.parametrize(
        ("mask", "attribute"),
        [
            (_TOSHIBA_REFRIGERATOR_DOOR_MASK, DeviceAttributes.refrigerator_door),
            (_TOSHIBA_FREEZER_DOOR_MASK, DeviceAttributes.freezer_door),
            (_TOSHIBA_BAR_DOOR_MASK, DeviceAttributes.bar_door),
            (_TOSHIBA_FLEX_ZONE_DOOR_MASK, DeviceAttributes.flex_zone_door),
        ],
    )
    def test_toshiba_door_masks(
        self,
        mask: int,
        attribute: DeviceAttributes,
    ) -> None:
        """Decode each Toshiba CA door bit independently."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[_TOSHIBA_NORMAL_DOOR_OFFSET] = mask
        frame = encode_toshiba_frame(DeviceType.CA, MessageType.query, body)
        status = device.process_message(bytes(frame))
        for door_attribute in (
            DeviceAttributes.refrigerator_door,
            DeviceAttributes.freezer_door,
            DeviceAttributes.bar_door,
            DeviceAttributes.flex_zone_door,
        ):
            assert status[door_attribute] is (door_attribute == attribute)

    @pytest.mark.parametrize("shifted", [False, True])
    def test_toshiba_requires_complete_base_status(self, shifted: bool) -> None:
        """Accept exact minimum bodies and reject one-byte truncations."""
        model = _TOSHIBA_SHIFTED_MODEL if shifted else "test_model"
        device = _build_toshiba_device(model=model)
        complete = _toshiba_status_body(shifted=shifted)
        frame = encode_toshiba_frame(DeviceType.CA, MessageType.query, complete)
        assert device.process_message(bytes(frame))[DeviceAttributes.mode] == 0

        truncated = complete[:-1]
        frame = encode_toshiba_frame(DeviceType.CA, MessageType.query, truncated)
        assert device.process_message(bytes(frame)) == {}

    @pytest.mark.parametrize(
        ("frame_type", "body_type"),
        [
            (MessageType.set, 0x00),
            (MessageType.query, 0x01),
            (MessageType.notify1, 0x01),
        ],
    )
    def test_toshiba_rejects_unsupported_frame_body_combinations(
        self,
        frame_type: MessageType,
        body_type: int,
    ) -> None:
        """Accept only complete Toshiba CA query/notify base statuses."""
        device = _build_toshiba_device()
        body = _toshiba_status_body()
        body[0] = body_type
        frame = encode_toshiba_frame(DeviceType.CA, frame_type, body)
        assert device.process_message(bytes(frame)) == {}

    def test_toshiba_fallback_requires_valid_supported_status(self) -> None:
        """Select fallback framing only after a complete decoded CA status."""
        device = _build_toshiba_device(None)
        fallback = device.build_query_fallback()[0]
        assert isinstance(fallback, ToshibaMessageRequest)

        body = _toshiba_status_body()
        invalid = encode_toshiba_frame(DeviceType.CA, MessageType.query, body)
        invalid[-1] ^= 1
        assert device.process_message(bytes(invalid)) == {}
        assert device._is_query_response_valid(fallback) is False
        assert device.toshiba_protocol is False

        wrong_type = encode_toshiba_frame(DeviceType.DB, MessageType.query, body)
        assert device.process_message(bytes(wrong_type)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x01
        unsupported = encode_toshiba_frame(DeviceType.CA, MessageType.query, body)
        assert device.process_message(bytes(unsupported)) == {}
        assert device.toshiba_protocol is False

        body[0] = 0x00
        valid = encode_toshiba_frame(DeviceType.CA, MessageType.query, body)
        assert device.process_message(bytes(valid))[DeviceAttributes.mode] == 0
        assert device._is_query_response_valid(fallback) is True
        assert device.toshiba_protocol is True

    def test_explicit_non_toshiba_identity_skips_fallback(self) -> None:
        """Do not probe Toshiba framing for a known different manufacturer."""
        device = _build_toshiba_device("1234")
        assert device.build_query_fallback() == []
        assert isinstance(device.build_query()[0], MessageQuery)

    def test_toshiba_write_is_rejected_before_send(self) -> None:
        """Keep Toshiba CA writes disabled until hardware verification."""
        device = _build_toshiba_device()
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.energy_saving_mode, True)
        send.assert_not_called()

    def test_process_message_general(self) -> None:
        """Test process message with a full general body."""
        body = _general_body(32)
        body[27] = 0x15  # microcrystal, electronic smell, humidity high
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert self.device.attributes[DeviceAttributes.energy_consumption] == 272
        assert self.device.attributes[DeviceAttributes.refrigerator_actual_temp] == 5.0
        assert self.device.attributes[DeviceAttributes.freezer_actual_temp] == -5.0
        assert self.device.attributes[DeviceAttributes.flex_zone_actual_temp] == 0.0
        assert (
            self.device.attributes[DeviceAttributes.right_flex_zone_actual_temp] == 10.0
        )
        assert self.device.attributes[DeviceAttributes.refrigerator_setting_temp] == 5
        assert self.device.attributes[DeviceAttributes.freezer_setting_temp] == -15
        assert self.device.attributes[DeviceAttributes.flex_zone_setting_temp] == -14
        assert (
            self.device.attributes[DeviceAttributes.right_flex_zone_setting_temp] == -20
        )
        assert self.device.attributes[DeviceAttributes.microcrystal_fresh] is True
        assert self.device.attributes[DeviceAttributes.electronic_smell] is True
        assert self.device.attributes[DeviceAttributes.humidity] == "high"
        assert self.device.attributes[DeviceAttributes.variable_mode] == "soft_freezing"
        assert new_status[DeviceAttributes.humidity.value] == "high"
        assert new_status[DeviceAttributes.variable_mode.value] == "soft_freezing"
        assert new_status[DeviceAttributes.energy_consumption.value] == 272

    def test_process_message_general_unknown_mappings(self) -> None:
        """Test process message with unmapped variable mode and humidity."""
        body = _general_body(32)
        body[5] = 0x20  # unmapped variable mode
        body[27] = 0x40  # unmapped humidity
        self.device.process_message(_build_message(MessageType.query, body))
        assert self.device.attributes[DeviceAttributes.humidity] is None
        assert self.device.attributes[DeviceAttributes.variable_mode] is None

    @pytest.mark.parametrize(("attribute", "offset", "mask"), DIAGNOSTIC_FLAGS)
    def test_process_message_diagnostic_flag(
        self,
        attribute: DeviceAttributes,
        offset: int,
        mask: int,
    ) -> None:
        """Expose each flag independently, retaining parser booleans or raw masks."""
        body = _general_body(25)
        body[offset] = mask
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        for flag, _, _ in DIAGNOSTIC_FLAGS:
            if flag in (
                DeviceAttributes.flood_light,
                DeviceAttributes.freezing_ice_machine_power,
            ):
                expected = mask if flag == attribute else 0
                assert type(self.device.attributes[flag]) is int
            else:
                expected = flag == attribute
                assert type(self.device.attributes[flag]) is bool
            assert self.device.attributes[flag] == expected
            assert new_status[flag.value] == expected

        body[offset] = 0
        new_status = self.device.process_message(
            _build_message(MessageType.query, body),
        )
        assert not self.device.attributes[attribute]
        assert not new_status[attribute.value]

    def test_notify_preserves_unknown_and_known_diagnostic_flags(self) -> None:
        """A door notification does not invent or overwrite general status flags."""
        notification = _build_message(MessageType.notify1, bytearray([0x00, 0x17]))
        new_status = self.device.process_message(notification)
        for attribute, _, _ in DIAGNOSTIC_FLAGS:
            assert self.device.attributes[attribute] is None
            assert attribute.value not in new_status

        body = _general_body(25)
        body[1] = 0xFF
        body[7] = 0x10
        body[8] = 0x80
        self.device.process_message(_build_message(MessageType.query, body))
        known_values = {
            attribute: self.device.attributes[attribute]
            for attribute, _, _ in DIAGNOSTIC_FLAGS
        }
        new_status = self.device.process_message(notification)
        for attribute, value in known_values.items():
            assert self.device.attributes[attribute] == value
            assert attribute.value not in new_status

    @pytest.mark.parametrize(("attribute", "offset", "mask"), DIAGNOSTIC_FLAGS)
    def test_diagnostic_flags_are_read_only(
        self,
        attribute: DeviceAttributes,
        offset: int,
        mask: int,
    ) -> None:
        """Setting a diagnostic attribute leaves its parsed value unchanged."""
        body = _general_body(25)
        body[offset] = mask
        self.device.process_message(_build_message(MessageType.query, body))
        previous = self.device.attributes[attribute]

        self.device.set_attribute(attribute.value, False)

        assert self.device.attributes[attribute] == previous

    def test_process_message_notify00(self) -> None:
        """Test process message with a notify00 body."""
        body = bytearray([0x00, 0x17])
        new_status = self.device.process_message(
            _build_message(MessageType.notify1, body),
        )
        assert self.device.attributes[DeviceAttributes.refrigerator_door] is True
        assert self.device.attributes[DeviceAttributes.freezer_door] is True
        assert self.device.attributes[DeviceAttributes.bar_door] is True
        assert self.device.attributes[DeviceAttributes.flex_zone_door] is True
        assert new_status[DeviceAttributes.refrigerator_door.value] is True

    def test_process_message_exception(self) -> None:
        """Test process message with an exception body."""
        body = bytearray([0x01, 0x0F, 0x00, 0x00])
        self.device.process_message(_build_message(MessageType.exception, body))
        assert (
            self.device.attributes[DeviceAttributes.refrigerator_door_overtime] is True
        )
        assert self.device.attributes[DeviceAttributes.freezer_door_overtime] is True
        assert self.device.attributes[DeviceAttributes.bar_door_overtime] is True
        assert self.device.attributes[DeviceAttributes.flex_zone_door_overtime] is True

    def test_process_message_unhandled(self) -> None:
        """Test process message with an unhandled message type."""
        body = bytearray(25)
        new_status = self.device.process_message(
            _build_message(MessageType.notify2, body),
        )
        assert new_status == {}

    def test_set_attribute(self) -> None:
        """Test set attribute is a no-op."""
        self.device.set_attribute(DeviceAttributes.microcrystal_fresh.value, True)
        assert self.device.attributes[DeviceAttributes.microcrystal_fresh] is False

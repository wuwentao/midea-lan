"""Test da Device."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.da import (
    DeviceAttributes,
    MideaDADevice,
    ToshibaDALegacyQuery,
    ToshibaDAQuery,
)
from midealan.devices.da.message import MessageQuery
from midealan.exceptions import ValueWrongType
from midealan.message import MessageType, encode_toshiba_frame


class TestMideaDADevice:
    """Test Midea DA Device."""

    device: MideaDADevice

    @pytest.fixture(autouse=True)
    def _setup_device(self) -> None:
        """Midea DA Device setup."""
        self.device = MideaDADevice(
            name="Test Device",
            device_id=1,
            ip_address="192.168.1.100",
            port=6444,
            token="AA",
            key="BB",
            device_protocol=ProtocolVersion.V3,
            model="test_model",
            subtype=1,
            customize="test_customize",
        )

    def test_initial_attributes(self) -> None:
        """Test initial attributes."""
        assert not self.device.attributes[DeviceAttributes.power]
        assert not self.device.attributes[DeviceAttributes.start]
        assert self.device.attributes[DeviceAttributes.error_code] is None
        assert self.device.attributes[DeviceAttributes.washing_data] == bytearray([])
        assert self.device.attributes[DeviceAttributes.program] is None
        assert self.device.attributes[DeviceAttributes.progress] == "unknown"
        assert self.device.attributes[DeviceAttributes.time_remaining] is None
        assert self.device.attributes[DeviceAttributes.wash_time] is None
        assert self.device.attributes[DeviceAttributes.soak_time] is None
        assert self.device.attributes[DeviceAttributes.dehydration_time] is None
        assert self.device.attributes[DeviceAttributes.dehydration_speed] is None
        assert self.device.attributes[DeviceAttributes.rinse_count] is None
        assert self.device.attributes[DeviceAttributes.rinse_level] is None
        assert self.device.attributes[DeviceAttributes.wash_level] is None
        assert self.device.attributes[DeviceAttributes.wash_strength] is None
        assert self.device.attributes[DeviceAttributes.softener] is None
        assert self.device.attributes[DeviceAttributes.detergent] is None

    def test_process_message(self) -> None:
        """Test process message."""
        with patch("midealan.devices.da.MessageDAResponse") as mock_message_response:
            mock_message = mock_message_response.return_value
            mock_message.protocol_version = ProtocolVersion.V3
            mock_message.power = True
            mock_message.start = True
            mock_message.error_code = 10
            mock_message.program = 5
            mock_message.wash_time = 30
            mock_message.soak_time = 10
            mock_message.dehydration_time = 2
            mock_message.dehydration_speed = 3
            mock_message.rinse_count = 3
            mock_message.rinse_level = 4
            mock_message.wash_level = 1
            mock_message.wash_strength = 2
            mock_message.softener = 5
            mock_message.detergent = 4
            mock_message.progress = 2
            mock_message.time_remaining = 15 + 60
            new_status = self.device.process_message(b"")
            assert new_status[DeviceAttributes.power.value]
            assert new_status[DeviceAttributes.start.value]
            assert new_status[DeviceAttributes.error_code.value] == 10
            assert new_status[DeviceAttributes.program.value] == "memory"
            assert new_status[DeviceAttributes.progress.value] == "rinse"
            assert new_status[DeviceAttributes.time_remaining.value] == 75
            assert new_status[DeviceAttributes.wash_time.value] == 30
            assert new_status[DeviceAttributes.soak_time.value] == 10
            assert new_status[DeviceAttributes.dehydration_time.value] == 2
            assert new_status[DeviceAttributes.dehydration_speed.value] == "high"
            assert new_status[DeviceAttributes.rinse_count.value] == 3
            assert new_status[DeviceAttributes.rinse_level.value] == 4
            assert new_status[DeviceAttributes.wash_level.value] == 1
            assert new_status[DeviceAttributes.wash_strength.value] == "medium"
            assert new_status[DeviceAttributes.softener.value] == "5"
            assert new_status[DeviceAttributes.detergent.value] == "4"

            mock_message.progress = 15
            mock_message.program = 15
            mock_message.rinse_level = 15
            mock_message.dehydration_speed = 15
            mock_message.detergent = 15
            mock_message.softener = 15
            mock_message.wash_strength = 15
            new_status = self.device.process_message(b"")
            assert new_status[DeviceAttributes.program.value] is None
            assert new_status[DeviceAttributes.progress.value] is None
            assert new_status[DeviceAttributes.rinse_level.value] == "-"
            assert new_status[DeviceAttributes.dehydration_speed.value] is None
            assert new_status[DeviceAttributes.softener.value] is None
            assert new_status[DeviceAttributes.detergent.value] is None
            assert new_status[DeviceAttributes.wash_strength.value] is None

    def test_process_message_partial_response(self) -> None:
        """Test process message skips missing response attributes."""
        with patch(
            "midealan.devices.da.MessageDAResponse",
            return_value=SimpleNamespace(power=True),
        ):
            new_status = self.device.process_message(b"")
        assert new_status == {DeviceAttributes.power.value: True}

    def test_build_query(self) -> None:
        """Build Midea queries first and both Toshiba fallback profiles."""
        queries = self.device.build_query()
        assert len(queries) == 1
        assert isinstance(queries[0], MessageQuery)

        fallback = self.device.build_query_fallback()
        assert [type(query) for query in fallback] == [
            ToshibaDAQuery,
            ToshibaDALegacyQuery,
        ]
        assert [query.serialize().hex() for query in fallback] == [
            "55aacc330f0001da000000000000030000a3e8",
            "55aacc330f0001db000000000000030000e687",
        ]

    def test_toshiba_profiles_select_answering_wire_type(self) -> None:
        """Probe both DA wire profiles, then retain the validated legacy type."""
        device = MideaDADevice(
            name="Toshiba DA",
            device_id=1,
            ip_address="192.0.2.1",
            port=6444,
            token="00",
            key="00",
            device_protocol=ProtocolVersion.V1,
            model="test",
            subtype=0,
            manufacturer_code="0008",
            customize="",
        )
        queries = device.build_query()
        assert isinstance(queries[0], ToshibaDAQuery)
        assert isinstance(queries[1], ToshibaDALegacyQuery)
        assert queries[0].serialize()[7] == DeviceType.DA
        assert queries[1].serialize()[7] == DeviceType.DB
        body = bytearray(47)
        body[3] = 1
        body[9] = 30
        body[18] = 0x04
        body[20:22] = (7).to_bytes(2, "little")
        body[22] = 2
        body[23:27] = (45).to_bytes(4, "little")
        status = device.process_message(
            bytes(
                encode_toshiba_frame(
                    DeviceType.DA,
                    MessageType.query,
                    body,
                    wire_device_type=DeviceType.DB,
                ),
            ),
        )
        assert status[DeviceAttributes.power] is True
        assert status[DeviceAttributes.start] is True
        assert status[DeviceAttributes.progress] == "rinse"
        assert status[DeviceAttributes.time_remaining] == 45
        selected = device.build_query()
        assert len(selected) == 1
        assert isinstance(selected[0], ToshibaDALegacyQuery)

        body[18] = 0x20
        status = device.process_message(
            bytes(
                encode_toshiba_frame(
                    DeviceType.DA,
                    MessageType.query,
                    body,
                    wire_device_type=DeviceType.DB,
                ),
            ),
        )
        assert status[DeviceAttributes.progress] == "soft_keep"

        body[9] = 0x82
        body[18] = 0
        status = device.process_message(
            bytes(
                encode_toshiba_frame(
                    DeviceType.DA,
                    MessageType.query,
                    body,
                    wire_device_type=DeviceType.DB,
                ),
            ),
        )
        assert status[DeviceAttributes.wash_time] == 120
        assert status[DeviceAttributes.progress] == "idle"
        assert (
            device.process_message(
                bytes(
                    encode_toshiba_frame(
                        DeviceType.DA,
                        MessageType.query,
                        b"\x00",
                        wire_device_type=DeviceType.DB,
                    ),
                ),
            )
            == {}
        )

        status = self.device.process_message(
            bytes(encode_toshiba_frame(DeviceType.DA, MessageType.query, body)),
        )
        assert status[DeviceAttributes.progress] == "idle"
        selected = self.device.build_query()
        assert len(selected) == 1
        assert isinstance(selected[0], ToshibaDAQuery)

    def test_explicit_non_toshiba_identity_ignores_toshiba_frame(self) -> None:
        """Keep an explicit non-Toshiba DA device on the Midea protocol."""
        device = MideaDADevice(
            name="Midea DA",
            device_id=1,
            ip_address="192.0.2.1",
            port=6444,
            token="00",
            key="00",
            device_protocol=ProtocolVersion.V1,
            model="test",
            subtype=0,
            manufacturer_code="1234",
            customize="",
        )
        body = bytearray(47)

        with patch("midealan.devices.da.MessageDAResponse") as response:
            response.return_value = SimpleNamespace(power=True)
            assert (
                device.process_message(
                    bytes(
                        encode_toshiba_frame(
                            DeviceType.DA,
                            MessageType.query,
                            body,
                        ),
                    ),
                )
                == {}
            )
            response.assert_not_called()
            assert device.process_message(b"") == {DeviceAttributes.power: True}

        assert device.toshiba_protocol is False
        assert isinstance(device.build_query()[0], MessageQuery)

    def test_toshiba_write_is_rejected_before_send(self) -> None:
        """Keep Toshiba DA writes disabled until hardware verification."""
        device = MideaDADevice(
            name="Toshiba DA",
            device_id=1,
            ip_address="192.0.2.1",
            port=6444,
            token="00",
            key="00",
            device_protocol=ProtocolVersion.V1,
            model="test",
            subtype=0,
            manufacturer_code="0008",
            customize="",
        )
        with (
            patch.object(device, "build_send") as send,
            pytest.raises(ValueError, match="hardware verification"),
        ):
            device.set_attribute(DeviceAttributes.power, True)
        send.assert_not_called()

    def test_set_attribute(self) -> None:
        """Test set attribute."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute(DeviceAttributes.power, True)
            mock_build_send.assert_called_once()

            self.device.set_attribute(DeviceAttributes.start, True)
            mock_build_send.assert_called()

            with pytest.raises(ValueWrongType):
                self.device.set_attribute(DeviceAttributes.start, "On")

    def test_set_attribute_ignores_unknown_bool_attribute(self) -> None:
        """Test unknown boolean attributes are ignored."""
        with patch.object(self.device, "build_send") as mock_build_send:
            self.device.set_attribute("unknown", True)
            mock_build_send.assert_not_called()

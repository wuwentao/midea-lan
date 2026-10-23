"""Test Toshiba 0x51 device."""

import pytest

from midealan.const import DeviceType, ProtocolVersion
from midealan.devices.x51 import DeviceAttributes, MideaX51Device
from midealan.devices.x51.message import (
    MessageQueryBase,
    MessageQueryReserved,
    MessageQuerySchedule,
)
from midealan.message import encode_toshiba_frame


def device() -> MideaX51Device:
    """Create a Toshiba 0x51 device without opening a socket."""
    return MideaX51Device(
        name="Toshiba 0x51",
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


def test_query_function_groups() -> None:
    """Query every documented Toshiba 0x51 function group."""
    queries = device().build_query()
    assert [type(query) for query in queries] == [
        MessageQueryBase,
        MessageQueryReserved,
        MessageQuerySchedule,
    ]
    assert [query.body for query in queries] == [
        bytearray([0]),
        bytearray([1]),
        bytearray([2]),
    ]
    assert queries[0].serialize() == bytes.fromhex(
        "55aacc330f00015100000000000003000013f7",
    )


def test_process_base_and_schedule_status() -> None:
    """Decode clock/sensor and schedule function responses."""
    appliance = device()
    base = bytearray([0, 30, 12, 19, 10, 0xEA, 0x07, 0x34, 0x12, 2, 1, 2])
    status = appliance.process_message(
        bytes(encode_toshiba_frame(DeviceType.X51, 3, base)),
    )
    assert status[DeviceAttributes.time_minute] == 30
    assert status[DeviceAttributes.time_year] == 2026
    assert status[DeviceAttributes.temperature] == 0x1234
    assert status[DeviceAttributes.light] == 0x0102
    assert status[DeviceAttributes.battery_status] == "low"

    schedule = bytearray([2, 1, 4, 6, 15, 18, 45])
    status = appliance.process_message(
        bytes(encode_toshiba_frame(DeviceType.X51, 4, schedule)),
    )
    assert status[DeviceAttributes.shoot] is True
    assert status[DeviceAttributes.mode] == 4
    assert status[DeviceAttributes.auto_mode] is True
    assert status[DeviceAttributes.periodical_mode] is False
    assert status[DeviceAttributes.first_schedule_hour] == 6
    assert status[DeviceAttributes.second_schedule_minute] == 45


def test_partial_schedule_error_and_read_only() -> None:
    """Decode short notifications and reject all writes for Toshiba-only 0x51."""
    appliance = device()
    status = appliance.process_message(
        bytes(encode_toshiba_frame(DeviceType.X51, 4, bytes([2, 0, 0x0A]))),
    )
    assert status[DeviceAttributes.request_mode] is True
    assert status[DeviceAttributes.direct_mode] is True
    assert DeviceAttributes.first_schedule_hour not in status

    assert (
        appliance.process_message(
            bytes(encode_toshiba_frame(DeviceType.X51, 3, b"")),
        )
        == {}
    )
    assert (
        appliance.process_message(
            bytes(encode_toshiba_frame(DeviceType.X51, 3, bytes([1]))),
        )
        == {}
    )

    assert (
        appliance.process_message(
            bytes(encode_toshiba_frame(DeviceType.X51, 3, bytes([2, 0, 0x0A]))),
        )
        == {}
    )

    status = appliance.process_message(
        bytes(encode_toshiba_frame(DeviceType.X51, 6, bytes([0xFE, 0x34, 0x12]))),
    )
    assert status[DeviceAttributes.error_code] == 0x1234

    with pytest.raises(ValueError, match="hardware verification"):
        appliance.set_attribute(attr=DeviceAttributes.mode, value=1)

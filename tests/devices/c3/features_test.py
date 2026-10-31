"""Curated telemetry and settings verified against independent vendor Lua output."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from midealan.devices.c3 import DeviceAttributes as A
from midealan.devices.c3.features import (
    CONTROL_TABLES,
    ENERGY_ATTRIBUTES,
    ENERGY_TABLES,
    MessageQueryTable,
    MessageSetSettings,
    decode_table,
)
from midealan.devices.c3.features import (
    FeatureSetting as S,
)
from midealan.message import ListTypes, MessageType

from .quintuple_test import QUERY_REPLY, device, frame

FIXTURES = Path(__file__).parents[2] / "responses"
RESPONSES = json.loads((FIXTURES / "c3-17100007.json").read_text())["responses"]
WRITES = json.loads((FIXTURES / "c3-17100007-writes.json").read_text())


@pytest.mark.parametrize("record", RESPONSES, ids=lambda r: r["table"])
def test_vendor_decoded_curated_values(record: dict) -> None:
    """Sanitized packet layouts retain independently decoded, distinct field values."""
    d = device()
    status = d.process_message(bytes.fromhex(record["frame"]))
    for key, expected in record["expected"].items():
        assert status[key] == expected, key
        assert d.attributes[A(key)] == expected, key
    assert not any(str(key).startswith("c3_") for key in d.attributes)
    assert len(json.dumps(d.attributes).encode()) < 16384


def test_curated_attributes_do_not_replace_power_flags() -> None:
    """DHW electrical kW is separate from the DHW on/off boolean."""
    d = device()
    d.process_message(QUERY_REPLY)
    for record in RESPONSES:
        d.process_message(bytes.fromhex(record["frame"]))
    assert d.attributes[A.dhw_power] is True
    assert isinstance(d.attributes[A.dhw_power_consumption], float)
    assert len(ENERGY_ATTRIBUTES) == 57


@pytest.mark.parametrize("case", WRITES)
def test_native_settings_match_vendor(case: dict) -> None:
    """These literal packets came from the vendor encoder, not this implementation."""
    values = {S(key): value for key, value in case["values"].items()}
    assert MessageSetSettings(values).serialize().hex() == case["frame"]


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"unknown": True},
        {S.ECO: True, S.SILENT_POWER: True},
        {S.ECO: "false"},
        {S.SILENT_LEVEL: "invalid"},
        {S.SILENT_LEVEL: True},
    ],
)
def test_setting_validation(values: dict) -> None:
    """Never write unknown fields, multiple tables, or coerced switch values."""
    with pytest.raises(ValueError, match=r"."):
        MessageSetSettings(values)


def test_polling_and_independent_tracking() -> None:
    """Five recurring tables plus one rotating control table limit polling volume."""
    d = device()
    controls = set()
    kinds = set()
    for _ in CONTROL_TABLES:
        queries = d.build_query()
        assert len(queries) == 6
        assert [int.from_bytes(q.body[1:3], "big") for q in queries[2:5]] == list(
            ENERGY_TABLES,
        )
        controls.add(int.from_bytes(queries[-1].body[1:3], "big"))
        kinds.update(type(q).__name__ for q in queries)
    assert controls == set(CONTROL_TABLES)
    assert len(kinds) == 8
    with pytest.raises(ValueError, match="Unknown"):
        MessageQueryTable(0xFFFF)


def test_sparse_invalid_and_partial_fields() -> None:
    """Sparse acknowledgements preserve untouched state and clear invalid readings."""
    d = device()
    d.process_message(QUERY_REPLY)
    envelope = "002050ffffffff01ffff"
    d.process_message(frame(bytes.fromhex(envelope + "0000010100010102")))
    assert d.attributes[A.silent_mode] is True
    assert d.attributes[A.silent_level] == "level_3"
    d.process_message(frame(bytes.fromhex(envelope + "00000100")))
    assert d.attributes[A.silent_level] == "off"
    d.process_message(frame(bytes.fromhex(envelope + "00000101")))
    assert d.attributes[A.silent_level] == "level_3"
    d.process_message(frame(bytes.fromhex(envelope + "000101ff")))
    assert d.attributes[A.silent_level] is None
    d.process_message(frame(bytes.fromhex(envelope + "000001ff")))
    assert d.attributes[A.silent_level] is None
    for raw in (
        "",
        "00",
        "00ffff00000000000000",
        "002050ffffffff00ffff00",
        envelope + "0000010100010100ff",
    ):
        assert decode_table(bytearray.fromhex(raw)) == {}
    assert decode_table(bytearray.fromhex(envelope + "00000102"))["silent_mode"] is None
    assert (
        decode_table(bytearray.fromhex(envelope + "00010103"))["_silent_level"] is None
    )
    assert decode_table(bytearray.fromhex(envelope + "000001ff"))["silent_mode"] is None
    # Mapped energy sentinel must not become zero or billions of kWh.
    assert (
        decode_table(bytearray.fromhex("002f12ffffffff01ffff001204ffffffff"))[
            "dhw_total_energy"
        ]
        is None
    )
    for message in (
        SimpleNamespace(body_type=ListTypes.X01, message_type=MessageType.query),
        SimpleNamespace(body_type=ListTypes.X00, message_type=MessageType.notify2),
    ):
        d._parse_features(message)


def test_settings_wait_and_native_routes() -> None:
    """Native switches and the level select use the same atomic sparse protocol."""
    d = device()
    with pytest.raises(ValueError, match="first 0x2010"):
        d.set_attribute(A.eco_mode, True)
    d.process_message(QUERY_REPLY)
    assert d.silent_modes == ["off", "level_1", "level_2", "level_3"]
    with patch.object(d, "build_send") as send:
        for attr in (A.eco_mode, A.disinfect, A.silent_mode):
            d.set_attribute(attr, True)
            assert isinstance(send.call_args.args[0], MessageSetSettings)
        send.reset_mock()
        d.set_attribute(A.silent_level, "level_2")
        send.assert_called_once()
        assert send.call_args.args[0].body.hex().endswith("0000010100010101")
        d.set_attribute(A.silent_level, "off")
        assert send.call_args.args[0].body.hex().endswith("00000100")
    for attr, value in [
        (A.silent_level, "invalid"),
        (A.silent_level, 2.0),
        (A.eco_mode, "false"),
    ]:
        with pytest.raises(ValueError, match=r"."):
            d.set_attribute(attr, value)

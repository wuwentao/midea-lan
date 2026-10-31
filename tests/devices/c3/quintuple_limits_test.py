"""Controller-reported limits must authorize every native temperature write."""

from unittest.mock import patch

import pytest

from midealan.devices.c3 import DeviceAttributes as A
from midealan.devices.c3.quintuple import BASIC_SIZES
from midealan.message import MessageType

from .quintuple_test import QUERY_REPLY, device, frame


def full_status(changes: dict[int, bytes]) -> bytes:
    """Change specific vendor tags in an otherwise valid sequential reply."""
    body = bytearray(QUERY_REPLY[10:-1])
    for tag, value in changes.items():
        assert len(value) == BASIC_SIZES[tag]
        start = 10 + sum(BASIC_SIZES[:tag])
        body[start : start + len(value)] = value
    return frame(body, MessageType.query)


def test_selectors_alone_cannot_enable_controls() -> None:
    """Mode/type TLVs must not authorize constructor temperature defaults."""
    d = device()
    d.process_message(frame(bytes.fromhex("002010ffffffff01ffff0003010300120100")))
    assert not d._quintuple_ready
    assert d.attributes[A.temperature_min][0] is None
    with (
        patch.object(d, "build_send") as send,
        pytest.raises(ValueError, match="first 0x2010"),
    ):
        d.set_target_temperature(33, None, 0)
    send.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "water_type", "limit_tag"),
    [
        (3, 0, 29),
        (3, 0, 30),
        (2, 0, 31),
        (2, 0, 32),
        (5, 0, 31),
        (3, 1, 37),
        (3, 1, 38),
    ],
)
def test_full_reply_clears_selected_limits(
    mode: int,
    water_type: int,
    limit_tag: int,
) -> None:
    """An unavailable active limit revokes readiness and clears derived bounds."""
    d = device()
    d.process_message(QUERY_REPLY)
    assert d._quintuple_ready
    d.process_message(
        full_status(
            {
                3: bytes((mode,)),
                18: bytes((water_type,)),
                28: b"\x01",
                limit_tag: b"\x7f\xff",
            },
        ),
    )
    assert not d._quintuple_ready
    bounds = [d.attributes[A.temperature_min][0], d.attributes[A.temperature_max][0]]
    assert None in bounds
    with (
        patch.object(d, "build_send") as send,
        pytest.raises(ValueError, match="first 0x2010"),
    ):
        d.set_target_temperature(25, None, 0)
    send.assert_not_called()
    d.process_message(QUERY_REPLY)
    assert d._quintuple_ready


def test_sparse_ack_preserves_omitted_limits_and_clears_explicit_sentinel() -> None:
    """An omitted zone is preserved; an explicitly unavailable limit is not."""
    d = device()
    d.process_message(QUERY_REPLY)
    second = d.attributes[A.zone_heating_temp_max][1]
    d.process_message(frame(bytes.fromhex("002010ffffffff01ffff001d020226")))
    assert d.attributes[A.zone_heating_temp_max] == [55, second]
    assert d._quintuple_ready
    d.process_message(frame(bytes.fromhex("002010ffffffff01ffff001d027fff")))
    assert d.attributes[A.zone_heating_temp_max] == [None, second]
    assert not d._quintuple_ready


@pytest.mark.parametrize("tag", [39, 40])
def test_unknown_dhw_limits_block_temperature_writes(tag: int) -> None:
    """DHW cannot reuse default or stale limits when the controller clears them."""
    d = device()
    d.process_message(QUERY_REPLY)
    d.process_message(full_status({tag: b"\x7f\xff"}))
    with (
        patch.object(d, "build_send") as send,
        pytest.raises(ValueError, match="limits"),
    ):
        d.set_attribute(A.dhw_target_temp, 49)
    send.assert_not_called()


@pytest.mark.parametrize("tag", [3, 18])
def test_invalid_selectors_clear_readiness(tag: int) -> None:
    """Unknown modes and temperature types cannot retain prior write readiness."""
    d = device()
    d.process_message(QUERY_REPLY)
    d.process_message(full_status({tag: b"\xff"}))
    assert not d._quintuple_ready
    assert d.attributes[A.temperature_min][0] is None


def test_auto_mode_requires_reported_actual_mode() -> None:
    """Unavailable auto selection cannot silently select the heating defaults."""
    d = device()
    d.process_message(full_status({3: b"\x05", 28: b"\xff"}))
    assert not d._quintuple_ready


@pytest.mark.parametrize("tag", [31, 32])
def test_mode_change_checks_destination_limits(tag: int) -> None:
    """A valid current heating range does not authorize unknown cooling limits."""
    d = device()
    d.process_message(full_status({tag: b"\x7f\xff"}))
    assert d._quintuple_ready  # Heating's own limits are still valid.
    with (
        patch.object(d, "build_send") as send,
        pytest.raises(ValueError, match="limits"),
    ):
        d.set_target_temperature(20, 2, 0)
    send.assert_not_called()


def test_mode_change_rejects_target_outside_destination_range() -> None:
    """A 33 C heating target cannot be reused for cooling, whose upper bound is 25."""
    d = device()
    d.process_message(QUERY_REPLY)
    with (
        patch.object(d, "build_send") as send,
        pytest.raises(ValueError, match="limits"),
    ):
        d.set_target_temperature(33, 2, 0)
    send.assert_not_called()


@pytest.mark.parametrize(
    ("lower", "upper"),
    [(None, 55), (25, None), (55, 25), (float("nan"), 55), (25, float("inf"))],
)
def test_unusable_limit_pairs(lower: float | None, upper: float | None) -> None:
    """Reject missing, inverted and non-finite limits."""
    assert not device()._valid_quintuple_limits(lower, upper)


def test_both_configured_zones_require_limits() -> None:
    """Readiness includes the second zone only when reported as configured."""
    d = device()
    d.process_message(full_status({17: b"\x01", 33: b"\x7f\xff"}))
    assert not d._quintuple_ready

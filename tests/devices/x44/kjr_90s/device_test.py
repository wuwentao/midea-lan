"""Test KJR-90S handoff through the ordinary AC lifecycle."""

from unittest.mock import Mock, patch

import pytest

from midealan.const import DeviceType
from midealan.device import MessageResult
from midealan.devices import ac, device_selector, x44
from midealan.message import MessageType
from midealan.packet_builder import PacketBuilder
from midealan.security import MSGTYPE_ENCRYPTED_RESPONSE, LocalSecurity
from tests.devices.x44 import AC_REPORT_VIA_90S, identity, select_device


@pytest.mark.parametrize(
    ("model", "sn8"),
    [("115P0303", None), ("KJR-90S", "115p0303"), ("115P0303", "00000000")],
)
def test_delegated_identity(model: str, sn8: str | None) -> None:
    """A LAN model or cloud SN8 selects the native AC class with the panel identity."""
    kwargs = identity(model, subtype=7)
    kwargs["sn8"] = sn8
    kwargs["cloud_name"] = "Test panel"
    kwargs["serial_number"] = "test-serial"
    customize = '{"temperature_step":1}'
    device = device_selector(device_type=DeviceType.X44, customize=customize, **kwargs)
    direct = ac.MideaAppliance(customize=customize, **kwargs)
    assert type(device) is ac.MideaAppliance
    assert device.device_type == DeviceType.AC
    assert (device.model, device.subtype, device.sn8) == (model, 7, direct.sn8)
    assert (device.cloud_name, device.serial_number) == ("Test panel", "test-serial")
    assert device.temperature_step == 1
    assert device.attributes == direct.attributes
    profile = x44.resolve_profile(model, 7, sn8)
    assert isinstance(profile, x44.DelegatedModel)
    assert (profile.name, profile.device_type, profile.driver) == (
        "KJR-90S",
        DeviceType.AC,
        ac.MideaAppliance,
    )


def test_native_ac_reports_queries_and_writes() -> None:
    """A 0x44 reply reaches AC. Polls and writes then use the native AC protocol."""
    device = select_device("115P0303")
    direct = ac.MideaAppliance(customize="", **identity("115P0303"))
    assert [type(q) for q in device.build_query()] == [
        type(q) for q in direct.build_query()
    ]

    updates = Mock()
    device.register_update(updates)
    peer = LocalSecurity()
    peer._tcp_key = device._security._tcp_key = bytes(32)
    packet = PacketBuilder(device.device_id, AC_REPORT_VIA_90S).finalize()
    via_lan = peer.encode_8370(packet, MSGTYPE_ENCRYPTED_RESPONSE)
    assert device.parse_message(via_lan) == MessageResult.SUCCESS
    expected = direct.process_message(AC_REPORT_VIA_90S)
    updates.assert_called_once_with(expected)
    assert device.attributes == direct.attributes
    assert device.attributes[ac.DeviceAttributes.power] is True
    assert device.attributes[ac.DeviceAttributes.target_temperature] == 25
    assert [q.serialize() for q in device.build_query()] == [
        q.serialize() for q in direct.build_query()
    ]

    with (
        patch.object(device, "send_message") as sent,
        patch.object(direct, "send_message") as direct_sent,
    ):
        device.set_attribute(ac.DeviceAttributes.target_temperature, 26)
        direct.set_attribute(ac.DeviceAttributes.target_temperature, 26)
        device.send_command(MessageType.query, bytearray([0x41]))
    assert sent.call_count == 2
    direct_sent.assert_called_once()
    control, raw_query = (
        device._security.aes_decrypt(call.args[0][40:-16])
        for call in sent.call_args_list
    )
    assert control == direct._security.aes_decrypt(
        direct_sent.call_args.args[0][40:-16],
    )
    assert (control[2], control[9]) == (DeviceType.AC, MessageType.set)
    assert (raw_query[2], raw_query[9]) == (DeviceType.AC, MessageType.query)

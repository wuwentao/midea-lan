"""Midea Lan CLI tests."""

import json
import logging
import runpy
import subprocess
import sys
import warnings
from argparse import Namespace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from midealan.cli import (
    MideaCLI,
    get_config_file_path,
    main,
)
from midealan.cloud import MideaAirCloud, SmartHomeCloud
from midealan.const import ProtocolVersion
from midealan.device import AuthException, NoSupportedProtocol
from midealan.discover import _extract_mac
from midealan.exceptions import SocketException


class TestMideaCLI(IsolatedAsyncioTestCase):
    """Test Midea CLI."""

    def setUp(self) -> None:
        """Create namespace for testing."""
        self.cli = MideaCLI()
        self.namespace = Namespace(
            cloud_name="SmartHome",
            username="user",
            password="pass",
            host="192.168.0.1",
            message=bytes.fromhex("00a1a2ac0f2a0000"),
            device_type=bytearray(),
            device_sn="",
            device_model=None,
            device_subtype=None,
            user=False,
            debug=True,
            get_sn=False,
            attribute="power",
            value="0",
            attr_type="bool",
            func=MagicMock(),
        )
        self.cli.namespace = self.namespace

    async def test_get_cloud(self) -> None:
        """Test get cloud."""
        mock_session_instance = AsyncMock()
        with (
            patch("aiohttp.ClientSession", return_value=mock_session_instance),
        ):
            cloud = await self.cli._get_cloud()

        assert isinstance(cloud, SmartHomeCloud)
        assert cloud._account == self.namespace.username
        assert cloud._password == self.namespace.password
        assert cloud._session == mock_session_instance

        # test default cloud
        self.namespace.cloud_name = None
        cloud = await self.cli._get_cloud()
        assert isinstance(cloud, MideaAirCloud)
        assert cloud._session == mock_session_instance

    async def test_get_keys(self) -> None:
        """Test get keys."""
        mock_cloud = AsyncMock()
        with (
            patch("midealan.cli.get_midea_cloud", return_value=mock_cloud),
            patch.object(
                mock_cloud,
                "get_default_keys",
                return_value={99: {"key": "key99", "token": "token99"}},
            ) as mock_default_keys,
            patch.object(
                mock_cloud,
                "get_cloud_keys",
                return_value={
                    0: {"key": "key0", "token": "token0"},
                    1: {"key": "key1", "token": "token1"},
                },
            ) as mock_cloud_keys,
            patch.object(mock_cloud, "login", side_effect=[True, False]),
        ):
            keys = await self.cli._get_keys(0)
            assert len(keys) == 3
            assert keys[0]["key"] == "key0"
            assert keys[1]["key"] == "key1"
            assert keys[99]["key"] == "key99"
            assert keys[0]["token"] == "token0"
            assert keys[1]["token"] == "token1"
            assert keys[99]["token"] == "token99"
            mock_default_keys.assert_called_once()
            mock_default_keys.reset_mock()
            mock_cloud_keys.assert_called_once_with(0)
            mock_cloud_keys.reset_mock()

            keys = await self.cli._get_keys(0)
            assert len(keys) == 1
            assert keys[99]["key"] == "key99"
            assert keys[99]["token"] == "token99"
            mock_default_keys.assert_called_once()
            mock_cloud_keys.assert_not_called()

    async def test_get_cert_bundle_no_credentials(self) -> None:
        """Without user credentials cert provisioning is refused."""
        self.namespace.cloud_name = None
        with self.assertLogs("cli", level="ERROR") as logs:
            assert await self.cli._get_cert_bundle() is None
        assert any("certificate" in line for line in logs.output)

    async def test_get_cert_bundle_login_failure(self) -> None:
        """A failed cloud login returns no cert bundle."""
        mock_cloud = AsyncMock()
        mock_cloud.login.return_value = False
        with (
            patch.object(self.cli, "_get_cloud", return_value=mock_cloud),
            self.assertLogs("cli", level="WARNING") as logs,
        ):
            assert await self.cli._get_cert_bundle() is None
        assert any("cert apply" in line for line in logs.output)
        mock_cloud.apply_cert.assert_not_called()

    async def test_get_cert_bundle_success(self) -> None:
        """A successful login provisions a cert bundle from the cloud."""
        sentinel = object()
        mock_cloud = AsyncMock()
        mock_cloud.login.return_value = True
        mock_cloud.apply_cert.return_value = sentinel
        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud):
            assert await self.cli._get_cert_bundle() is sentinel
        mock_cloud.apply_cert.assert_awaited_once()

    def test_extract_mac(self) -> None:
        """Test _extract_mac."""
        expected_mac = "1234567890ab"
        mac = _extract_mac(
            reply=b"",
            ssid_len=0,
            sn="a" * 16 + expected_mac + "1234",
        )
        assert mac == expected_mac
        mac2 = _extract_mac(
            reply=b"a" * 63 + b"bb" + b"\x12\x34\x56\x78\x90\xab",
            ssid_len=2,
            sn="a" * 16 + expected_mac + "1234",
        )
        assert mac2 == expected_mac
        mac3 = _extract_mac(b"", 1, "shortsn")
        assert mac3 is None

    async def test_discover(self) -> None:
        """Test discover."""
        mock_device = {
            "device_id": 1,
            "protocol": ProtocolVersion.V3,
            "type": 0xAC,
            "ip_address": "192.168.0.2",
            "port": 6444,
            "model": "AC123000",
            "device_subtype": 44204,
            "manufacturer_code": 0,
            "sn": "0000AC12300000001234567890ABCDEF",
            "mac": "1234567890AB",
        }
        mock_cloud_instance = AsyncMock()
        mock_device_instance = MagicMock()
        mock_device_instance.connect = AsyncMock(return_value=True)
        with (
            patch(
                "midealan.cli.discover",
            ) as mock_discover,
            patch.object(
                self.cli,
                "_get_cloud",
                return_value=mock_cloud_instance,
            ),
            patch(
                "midealan.cli.device_selector",
                return_value=mock_device_instance,
            ) as mock_device_selector,
            patch.object(
                mock_device_instance,
                "refresh_status",
                new_callable=AsyncMock,
            ) as refresh_status_mock,
        ):
            mock_discover.return_value = {1: mock_device}
            mock_cloud_instance.get_cloud_keys.return_value = {
                0: {"token": "token", "key": "key"},
            }
            mock_cloud_instance.get_default_keys.return_value = {
                99: {"token": "token", "key": "key"},
            }

            # test V3 device get_sn
            self.namespace.get_sn = True
            await self.cli.discover()  # test V3 device get_sn
            mock_discover.assert_called()

            # get_sn for a TLS device: the encrypted-serial warning is logged
            mock_discover.return_value = {
                2: {**mock_device, "device_id": 2, "sn": "", "sn_encrypted": True},
            }
            with self.assertLogs("cli", level="WARNING") as logs:
                await self.cli.discover()
            assert any("encrypted" in line for line in logs.output)
            mock_discover.return_value = {1: mock_device}

            # set get_sn to default False after test done
            self.namespace.get_sn = False

            # test V3 device: connect() already authenticated, discover only
            # calls refresh_status (once per candidate key).
            refresh_status_mock.side_effect = None
            mock_device_selector.reset_mock()
            with self.assertLogs("cli", level="INFO") as logs:
                await self.cli.discover()  # V3 device
            refresh_status_mock.assert_called_with(True)
            # The discovered subtype is reused (not 0) and the identity line is
            # surfaced for later use.
            assert mock_device_selector.call_args.kwargs["subtype"] == 44204
            assert any(
                "Discovered device" in line and "subtype 44204" in line
                for line in logs.output
            )
            refresh_status_mock.reset_mock()

            # V3 device where refresh_status raises: each failure is caught and
            # the device is simply not added to the list.
            refresh_status_mock.side_effect = [AuthException, NoSupportedProtocol]
            assert await self.cli.discover() == []
            refresh_status_mock.reset_mock()

            refresh_status_mock.side_effect = [SocketException, None]
            await self.cli.discover()  # V3 device SocketException on first key
            refresh_status_mock.reset_mock()

            refresh_status_mock.side_effect = [OSError, None]
            await self.cli.discover()  # V3 device OSError on first key
            refresh_status_mock.reset_mock()

            mock_device["protocol"] = ProtocolVersion.V2
            refresh_status_mock.side_effect = None
            await self.cli.discover()  # V2 device
            refresh_status_mock.assert_called_with(True)
            refresh_status_mock.reset_mock()

            mock_device_instance.connect.return_value = False
            await self.cli.discover()  # connect failed

            mock_discover.return_value = {}

            await self.cli.discover()  # No devices

            # An unsupported device (surfaced by discover but with no package)
            # is reported and skipped, never passed to device_selector.
            mock_device_instance.connect.reset_mock()
            mock_discover.return_value = {
                3: {
                    **mock_device,
                    "device_id": 3,
                    "type": 0x99,
                    "support": "unsupported",
                    "support_reason": "no device package for type 0x99",
                },
            }
            with self.assertLogs("cli", level="WARNING") as logs:
                assert await self.cli.discover() == []
            assert any("unsupported" in line for line in logs.output)
            mock_device_instance.connect.assert_not_called()

    async def test_discover_tls_device(self) -> None:
        """A TLS device provisions a cert bundle and drives control with it."""
        tls_device = {
            "device_id": 3,
            "protocol": ProtocolVersion.V3,
            "type": 0xE3,
            "ip_address": "192.168.0.3",
            "port": 6444,
            "model": "",
            "sn": "",
            "mac": "1234567890AB",
            "sn_encrypted": True,
        }
        cert_bundle = object()
        mock_device_instance = MagicMock()
        mock_device_instance.connect = AsyncMock(return_value=True)
        mock_device_instance.refresh_status = AsyncMock()
        with (
            patch("midealan.cli.discover", return_value={3: tls_device}),
            patch(
                "midealan.cli.device_selector",
                return_value=mock_device_instance,
            ) as device_selector_mock,
            patch.object(
                self.cli,
                "_get_cert_bundle",
                return_value=cert_bundle,
            ) as cert_bundle_mock,
        ):
            await self.cli.discover()
        cert_bundle_mock.assert_awaited_once()
        assert device_selector_mock.call_args.kwargs["cert_bundle"] is cert_bundle
        assert device_selector_mock.call_args.kwargs["token"] == ""

    async def test_discover_tls_devices_provision_cert_once(self) -> None:
        """Multiple TLS devices share a single cert provisioning."""

        def _tls(device_id: int, ip: str) -> dict[str, Any]:
            return {
                "device_id": device_id,
                "protocol": ProtocolVersion.V3,
                "type": 0xE3,
                "ip_address": ip,
                "port": 6444,
                "model": "",
                "sn": "",
                "mac": "1234567890AB",
                "sn_encrypted": True,
            }

        devices = {3: _tls(3, "192.168.0.3"), 4: _tls(4, "192.168.0.4")}
        cert_bundle = object()
        mock_device_instance = MagicMock()
        mock_device_instance.connect = AsyncMock(return_value=True)
        mock_device_instance.refresh_status = AsyncMock()
        with (
            patch("midealan.cli.discover", return_value=devices),
            patch(
                "midealan.cli.device_selector",
                return_value=mock_device_instance,
            ) as device_selector_mock,
            patch.object(
                self.cli,
                "_get_cert_bundle",
                return_value=cert_bundle,
            ) as cert_bundle_mock,
        ):
            await self.cli.discover()
        # Two TLS devices, but the certificate is provisioned only once.
        cert_bundle_mock.assert_awaited_once()
        assert device_selector_mock.call_count == 2
        for call in device_selector_mock.call_args_list:
            assert call.kwargs["cert_bundle"] is cert_bundle

    async def test_discover_tls_device_no_cert(self) -> None:
        """A TLS device with no provisionable cert is skipped."""
        tls_device = {
            "device_id": 3,
            "protocol": ProtocolVersion.V3,
            "type": 0xE3,
            "ip_address": "192.168.0.3",
            "port": 6444,
            "model": "",
            "sn": "",
            "mac": "1234567890AB",
            "sn_encrypted": True,
        }
        with (
            patch("midealan.cli.discover", return_value={3: tls_device}),
            patch(
                "midealan.cli.device_selector",
            ) as device_selector_mock,
            patch.object(self.cli, "_get_cert_bundle", return_value=None),
        ):
            assert await self.cli.discover() == []
        device_selector_mock.assert_not_called()

    def test_message(self) -> None:
        """Test message."""
        mock_device_instance = MagicMock()
        with patch(
            "midealan.cli.device_selector",
            return_value=mock_device_instance,
        ) as mock_device_selector:
            mock_device_selector.return_value = mock_device_instance

            self.cli.message()

            mock_device_selector.assert_called_once_with(
                device_id=0,
                name="",
                device_type=int(self.namespace.message[2]),
                ip_address="192.168.192.168",
                port=6664,
                device_protocol=ProtocolVersion.V2,
                model="0000",
                token="",
                key="",
                subtype=0,
                customize="",
            )
            mock_device_instance.process_message.assert_called_once_with(
                self.namespace.message,
            )

    def test_save(self) -> None:
        """Test save."""
        mock_path_instance = MagicMock()
        with patch("midealan.cli.get_config_file_path") as mock_get_config_file_path:
            mock_get_config_file_path.return_value = mock_path_instance

            self.cli.save()

            mock_get_config_file_path.assert_called_once_with(not self.namespace.user)
            mock_path_instance.open.assert_called_once_with(mode="w+", encoding="utf-8")
            handle = mock_path_instance.open.return_value.__enter__.return_value
            handle.write.assert_called_once_with(
                json.dumps(
                    {
                        "username": self.namespace.username,
                        "password": self.namespace.password,
                        "cloud_name": self.namespace.cloud_name,
                    },
                ),
            )

    async def test_download(self) -> None:
        """Test download."""
        mock_device = {
            "device_id": 1,
            "protocol": ProtocolVersion.V3,
            "type": 0xAC,
            "ip_address": "192.168.0.2",
            "port": 6444,
            "model": "ABCD1234",
            "device_subtype": 44204,
            "sn": "0000AC000ABCD1234000000000000000",
        }
        # An AC serial number: the type byte at sn[4:6] is "00", so the type
        # must come from the cloud appliance list, not the serial number.
        cloud_sn = "00000051222270043261305102930000"
        cloud_appliance = {
            "name": "AC",
            "type": 0xAC,
            "sn": cloud_sn,
            "sn8": "22270043",
            "model_number": 44204,
            "manufacturer_code": "0000",
            "model": "KFR-72L",
            "online": True,
        }
        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.list_appliances.return_value = {1: cloud_appliance}
        with (
            patch(
                "midealan.cli.discover",
                side_effect=[
                    {},  # test no device
                    {1: mock_device},  # test download lua with host ip
                ],
            ) as mock_discover,
            patch.object(
                self.cli,
                "_get_cloud",
                return_value=mock_cloud_instance,
            ),
        ):
            # cloud login failed: nothing is discovered or downloaded
            mock_cloud_instance.login.return_value = False
            await self.cli.download()
            mock_cloud_instance.login.assert_called_once()
            mock_discover.assert_not_called()
            mock_cloud_instance.download_lua.assert_not_called()
            mock_cloud_instance.login.reset_mock()

            mock_cloud_instance.login.return_value = True

            # host mode but no device found
            await self.cli.download()
            mock_discover.assert_called_once_with(ip_address=self.namespace.host)
            mock_discover.reset_mock()
            mock_cloud_instance.download_lua.assert_not_called()

            # download lua with host (device type comes from discovery)
            await self.cli.download()
            mock_discover.assert_called_once_with(ip_address=self.namespace.host)
            mock_discover.reset_mock()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                mock_device["type"],
                mock_device["sn"],
                mock_device["device_subtype"],
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()
            mock_cloud_instance.download_plugin.assert_called_once_with(
                str(Path()),
                mock_device["type"],
                mock_device["sn"],
            )
            mock_cloud_instance.download_plugin.reset_mock()

            # download lua with SN: type/subtype resolved from the cloud list
            # (the AC serial's sn[4:6] is "00", so the cloud value fixes it)
            self.namespace.host = None
            self.namespace.device_sn = cloud_sn
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                cloud_appliance["type"],
                cloud_sn,
                cloud_appliance["model_number"],
                cloud_appliance["manufacturer_code"],
            )
            mock_cloud_instance.download_lua.reset_mock()
            mock_cloud_instance.download_plugin.assert_called_once_with(
                str(Path()),
                cloud_appliance["type"],
                cloud_sn,
            )
            mock_cloud_instance.download_plugin.reset_mock()

            # download lua with SN and explicit device_type override: the legacy
            # path, which uses the argument without consulting the cloud
            # account. No subtype was supplied in this case.
            self.namespace.device_sn = cloud_sn
            self.namespace.device_type = bytes.fromhex("AC")
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0xAC,
                cloud_sn,
                None,
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()
            self.namespace.device_type = bytearray()

            # SN not on the account and no device_type: legacy fallback derives
            # the type from sn[4:6] (0xFF here). No subtype is available.
            unknown_sn = "0000FF00UNKNOWN00000000000000000"
            self.namespace.device_sn = unknown_sn
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0xFF,
                unknown_sn,
                None,
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()

            # SN not on the account with explicit device_type: honored as-is
            self.namespace.device_sn = unknown_sn
            self.namespace.device_type = bytes.fromhex("B0")
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0xB0,
                unknown_sn,
                None,
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()
            self.namespace.device_type = bytearray()

            # Invalid hex in the legacy SN type slot falls back to 0.
            invalid_hex_sn = "0000ZZ00UNKNOWN00000000000000000"
            self.namespace.device_sn = invalid_hex_sn
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0,
                invalid_hex_sn,
                None,
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()

            # Short legacy SNs skip the hex-derived type path and keep 0.
            short_sn = "SHORTSN"
            self.namespace.device_sn = short_sn
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0,
                short_sn,
                None,
                "0000",
            )
            mock_cloud_instance.download_lua.reset_mock()

            # no host and no SN: download every device in the cloud account
            self.namespace.host = None
            self.namespace.device_sn = None
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                cloud_appliance["type"],
                cloud_sn,
                cloud_appliance["model_number"],
                cloud_appliance["manufacturer_code"],
            )
            mock_cloud_instance.download_lua.reset_mock()

            # no host, no SN, and no devices on the account
            mock_cloud_instance.list_appliances.return_value = {}
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_not_called()

    async def test_download_host_encrypted_serial(self) -> None:
        """Download via --host for a TLS device whose LAN serial is encrypted.

        discover() returns an empty serial/model flagged ``sn_encrypted``; the
        host path must resolve a real serial from the cloud account -- by
        device id first, then by a unique device type -- before downloading,
        and refuse when neither matches or the type match is ambiguous.
        """
        device_id = 42
        tls_device = {
            "device_id": device_id,
            "protocol": ProtocolVersion.V3,
            "type": 0xAC,
            "ip_address": "192.168.0.2",
            "port": 6444,
            "model": "",
            "sn": "",
            "sn_encrypted": True,
        }
        cloud_sn = "00000051222270043261305102930000"
        cloud_appliance = {
            "name": "AC",
            "type": 0xAC,
            "sn": cloud_sn,
            "model": "KFR-72L",
            "model_number": 44204,
            "manufacturer_code": "1234",
        }
        other_appliance = {**cloud_appliance, "type": 0xDB}
        self.namespace.host = "192.168.0.1"
        self.namespace.device_sn = ""
        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.login.return_value = True
        with (
            patch(
                "midealan.cli.discover",
                # download() pops from the returned dict, so hand back a fresh
                # copy for each of the sub-cases below.
                side_effect=lambda **_: {device_id: dict(tls_device)},
            ),
            patch.object(
                self.cli,
                "_get_cloud",
                return_value=mock_cloud_instance,
            ),
        ):
            # id match: the appliance keyed by device_id is used verbatim,
            # including its non-default manufacturer code.
            mock_cloud_instance.list_appliances.return_value = {
                device_id: cloud_appliance,
            }
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0xAC,
                cloud_sn,
                cloud_appliance["model_number"],
                cloud_appliance["manufacturer_code"],
            )
            mock_cloud_instance.download_lua.reset_mock()

            # id absent, unique type match: fall back to the type match
            mock_cloud_instance.list_appliances.return_value = {7: cloud_appliance}
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once_with(
                str(Path()),
                0xAC,
                cloud_sn,
                cloud_appliance["model_number"],
                cloud_appliance["manufacturer_code"],
            )
            mock_cloud_instance.download_lua.reset_mock()

            # id absent and no device of that type: stop without downloading
            mock_cloud_instance.list_appliances.return_value = {7: other_appliance}
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_not_called()

            # id absent and ambiguous type match: stop and ask for --sn
            mock_cloud_instance.list_appliances.return_value = {
                7: cloud_appliance,
                8: {**cloud_appliance, "sn": "00000051222270043261305102939999"},
            }
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_not_called()

            # no user credentials: the preset fallback account cannot list the
            # user's devices, so stop early with guidance and never query the
            # cloud for appliances.
            mock_cloud_instance.list_appliances.reset_mock()
            self.namespace.username = ""
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.download()
            assert any(
                "--cloud" in line and "--username" in line for line in logs.output
            )
            mock_cloud_instance.list_appliances.assert_not_called()
            mock_cloud_instance.download_lua.assert_not_called()
            self.namespace.username = "user"

    async def test_download_without_complete_serial(self) -> None:
        """Type plus model/subtype downloads without exposing a real SN."""
        self.namespace.host = None
        self.namespace.device_sn = None
        self.namespace.device_type = bytes.fromhex("AC")
        self.namespace.device_model = "22013279"
        self.namespace.device_subtype = "8"
        mock_cloud = AsyncMock()
        mock_cloud.login.return_value = True

        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud):
            await self.cli.download()

            synthetic_sn = "0000AC00022013279" + "0" * 15
            assert len(synthetic_sn) == 32
            mock_cloud.download_lua.assert_awaited_once_with(
                str(Path()),
                0xAC,
                synthetic_sn,
                "8",
                "0000",
            )
            mock_cloud.download_plugin.assert_awaited_once_with(
                str(Path()),
                0xAC,
                synthetic_sn,
            )

            # Subtype-only lookup can select subtype/common lua, but cannot
            # identify an exact plugin because plugin matching uses SN8.
            mock_cloud.reset_mock()
            mock_cloud.login.return_value = True
            self.namespace.device_model = None
            with self.assertLogs("cli", level="WARNING") as logs:
                await self.cli.download()
            zero_model_sn = "0000AC00000000000" + "0" * 15
            mock_cloud.download_lua.assert_awaited_once_with(
                str(Path()),
                0xAC,
                zero_model_sn,
                "8",
                "0000",
            )
            mock_cloud.download_plugin.assert_not_awaited()
            assert any("exact plugin" in line for line in logs.output)

            # A model/subtype without a device type is not enough to form the
            # cloud lookup identity.
            mock_cloud.reset_mock()
            mock_cloud.login.return_value = True
            self.namespace.device_type = bytearray()
            self.namespace.device_model = "22013279"
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.download()
            mock_cloud.download_lua.assert_not_awaited()
            assert any("--type is required" in line for line in logs.output)

            # Reject marketing model names and truncated SN8 values instead of
            # silently shifting the synthetic serial offsets.
            self.namespace.device_type = bytes.fromhex("AC")
            self.namespace.device_model = "KFR-72L"
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.download()
            mock_cloud.download_lua.assert_not_awaited()
            assert any("8-character" in line for line in logs.output)

    async def test_download_not_supported(self) -> None:
        """Download on a cloud without lua/plugin support is handled cleanly."""
        cloud_sn = "0000FA00ABCD1234000000000000000A"
        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.login.return_value = True
        mock_cloud_instance.list_appliances.return_value = {}
        # MideaAirCloud raises NotImplementedError for these downloads.
        mock_cloud_instance.download_lua.side_effect = NotImplementedError
        mock_cloud_instance.download_plugin.side_effect = NotImplementedError
        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud_instance):
            self.namespace.host = None
            self.namespace.device_sn = cloud_sn
            self.namespace.device_type = bytes.fromhex("FA")
            # Must not raise: the NotImplementedError is caught and logged.
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once()
            # lua download failed, so the plugin download is not attempted.
            mock_cloud_instance.download_plugin.assert_not_called()

    async def test_download_lua_only(self) -> None:
        """A cloud with lua but no plugin support downloads lua and warns."""
        cloud_sn = "0000FA00ABCD1234000000000000000A"
        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.login.return_value = True
        mock_cloud_instance.list_appliances.return_value = {}
        # Legacy MideaAirCloud: lua downloads, plugin is not supported.
        mock_cloud_instance.download_lua.return_value = "fileName.lua"
        mock_cloud_instance.download_plugin.side_effect = NotImplementedError
        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud_instance):
            self.namespace.host = None
            self.namespace.device_sn = cloud_sn
            self.namespace.device_type = bytes.fromhex("FA")
            # Must not raise: the plugin NotImplementedError is caught and the
            # successful lua download stands.
            await self.cli.download()
            mock_cloud_instance.download_lua.assert_called_once()
            mock_cloud_instance.download_plugin.assert_called_once()

    async def test_download_continues_after_device_failures(self) -> None:
        """Bulk download continues when individual devices fail."""
        appliances = {
            1: {
                "type": 0xAC,
                "sn": "0000AC000FIRST00000000000000000",
                "model": "FIRST",
                "manufacturer_code": "0001",
            },
            2: {
                "type": 0xB0,
                "sn": "0000B000SECOND0000000000000000",
                "model": "SECOND",
                "manufacturer_code": "0002",
            },
            3: {
                "type": 0xFA,
                "sn": "0000FA00THIRD00000000000000000",
                "model": "THIRD",
                "manufacturer_code": "0003",
            },
        }
        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.login.return_value = True
        mock_cloud_instance.list_appliances.return_value = appliances
        mock_cloud_instance.download_lua.side_effect = [
            RuntimeError("lua failed"),
            "second.lua",
            "third.lua",
        ]
        mock_cloud_instance.download_plugin.side_effect = [
            RuntimeError("plugin failed"),
            "third.plugin",
        ]
        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud_instance):
            self.namespace.host = None
            self.namespace.device_sn = None
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.download()

        assert mock_cloud_instance.download_lua.await_count == 3
        assert mock_cloud_instance.download_plugin.await_count == 2
        assert mock_cloud_instance.download_lua.await_args_list[0].args == (
            str(Path()),
            appliances[1]["type"],
            appliances[1]["sn"],
            None,
            appliances[1]["manufacturer_code"],
        )
        assert mock_cloud_instance.download_lua.await_args_list[2].args == (
            str(Path()),
            appliances[3]["type"],
            appliances[3]["sn"],
            None,
            appliances[3]["manufacturer_code"],
        )
        assert mock_cloud_instance.download_plugin.await_args_list[0].args == (
            str(Path()),
            appliances[2]["type"],
            appliances[2]["sn"],
        )
        assert mock_cloud_instance.download_plugin.await_args_list[1].args == (
            str(Path()),
            appliances[3]["type"],
            appliances[3]["sn"],
        )
        assert "Failed to download lua file for 0000AC000FIRST" in logs.output[0]
        assert "Failed to download plugin file for 0000B000SECOND" in logs.output[1]

    async def test_info(self) -> None:
        """Test the info command lists cloud appliances grouped by home."""
        home_a = {
            1: {
                "name": "Living Room AC",
                "type": 0xAC,
                "sn8": "22270043",
                "model": "KFR-72L",
                "online": True,
            },
            2: {
                "name": "Washer",
                "type": 0xDB,
                "sn8": "38127874",
                "model": "MD100",
                "online": False,
            },
        }
        home_b = {
            3: {
                "name": "Kitchen Hood",
                "type": 0xEA,
                "sn8": "12345678",
                "model": "CXW-200",
                "online": True,
            },
        }
        # Two homes (groups) under one account, keyed by home id.
        homes = {63535541: "Home A", 107400725: "Home B"}
        by_home = {"63535541": home_a, "107400725": home_b}

        # Device 1 has a richer per-device record (Meiju-style, carrying the
        # Wi-Fi version); the others have none, so info() falls back to the list
        # entry, which has no wifi_version key.
        device_infos = {1: {**home_a[1], "wifi_version": "059009012205"}}

        def _appliances_for(home_id: str) -> dict[int, dict[str, Any]]:
            return by_home.get(home_id, {})

        mock_cloud_instance = AsyncMock()
        mock_cloud_instance.list_home.return_value = homes
        mock_cloud_instance.list_appliances.side_effect = _appliances_for
        mock_cloud_instance.get_device_info.side_effect = device_infos.get
        with patch.object(self.cli, "_get_cloud", return_value=mock_cloud_instance):
            # cloud login failed: nothing is listed
            mock_cloud_instance.login.return_value = False
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.info()
            mock_cloud_instance.login.assert_called_once()
            mock_cloud_instance.list_appliances.assert_not_called()
            assert any("Failed to authenticate" in line for line in logs.output)
            mock_cloud_instance.login.reset_mock()

            mock_cloud_instance.login.return_value = True

            # no appliances in any home -> one error after the home headers
            mock_cloud_instance.list_appliances.side_effect = None
            mock_cloud_instance.list_appliances.return_value = {}
            with self.assertLogs("cli", level="ERROR") as logs:
                await self.cli.info()
            assert any("No devices found" in line for line in logs.output)

            # appliances present: each home prints its own devices, with the
            # Wi-Fi version taken from the per-device record where available.
            mock_cloud_instance.list_appliances.return_value = None
            mock_cloud_instance.list_appliances.side_effect = _appliances_for
            mock_cloud_instance.get_device_info.reset_mock()
            with self.assertLogs("cli", level="INFO") as logs:
                await self.cli.info()

        assert mock_cloud_instance.get_device_info.await_count == 3
        output = "\n".join(logs.output)
        # Homes are printed as separate groups, each under its own header.
        assert "Home 63535541 (Home A): 2 device(s)" in output
        assert "Home 107400725 (Home B): 1 device(s)" in output
        assert "name Living Room AC" in output
        assert "type 0xAC" in output
        assert "wifi_version 059009012205" in output
        assert "name Washer" in output
        assert "type 0xDB" in output
        # Device 2 fell back to the list entry: no Wi-Fi version is available.
        assert "sn8 38127874" in output
        assert "wifi_version None" in output
        # The second home's device is listed too.
        assert "name Kitchen Hood" in output
        assert "Found 3 device(s) across 2 home(s)" in output

    async def test_set_attribute(self) -> None:
        """Test set attribute."""
        mock_device_instance = MagicMock()
        mock_device_instance.connect = AsyncMock(return_value=True)
        mock_device_instance.refresh_status = AsyncMock()
        with (
            patch.object(
                self.cli,
                "discover",
                side_effect=[
                    [],
                    [mock_device_instance],
                    [mock_device_instance],
                    [mock_device_instance],
                ],
            ),
            patch("midealan.cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await self.cli.set_attribute()
            mock_device_instance.set_attribute.assert_not_called()

            await self.cli.set_attribute()
            mock_device_instance.set_attribute.assert_called_once_with("power", False)
            mock_device_instance.reset_mock()

            self.namespace.attribute = "mode"
            self.namespace.value = "2"
            self.namespace.attr_type = "int"

            await self.cli.set_attribute()
            mock_device_instance.set_attribute.assert_called_once_with("mode", 2)
            mock_device_instance.reset_mock()

            self.namespace.attribute = "attr"
            self.namespace.value = "string"
            self.namespace.attr_type = "str"

            await self.cli.set_attribute()
            mock_device_instance.set_attribute.assert_called_once_with("attr", "string")

    def test_run(self) -> None:
        """Test run."""
        mock_logger = MagicMock()
        with (
            patch("logging.basicConfig") as mock_basic_config,
            patch("logging.getLogger", return_value=mock_logger),
            patch.object(mock_logger, "setLevel") as mock_set_level,
        ):
            self.cli.session = AsyncMock()
            self.cli.run(self.namespace)
            mock_basic_config.assert_called_once_with(level=logging.DEBUG)
            mock_basic_config.reset_mock()
            mock_set_level.assert_called_with(logging.INFO)
            mock_set_level.reset_mock()
            self.namespace.func.assert_called_once()

            # Test coroutine function
            self.namespace.func = AsyncMock()
            self.namespace.debug = False
            self.cli.run(self.namespace)
            mock_basic_config.assert_called_once_with(level=logging.INFO)
            mock_set_level.assert_called_with(logging.WARNING)
            self.namespace.func.assert_called_once()

    def test_run_without_cloud_session(self) -> None:
        """A command that does not use the cloud has no session to close."""
        cli = MideaCLI()
        mock_logger = MagicMock()
        with (
            patch("logging.basicConfig"),
            patch("logging.getLogger", return_value=mock_logger),
        ):
            cli.run(self.namespace)

        self.namespace.func.assert_called_once()
        assert not hasattr(cli, "session")

    def test_main_call(self) -> None:
        """Test main call."""
        # Command to run the script
        cmd = [
            sys.executable,
            "-m",
            "midealan.cli",
        ]
        clear_config = False
        if not get_config_file_path().exists():
            clear_config = True
            subprocess.run([*cmd, "save"], capture_output=True, text=True, check=False)  # noqa: S603

        # Run the command and capture the output
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

        # Check if the script executed without errors
        assert result.returncode == 2

        result = subprocess.run(  # noqa: S603
            [*cmd, "save"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0

        if clear_config:
            get_config_file_path().unlink()

    def test_main(self) -> None:
        """Test main entry parses args and merges config file values."""
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "midea-lan.json"
            config_file.write_text(
                json.dumps({"username": "configuser", "password": "configpass"}),
                encoding="utf-8",
            )
            exit_code: int | str | None = None
            with (
                patch.object(sys, "argv", ["midealan", "discover", "-p", "argpass"]),
                patch(
                    "midealan.cli.get_config_file_path",
                    return_value=config_file,
                ),
                patch.object(MideaCLI, "run") as mock_run,
            ):
                try:
                    main()
                except SystemExit as exc:
                    exit_code = exc.code

            assert exit_code == 0
            mock_run.assert_called_once()
            namespace = mock_run.call_args[0][0]
            # username not passed on command line: filled from the config file
            assert namespace.username == "configuser"
            # password passed on command line: config value is not applied
            assert namespace.password == "argpass"
            assert namespace.func.__name__ == "discover"

    def test_main_without_config_file(self) -> None:
        """The CLI runs with command-line defaults when no config exists."""
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "missing.json"
            exit_code: int | str | None = None
            with (
                patch.object(sys, "argv", ["midealan", "discover"]),
                patch(
                    "midealan.cli.get_config_file_path",
                    return_value=config_file,
                ),
                patch.object(MideaCLI, "run") as mock_run,
            ):
                try:
                    main()
                except SystemExit as exc:
                    exit_code = exc.code

        assert exit_code == 0
        mock_run.assert_called_once()

    def test_download_identity_argument_aliases(self) -> None:
        """Short options and compatibility aliases populate the same fields."""
        argument_sets = [
            [
                "--cloud",
                "SmartHome",
                "--sn",
                "SERIAL",
                "--type",
                "AC",
                "--model",
                "22013279",
                "--subtype",
                "8",
            ],
            [
                "--cloud-name",
                "SmartHome",
                "--device-sn",
                "SERIAL",
                "--device-type",
                "AC",
                "--device-model",
                "22013279",
                "--device-subtype",
                "8",
            ],
            [
                "--cloud-name",
                "SmartHome",
                "--device-sn",
                "SERIAL",
                "--device-type",
                "AC",
                "--device-model",
                "22013279",
                "--model-number",
                "8",
            ],
        ]
        for identity_args in argument_sets:
            with (
                self.subTest(identity_args=identity_args),
                TemporaryDirectory() as tmpdir,
            ):
                config_file = Path(tmpdir) / "missing.json"
                exit_code: int | str | None = None
                with (
                    patch.object(sys, "argv", ["midealan", "download", *identity_args]),
                    patch(
                        "midealan.cli.get_config_file_path",
                        return_value=config_file,
                    ),
                    patch.object(MideaCLI, "run") as mock_run,
                ):
                    try:
                        main()
                    except SystemExit as exc:
                        exit_code = exc.code

                assert exit_code == 0
                namespace = mock_run.call_args.args[0]
                assert namespace.device_sn == "SERIAL"
                assert namespace.device_type == bytes.fromhex("AC")
                assert namespace.device_model == "22013279"
                assert namespace.device_subtype == "8"
                assert namespace.cloud_name == "SmartHome"

    def test_download_help_shows_only_short_identity_options(self) -> None:
        """Help recommends concise options while compatibility aliases stay hidden."""
        exit_code: int | str | None = None
        with (
            patch.object(sys, "argv", ["midealan", "download", "--help"]),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code

        assert exit_code == 0
        help_text = stdout.getvalue()
        for option in ("--cloud", "--sn", "--type", "--model", "--subtype"):
            assert option in help_text
        for alias in (
            "--cloud-name",
            "--device-sn",
            "--device-type",
            "--device-model",
            "--device-subtype",
            "--model-number",
        ):
            assert alias not in help_text

    def test_main_module_entry(self) -> None:
        """Test the __main__ guard when running the module as a script."""
        with (
            patch.object(sys, "argv", ["midealan.cli", "--version"]),
            warnings.catch_warnings(),
        ):
            # runpy warns when re-executing an already imported module
            warnings.simplefilter("ignore", RuntimeWarning)
            with pytest.raises(SystemExit) as exit_info:
                runpy.run_module("midealan.cli", run_name="__main__")

        assert exit_info.value.code == 0

    def test_get_config_file_path(self) -> None:
        """Test get config file path."""
        mock_path = MagicMock()
        with (
            patch("midealan.cli.Path", return_value=mock_path),
            patch.object(mock_path, "exists", return_value=False),
        ):
            get_config_file_path()

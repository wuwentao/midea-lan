"""Test cloud."""

import json
import logging
from collections.abc import Callable
from copy import deepcopy
from hashlib import md5, sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientConnectionError, ClientSession, ClientTimeout, web

from midealan.cloud import (
    DEFAULT_KEYS,
    SUPPORTED_CLOUDS,
    MeijuCloud,
    MideaAirCloud,
    MideaCloud,
    SmartHomeCloud,
    ToshibaIOLife,
    TSmartLifeCloud,
    _mask_token,
    _redact_data,
    get_default_cloud,
    get_midea_cloud,
    get_preset_account_cloud,
)
from midealan.exceptions import CloudAuthError, CloudError, ElementMissing
from midealan.security import ToshibaIOLifeSecurity

# ``CloudSecurity.get_udp_id(100, method)``. Hard-coded on purpose: deriving them
# with the same helper the implementation calls would not catch a request that
# sends the wrong method's UDP ID.
UDP_IDS = {
    1: "dec4da86e0aeefadde14a4e553680b9b",
    2: "b2dd199071d527a33c8239833a5bf5fb",
}
_TOSHIBA_APP_KEY = SUPPORTED_CLOUDS["Toshiba Iolife"]["app_key"]
_TOSHIBA_ACCESS_TOKEN = (
    "bd18a46bb4d681f5142bca381d56924a86aad13f1f9870157f22b7c924ddb431"
)
_TOSHIBA_ENCRYPTED_SN = (
    "e1f17526c18d049e4862e19f5d6cd269"
    "df9b09edd41d4b2627b35dbb2d47b963"
    "a433df71998b41d4dc354e9bdf78902a"
)
_TOSHIBA_EXPECTED_SN = "0008AC0000000000000000000000BEEF"


def _token_requests(session: Mock) -> list[tuple[str, dict]]:
    """Return (url, payload) for every getToken request the client actually sent.

    The response side_effect only controls what comes back; these assertions
    pin down what goes out, so a regression to the v1 endpoint or to a
    string-valued ``applianceCodes`` cannot pass silently.
    """
    out = []
    for call in session.request.await_args_list:
        url = call.args[1] if len(call.args) > 1 else call.kwargs.get("url", "")
        if "getToken" not in url:
            continue
        out.append((url, json.loads(call.kwargs["data"])))
    return out


class CloudTest(IsolatedAsyncioTestCase):
    """Cloud test case."""

    responses: ClassVar[dict[str, bytes]] = {}

    def setUp(self) -> None:
        """Set tests up."""
        file_path = Path(__file__)
        for file in Path.iterdir(Path(file_path.parent, "responses")):
            file_path = Path(file)
            with file_path.open(
                encoding="utf-8",
            ) as f:
                self.responses[file_path.name] = bytes(f.read(), encoding="utf-8")

    def test_lua_download_metadata(self) -> None:
        """Test lua download metadata validation and filename sanitization."""
        metadata = MideaCloud._get_lua_download_metadata(
            "downloads",
            {"url": "url", "fileName": "../lua.lua"},
            "serial",
        )
        assert metadata == ("url", Path("downloads/lua.lua"))

        with self.assertLogs("midealan.cloud", level="WARNING") as logs:
            assert (
                MideaCloud._get_lua_download_metadata(
                    "downloads",
                    {"fileName": "lua.lua"},
                    "serial",
                )
                is None
            )
            assert (
                MideaCloud._get_lua_download_metadata(
                    "downloads",
                    {"url": "", "fileName": "lua.lua"},
                    "serial",
                )
                is None
            )
            assert (
                MideaCloud._get_lua_download_metadata(
                    "downloads",
                    {"url": "url"},
                    "serial",
                )
                is None
            )
            assert (
                MideaCloud._get_lua_download_metadata(
                    "downloads",
                    {"url": "url", "fileName": None},
                    "serial",
                )
                is None
            )
            assert (
                MideaCloud._get_lua_download_metadata(
                    "downloads",
                    {"url": "url", "fileName": ".."},
                    "serial",
                )
                is None
            )
        assert len(logs.output) == 5

    def test_get_midea_cloud(self) -> None:
        """Test get midea cloud."""
        session = AsyncMock()
        assert isinstance(get_midea_cloud("美的美居", session, "", ""), MeijuCloud)
        assert isinstance(
            get_midea_cloud("SmartHome", session, "", ""),
            SmartHomeCloud,
        )
        assert isinstance(get_midea_cloud("Midea Air", session, "", ""), MideaAirCloud)
        assert isinstance(
            get_midea_cloud("NetHome Plus", session, "", ""),
            MideaAirCloud,
        )
        assert isinstance(
            get_midea_cloud("Ariston Clima", session, "", ""),
            MideaAirCloud,
        )
        assert isinstance(
            get_midea_cloud("Toshiba Iolife", session, "", ""),
            ToshibaIOLife,
        )
        with pytest.raises(ElementMissing):
            get_midea_cloud("Invalid", session, "", "")
        assert isinstance(
            get_midea_cloud("TSmartLife", session, "account", "password"),
            TSmartLifeCloud,
        )

    async def test_get_default_cloud(self) -> None:
        """Test get default cloud name."""
        default_cloud = get_default_cloud()
        assert default_cloud == "NetHome Plus"

    async def test_get_default_cloud_missing(self) -> None:
        """Test get default cloud name without any default cloud."""
        with (
            patch.dict(
                "midealan.cloud.SUPPORTED_CLOUDS",
                {"NoDefault": {}},
                clear=True,
            ),
            pytest.raises(ElementMissing),
        ):
            get_default_cloud()

    def test_mask_token(self) -> None:
        """Test _mask_token."""
        assert _mask_token("") == ""
        assert _mask_token("1234567890") == "12345*****"

    def test_redact_data_masks_token_and_key(self) -> None:
        """Test _redact_data masks token/key values in a getToken payload.

        The raw getToken response reaches the debug log via ``str(raw)``; its
        ``token`` and ``key`` values must be masked so LAN credentials never
        appear in full.
        """
        raw = (
            '{"code": 0, "data": {"tokenlist": [{"udpId": "u", '
            '"token": "SECRET_TOKEN_VALUE", "key": "SECRET_KEY_VALUE"}]}}'
        )
        redacted = _redact_data(raw)
        assert "SECRET_TOKEN_VALUE" not in redacted
        assert "SECRET_KEY_VALUE" not in redacted
        # First five characters stay visible, matching _mask_token.
        assert "SECRE*****" in redacted
        # Non-sensitive structure is preserved.
        assert '"udpId": "u"' in redacted

        # dict-repr shape (single quotes) is handled too.
        repr_raw = "{'token': 'abcdefghij', 'key': 'zyxwvutsrq'}"
        redacted_repr = _redact_data(repr_raw)
        assert "abcdefghij" not in redacted_repr
        assert "zyxwvutsrq" not in redacted_repr

    async def test_get_cloud_servers(self) -> None:
        """Test get cloud servers."""
        servers = await MideaCloud.get_cloud_servers()
        assert len(servers.items()) == 7

    async def test_midea_cloud_api_request_timeout(self) -> None:
        """Test _api_request retries and returns None on timeout."""
        session = Mock()
        session.request = AsyncMock(side_effect=TimeoutError("timeout"))
        security = Mock()
        security.sign.return_value = "signature"
        cloud = MideaCloud(
            session=session,
            security=security,
            app_id="appid",
            app_key="appkey",
            account="account",
            password="password",
            api_url="http://api.url/",
        )
        with self.assertLogs("midealan.cloud", level="WARNING") as logs:
            assert await cloud._api_request(endpoint="/endpoint", data={}) is None
        assert len(logs.output) == 3

    async def test_get_preset_account_cloud(self) -> None:
        """Test get preset cloud account."""
        credentials = get_preset_account_cloud()
        assert credentials["password"] == "a0d6e30c94b15"
        assert credentials["cloud_name"] == "NetHome Plus"

    async def test_midea_cloud_unimplemented(self) -> None:
        """Test unimplemented MideaCloud methods."""
        session = Mock()
        security = Mock()
        cloud = MideaCloud(
            session=session,
            security=security,
            app_id="appid",
            app_key="appkey",
            account="account",
            password="password",
            api_url="http://api.url/",
        )
        assert cloud._make_general_data() == {}
        with pytest.raises(NotImplementedError):
            await cloud.login()
        with pytest.raises(NotImplementedError):
            await cloud.list_appliances(None)
        with pytest.raises(NotImplementedError):
            await cloud.download_lua("path", 10, "0000AC000ABCD1234000")
        with pytest.raises(NotImplementedError):
            await cloud.download_plugin("path", 10, "0000AC000ABCD1234000")

    async def test_meijucloud_login_success(self) -> None:
        """Test MeijuCloud login."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["cloud_login_id.json"],
                self.responses["meijucloud_login.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

    async def test_meijucloud_login_invalid_user(self) -> None:
        """Test MeijuCloud login invalid user."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["cloud_invalid_response.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert not await cloud.login()

    async def test_meijucloud_login_api_request_none(self) -> None:
        """Test MeijuCloud login failure when the login response is missing."""
        session = Mock()
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            assert not await cloud.login()
        assert "Meiju Cloud login failed" in logs.output[0]

    async def test_meijucloud_login_response_none(self) -> None:
        """Test MeijuCloud login failure when the final login API returns none."""
        session = Mock()
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_get_login_id", AsyncMock(return_value="loginid")),
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            assert not await cloud.login()
        assert "Meiju Cloud login failed" in logs.output[0]

    async def test_meijucloud_get_keys(self) -> None:
        """Test MeijuCloud get_cloud_keys."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                # get_cloud_keys() lists homes first, then queries the v2
                # endpoint per method until one home returns keys.
                self.responses["meijucloud_list_home.json"],
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
                self.responses["meijucloud_list_home.json"],
                self.responses["meijucloud_get_keys1.json"],
                self.responses["cloud_invalid_response.json"],
                self.responses["meijucloud_list_home.json"],
                self.responses["cloud_invalid_response.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None

        # test method1 + method2
        keys3: dict = await cloud.get_cloud_keys(100)
        # test response token/key
        assert keys3[1]["token"] == "method1_return_token1"
        assert keys3[1]["key"] == "method1_return_key1"
        assert keys3[2]["token"] == "method2_return_token2"
        assert keys3[2]["key"] == "method2_return_key2"
        # simple test default key with length
        assert len(keys3) == 2

        # test method1
        keys1: dict = await cloud.get_cloud_keys(100)
        # test response token/key
        assert keys1[1]["token"] == "method1_return_token1"
        assert keys1[1]["key"] == "method1_return_key1"
        # simple test default key with length
        assert len(keys1) == 1

        # test method2
        keys2: dict = await cloud.get_cloud_keys(100)
        # test response token/key
        assert keys2[2]["token"] == "method2_return_token2"
        assert keys2[2]["key"] == "method2_return_key2"
        # simple test default key with length
        assert len(keys2) == 1

        # test only default key
        keys = await cloud.get_default_keys()
        assert len(keys) == 1
        assert keys == DEFAULT_KEYS

        # Pin the outbound contract: every lookup must hit v2 and send
        # homegroupId + udpid + a list-valued applianceCodes.
        requests = _token_requests(session)
        assert requests
        for url, payload in requests:
            assert url.endswith("/v2/iot/secure/getToken")
            assert payload["applianceCodes"] == ["100"]
        # Each of the three lookups stops at the first home that returns a key,
        # so the exact sequence is home "1" x method 1, method 2 -- three times.
        assert [(p["homegroupId"], p["udpid"]) for _url, p in requests] == [
            ("1", UDP_IDS[1]),
            ("1", UDP_IDS[2]),
        ] * 3

    async def test_meijucloud_get_keys_v2_fallback_to_v1(self) -> None:
        """Test MeijuCloud falls back to the v1 endpoint when v2 returns nothing."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["meijucloud_list_home.json"],
                # v2, home 1: both methods come back empty
                self.responses["cloud_invalid_response.json"],
                self.responses["cloud_invalid_response.json"],
                # v2, home 2: same
                self.responses["cloud_invalid_response.json"],
                self.responses["cloud_invalid_response.json"],
                # v1 fallback
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None

        keys: dict = await cloud.get_cloud_keys(100)
        assert keys[1]["token"] == "method1_return_token1"
        assert keys[1]["key"] == "method1_return_key1"
        assert keys[2]["token"] == "method2_return_token2"
        assert keys[2]["key"] == "method2_return_key2"
        assert len(keys) == 2

        # v2 is tried for both homes x both methods, then v1 once per method.
        requests = _token_requests(session)
        v2 = [r for r in requests if r[0].endswith("/v2/iot/secure/getToken")]
        v1 = [r for r in requests if r[0].endswith("/v1/iot/secure/getToken")]
        for _url, payload in v2:
            assert payload["applianceCodes"] == ["100"]
        for _url, payload in v1:
            # the inherited v1 implementation sends the plain string form
            assert payload["applianceCodes"] == "100"
        # Both homes are tried, each with both methods, in order.
        assert [(p["homegroupId"], p["udpid"]) for _url, p in v2] == [
            ("1", UDP_IDS[1]),
            ("1", UDP_IDS[2]),
            ("2", UDP_IDS[1]),
            ("2", UDP_IDS[2]),
        ]
        # The full ordered endpoint sequence: four v2 calls then two v1 calls,
        # proving no v1 request is interleaved into the v2 phase.
        assert [url.rsplit("=", 1)[-1] for url, _payload in requests] == [
            *(["/v2/iot/secure/getToken"] * 4),
            *(["/v1/iot/secure/getToken"] * 2),
        ]
        # v1 keeps the method-specific UDP ID but carries no home.
        assert [p["udpid"] for _url, p in v1] == [UDP_IDS[1], UDP_IDS[2]]
        assert all("homegroupId" not in p for _url, p in v1)

    async def test_meijucloud_get_keys_no_home(self) -> None:
        """Test MeijuCloud get_cloud_keys when the home list is unavailable."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                # list_home fails, so v2 is skipped entirely
                self.responses["cloud_invalid_response.json"],
                # v1 fallback
                self.responses["meijucloud_get_keys1.json"],
                self.responses["cloud_invalid_response.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None

        keys: dict = await cloud.get_cloud_keys(100)
        assert keys[1]["token"] == "method1_return_token1"
        assert len(keys) == 1

        # No home list means v2 is skipped entirely; only v1 is called.
        requests = _token_requests(session)
        assert requests
        for url, _payload in requests:
            assert url.endswith("/v1/iot/secure/getToken")

    async def test_meijucloud_get_keys_ignores_nonmatching_token(self) -> None:
        """Test get_cloud_keys skips non-matching token entries.

        Non-matching tokens are ignored on both the v2 path (all homes and
        methods) and the inherited v1 fallback, so the overall result is empty.
        """
        nonmatching = (
            b'{"code": 0, "data": {"tokenlist": [{"udpId": "wrong", '
            b'"token": "TOK", "key": "KEY"}]}}'
        )
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["meijucloud_list_home.json"],
                # v2: two homes x two methods, every token has a wrong udpId
                nonmatching,
                nonmatching,
                nonmatching,
                nonmatching,
                # v1 fallback: both methods also non-matching
                nonmatching,
                nonmatching,
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.get_cloud_keys(100) == {}

    async def test_meijucloud_list_home(self) -> None:
        """Test MeijuCloud list_home."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["meijucloud_list_home.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        homes = await cloud.list_home()
        assert homes is not None
        assert len(homes.keys()) == 2
        assert homes[1] == "Home 1"
        assert homes[2] == "Home 2"

        response.read = AsyncMock(
            return_value=self.responses["cloud_invalid_response.json"],
        )
        assert await cloud.list_home() is None

    async def test_meijucloud_list_appliances(self) -> None:
        """Test MeijuCloud list_appliances."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["cloud_login_id.json"],
                self.responses["meijucloud_login.json"],
                self.responses["meijucloud_list_appliances.json"],
                self.responses["cloud_invalid_response.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()
        appliances = await cloud.list_appliances("1")
        assert appliances is not None
        assert len(appliances.keys()) == 2
        appliance = appliances.get(1)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == "mySecretKey"
        assert appliance.get("sn8") == "9d52c159"
        assert appliance.get("model_number") == 10
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == "Product Model"
        assert appliance.get("online")

        appliance = appliances.get(2)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name 2"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == ""
        assert appliance.get("sn8") == "00000000"
        assert appliance.get("model_number") == 0
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == "00000000"
        assert not appliance.get("online")

        appliances = await cloud.list_appliances("1")
        assert appliances is None

    async def test_meijucloud_get_device_info(self) -> None:
        """Test MeijuCloud get_device_info."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["cloud_login_id.json"],
                self.responses["meijucloud_login.json"],
                self.responses["meijucloud_get_device_info.json"],
                self.responses["meijucloud_get_device_info_alt.json"],
                self.responses["cloud_invalid_response.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        device = await cloud.get_device_info(1)
        assert device is not None
        assert device.get("name") == "Appliance Name"
        assert device.get("type") == 0xAC
        assert device.get("sn") == "mySecretKey"
        assert device.get("sn8") == "9d52c159"
        assert device.get("model_number") == 10
        assert device.get("manufacturer_code") == "1234"
        assert device.get("model") == "Product Model"
        assert device.get("online")

        device = await cloud.get_device_info(2)
        assert device is not None
        assert device.get("name") == "Appliance Name 2"
        assert device.get("type") == 0xAC
        assert device.get("sn") == ""
        assert device.get("sn8") == "00000000"
        assert device.get("model_number") == 0
        assert device.get("manufacturer_code") == "1234"
        assert device.get("model") == "00000000"
        assert not device.get("online")
        assert device.get("des") is None
        assert device.get("active_status") == 1
        assert device.get("active_time") == "2024-06-12 10:45:45"
        assert device.get("master_id") is None
        assert device.get("wifi_version") == "059009012205"
        assert device.get("enterprise") == "0000"
        assert device.get("is_other_equipment") is None
        assert device.get("attrs") is None
        assert device.get("room_name") is None
        assert device.get("bt_mac") == "54B8740FA801"
        assert device.get("bt_token") is None
        assert device.get("hotspot_name") is None
        assert device.get("is_bluetooth") == 0
        assert device.get("bind_type") is None
        assert device.get("ability") is None
        assert device.get("name_changed") is None
        assert not device.get("support_wot")
        assert device.get("template_of_tsl") is None
        assert device.get("shadow_level") is None
        assert device.get("smart_product_id") == 10004256
        assert device.get("brand") is None

        device = await cloud.get_device_info(99)
        assert device is None

    async def test_meijucloud_download_lua(self) -> None:
        """Test MeijuCloud download_lua."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["cloud_login_id.json"],
                self.responses["meijucloud_login.json"],
                self.responses["meijucloud_download_lua.json"],
                self.responses["meijucloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="9d52c159dcdd32bac5109cf54080fca7")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            file = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            Path.unlink(file_path)
            session.get.assert_awaited_once_with(
                "returnedURL",
                timeout=ClientTimeout(10),
            )

            res.status = 404
            assert (
                await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010") is None
            )
            with patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "returnedURL"}),
            ):
                assert await cloud.download_lua(tmpdir, 10, "00000000") is None
            with patch.object(cloud, "_api_request", AsyncMock(return_value=None)):
                assert await cloud.download_lua(tmpdir, 10, "00000000") is None

    async def test_meijucloud_download_lua_empty_payload(self) -> None:
        """Test MeijuCloud download_lua with an empty payload."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["cloud_login_id.json"],
                self.responses["meijucloud_login.json"],
                self.responses["meijucloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            result = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert result is None

    async def test_meijucloud_download_plugin(self) -> None:
        """Test MeijuCloud download_plugin."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=(
                b'{"code": 0, "data": {"list": [{"url": "http://host/plugin.zip"}]}}'
            ),
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.read = AsyncMock(return_value=b"plugin content")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None

        with TemporaryDirectory() as tmpdir:
            file = await cloud.download_plugin(tmpdir, 10, "0000AC000ABCD1234000")
            assert file is not None
            file_path = Path(file)
            assert file_path.name == "plugin.zip"
            assert Path.exists(file_path)
            Path.unlink(file_path)

            res.status = 404
            assert (
                await cloud.download_plugin(tmpdir, 10, "0000AC000ABCD1234000") is None
            )

    async def test_meijucloud_download_plugin_empty_payload(self) -> None:
        """Test MeijuCloud download_plugin with an empty payload."""
        session = Mock()
        res = Mock()
        res.status = 200
        res.read = AsyncMock(return_value=b"")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"list": [{"url": "http://host/plugin.zip"}]}),
            ),
            TemporaryDirectory() as tmpdir,
        ):
            assert (
                await cloud.download_plugin(
                    tmpdir,
                    10,
                    "0000AC000ABCD1234000",
                )
                is None
            )

    async def test_meijucloud_download_plugin_no_response(self) -> None:
        """Test MeijuCloud download_plugin when the API returns nothing."""
        session = Mock()
        cloud = get_midea_cloud(
            "美的美居",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            TemporaryDirectory() as tmpdir,
        ):
            assert (
                await cloud.download_plugin(
                    tmpdir,
                    10,
                    "0000AC000ABCD1234000",
                )
                is None
            )

    async def test_msmartcloud_login_success(self) -> None:
        """Test MSmartCloud login."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

    async def test_msmartcloud_login_invalid_user(self) -> None:
        """Test MSmartCloud login invalid user."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["cloud_invalid_response.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert not await cloud.login()

    async def test_msmartcloud_login_api_request_none(self) -> None:
        """Test MSmartCloud login failure when login response is missing."""
        session = Mock()
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_get_login_id", AsyncMock(return_value="loginid")),
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            assert not await cloud.login()
        assert "SmartHome Cloud login failed" in logs.output[0]

    async def test_get_keys_debug_log_redacts_token_material(self) -> None:
        """Test the inherited v1 get_cloud_keys never logs token/key material.

        The debug line must report only the tokenlist entry count, not the
        raw response, so a debug log cannot leak the LAN credentials.
        """
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with self.assertLogs("midealan.cloud", level="DEBUG") as logs:
            keys = await cloud.get_cloud_keys(100)
        # The keys are still returned so behaviour is unchanged.
        assert keys[1]["token"] == "method1_return_token1"
        assert keys[2]["key"] == "method2_return_key2"

        output = "\n".join(logs.output)
        # Sensitive material must never reach the log in full, on either the
        # get_cloud_keys() line or the lower-level _api_request debug line.
        assert "method1_return_token1" not in output
        assert "method1_return_key1" not in output
        assert "method2_return_token2" not in output
        assert "method2_return_key2" not in output
        # The get_cloud_keys() line reports only the entry count.
        assert "returned 1 token entries" in output

    async def test_msmartcloud_list_home(self) -> None:
        """Test MSmartCloud list_home."""
        session = Mock()
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        homes = await cloud.list_home()
        assert homes is not None
        assert len(homes.keys()) == 1

    async def test_msmartcloud_list_appliances(self) -> None:
        """Test MSmartCloud list_appliances."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["msmartcloud_list_appliances.json"],
                self.responses["cloud_invalid_response.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()
        appliances = await cloud.list_appliances(None)
        assert appliances is not None
        assert len(appliances.keys()) == 2
        appliance = appliances.get(1)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == "1234567890abcdef1234567890abcdef"
        assert appliance.get("sn8") == "0abcdef1"
        assert appliance.get("model_number") == 10
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == "0abcdef1"
        assert appliance.get("online")

        appliance = appliances.get(2)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name 2"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == ""
        assert appliance.get("sn8") == ""
        assert appliance.get("model_number") == 0
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == ""
        assert not appliance.get("online")

        appliances = await cloud.list_appliances(None)
        assert appliances is None

    async def test_msmartcloud_get_device_info(self) -> None:
        """Test MSmartCloud get_device_info."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["msmartcloud_list_appliances.json"],
                ClientConnectionError(),
                self.responses["msmartcloud_list_appliances.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        device = await cloud.get_device_info(1)
        assert device is not None
        assert device.get("name") == "Appliance Name"
        assert device.get("type") == 0xAC
        assert device.get("sn") == "1234567890abcdef1234567890abcdef"
        assert device.get("sn8") == "0abcdef1"
        assert device.get("model_number") == 10
        assert device.get("manufacturer_code") == "1234"
        assert device.get("model") == "0abcdef1"
        assert device.get("online")

        device = await cloud.get_device_info(99)
        assert device is None

    async def test_msmartcloud_download_lua(self) -> None:
        """Test MSmartCloud download_lua."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["meijucloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="4ABE0FE395F3AD3B6BC4D223F1ADFA7C")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            file = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            Path.unlink(file_path)
            session.get.assert_awaited_once_with(
                "returnedURL",
                timeout=ClientTimeout(10),
            )
            with patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "returnedURL"}),
            ):
                assert await cloud.download_lua(tmpdir, 10, "00000000") is None
            with patch.object(cloud, "_api_request", AsyncMock(return_value=None)):
                assert await cloud.download_lua(tmpdir, 10, "00000000") is None

    async def test_msmartcloud_download_lua_empty_payload(self) -> None:
        """Test MSmartCloud download_lua with an empty payload."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["meijucloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            result = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert result is None

    async def test_msmartcloud_download_lua_non_ok_response(self) -> None:
        """Test MSmartCloud download_lua with a non-OK download response."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["msmartcloud_login.json"],
                self.responses["meijucloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 404
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            result = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert result is None

    async def test_msmartcloud_download_plugin(self) -> None:
        """Test MSmartCloud download_plugin."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=(
                b'{"code": 0, "data": {"result": [{"url": "http://host/plugin.zip"}]}}'
            ),
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        res.read = AsyncMock(return_value=b"plugin content")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None

        with TemporaryDirectory() as tmpdir:
            file = await cloud.download_plugin(tmpdir, 10, "0000AC000ABCD1234000")
            assert file is not None
            file_path = Path(file)
            assert file_path.name == "plugin.zip"
            assert Path.exists(file_path)
            Path.unlink(file_path)

            res.status = 404
            assert (
                await cloud.download_plugin(tmpdir, 10, "0000AC000ABCD1234000") is None
            )

    async def test_msmartcloud_download_plugin_empty_payload(self) -> None:
        """Test MSmartCloud download_plugin with an empty payload."""
        session = Mock()
        res = Mock()
        res.status = 200
        res.read = AsyncMock(return_value=b"")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"result": [{"url": "http://host/plugin.zip"}]}),
            ),
            TemporaryDirectory() as tmpdir,
        ):
            assert (
                await cloud.download_plugin(
                    tmpdir,
                    10,
                    "0000AC000ABCD1234000",
                )
                is None
            )

    async def test_msmartcloud_download_plugin_non_ok_response(self) -> None:
        """Test MSmartCloud download_plugin with a non-OK download response."""
        session = Mock()
        res = Mock()
        res.status = 404
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"result": [{"url": "http://host/plugin.zip"}]}),
            ),
            TemporaryDirectory() as tmpdir,
        ):
            assert (
                await cloud.download_plugin(
                    tmpdir,
                    10,
                    "0000AC000ABCD1234000",
                )
                is None
            )

    async def test_msmartcloud_download_plugin_no_response(self) -> None:
        """Test MSmartCloud download_plugin when the API returns nothing."""
        session = Mock()
        cloud = get_midea_cloud(
            "SmartHome",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            TemporaryDirectory() as tmpdir,
        ):
            result = await cloud.download_plugin(
                tmpdir,
                10,
                "0000AC000ABCD1234000",
            )
            assert result is None

    async def test_mideaaircloud_login_success(self) -> None:
        """Test MideaAirCloud login."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["mideaaircloud_login_id.json"],
                self.responses["mideaaircloud_login.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

    async def test_mideaaircloud_login_api_request_none(self) -> None:
        """Test MideaAirCloud login failure when login response is missing."""
        session = Mock()
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            patch.object(cloud, "_get_login_id", AsyncMock(return_value="loginid")),
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            assert not await cloud.login()
        assert "Midea Air Cloud login failed" in logs.output[0]

    async def test_mideaaircloud_login_invalid_user(self) -> None:
        """Test MideaAirCloud login invalid user."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["mideaaircloud_invalid_response.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert not await cloud.login()

    async def test_mideaaircloud_api_request_timeout(self) -> None:
        """Test MideaAirCloud _api_request retries on timeout."""
        session = Mock()
        session.request = AsyncMock(side_effect=TimeoutError("timeout"))
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with self.assertLogs("midealan.cloud", level="WARNING") as logs:
            assert await cloud._api_request(endpoint="/endpoint", data={}) is None
        assert len(logs.output) == 3

    async def test_mideaaircloud_api_request_success_without_payload(self) -> None:
        """Test MideaAirCloud _api_request with no result or data payload."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(return_value=b'{"errorCode": 0}')
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud._api_request(endpoint="/endpoint", data={}) is None

    async def test_mideaaircloud_api_request_error_code_logged(self) -> None:
        """Test MideaAirCloud _api_request logs the cloud error and returns None.

        The legacy appsmb.com backend answers getToken with
        9999 "system error" since Midea retired that service; the error code
        and message must reach the log so the root cause is visible.
        """
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=b'{"errorCode": 9999, "msg": "system error"}',
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "NetHome Plus",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with self.assertLogs("midealan.cloud", level="WARNING") as logs:
            assert (
                await cloud._api_request(
                    endpoint="/v1/iot/secure/getToken",
                    data={},
                )
                is None
            )
        joined = "\n".join(logs.output)
        assert "9999" in joined
        assert "system error" in joined
        assert "/v1/iot/secure/getToken" in joined

    async def test_mideaaircloud_api_request_negative_error_code_logged(self) -> None:
        """Test a cloud-returned errorCode of -1 is still logged, not swallowed.

        A parsed response is distinguished from an absent reply by tracking
        parse success, so a cloud that genuinely answers errorCode -1 must
        reach the warning log rather than being mistaken for "no response".
        """
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=b'{"errorCode": -1, "msg": "error"}',
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "NetHome Plus",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with self.assertLogs("midealan.cloud", level="WARNING") as logs:
            assert await cloud._api_request(endpoint="/endpoint", data={}) is None
        joined = "\n".join(logs.output)
        assert "returned error -1" in joined
        assert "error" in joined

    @staticmethod
    def _mideaair_cbc_lua(cloud: MideaAirCloud, plaintext: bytes) -> str:
        """Encrypt lua with the current luaGetCbc scheme (CBC/SHA256)."""
        app_key = SUPPORTED_CLOUDS["Midea Air"]["app_key"]
        digest = sha256(app_key.encode("ascii")).hexdigest()
        return cloud._security.aes_encrypt(
            plaintext,
            digest[:16].encode("ascii"),
            digest[16:32].encode("ascii"),
        ).hex()

    @staticmethod
    def _mideaair_ecb_lua(cloud: MideaAirCloud, plaintext: bytes) -> str:
        """Encrypt lua with the legacy luaGet scheme (ECB/MD5)."""
        app_key = SUPPORTED_CLOUDS["Midea Air"]["app_key"]
        lua_key = (
            md5(app_key.encode("ascii"), usedforsecurity=False)
            .hexdigest()[:16]
            .encode("ascii")
        )
        return cloud._security.aes_encrypt(plaintext, lua_key).hex()

    async def test_mideaaircloud_download_lua(self) -> None:
        """Test MideaAirCloud download_lua via the current luaGetCbc endpoint."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["mideaaircloud_login_id.json"],
                self.responses["mideaaircloud_login.json"],
                self.responses["mideaaircloud_download_lua.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        res = Mock()
        res.status = 200
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert isinstance(cloud, MideaAirCloud)
        res.text = AsyncMock(
            return_value=self._mideaair_cbc_lua(cloud, b"function test() return 1 end"),
        )
        assert await cloud.login()

        with TemporaryDirectory() as tmpdir:
            file = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            assert file_path.read_text().startswith(  # noqa: ASYNC240
                'local bit = require "bit"',
            )
            Path.unlink(file_path)
            # The current endpoint succeeds first, so only one file is fetched.
            session.get.assert_awaited_once_with(
                "returnedURL",
                timeout=ClientTimeout(10),
            )

    async def test_mideaaircloud_download_lua_legacy_fallback(self) -> None:
        """Test download_lua falls back to the legacy luaGet/ECB endpoint."""
        session = Mock()
        session.request = AsyncMock()
        res = Mock()
        res.status = 200
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert isinstance(cloud, MideaAirCloud)
        res.text = AsyncMock(
            return_value=self._mideaair_ecb_lua(cloud, b"function test() return 1 end"),
        )
        # Mimic _api_request mutating the request with a per-call signature:
        # the first (luaGetCbc) attempt signs its data and yields no metadata,
        # the second (luaGet) attempt must receive a copy without that sign.
        seen_data: list[dict] = []

        async def fake_api_request(endpoint: str, data: dict) -> dict | None:
            seen_data.append(dict(data))
            data["sign"] = f"sign-for-{endpoint}"
            if endpoint.endswith("luaGetCbc"):
                return None
            return {"url": "returnedURL", "fileName": "f.lua"}

        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(side_effect=fake_api_request),
            ) as api_request,
        ):
            file = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            assert file_path.read_text().startswith(  # noqa: ASYNC240
                'local bit = require "bit"',
            )
            Path.unlink(file_path)
        endpoints = [call.kwargs["endpoint"] for call in api_request.await_args_list]
        assert endpoints == [
            "/v1/appliance/protocol/lua/luaGetCbc",
            "/v1/appliance/protocol/lua/luaGet",
        ]
        # The legacy attempt must not inherit the signed CBC request.
        assert "sign" not in seen_data[1]

    async def test_mideaaircloud_download_lua_non_ok_response(self) -> None:
        """Test download_lua returns None when both endpoints fail download."""
        session = Mock()
        res = Mock()
        res.status = 404
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "returnedURL", "fileName": "f.lua"}),
            ),
        ):
            assert (
                await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010") is None
            )

    async def test_mideaaircloud_download_lua_download_error_fallback(self) -> None:
        """Test download_lua tries the legacy endpoint after a download error."""
        session = Mock()
        res = Mock()
        res.status = 200
        # First (luaGetCbc) download raises; second (luaGet) download succeeds.
        session.get = AsyncMock(side_effect=[ClientConnectionError("boom"), res])
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert isinstance(cloud, MideaAirCloud)
        res.text = AsyncMock(
            return_value=self._mideaair_ecb_lua(cloud, b"function test() return 1 end"),
        )
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "returnedURL", "fileName": "f.lua"}),
            ),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            file = await cloud.download_lua(tmpdir, 10, "00000000", "0xAC", "0010")
            assert file is not None
            Path.unlink(Path(file))
        assert "Failed to download lua for appliance 00000000" in "\n".join(logs.output)
        assert session.get.await_count == 2

    async def test_mideaaircloud_download_lua_invalid_metadata(self) -> None:
        """Test download_lua returns None when metadata lacks a usable name."""
        session = Mock()
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "returnedURL"}),
            ),
        ):
            assert await cloud.download_lua(tmpdir, 10, "00000000") is None

    async def test_mideaaircloud_download_lua_no_response(self) -> None:
        """Test MideaAirCloud download_lua with no lua metadata."""
        session = Mock()
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(cloud, "_api_request", AsyncMock(return_value=None)),
        ):
            assert await cloud.download_lua(tmpdir, 10, "00000000") is None
        session.get.assert_not_called()

    async def test_mideaaircloud_download_lua_empty_payload(self) -> None:
        """Test MideaAirCloud download_lua with an empty lua payload."""
        session = Mock()
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "url", "fileName": "lua.lua"}),
            ),
        ):
            assert await cloud.download_lua(tmpdir, 10, "00000000") is None

    async def test_mideaaircloud_download_lua_decrypt_failure(self) -> None:
        """Test MideaAirCloud download_lua handles invalid encrypted lua."""
        session = Mock()
        res = Mock()
        res.status = 200
        res.text = AsyncMock(return_value="not-hex")
        session.get = AsyncMock(return_value=res)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(return_value={"url": "url", "fileName": "lua.lua"}),
            ),
            self.assertLogs("midealan.cloud", level="WARNING") as logs,
        ):
            assert await cloud.download_lua(tmpdir, 10, "00000000") is None
        joined = "\n".join(logs.output)
        assert "Failed to decrypt lua for appliance 00000000" in joined
        # Both schemes are attempted and reported in the fallback path.
        assert "cbc:" in joined
        assert "ecb:" in joined

    async def test_mideaaircloud_download_plugin_not_implemented(self) -> None:
        """Test MideaAirCloud does not implement download_plugin."""
        session = Mock()
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        with pytest.raises(NotImplementedError):
            await cloud.download_plugin("path", 10, "0000AC000ABCD1234000")

    async def test_mideaaircloud_list_home(self) -> None:
        """Test MideaAirCloud list_home."""
        session = Mock()
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        homes = await cloud.list_home()
        assert homes is not None
        assert len(homes.keys()) == 1

    async def test_mideaaircloud_list_appliances(self) -> None:
        """Test MideaAirCloud list_appliances."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["mideaaircloud_login_id.json"],
                self.responses["mideaaircloud_login.json"],
                self.responses["mideaaircloud_list_appliances.json"],
                self.responses["mideaaircloud_invalid_response.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()
        appliances = await cloud.list_appliances(None)
        assert appliances is not None
        assert len(appliances.keys()) == 2
        appliance = appliances.get(1)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == "1234567890abcdef1234567890abcdef"
        assert appliance.get("sn8") == "0abcdef1"
        assert appliance.get("model_number") == 10
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == "0abcdef1"
        assert appliance.get("online")

        appliance = appliances.get(2)
        assert appliance is not None
        assert appliance.get("name") == "Appliance Name 2"
        assert appliance.get("type") == 0xAC
        assert appliance.get("sn") == ""
        assert appliance.get("sn8") == ""
        assert appliance.get("model_number") == 0
        assert appliance.get("manufacturer_code") == "1234"
        assert appliance.get("model") == ""
        assert not appliance.get("online")

        appliances = await cloud.list_appliances(None)
        assert appliances is None

    async def test_mideaaircloud_get_device_info(self) -> None:
        """Test MideaAirCloud get_device_info."""
        session = Mock()
        response1 = Mock()
        response1.read = AsyncMock(
            return_value=self.responses["mideaaircloud_login_id.json"],
        )
        response2 = Mock()
        response2.read = AsyncMock(
            return_value=self.responses["mideaaircloud_login.json"],
        )
        response3 = Mock()
        response3.read = AsyncMock(
            return_value=self.responses["mideaaircloud_list_appliances.json"],
        )

        session.request = AsyncMock(
            side_effect=[
                response1,
                response2,
                response3,
                ClientConnectionError(),
                response3,
            ],
        )
        cloud = get_midea_cloud(
            "Midea Air",
            session=session,
            account="account",
            password="password",
        )
        assert cloud is not None
        assert await cloud.login()

        device = await cloud.get_device_info(1)
        assert device is not None
        assert device.get("name") == "Appliance Name"
        assert device.get("type") == 0xAC
        assert device.get("sn") == "1234567890abcdef1234567890abcdef"
        assert device.get("sn8") == "0abcdef1"
        assert device.get("model_number") == 10
        assert device.get("manufacturer_code") == "1234"
        assert device.get("model") == "0abcdef1"
        assert device.get("online")

        device = await cloud.get_device_info(99)
        assert device is None


@pytest.fixture(name="make_toshiba_cloud")
def make_toshiba_cloud_fixture() -> Callable[[Mock], ToshibaIOLife]:
    """Return a factory for ToshibaIOLife clouds on a mocked session."""

    def _make(session: Mock) -> ToshibaIOLife:
        cloud = get_midea_cloud(
            "Toshiba Iolife",
            session=session,
            account="account",
            password="password",
        )
        assert isinstance(cloud, ToshibaIOLife)
        assert cloud._app_key == _TOSHIBA_APP_KEY
        assert isinstance(cloud._security, ToshibaIOLifeSecurity)
        return cloud

    return _make


class TestToshibaDecryptSn:
    """Unit tests for ToshibaIOLife._decrypt_sn."""

    @pytest.mark.parametrize(
        ("encrypted_sn", "access_token", "expected"),
        [
            (_TOSHIBA_ENCRYPTED_SN, _TOSHIBA_ACCESS_TOKEN, _TOSHIBA_EXPECTED_SN),
            (_TOSHIBA_ENCRYPTED_SN, None, ""),
            ("", _TOSHIBA_ACCESS_TOKEN, ""),
        ],
    )
    def test_decrypt_sn(
        self,
        make_toshiba_cloud: Callable[[Mock], ToshibaIOLife],
        encrypted_sn: str,
        access_token: str | None,
        expected: str,
    ) -> None:
        """_decrypt_sn returns correct SN or an empty string."""
        cloud = make_toshiba_cloud(Mock())
        cloud._access_token = access_token
        assert cloud._decrypt_sn(encrypted_sn) == expected

    @pytest.mark.parametrize(
        ("encrypted_sn", "access_token"),
        [
            ("deadbeef" * 4, _TOSHIBA_ACCESS_TOKEN),
            ("nothexatall", _TOSHIBA_ACCESS_TOKEN),
            (_TOSHIBA_ENCRYPTED_SN, "nothexatall"),
        ],
    )
    def test_decrypt_sn_hides_security_errors(
        self,
        make_toshiba_cloud: Callable[[Mock], ToshibaIOLife],
        encrypted_sn: str,
        access_token: str,
    ) -> None:
        """_decrypt_sn returns an empty string when security rejects the payload."""
        cloud = make_toshiba_cloud(Mock())
        cloud._access_token = access_token
        assert cloud._decrypt_sn(encrypted_sn) == ""


class ToshibaIOLifeTest(IsolatedAsyncioTestCase):
    """ToshibaIOLife cloud async tests."""

    responses: ClassVar[dict[str, bytes]] = {}
    make_cloud: Callable[[Mock], ToshibaIOLife]

    def setUp(self) -> None:
        """Set tests up."""
        file_path = Path(__file__)
        for file in Path.iterdir(Path(file_path.parent, "responses")):
            file_path = Path(file)
            with file_path.open(
                encoding="utf-8",
            ) as f:
                self.responses[file_path.name] = bytes(f.read(), encoding="utf-8")

    @pytest.fixture(autouse=True)
    def _inject_cloud_factory(
        self,
        make_toshiba_cloud: Callable[[Mock], ToshibaIOLife],
    ) -> None:
        """Share the cloud factory with these unittest-style tests."""
        self.make_cloud = make_toshiba_cloud

    async def test_list_appliances_success(self) -> None:
        """list_appliances decrypts SN inline and skips virtual devices."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["mideaaircloud_login_id.json"],
                self.responses["mideaaircloud_login.json"],
                self.responses["toshibaiolife_list_appliances.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)
        cloud = self.make_cloud(session)
        assert await cloud.login()
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN

        appliances = await cloud.list_appliances(None)
        assert len(appliances) == 1

        dev = appliances[12345678]
        assert dev["name"] == "Living Room AC"
        assert dev["type"] == 0xAC
        assert dev["sn"] == _TOSHIBA_EXPECTED_SN
        assert dev["sn8"] == "00000000"
        assert dev["model_number"] == 10
        assert dev["manufacturer_code"] == "0008"
        assert dev["model"] == "00000000"
        assert dev["online"] is True

    async def test_list_appliances_uses_cloud_app_version(self) -> None:
        """AppVersion comes from the SUPPORTED_CLOUDS entry."""
        cloud = self.make_cloud(Mock())
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        request = AsyncMock(return_value=[])
        with patch.object(cloud, "_api_request", new=request):
            await cloud.list_appliances(None)
        assert request.await_args is not None
        assert request.await_args.kwargs["data"]["appVersion"] == "3.4.0"

    async def test_list_appliances_skips_malformed_entries(self) -> None:
        """Entries with an unusable id or type are skipped."""
        cloud = self.make_cloud(Mock())
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        good = {
            "id": "12345678",
            "type": "0xAC",
            "name": "Living Room AC",
            "modelNumber": "10",
            "onlineStatus": "1",
        }
        with patch.object(
            cloud,
            "_api_request",
            new=AsyncMock(
                return_value=[
                    {"id": "not-a-number", "type": "0xAC"},
                    {"id": "1", "type": "not-hex"},
                    {"type": "0xAC"},
                    {"id": "2", "type": None},
                    good,
                ],
            ),
        ):
            appliances = await cloud.list_appliances(None)
        assert list(appliances) == [12345678]

    async def test_list_appliances_non_numeric_model_number(self) -> None:
        """A non-numeric modelNumber falls back to 0."""
        cloud = self.make_cloud(Mock())
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        with patch.object(
            cloud,
            "_api_request",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "12345678",
                        "type": "0xAC",
                        "name": "Living Room AC",
                        "modelNumber": "RAS-X221DZ",
                        "onlineStatus": "1",
                    },
                ],
            ),
        ):
            appliances = await cloud.list_appliances(None)
        assert appliances[12345678]["model_number"] == 0

    async def test_list_appliances_api_failure(self) -> None:
        """list_appliances returns an empty dict on API failure."""
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["mideaaircloud_invalid_response.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = self.make_cloud(session)
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        assert await cloud.list_appliances(None) == {}

    async def test_list_appliances_non_list_response(self) -> None:
        """list_appliances returns an empty dict for a non-list response."""
        cloud = self.make_cloud(Mock())
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        with patch.object(
            cloud,
            "_api_request",
            new=AsyncMock(return_value={"result": []}),
        ):
            assert await cloud.list_appliances(None) == {}

    async def test_list_appliances_skips_non_mapping_entries(self) -> None:
        """list_appliances silently skips non-mapping entries in the list."""
        entry = {
            "id": "12345678",
            "type": "0xAC",
            "name": "Living Room AC",
            "modelNumber": 10,
            "onlineStatus": "1",
            "sn": _TOSHIBA_ENCRYPTED_SN,
        }
        cloud = self.make_cloud(Mock())
        cloud._access_token = _TOSHIBA_ACCESS_TOKEN
        with patch.object(
            cloud,
            "_api_request",
            new=AsyncMock(return_value=["not-a-mapping", entry]),
        ):
            appliances = await cloud.list_appliances(None)
        assert len(appliances) == 1


class DayReportTest(IsolatedAsyncioTestCase):
    """Day report test case."""

    @staticmethod
    def _cloud(
        session: Mock,
        api_url: str = "https://mp-prod.smartmidea.net/mas/v5/app/proxy?alias=",
    ) -> MideaCloud:
        """Build a cloud client for the day report tests."""
        return MideaCloud(
            session=session,
            security=Mock(),
            app_id="appid",
            app_key="appkey",
            account="account",
            password="password",
            api_url=api_url,
        )

    @staticmethod
    def _session(payload: object) -> Mock:
        """Return a session whose single request answers with a payload."""
        response = Mock()
        response.json = AsyncMock(return_value=payload)
        session = Mock()
        session.request = AsyncMock(return_value=response)
        return session

    async def test_get_day_report(self) -> None:
        """Request the usage report with the access token and proxy alias."""
        session = self._session({"retCode": "0", "result": {"date": "2026-09-10"}})
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        result = await cloud.get_day_report(100)
        assert result == {"date": "2026-09-10"}
        call = session.request.await_args
        assert call.args[0] == "POST"
        assert call.args[1] == (
            "https://mp-prod.smartmidea.net/mas/v5/app/proxy?alias=/cfhrs/e3/v1/api"
        )
        assert call.kwargs["headers"] == {
            "content-type": "application/json; charset=utf-8",
            "accessToken": "token",
        }
        assert call.kwargs["json"] == {
            "msg": "dayReportV2",
            "params": {"applianceId": "100"},
        }
        assert call.kwargs["allow_redirects"] is False

    async def test_get_day_report_does_not_follow_redirect(self) -> None:
        """Do not follow day-report redirects with the access token header."""
        target_tokens: list[str | None] = []

        async def target_handler(request: web.Request) -> web.Response:
            target_tokens.append(request.headers.get("accessToken"))
            return web.json_response({"retCode": "0", "result": {}})

        target_runner = web.AppRunner(web.Application())
        target_runner.app.router.add_post("/target", target_handler)
        await target_runner.setup()
        target_site = web.TCPSite(target_runner, "127.0.0.1", 0)
        await target_site.start()
        assert target_site._server is not None
        target_port = target_site._server.sockets[0].getsockname()[1]

        async def redirect_handler(_request: web.Request) -> web.Response:
            return web.Response(
                status=307,
                headers={"Location": f"http://127.0.0.1:{target_port}/target"},
            )

        redirect_runner = web.AppRunner(web.Application())
        redirect_runner.app.router.add_post("/mas/v5/app/proxy", redirect_handler)
        await redirect_runner.setup()
        redirect_site = web.TCPSite(redirect_runner, "127.0.0.1", 0)
        await redirect_site.start()
        assert redirect_site._server is not None
        redirect_port = redirect_site._server.sockets[0].getsockname()[1]

        try:
            async with ClientSession() as session:
                cloud = self._cloud(
                    session,
                    api_url=f"http://127.0.0.1:{redirect_port}/mas/v5/app/proxy?alias=",
                )
                cloud.set_access_token("token")
                with pytest.raises(CloudError):
                    await cloud.get_day_report(100)
        finally:
            await redirect_runner.cleanup()
            await target_runner.cleanup()
        assert target_tokens == []

    async def test_get_day_report_empty_result(self) -> None:
        """Return None when the cloud holds no report for the appliance."""
        session = self._session({"retCode": "0"})
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        assert await cloud.get_day_report(100) is None

    async def test_get_day_report_auth_error(self) -> None:
        """Map a rejected access token to CloudAuthError."""
        session = self._session({"code": 40002, "msg": "token invalid"})
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        with pytest.raises(CloudAuthError):
            await cloud.get_day_report(100)

    async def test_get_day_report_gateway_error(self) -> None:
        """Map a gateway error to CloudError."""
        session = self._session({"code": 1234, "msg": "boom"})
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        with pytest.raises(CloudError):
            await cloud.get_day_report(100)

    async def test_get_day_report_failed_ret_code(self) -> None:
        """Map a non-zero retCode to CloudError."""
        session = self._session({"retCode": "1", "desc": "no report"})
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        with pytest.raises(CloudError):
            await cloud.get_day_report(100)

    async def test_get_day_report_invalid_response(self) -> None:
        """Reject a response that is not a JSON object."""
        session = self._session([])
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        with pytest.raises(CloudError):
            await cloud.get_day_report(100)

    async def test_get_day_report_request_failure(self) -> None:
        """Map a connection failure to CloudError."""
        session = Mock()
        session.request = AsyncMock(side_effect=ClientConnectionError())
        cloud = self._cloud(session)
        cloud.set_access_token("token")
        with pytest.raises(CloudError):
            await cloud.get_day_report(100)

    async def test_get_day_report_no_token(self) -> None:
        """Reject a report request without an access token."""
        with pytest.raises(CloudAuthError):
            await self._cloud(Mock()).get_day_report(100)

    async def test_get_day_report_no_alias(self) -> None:
        """Reject a report request on a cloud without the proxy alias."""
        cloud = self._cloud(
            Mock(),
            api_url="https://mapp.appsmb.com",  # codespell:ignore
        )
        cloud.set_access_token("token")
        with pytest.raises(CloudError):
            await cloud.get_day_report(100)


# Snapshotted once, at module import, before any test (in this file or
# any other) can mutate SUPPORTED_CLOUDS["TSmartLife"]. TestTSmartLifeCloud's
# setUp/tearDown below always reset to this fixed baseline rather than
# re-snapshotting whatever happens to be live -- fixes a real
# test-order-dependency CodeRabbit's 2026-10-14 review on PR #198 found
# (reproduced: running tests/tsmartlife_auth_harness_test.py before this
# file made test_endpoint_configuration_matches_confirmed_evidence fail,
# because the old per-setUp snapshot picked up that file's leftover
# synthetic values as if they were "the real entry").
_TSMARTLIFE_REAL_ENTRY = dict(SUPPORTED_CLOUDS["TSmartLife"])


class TestTSmartLifeCloud(IsolatedAsyncioTestCase):
    """Test TSmartLifeCloud -- draft provider, see issue #364.

    These tests never contact a real server: several tests temporarily
    override the module-level SUPPORTED_CLOUDS entry with clearly-fake
    placeholder credentials, always reset to the fixed, real baseline
    snapshotted at module import (_TSMARTLIFE_REAL_ENTRY above) in both
    setUp and tearDown -- regardless of what any other test file leaves
    behind -- purely to exercise TSmartLifeCloud's inherited
    SmartHomeCloud request/response code paths against mocked HTTP
    responses, exactly as every other cloud class in this file is
    tested. The real app_id/app_key ARE known and used by default (see
    SUPPORTED_CLOUDS["TSmartLife"] itself) -- only per-user account
    credentials and per-device LAN tokens are never used here.
    """

    responses: ClassVar[dict[str, bytes]] = {}

    def setUp(self) -> None:
        """Load response fixtures and reset to the fixed, known-good baseline.

        Resets SUPPORTED_CLOUDS["TSmartLife"] to _TSMARTLIFE_REAL_ENTRY
        before every test, not just in tearDown -- so even if an earlier
        test (in this file or another) left the global entry mutated,
        this test still starts from the true original, not whatever was
        live when setUp happened to run.
        """
        file_path = Path(__file__)
        for file in Path.iterdir(Path(file_path.parent, "responses")):
            file_path = Path(file)
            with file_path.open(encoding="utf-8") as f:
                self.responses[file_path.name] = bytes(f.read(), encoding="utf-8")
        SUPPORTED_CLOUDS["TSmartLife"].clear()
        SUPPORTED_CLOUDS["TSmartLife"].update(_TSMARTLIFE_REAL_ENTRY)

    def tearDown(self) -> None:
        """Restore the fixed, known-good baseline again after this test.

        Defense in depth alongside setUp's reset above: covers any
        inspection of global state that might happen between this test
        and the next (e.g. a differently-ordered or parallel test
        runner), not just this file's own next setUp call.
        """
        SUPPORTED_CLOUDS["TSmartLife"].clear()
        SUPPORTED_CLOUDS["TSmartLife"].update(_TSMARTLIFE_REAL_ENTRY)

    def test_endpoint_configuration_matches_confirmed_evidence(self) -> None:
        """SUPPORTED_CLOUDS["TSmartLife"] matches the confirmed findings.

        Pins the exact confirmed api_url, manufacturer_code, and the 4
        published app-level constants so a future edit cannot silently
        drift from the evidence recorded in issue #364 / published at
        jaspweowaale/toshiba-tsmartlife-local without this test failing.
        These 4 values are shared app-level constants, not personal
        account or per-device secrets -- see that repo's
        docs/APP_CREDENTIAL_SECURITY.md for the full classification.
        """
        entry = SUPPORTED_CLOUDS["TSmartLife"]
        assert entry["class_name"] == "TSmartLifeCloud"
        assert (
            entry["api_url"] == "https://mp-jp-prod.appsmb.com/mas/v5/app/proxy?alias="
        )
        assert entry["manufacturer_code"] == "0008"
        assert entry["app_id"] == "1020"
        assert entry["app_key"] == "d1ba2a7513bef7bbcd58478b678ff655"
        assert entry["iot_key"] == "meicloud"
        assert entry["hmac_key"] == "PROD_VnoClJI9aikS8dyy"

    def test_construction_refuses_without_app_id(self) -> None:
        """Refuses to construct when app_id is blank.

        SUPPORTED_CLOUDS["TSmartLife"] now holds real, non-blank values
        by default, so this explicitly blanks app_id first -- the guard
        itself is unchanged, this just confirms it still fires correctly
        for any future fork/variant that lacks a value, not just the
        pre-publication state this test originally targeted.
        """
        SUPPORTED_CLOUDS["TSmartLife"]["app_id"] = ""
        session = Mock()
        with pytest.raises(ElementMissing, match="TSmartLife cloud credentials"):
            TSmartLifeCloud(
                cloud_name="TSmartLife",
                session=session,
                account="account",
                password="password",
            )

    def test_construction_refuses_without_app_key(self) -> None:
        """Refuses to construct when app_id is set but app_key is blank."""
        SUPPORTED_CLOUDS["TSmartLife"]["app_id"] = "test_only_not_real"
        SUPPORTED_CLOUDS["TSmartLife"]["app_key"] = ""
        session = Mock()
        with pytest.raises(ElementMissing, match="TSmartLife cloud credentials"):
            TSmartLifeCloud(
                cloud_name="TSmartLife",
                session=session,
                account="account",
                password="password",
            )

    def test_construction_succeeds_once_placeholder_credentials_are_supplied(
        self,
    ) -> None:
        """Once config is non-blank, TSmartLifeCloud constructs normally.

        This does not claim the placeholder values are real -- it confirms
        the refusal guard is the *only* thing blocking construction today,
        not some other structural issue in the new class.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        cloud = get_midea_cloud(
            "TSmartLife",
            session=Mock(),
            account="account",
            password="password",
        )
        assert isinstance(cloud, TSmartLifeCloud)
        assert isinstance(cloud, SmartHomeCloud)

    async def test_request_construction_targets_confirmed_endpoint(self) -> None:
        """The first real request (re-route) goes to the confirmed real host.

        Deliberately exercises only `_re_route()`, not the full login flow:
        the later AES-key-exchange step in `login()` decrypts a payload
        whose ciphertext in the shared `msmartcloud_login.json` fixture was
        recorded against SmartHome's own *real* app_key -- reusing a
        different (placeholder) app_key here would fail to decrypt it for
        reasons unrelated to what this test checks, and this project must
        not reuse another cloud's real credentials for TSmartLife (see
        SUPPORTED_CLOUDS["TSmartLife"]'s own comment). `_re_route()` needs
        no decryption at all, so it is the right-sized slice to test the
        actual claim: TSmartLife's real, confirmed endpoint is used, not a
        default or another cloud's host.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["msmartcloud_reroute.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "TSmartLife",
            session=session,
            account="account",
            password="password",
        )
        assert isinstance(cloud, TSmartLifeCloud)
        await cloud._re_route()

        first_call = session.request.await_args_list[0]
        first_url = (
            first_call.args[1]
            if len(first_call.args) > 1
            else first_call.kwargs.get("url", "")
        )
        assert first_url.startswith(
            "https://mp-jp-prod.appsmb.com/mas/v5/app/proxy?alias=",
        )

    async def test_token_response_parsing_reuses_base_gettoken_shape(self) -> None:
        """get_cloud_keys parses a getToken success response normally.

        Calls get_cloud_keys() directly, without a prior login() -- the
        base MideaCloud.get_cloud_keys()/_retrieve_cloud_keys() path this
        exercises does not require a completed login, only a constructed
        client, and skipping login() avoids the unrelated AES-key fixture
        mismatch explained in test_request_construction_targets_confirmed_
        endpoint above. Confirms TSmartLifeCloud (via its unmodified
        SmartHomeCloud/MideaCloud inheritance) parses a real getToken
        response shape correctly -- this is NOT a claim that this response
        came from a real TSmartLife server; it is the same base-class
        parsing path already covered for SmartHome, exercised once more
        via this new subclass so a future refactor cannot silently break
        it here.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        session = Mock()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["meijucloud_get_keys1.json"],
        )
        session.request = AsyncMock(return_value=response)
        cloud = get_midea_cloud(
            "TSmartLife",
            session=session,
            account="account",
            password="password",
        )

        result = await cloud.get_cloud_keys(100)
        assert result == {
            1: {"token": "method1_return_token1", "key": "method1_return_key1"},
        }

    def test_login_is_inherited_unmodified_from_smarthome(self) -> None:
        """TSmartLifeCloud does not override login().

        A full mocked login() round trip is deliberately not attempted
        here -- see test_request_construction_targets_confirmed_endpoint's
        own docstring above for why (the shared login fixture's ciphertext
        is tied to SmartHome's real app_key). This identity check is the
        right-sized alternative: it is a genuine regression guard (it
        would fail immediately if a future edit ever added a TSmartLife-
        specific login() override) without claiming a fixture-based
        round trip this project's own rules don't allow it to construct
        honestly. Login itself IS separately confirmed live-working: see
        https://github.com/jaspweowaale/toshiba-tsmartlife-local, which
        calls this exact inherited method against the real TSmartLife
        cloud with real (not published here) app credentials.
        """
        assert TSmartLifeCloud.login is SmartHomeCloud.login

    async def test_list_appliances_uses_inherited_smarthome_implementation(
        self,
    ) -> None:
        """TSmartLifeCloud.list_appliances reuses SmartHomeCloud's method.

        Patches _api_request directly with an inline, blank-SN appliance
        payload -- shaped exactly like _api_request's real already-
        unwrapped return value, not a raw HTTP envelope. SmartHomeCloud's
        list_appliances() calls self._security.aes_decrypt() on each
        appliance's sn field, which requires AES session keys that only
        get set during a completed login() -- and this test deliberately
        skips login() for the same reason the other tests above do (no
        real TSmartLife app_key to complete that round trip honestly).
        aes_decrypt() short-circuits to "" for zero-length input before
        touching any key material (see midealan/security.py), so a
        blank-SN payload exercises the real parsing/field-mapping code
        path without needing login() first -- the same "right-sized
        slice" approach already used for _re_route()/get_cloud_keys()
        above. Appliance discovery itself IS separately confirmed
        live-working: see
        https://github.com/jaspweowaale/toshiba-tsmartlife-local.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        cloud = get_midea_cloud(
            "TSmartLife",
            session=Mock(),
            account="account",
            password="password",
        )
        assert isinstance(cloud, SmartHomeCloud)

        fake_response = {
            "list": [
                {
                    "modelNumber": "310A079W",
                    "name": "Test Appliance (blank SN, no AES session key needed)",
                    "type": "0xCA",
                    "sn": "",
                    "enterpriseCode": "0008",
                    "onlineStatus": "1",
                    "id": "1",
                },
            ],
        }

        with patch.object(
            cloud,
            "_api_request",
            AsyncMock(return_value=fake_response),
        ):
            appliances = await cloud.list_appliances(home_id=None)

        assert appliances == {
            1: {
                "name": "Test Appliance (blank SN, no AES session key needed)",
                "type": 0xCA,
                "sn": "",
                "sn8": "",
                "model_number": 0,
                "manufacturer_code": "0008",
                "model": "",
                "online": True,
            },
        }

    async def test_download_lua_uses_inherited_smarthome_implementation(
        self,
    ) -> None:
        """TSmartLifeCloud.download_lua uses SmartHomeCloud's implementation.

        Exercises the inherited code path directly via a patched
        `_api_request`/`_session.get` -- no login() call, no real or
        fixture-derived credentials. The "encrypted" lua text is produced
        with the library's own account-independent "fixed key" AES helper,
        so this fixture is entirely self-consistent and contains no real
        device/account data. The mocked API request is checked as well as
        the decryption and file-writing path.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        cloud = get_midea_cloud(
            "TSmartLife",
            session=Mock(),
            account="account",
            password="password",
        )
        assert isinstance(cloud, SmartHomeCloud)

        fake_lua_source = "function test() return 1 end"
        encrypted_hex = cloud._security.aes_encrypt_with_fixed_key(
            fake_lua_source.encode("ascii"),
        ).hex()

        get_response = Mock()
        get_response.status = 200
        get_response.text = AsyncMock(return_value=encrypted_hex)
        fake_session = Mock()
        fake_session.get = AsyncMock(return_value=get_response)
        cloud._session = fake_session

        api_request = AsyncMock(
            return_value={
                "url": "https://example.invalid/fake.lua",
                "fileName": "fake_0xCA.lua",
            },
        )
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                api_request,
            ),
        ):
            file = await cloud.download_lua(
                tmpdir,
                0xCA,
                "0000000000000000",
                model_number="310A079W",
            )
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            assert file_path.read_text() == (  # noqa: ASYNC240
                'local bit = require "bit"\n' + fake_lua_source
            )
            Path.unlink(file_path)
            api_request.assert_awaited_once()
            request = api_request.await_args
            assert request is not None
            assert request.kwargs["endpoint"] == "/v2/luaEncryption/luaGet"
            request_data = request.kwargs["data"]
            assert request_data["applianceMFCode"] == "0000"
            assert request_data["applianceType"] == "0xca"
            assert request_data["modelNumber"] == "310A079W"
            assert request_data["encryptedType"] == "2"
            assert "encryptedType " not in request_data
            fake_session.get.assert_awaited_once_with(
                "https://example.invalid/fake.lua",
                timeout=ClientTimeout(10),
            )

    async def test_download_plugin_uses_inherited_smarthome_implementation(
        self,
    ) -> None:
        """TSmartLifeCloud.download_plugin reuses SmartHomeCloud's method.

        Same isolation approach as the download_lua test above: patches
        `_api_request` directly, no login() call, no real credentials.
        download_plugin writes the response body as-is (no decryption), so
        a plain placeholder byte string is sufficient here.
        """
        SUPPORTED_CLOUDS["TSmartLife"].update(
            {
                "app_id": "test_only_app_id_not_real",
                "app_key": "test_only_app_key_not_real",
                "iot_key": "test_only_iot_key_not_real",
                "hmac_key": "test_only_hmac_key_not_real",
            },
        )
        cloud = get_midea_cloud(
            "TSmartLife",
            session=Mock(),
            account="account",
            password="password",
        )
        assert isinstance(cloud, SmartHomeCloud)

        get_response = Mock()
        get_response.status = 200
        get_response.read = AsyncMock(return_value=b"fake plugin zip content")
        fake_session = Mock()
        fake_session.get = AsyncMock(return_value=get_response)
        cloud._session = fake_session

        with (
            TemporaryDirectory() as tmpdir,
            patch.object(
                cloud,
                "_api_request",
                AsyncMock(
                    return_value={
                        "result": [
                            {"url": "https://example.invalid/fake_plugin.zip"},
                        ],
                    },
                ),
            ),
        ):
            file = await cloud.download_plugin(
                tmpdir,
                0xCA,
                "0000CA000000000000000000",
            )
            assert file is not None
            file_path = Path(file)
            assert Path.exists(file_path)
            assert file_path.read_bytes() == b"fake plugin zip content"  # noqa: ASYNC240
            Path.unlink(file_path)
            fake_session.get.assert_awaited_once_with(
                "https://example.invalid/fake_plugin.zip",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud_name", ["SmartHome", "美的美居", "TSmartLife"])
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        pytest.param(None, {}, id="missing-response"),
        pytest.param({}, {}, id="missing-token-list"),
        pytest.param({"tokenlist": None}, {}, id="null-token-list"),
        pytest.param({"tokenlist": []}, {}, id="empty-token-list"),
        pytest.param(
            {
                "tokenlist": [
                    {
                        "udpId": "other-device",
                        "token": "SYNTHETIC_OTHER_TOKEN",
                        "key": "SYNTHETIC_OTHER_KEY",
                    },
                ],
            },
            {},
            id="unmatched-token",
        ),
        pytest.param(
            {"tokenlist": [{"udpId": UDP_IDS[1].upper()}]},
            {},
            id="case-sensitive-udp-id",
        ),
        pytest.param(
            {"tokenlist": [{"udpId": UDP_IDS[1], "token": "", "key": ""}]},
            {1: {"token": "", "key": ""}},
            id="empty-credential-strings",
        ),
        pytest.param(
            {
                "tokenlist": [
                    {"udpId": "other-device"},
                    {
                        "udpId": UDP_IDS[1],
                        "token": "SYNTHETIC_METHOD1_TOKEN",
                        "key": "SYNTHETIC_METHOD1_KEY",
                    },
                    {
                        "udpId": UDP_IDS[2],
                        "token": "SYNTHETIC_METHOD2_TOKEN",
                        "key": "SYNTHETIC_METHOD2_KEY",
                    },
                ],
            },
            {
                1: {
                    "token": "synthetic_method1_token",
                    "key": "synthetic_method1_key",
                },
                2: {
                    "token": "synthetic_method2_token",
                    "key": "synthetic_method2_key",
                },
            },
            id="match-and-lowercase-both-methods",
        ),
        pytest.param(
            {
                "tokenlist": [
                    {
                        "udpId": UDP_IDS[1],
                        "token": "SYNTHETIC_FIRST_TOKEN",
                        "key": "SYNTHETIC_FIRST_KEY",
                    },
                    {
                        "udpId": UDP_IDS[1],
                        "token": "SYNTHETIC_LAST_TOKEN",
                        "key": "SYNTHETIC_LAST_KEY",
                    },
                    {"udpId": "other-device"},
                ],
            },
            {
                1: {
                    "token": "synthetic_last_token",
                    "key": "synthetic_last_key",
                },
            },
            id="last-matching-token-wins",
        ),
    ],
)
async def test_cloud_key_token_parsing(
    cloud_name: str,
    response: dict | None,
    expected: dict[int, dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep shared parsing and credential-safe logging consistent across clouds."""
    cloud = get_midea_cloud(
        cloud_name,
        session=Mock(),
        account="account",
        password="password",
    )
    assert cloud is not None
    original_response = deepcopy(response)
    with (
        patch.object(
            cloud,
            "_api_request",
            AsyncMock(return_value=response),
        ) as api_request,
        patch.object(cloud, "list_home", AsyncMock(return_value={1: "Test home"})),
        caplog.at_level(logging.DEBUG, logger="midealan.cloud"),
    ):
        assert await cloud.get_cloud_keys(100) == expected

    assert response == original_response
    expected_requests = 2 if expected or cloud_name == "SmartHome" else 4
    assert api_request.await_count == expected_requests
    tokens = (response or {}).get("tokenlist") or []
    assert f"returned {len(tokens)} token entries" in caplog.text
    for token in tokens:
        for field in ("token", "key"):
            if value := token.get(field):
                assert value not in caplog.text
                assert value.lower() not in caplog.text

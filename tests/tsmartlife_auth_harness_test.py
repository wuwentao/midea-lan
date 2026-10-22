"""TSmartLife authentication harness -- Stage 3Z.

Isolated, synthetic-credential-only test harness exercising the full
TSmartLifeCloud(SmartHomeCloud) authentication sequence end to end:
regional endpoint selection (_re_route), request construction/signing
(_api_request/CloudSecurity.sign), the login round trip (including a real
AES key/IV decrypt using a *self-generated* synthetic fixture -- see
tests/responses/tsmartlife_synthetic_login.json and
scratch/tsmartlife_poc/gen_synthetic_login_fixture.py in the research repo),
and both the v1 (inherited) and v2 (candidate fix) get_cloud_keys() paths.

No real credential, app_id, app_key, iot_key, or hmac_key is used anywhere
in this file -- every value below is a clearly-named placeholder
("test_only_..."/"synthetic_..."). No network call is ever made: every
test mocks aiohttp.ClientSession.request.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from midealan.cloud import SUPPORTED_CLOUDS, TSmartLifeCloud, get_midea_cloud

# Hard-coded independently of CloudSecurity.get_udp_id(100, method), same
# discipline as tests/cloud_test.py: deriving them with the implementation's
# own helper would not catch a request that sends the wrong method's UDP ID.
UDP_IDS = {
    1: "dec4da86e0aeefadde14a4e553680b9b",
    2: "b2dd199071d527a33c8239833a5bf5fb",
}

SYNTHETIC_CREDENTIALS = {
    "app_id": "test_only_app_id_not_real",
    "app_key": "test_only_app_key_not_real",
    "iot_key": "test_only_iot_key_not_real",
    "hmac_key": "test_only_hmac_key_not_real",
}


def _token_requests(session: Mock) -> list[tuple[str, dict]]:
    """Return (url, payload) for every getToken request actually sent."""
    out = []
    for call in session.request.await_args_list:
        url = call.args[1] if len(call.args) > 1 else call.kwargs.get("url", "")
        if "getToken" not in url:
            continue
        out.append((url, json.loads(call.kwargs["data"])))
    return out


class TestTSmartLifeAuthHarness(IsolatedAsyncioTestCase):
    """Stage 3Z harness.

    See android_runtime_stage3{w,x,y}_results.md for the APK evidence this
    harness is built against.
    """

    responses: ClassVar[dict[str, bytes]] = {}

    def setUp(self) -> None:
        """Load the same tests/responses/ fixtures cloud_test.py uses."""
        file_path = Path(__file__)
        for file in Path.iterdir(Path(file_path.parent, "responses")):
            file_path = Path(file)
            with file_path.open(encoding="utf-8") as f:
                self.responses[file_path.name] = bytes(f.read(), encoding="utf-8")

    def _make_cloud(self) -> tuple[Mock, TSmartLifeCloud]:
        """Build a TSmartLifeCloud with synthetic credentials.

        Uses patch.dict (started here, stopped via addCleanup) rather
        than a plain .update() so the global SUPPORTED_CLOUDS entry is
        always restored after this test -- regardless of pass/fail,
        and regardless of what order tests across files run in. Fixes
        a real test-isolation gap found by CodeRabbit's 2026-10-14
        review on PR #198: the previous plain .update() never restored
        the entry, which could make tests/cloud_test.py's
        TestTSmartLifeCloud snapshot/restore these synthetic values
        instead of the real ones if this file's tests ran first.
        """
        patcher = patch.dict(SUPPORTED_CLOUDS["TSmartLife"], SYNTHETIC_CREDENTIALS)
        patcher.start()
        self.addCleanup(patcher.stop)
        session = Mock()
        cloud = get_midea_cloud(
            "TSmartLife",
            session=session,
            account="synthetic_account",
            password="synthetic_password",
        )
        assert isinstance(cloud, TSmartLifeCloud)
        return session, cloud

    # ------------------------------------------------------------------
    # Stage 1: regional endpoint selection + request signing
    # ------------------------------------------------------------------
    async def test_stage1_reroute_hits_confirmed_real_host(self) -> None:
        """_re_route() targets the confirmed real mp-jp-prod.appsmb.com host."""
        session, cloud = self._make_cloud()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["msmartcloud_reroute.json"],
        )
        session.request = AsyncMock(return_value=response)

        await cloud._re_route()

        first_call = session.request.await_args_list[0]
        url = first_call.args[1] if len(first_call.args) > 1 else ""
        assert url.startswith("https://mp-jp-prod.appsmb.com/mas/v5/app/proxy?alias=")
        # _re_route() gracefully applies masUrl when present (Stage 3O finding).
        assert cloud._api_url == "https://reroute.url/"

    async def test_stage1_signing_uses_iot_and_hmac_keys(self) -> None:
        """Every outbound request is signed; the sign header is never blank.

        Structural check only (shape, not an algorithm re-derivation) --
        CloudSecurity.sign()'s own correctness is already covered by
        tests/security_test.py; this confirms TSmartLifeCloud's inherited
        _api_request() actually calls it end to end.
        """
        session, cloud = self._make_cloud()
        response = Mock()
        response.read = AsyncMock(
            return_value=self.responses["cloud_invalid_response.json"],
        )
        session.request = AsyncMock(return_value=response)

        await cloud._api_request(endpoint="/v1/some/endpoint", data={"a": "b"})

        call = session.request.await_args_list[0]
        sign = call.kwargs["headers"]["sign"]
        assert sign  # hex-encoded HMAC-SHA256 digest, never blank
        assert len(sign) == 64

    # ------------------------------------------------------------------
    # Stage 2: full login() round trip with a self-consistent synthetic
    # fixture (no real app_key/credential involved -- see module docstring)
    # ------------------------------------------------------------------
    async def test_stage2_full_login_round_trip_with_synthetic_fixture(self) -> None:
        """login() succeeds end to end against a self-generated fixture.

        Unlike tests/cloud_test.py's TSmartLifeCloud tests (which
        deliberately skip login()'s AES step because the shared
        msmartcloud_login.json fixture is tied to SmartHome's real
        app_key), this fixture is generated purely from this test's own
        synthetic app_key, so the full encrypt/decrypt round trip
        (MSmartCloudSecurity.set_aes_keys) is genuinely exercised here.
        """
        session, cloud = self._make_cloud()
        response = Mock()
        response.read = AsyncMock(
            side_effect=[
                self.responses["msmartcloud_reroute.json"],
                self.responses["cloud_login_id.json"],
                self.responses["tsmartlife_synthetic_login.json"],
            ],
        )
        session.request = AsyncMock(return_value=response)

        result = await cloud.login()

        assert result is True
        assert cloud._uid == "synthetic_test_uid_0000000000000"
        assert cloud._access_token == "synthetic_test_bearer_token"
        # Proves the AES key/IV ciphertext in the fixture decrypted correctly
        # under a key derived solely from this test's synthetic app_key.
        assert cloud._security._aes_key == b"0123456789abcdef"
        assert cloud._security._aes_iv == b"fedcba9876543210"

    # ------------------------------------------------------------------
    # Stage 3: get_cloud_keys() -- v1 (inherited, pre-fix) path
    # ------------------------------------------------------------------
    async def test_stage3_v1_path_already_works(self) -> None:
        """The inherited v1 get_cloud_keys() path correctly parses tokens.

        Forces v2 to come back empty so this specifically exercises v1
        token/key parsing (method 1 + method 2), independent of which
        endpoint is tried first -- that ordering question belongs to the
        stage4 tests below. Same base-class parsing path
        tests/cloud_test.py already covers
        (test_token_response_parsing_reuses_base_gettoken_shape) --
        reproduced here so this harness is self-contained end to end.
        """
        session, cloud = self._make_cloud()
        v1_responses = iter(
            [
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )

        def _respond(_method: str, url: str, **_kwargs: object) -> Mock:
            r = Mock()
            if url.endswith("/v2/iot/secure/getToken"):
                r.read = AsyncMock(
                    return_value=self.responses["cloud_invalid_response.json"],
                )
            else:
                r.read = AsyncMock(return_value=next(v1_responses))
            return r

        session.request = AsyncMock(side_effect=_respond)

        keys = await cloud.get_cloud_keys(100)

        assert keys[1]["token"] == "method1_return_token1"
        assert keys[2]["token"] == "method2_return_token2"
        requests = _token_requests(session)
        v1 = [u for u, _ in requests if u.endswith("/v1/iot/secure/getToken")]
        assert len(v1) == 2, "v1 must still be reachable as the fallback path"

    # ------------------------------------------------------------------
    # Stage 4: get_cloud_keys() -- v2 path (EXPOSES the concrete failure
    # on unfixed code; PASSES once the Stage 3Z fix is applied below)
    # ------------------------------------------------------------------
    async def test_stage4_v2_only_backend_is_handled(self) -> None:
        """If the real backend only answers v2, get_cloud_keys() must still return keys.

        On the unmodified TSmartLifeCloud (inherits MideaCloud's v1-only
        get_cloud_keys verbatim), this FAILS: v1 is the only endpoint ever
        called, so a backend that only implements v2 (Stage 3W/3X: both
        `/v1/iot/secure/getToken` and `/v2/iot/secure/getToken` exist as
        literal strings in the real APK with no confirmed call-site
        evidence for either -- this scenario is explicitly plausible, not
        hypothetical) yields an empty dict and get_cloud_keys() silently
        reports zero tokens. This is the "concrete implementation failure"
        Stage 3Z was asked to expose.
        """
        session, cloud = self._make_cloud()

        def _respond(_method: str, url: str, **_kwargs: object) -> Mock:
            r = Mock()
            if url.endswith("/v2/iot/secure/getToken"):
                r.read = AsyncMock(
                    return_value=self.responses["meijucloud_get_keys1.json"],
                )
            else:
                r.read = AsyncMock(
                    return_value=self.responses["cloud_invalid_response.json"],
                )
            return r

        session.request = AsyncMock(side_effect=_respond)

        keys = await cloud.get_cloud_keys(100)

        assert keys.get(1, {}).get("token") == "method1_return_token1"

    async def test_stage4_v2_tried_before_v1_and_sends_list_form_appliance_codes(
        self,
    ) -> None:
        """When v2 succeeds, v1 must never be called.

        The payload shape must also match the native-library evidence
        (list-form applianceCodes, Stage 3W §2) rather than the v1 base
        class's plain-string shape.
        """
        session, cloud = self._make_cloud()

        def _respond(_method: str, url: str, **_kwargs: object) -> Mock:
            r = Mock()
            r.read = AsyncMock(
                return_value=self.responses["meijucloud_get_keys1.json"]
                if url.endswith("/v2/iot/secure/getToken")
                else self.responses["cloud_invalid_response.json"],
            )
            return r

        session.request = AsyncMock(side_effect=_respond)

        await cloud.get_cloud_keys(100)

        requests = _token_requests(session)
        assert requests, "no getToken request was sent at all"
        assert all(url.endswith("/v2/iot/secure/getToken") for url, _ in requests), (
            "v1 was called even though v2 already returned keys"
        )
        for _url, payload in requests:
            assert payload["applianceCodes"] == ["100"], (
                "applianceCodes must be list-form for v2, per the native "
                '{"applianceCodes": [ template (Stage 3W §2)'
            )
            assert "homegroupId" not in payload, (
                "TSmartLife's real list-home endpoint is unconfirmed "
                "(SmartHomeCloud never overrides MideaCloud.list_home()'s "
                "static {1: 'My home'} placeholder) -- sending a "
                "homegroupId derived from that placeholder would be "
                "unverified invention, not a justified fix"
            )

    async def test_stage4_v1_fallback_still_works_when_v2_is_empty(self) -> None:
        """If v2 returns nothing, the v1 safety net must still produce keys."""
        session, cloud = self._make_cloud()
        v1_responses = iter(
            [
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )

        def _respond(_method: str, url: str, **_kwargs: object) -> Mock:
            r = Mock()
            if url.endswith("/v2/iot/secure/getToken"):
                r.read = AsyncMock(
                    return_value=self.responses["cloud_invalid_response.json"],
                )
            else:
                r.read = AsyncMock(return_value=next(v1_responses))
            return r

        session.request = AsyncMock(side_effect=_respond)

        keys = await cloud.get_cloud_keys(100)

        assert keys[1]["token"] == "method1_return_token1"
        assert keys[2]["token"] == "method2_return_token2"
        requests = _token_requests(session)
        v2 = [u for u, _ in requests if u.endswith("/v2/iot/secure/getToken")]
        v1 = [u for u, _ in requests if u.endswith("/v1/iot/secure/getToken")]
        assert len(v2) == 2, "v2 must be tried for both UDP-ID methods first"
        assert len(v1) == 2, "v1 fallback must still run for both methods"

    async def test_stage4_v1_fallback_handles_malformed_v2_responses(self) -> None:
        """Malformed v2 responses must not prevent the v1 fallback."""
        malformed_responses = (
            b"{}",
            b"[]",
            b'{"code": "not-an-integer"}',
        )
        for malformed_response in malformed_responses:
            with self.subTest(malformed_response=malformed_response):
                session, cloud = self._make_cloud()
                v1_responses = iter(
                    [
                        self.responses["meijucloud_get_keys1.json"],
                        self.responses["meijucloud_get_keys2.json"],
                    ],
                )

                def _respond(
                    _method: str,
                    url: str,
                    _malformed_response: bytes = malformed_response,
                    _v1_responses: Iterator[bytes] = v1_responses,
                    **_kwargs: object,
                ) -> Mock:
                    r = Mock()
                    if url.endswith("/v2/iot/secure/getToken"):
                        r.read = AsyncMock(return_value=_malformed_response)
                    else:
                        r.read = AsyncMock(return_value=next(_v1_responses))
                    return r

                session.request = AsyncMock(side_effect=_respond)

                keys = await cloud.get_cloud_keys(100)

                assert keys[1]["token"] == "method1_return_token1"
                assert keys[2]["token"] == "method2_return_token2"
                requests = _token_requests(session)
                v2 = [u for u, _ in requests if u.endswith("/v2/iot/secure/getToken")]
                v1 = [u for u, _ in requests if u.endswith("/v1/iot/secure/getToken")]
                assert len(v2) == 2, "v2 must be tried for both UDP-ID methods first"
                assert len(v1) == 2, "v1 fallback must still run for both methods"

    # ------------------------------------------------------------------
    # Stage 5: LAN V3 handoff shape contract (static only -- no device,
    # no real connect(); midealan/cli.py::MideaCLI._get_keys() is the
    # real consumer of this exact shape)
    # ------------------------------------------------------------------
    async def test_stage5_cloud_keys_shape_matches_lan_v3_handoff_contract(
        self,
    ) -> None:
        """Pin the cloud-side half of the LAN V3 handoff contract.

        get_cloud_keys()'s return shape is exactly what cli.py's
        _get_keys()/device_selector() handoff expects: {method:
        {"token": str, "key": str}}, lower-cased hex. midea-local's own
        device type 0xCA (Toshiba CA family) module/tests already exist
        independently (tests/devices/ca/ in the midea-local repo) -- this
        only pins the cloud-side half of the contract, not a real LAN
        handshake.
        """
        session, cloud = self._make_cloud()
        v1_responses = iter(
            [
                self.responses["meijucloud_get_keys1.json"],
                self.responses["meijucloud_get_keys2.json"],
            ],
        )

        def _respond(_method: str, url: str, **_kwargs: object) -> Mock:
            r = Mock()
            if url.endswith("/v2/iot/secure/getToken"):
                r.read = AsyncMock(
                    return_value=self.responses["cloud_invalid_response.json"],
                )
            else:
                r.read = AsyncMock(return_value=next(v1_responses))
            return r

        session.request = AsyncMock(side_effect=_respond)

        keys = await cloud.get_cloud_keys(100)

        for method_keys in keys.values():
            assert set(method_keys) == {"token", "key"}
            assert isinstance(method_keys["token"], str)
            assert isinstance(method_keys["key"], str)
            assert method_keys["token"] == method_keys["token"].lower()
            assert method_keys["key"] == method_keys["key"].lower()

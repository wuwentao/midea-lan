"""Midea E1 cloud features."""

import asyncio
import re
from typing import Any

from aiohttp import ClientSession

from midealan.cloud import (
    AUTH_ERROR_CODES,
    SUPPORTED_CLOUDS,
    MideaCloud,
    get_midea_cloud,
)
from midealan.exceptions import CloudAuthError, CloudError

E1_FILTER_WASH_TIME_ALIAS = "/cfhrs/e1/v1/api"
E1_FILTER_WASH_TIME_MESSAGE = "selfCleanV2"
E1_FILTER_WASH_TIME_ACTION = "getCleanTimes"
AUTH_RETRY_DELAY = 3.0


class _LoginTokenRejected(CloudAuthError):
    """Raised when the proxy still rejects a freshly issued login token."""

    def __init__(self, cloud: MideaCloud, message: str) -> None:
        """Remember which cached client supplied the rejected token."""
        super().__init__(message)
        self.cloud = cloud


async def get_filter_wash_time(cloud: MideaCloud, appliance_id: int) -> int | None:
    """Read an E1 appliance's cumulative filter-wash time in minutes.

    The 7600644C app plugin reads ``selfCleanV2/getCleanTimes`` through the
    signed proxy. The generic cloud layer supplies authentication and request
    transport; this module owns the E1-specific payload and response parsing.

    Returns:
        Whole, non-negative minutes, or None when the result is missing or
        invalid. Zero is a valid reading, not a fallback.

    Raises:
        CloudAuthError: If the user access token is absent or rejected.
        CloudError: If the proxy request fails or returns an error.

    """
    data = await cloud.request_signed_proxy(
        E1_FILTER_WASH_TIME_ALIAS,
        {
            "msg": E1_FILTER_WASH_TIME_MESSAGE,
            "params": {
                "applianceId": str(appliance_id),
                "action": E1_FILTER_WASH_TIME_ACTION,
                "diffWashTimes": 0,
                "totalWashTimes": 0,
            },
        },
    )
    code = data.get("code")
    if str(code) in {str(auth_code) for auth_code in AUTH_ERROR_CODES}:
        msg = "Midea cloud rejected the E1 filter query credentials"
        raise CloudAuthError(msg)
    if code is not None or str(data.get("retCode")) != "0":
        msg = "Midea cloud rejected the E1 filter query"
        raise CloudError(msg)
    result: Any = data.get("result")
    minutes = result.get("time") if isinstance(result, dict) else None
    if isinstance(minutes, int) and not isinstance(minutes, bool):
        return minutes if minutes >= 0 else None
    # Accept decimal integer strings and zero-only fractional suffixes,
    # without rounding, float conversion or interpreting a boolean as time.
    if isinstance(minutes, str) and re.fullmatch(r"[0-9]+(?:\.0+)?", minutes):
        try:
            return int(minutes.partition(".")[0])
        except ValueError:
            return None  # Python may limit very large integer strings.
    return None


class E1CloudClient:
    """Fetch E1 cloud features with a registered Midea cloud account.

    Authentication and token-propagation retries live beside the E1-specific
    request instead of being reimplemented by each integration. The cloud is
    selected from :data:`SUPPORTED_CLOUDS`, so additional registered providers
    can use the same E1 feature without changing this module.
    """

    def __init__(
        self,
        cloud_name: str,
        session: ClientSession,
        account: str,
        password: str,
    ) -> None:
        """Initialize for a registered cloud without starting a session."""
        if cloud_name not in SUPPORTED_CLOUDS:
            msg = f"Unsupported cloud: {cloud_name}"
            raise CloudError(msg)
        cloud_data = SUPPORTED_CLOUDS[cloud_name]
        api_url = cloud_data.get("api_url") if isinstance(cloud_data, dict) else None
        if not isinstance(api_url, str) or "alias=" not in api_url:
            msg = f"Cloud does not support E1 reports: {cloud_name}"
            raise CloudError(msg)
        self._cloud_name = cloud_name
        self._session = session
        self._account = account
        self._password = password
        self._cloud: MideaCloud | None = None
        self._login_lock = asyncio.Lock()

    async def async_get_report(self, appliance_id: int) -> int | None:
        """Fetch cumulative filter-wash minutes.

        A newly issued token can take a few seconds to propagate through the
        proxy. Retry it once, then perform one fresh login if it is still
        rejected.
        """
        try:
            return await self._async_fetch(appliance_id)
        except _LoginTokenRejected as rejected:
            async with self._login_lock:
                # Another caller may already have replaced this rejected client.
                if self._cloud is rejected.cloud:
                    self._cloud = None
            return await self._async_fetch(appliance_id)

    async def _async_fetch(self, appliance_id: int) -> int | None:
        """Fetch with the current login and retry a newly issued token once."""
        cloud = await self._async_cloud()
        try:
            return await get_filter_wash_time(cloud, appliance_id)
        except CloudAuthError:
            await asyncio.sleep(AUTH_RETRY_DELAY)
            try:
                return await get_filter_wash_time(cloud, appliance_id)
            except CloudAuthError as retry_err:
                raise _LoginTokenRejected(cloud, str(retry_err)) from retry_err

    async def _async_cloud(self) -> MideaCloud:
        """Return a logged-in cloud client, creating it on first use."""
        if self._cloud is None:
            async with self._login_lock:
                if self._cloud is None:
                    if not self._account or not self._password:
                        msg = "No Midea cloud account stored"
                        raise CloudAuthError(msg)
                    cloud = get_midea_cloud(
                        self._cloud_name,
                        self._session,
                        self._account,
                        self._password,
                    )
                    try:
                        logged_in = await cloud.login()
                    except (KeyError, TypeError, ValueError):
                        msg = "Midea cloud login failed"
                        raise CloudAuthError(msg) from None
                    if not logged_in:
                        msg = "Midea cloud login failed"
                        raise CloudAuthError(msg)
                    self._cloud = cloud
        return self._cloud

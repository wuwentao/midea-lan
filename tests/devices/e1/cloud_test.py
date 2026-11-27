"""Test E1 cloud features."""

import asyncio
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

from midealan.devices.e1.cloud import E1CloudClient, get_filter_wash_time
from midealan.exceptions import CloudAuthError, CloudError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"time": "601.0"}, 601),
        ({"time": 0}, 0),
        ({"totalTimes": 16}, None),
        ({"time": "12.5"}, None),
        ({"time": -1}, None),
        ({"time": True}, None),
    ],
)
async def test_get_filter_wash_time(
    result: dict[str, object],
    expected: int | None,
) -> None:
    """Parse whole wash minutes through the generic signed proxy."""
    cloud = Mock()
    cloud.request_signed_proxy = AsyncMock(
        return_value={"retCode": "0", "result": result},
    )

    assert await get_filter_wash_time(cloud, 100) == expected

    cloud.request_signed_proxy.assert_awaited_once_with(
        "/cfhrs/e1/v1/api",
        {
            "msg": "selfCleanV2",
            "params": {
                "applianceId": "100",
                "action": "getCleanTimes",
                "diffWashTimes": 0,
                "totalWashTimes": 0,
            },
        },
    )


@pytest.mark.asyncio
async def test_get_filter_wash_time_rejects_oversized_digits() -> None:
    """A digit string above the int limit is invalid, not a fallback value."""
    cloud = Mock()
    cloud.request_signed_proxy = AsyncMock(
        return_value={"retCode": "0", "result": {"time": "1" * 641}},
    )

    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        assert await get_filter_wash_time(cloud, 100) is None
    finally:
        sys.set_int_max_str_digits(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"code": "40002", "msg": "private-cloud-detail"}, CloudAuthError),
        ({"retCode": "1", "desc": "private-cloud-detail"}, CloudError),
    ],
)
async def test_get_filter_wash_time_failure_is_sanitized(
    response: dict[str, str],
    error: type[CloudError],
) -> None:
    """Expose a safe failure, never a zero reading or server-provided text."""
    cloud = Mock()
    cloud.request_signed_proxy = AsyncMock(return_value=response)

    with pytest.raises(error) as exc:
        await get_filter_wash_time(cloud, 100)

    assert type(exc.value) is error
    assert "private-cloud-detail" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud_name", ["美的美居", "SmartHome", "TSmartLife"])
async def test_e1_cloud_client_logs_in_and_fetches(cloud_name: str) -> None:
    """Authenticate lazily and delegate the device-specific request."""
    cloud = Mock(login=AsyncMock(return_value=True))
    session = Mock()
    client = E1CloudClient(cloud_name, session, "account", "password")
    with (
        patch(
            "midealan.devices.e1.cloud.get_midea_cloud",
            return_value=cloud,
        ) as get_cloud,
        patch(
            "midealan.devices.e1.cloud.get_filter_wash_time",
            AsyncMock(return_value=42),
        ) as get_minutes,
    ):
        assert await client.async_get_report(100) == 42
        assert await client.async_get_report(101) == 42
    get_cloud.assert_called_once_with(cloud_name, session, "account", "password")
    cloud.login.assert_awaited_once()
    assert get_minutes.await_args_list == [
        ((cloud, 100), {}),
        ((cloud, 101), {}),
    ]


@pytest.mark.asyncio
async def test_e1_cloud_client_retries_token_then_logs_in_again() -> None:
    """Retry token propagation, then replace a persistently rejected login."""
    first_cloud = Mock(login=AsyncMock(return_value=True))
    second_cloud = Mock(login=AsyncMock(return_value=True))
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    get_minutes = AsyncMock(
        side_effect=[
            CloudAuthError("rejected"),
            CloudAuthError("still rejected"),
            24,
        ],
    )
    with (
        patch(
            "midealan.devices.e1.cloud.get_midea_cloud",
            side_effect=[first_cloud, second_cloud],
        ) as get_cloud,
        patch("midealan.devices.e1.cloud.get_filter_wash_time", get_minutes),
        patch("asyncio.sleep", AsyncMock()) as sleep,
    ):
        assert await client.async_get_report(100) == 24
    assert get_cloud.call_count == 2
    first_cloud.login.assert_awaited_once()
    second_cloud.login.assert_awaited_once()
    sleep.assert_awaited_once_with(3.0)
    assert get_minutes.await_count == 3


@pytest.mark.asyncio
async def test_e1_cloud_client_serializes_concurrent_relogin() -> None:
    """Overlapping rejected tokens share one replacement cloud login."""
    old_cloud = Mock()
    new_cloud = Mock(login=AsyncMock(return_value=True))
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    client._cloud = old_cloud
    initial_calls = 0
    both_started = asyncio.Event()

    async def fetch(cloud: Mock, appliance_id: int) -> int:
        nonlocal initial_calls
        if cloud is new_cloud:
            return appliance_id
        initial_calls += 1
        if initial_calls <= 2:
            if initial_calls == 2:
                both_started.set()
            await both_started.wait()
        raise CloudAuthError("rejected")

    with (
        patch(
            "midealan.devices.e1.cloud.get_midea_cloud",
            return_value=new_cloud,
        ) as get_cloud,
        patch(
            "midealan.devices.e1.cloud.get_filter_wash_time",
            side_effect=fetch,
        ),
        patch("asyncio.sleep", AsyncMock()),
    ):
        results = await asyncio.gather(
            client.async_get_report(100),
            client.async_get_report(101),
        )
        assert tuple(results) == (100, 101)
    get_cloud.assert_called_once()
    new_cloud.login.assert_awaited_once()


@pytest.mark.asyncio
async def test_e1_cloud_client_serializes_concurrent_initial_login() -> None:
    """Overlapping first reports wait for one shared cloud login."""
    login_started = asyncio.Event()
    allow_login = asyncio.Event()

    async def login() -> bool:
        login_started.set()
        await allow_login.wait()
        return True

    cloud = Mock(login=AsyncMock(side_effect=login))
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    with (
        patch(
            "midealan.devices.e1.cloud.get_midea_cloud",
            return_value=cloud,
        ) as get_cloud,
        patch(
            "midealan.devices.e1.cloud.get_filter_wash_time",
            AsyncMock(return_value=12),
        ),
    ):
        reports = [
            asyncio.create_task(client.async_get_report(appliance_id))
            for appliance_id in (100, 101)
        ]
        await login_started.wait()
        await asyncio.sleep(0)
        allow_login.set()
        assert tuple(await asyncio.gather(*reports)) == (12, 12)
    get_cloud.assert_called_once()
    cloud.login.assert_awaited_once()


@pytest.mark.asyncio
async def test_e1_cloud_client_raises_after_second_login_is_rejected() -> None:
    """Stop after retrying both the initial and replacement login tokens."""
    clouds = [
        Mock(login=AsyncMock(return_value=True)),
        Mock(login=AsyncMock(return_value=True)),
    ]
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    get_minutes = AsyncMock(side_effect=CloudAuthError("rejected"))
    with (
        patch(
            "midealan.devices.e1.cloud.get_midea_cloud",
            side_effect=clouds,
        ),
        patch("midealan.devices.e1.cloud.get_filter_wash_time", get_minutes),
        patch("asyncio.sleep", AsyncMock()) as sleep,
        pytest.raises(CloudAuthError, match="rejected"),
    ):
        await client.async_get_report(100)
    assert get_minutes.await_count == 4
    assert sleep.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("credentials", [("", "password"), ("account", "")])
async def test_e1_cloud_client_requires_account(credentials: tuple[str, str]) -> None:
    """Reject missing credentials without creating a cloud client."""
    client = E1CloudClient("美的美居", Mock(), *credentials)
    with (
        patch("midealan.devices.e1.cloud.get_midea_cloud") as get_cloud,
        pytest.raises(CloudAuthError, match="account"),
    ):
        await client.async_get_report(100)
    get_cloud.assert_not_called()


@pytest.mark.asyncio
async def test_e1_cloud_client_rejects_failed_login() -> None:
    """Expose a failed Meiju login as an authentication error."""
    cloud = Mock(login=AsyncMock(return_value=False))
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    with (
        patch("midealan.devices.e1.cloud.get_midea_cloud", return_value=cloud),
        pytest.raises(CloudAuthError, match="login failed"),
    ):
        await client.async_get_report(100)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [KeyError("result"), TypeError(), ValueError()])
async def test_e1_cloud_client_sanitizes_malformed_login(failure: Exception) -> None:
    """Map malformed cloud login replies to the public authentication error."""
    cloud = Mock(login=AsyncMock(side_effect=failure))
    client = E1CloudClient("美的美居", Mock(), "account", "password")
    get_minutes = AsyncMock()
    with (
        patch("midealan.devices.e1.cloud.get_midea_cloud", return_value=cloud),
        patch("midealan.devices.e1.cloud.get_filter_wash_time", get_minutes),
        pytest.raises(CloudAuthError, match="login failed") as exc,
    ):
        await client.async_get_report(100)
    assert type(exc.value) is CloudAuthError
    assert exc.value.__cause__ is None
    assert client._cloud is None
    get_minutes.assert_not_awaited()


def test_e1_cloud_client_rejects_unsupported_cloud() -> None:
    """Reject cloud names that are absent from the shared registry."""
    with pytest.raises(CloudError, match="Unsupported cloud: Invalid"):
        E1CloudClient("Invalid", Mock(), "account", "password")


@pytest.mark.parametrize(
    "cloud_name",
    ["Midea Air", "NetHome Plus", "Ariston Clima", "Toshiba Iolife"],
)
def test_e1_cloud_client_rejects_cloud_without_signed_proxy(
    cloud_name: str,
) -> None:
    """Reject registered clouds whose API URL has no proxy alias."""
    with pytest.raises(CloudError, match="does not support E1 reports"):
        E1CloudClient(cloud_name, Mock(), "account", "password")

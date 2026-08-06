"""Regression tests for transient WF-RAC transport failures."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientConnectionError

from custom_components.mitsubishi_wf_rac.wfrac.device import Device
from custom_components.mitsubishi_wf_rac.wfrac.repository import (
    AirconConnectionError,
    Repository,
)

from ..unit.live_captures import LIVE_CAPTURES

ON_COOL_PAYLOAD, _ = LIVE_CAPTURES["on_cool"]


def _stats_response(payload: str) -> dict:
    return {
        "numOfAccount": 1,
        "airconStat": payload,
        "updatedBy": "local",
    }


class _FakeResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.content_type = "application/json"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self) -> str:
        return self._body


class _SequenceSession:
    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.urls: list[str] = []

    def post(self, url, **kwargs):
        self.urls.append(url)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


async def test_device_transport_failure_does_not_reregister_account(hass):
    device = Device(
        hass,
        "Test AC",
        "127.0.0.1",
        51443,
        "device-id",
        "operator-id",
        "airco-id",
        availability_retry=True,
        availability_retry_limit=3,
        create_swing_mode_select=True,
    )
    device._api = AsyncMock()
    device._api.get_aircon_stats.return_value = _stats_response(ON_COOL_PAYLOAD)
    await device.update()
    assert device.available is True

    device._api.get_aircon_stats.side_effect = AirconConnectionError("offline")
    device._api.update_account_info = AsyncMock()

    await device.update()

    assert device.available is True  # first failure stays inside retry tolerance
    device._api.update_account_info.assert_not_awaited()


async def test_confirmed_method_is_kept_after_short_disconnect(hass):
    repository = Repository(
        hass,
        "127.0.0.1",
        51443,
        "operator-id",
        "device-id",
        method="http",
    )
    repository._method_confirmed = True
    repository._session = _SequenceSession([ClientConnectionError("offline")])

    with pytest.raises(AirconConnectionError):
        await repository._post("getDeviceInfo")

    assert repository.method == "http"
    assert repository._connection_failure_count == 1
    assert len(repository._session.urls) == 1
    assert repository._session.urls[0].startswith("http://")


async def test_confirmed_method_is_cleared_after_three_failures(hass):
    repository = Repository(
        hass,
        "127.0.0.1",
        51443,
        "operator-id",
        "device-id",
        method="http",
    )
    repository._method_confirmed = True
    repository._session = _SequenceSession(
        [ClientConnectionError("offline") for _ in range(3)]
    )

    for _ in range(3):
        with pytest.raises(AirconConnectionError):
            await repository._post("getDeviceInfo")

    assert repository.method is None
    assert repository._connection_failure_count == 0
    assert repository._method_confirmed is False
    assert len(repository._session.urls) == 3


async def test_stale_persisted_method_tries_alternate_once(hass):
    repository = Repository(
        hass,
        "127.0.0.1",
        51443,
        "operator-id",
        "device-id",
        method="http",
    )
    repository._get_ssl_context = AsyncMock(return_value=False)
    repository._session = _SequenceSession(
        [
            ClientConnectionError("stale http"),
            _FakeResponse('{"contents": {"airconId": "airco-id"}}'),
        ]
    )

    response = await repository._post("getDeviceInfo")

    assert response["contents"]["airconId"] == "airco-id"
    assert repository.method == "https"
    assert repository._method_confirmed is True
    assert len(repository._session.urls) == 2
    assert repository._session.urls[0].startswith("http://")
    assert repository._session.urls[1].startswith("https://")

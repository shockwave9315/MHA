"""Regression tests for Home Leave number ranges."""

from unittest.mock import AsyncMock

import pytest

from custom_components.mitsubishi_wf_rac.number import HomeLeaveModeNumber
from custom_components.mitsubishi_wf_rac.wfrac.device import Device


@pytest.fixture
async def device(hass):
    dev = Device(
        hass, "Test AC", "127.0.0.1", 51443, "device-id", "operator-id", "airco-id",
        create_swing_mode_select=True,
    )
    dev._api = AsyncMock()
    return dev


@pytest.mark.parametrize(
    "mode,attribute,minimum,maximum",
    [
        ("cooling", "TempRule", 10.0, 50.0),
        ("cooling", "TempSetting", 10.0, 50.0),
        ("heating", "TempRule", -20.0, 30.0),
        ("heating", "TempSetting", 0.0, 30.0),
    ],
)
async def test_home_leave_number_uses_mode_specific_bounds(
    device, mode, attribute, minimum, maximum
):
    entity = HomeLeaveModeNumber(device, mode, attribute)

    assert entity._attr_native_min_value == minimum
    assert entity._attr_native_max_value == maximum

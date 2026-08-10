"""Regression tests for the target-temperature sensor offset."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACMode

from custom_components.mitsubishi_wf_rac.const import (
    ATTR_TARGET_TEMPERATURE,
    CONF_TARGET_OFFSET,
    CONF_TARGET_OFFSET_COOL,
    CONF_TARGET_OFFSET_HEAT,
    HVAC_TRANSLATION,
)
from custom_components.mitsubishi_wf_rac.sensor import TemperatureSensor
from custom_components.mitsubishi_wf_rac.wfrac.device import Device


@pytest.fixture
async def device(hass):
    dev = Device(
        hass, "Test AC", "127.0.0.1", 51443, "device-id", "operator-id", "airco-id",
        create_swing_mode_select=True,
    )
    dev._api = AsyncMock()
    dev.config_entry = SimpleNamespace(options={})
    return dev


@pytest.mark.parametrize(
    "hvac_mode,expected_offset",
    [
        (HVACMode.COOL, 2.0),
        (HVACMode.DRY, 2.0),
        (HVACMode.HEAT, -1.5),
        (HVACMode.AUTO, 0.5),
    ],
)
async def test_target_sensor_uses_same_mode_aware_offset(device, hvac_mode, expected_offset):
    device.config_entry.options.update(
        {
            CONF_TARGET_OFFSET: 0.5,
            CONF_TARGET_OFFSET_COOL: 2.0,
            CONF_TARGET_OFFSET_HEAT: -1.5,
        }
    )
    device.airco.OperationMode = HVAC_TRANSLATION[hvac_mode]
    device.airco.PresetTemp = 21.0

    entity = TemperatureSensor(device, "Target", ATTR_TARGET_TEMPERATURE, False)

    assert entity._attr_native_value == 21.0 + expected_offset

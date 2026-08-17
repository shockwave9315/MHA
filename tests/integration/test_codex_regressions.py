"""Regression coverage for fork fixes found by earlier Codex reviews."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACMode
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitsubishi_wf_rac.const import (
    ATTR_TARGET_TEMPERATURE,
    CONF_TARGET_OFFSET,
    CONF_TARGET_OFFSET_COOL,
    CONF_TARGET_OFFSET_HEAT,
    DOMAIN,
    HVAC_TRANSLATION,
)
from custom_components.mitsubishi_wf_rac.number import HomeLeaveModeNumber
from custom_components.mitsubishi_wf_rac.sensor import TemperatureSensor
from custom_components.mitsubishi_wf_rac.wfrac.fork_device import ForkDevice
from custom_components.mitsubishi_wf_rac.wfrac.fork_parser import ForkRacParser
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import Aircon


@pytest.fixture
async def device(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_TARGET_OFFSET: 0.5,
            CONF_TARGET_OFFSET_COOL: 2.0,
            CONF_TARGET_OFFSET_HEAT: -1.5,
        },
    )
    dev = ForkDevice(
        hass,
        entry,
        "Test AC",
        "127.0.0.1",
        51443,
        "device-id",
        "operator-id",
        "airco-id",
        swing_selects_enabled_default=True,
    )
    dev._api = AsyncMock()
    dev._airco = Aircon()
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
async def test_home_leave_numbers_use_field_specific_bounds(
    device, mode, attribute, minimum, maximum
):
    entity = HomeLeaveModeNumber(device, mode, attribute)

    assert entity._attr_native_min_value == minimum
    assert entity._attr_native_max_value == maximum


def test_home_leave_decoder_preserves_negative_heating_temperature() -> None:
    parser = ForkRacParser()
    ac = Aircon()
    vals = []
    # Heating TempRule=-20 C is encoded as signed byte -40. Airflow fields are
    # bit patterns and deliberately stay unsigned.
    for sub, value in zip((27, 28, 29, 30, 31, 32), (70, -40, 66, 20, 3, 7)):
        vals += [-8, 16, sub, value]

    parser._parse_temperatures(ac, vals)

    assert ac.HomeLeaveModeForHeating is not None
    assert ac.HomeLeaveModeForHeating.TempRule == -20.0


@pytest.mark.parametrize(
    "hvac_mode,expected_offset",
    [
        (HVACMode.COOL, 2.0),
        (HVACMode.DRY, 2.0),
        (HVACMode.HEAT, -1.5),
        (HVACMode.AUTO, 0.5),
    ],
)
async def test_target_sensor_uses_same_mode_aware_offset(
    device, hvac_mode, expected_offset
):
    device.airco.OperationMode = HVAC_TRANSLATION[hvac_mode]
    device.airco.PresetTemp = 21.0

    entity = TemperatureSensor(device, "Target", ATTR_TARGET_TEMPERATURE, False)

    assert entity._attr_native_value == 21.0 + expected_offset

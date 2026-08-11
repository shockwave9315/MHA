"""Regression coverage for findings from the 2026.9.4-beta1 Codex review."""

from datetime import datetime, timedelta
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
from custom_components.mitsubishi_wf_rac.number import HomeLeaveModeNumber
from custom_components.mitsubishi_wf_rac.sensor import TemperatureSensor
from custom_components.mitsubishi_wf_rac.wfrac import device as device_module
from custom_components.mitsubishi_wf_rac.wfrac.device import Device
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import Aircon
from custom_components.mitsubishi_wf_rac.wfrac.rac_parser import RacParser


@pytest.fixture
async def device(hass):
    dev = Device(
        hass,
        "Test AC",
        "127.0.0.1",
        51443,
        "device-id",
        "operator-id",
        "airco-id",
        create_swing_mode_select=True,
    )
    dev._api = AsyncMock()
    dev.config_entry = SimpleNamespace(options={})
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
    parser = RacParser()
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


async def test_service_data_write_is_skipped_when_fresh_state_read_fails(
    device, monkeypatch
):
    monkeypatch.setattr(
        device_module, "SERVICE_DATA_REQUEST_OFFSET", timedelta(milliseconds=0)
    )
    device.update = AsyncMock(return_value=False)
    device._api.send_airco_command = AsyncMock()

    await device._async_request_service_data()

    device.update.assert_awaited_once()
    device._api.send_airco_command.assert_not_awaited()


async def test_missing_service_field_expires_independently(device):
    now = datetime.now()
    device._airco.CompressorFrequency = 40.0
    device._airco.EevPulses = 180
    device._last_service_data_response = {
        "CompressorFrequency": now - timedelta(seconds=1),
        "EevPulses": now
        - (device_module.SERVICE_DATA_MAX_AGE + timedelta(seconds=1)),
    }

    new_airco = Aircon()
    new_airco.CompressorFrequency = 45.0
    device._carry_forward_service_data(new_airco)

    assert new_airco.CompressorFrequency == 45.0
    assert new_airco.EevPulses is None

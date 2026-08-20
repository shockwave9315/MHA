"""Fork regressions layered on top of the upstream 2026.9.5 architecture."""

from datetime import datetime, timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitsubishi_wf_rac.const import DOMAIN
from custom_components.mitsubishi_wf_rac.wfrac.device import SERVICE_DATA_MAX_AGE
from custom_components.mitsubishi_wf_rac.wfrac.fork_device import ForkDevice
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import Aircon
from custom_components.mitsubishi_wf_rac.wfrac.rac_parser import (
    SERVICE_DATA_COMPRESSOR_FREQ,
    SERVICE_DATA_OPERATING_CURRENT,
)


def _device(hass) -> ForkDevice:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    return ForkDevice(
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


async def test_live_frequency_does_not_keep_missing_current_fresh(hass, monkeypatch):
    """Freshness belongs to a field, not to the operation-data block."""
    device = _device(hass)
    monkeypatch.setattr(
        device,
        "async_contexts",
        lambda: {SERVICE_DATA_COMPRESSOR_FREQ, SERVICE_DATA_OPERATING_CURRENT},
    )

    device._airco = Aircon(CompressorFrequency=40.0, OperatingCurrent=5.0)
    device._last_service_data_response_by_field["CompressorFrequency"] = datetime.now()
    device._last_service_data_response_by_field["OperatingCurrent"] = (
        datetime.now() - SERVICE_DATA_MAX_AGE - timedelta(seconds=1)
    )

    new_airco = Aircon(CompressorFrequency=41.0, OperatingCurrent=None)
    device._carry_forward_service_data(new_airco)

    assert new_airco.CompressorFrequency == 41.0
    assert new_airco.OperatingCurrent is None


async def test_recent_missing_field_is_carried_independently(hass, monkeypatch):
    """A short skipped segment keeps its own last value within max age."""
    device = _device(hass)
    monkeypatch.setattr(
        device,
        "async_contexts",
        lambda: {SERVICE_DATA_COMPRESSOR_FREQ, SERVICE_DATA_OPERATING_CURRENT},
    )

    device._airco = Aircon(CompressorFrequency=40.0, OperatingCurrent=5.0)
    device._last_service_data_response_by_field["OperatingCurrent"] = datetime.now()

    new_airco = Aircon(CompressorFrequency=41.0, OperatingCurrent=None)
    device._carry_forward_service_data(new_airco)

    assert new_airco.OperatingCurrent == 5.0

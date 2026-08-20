"""Regression coverage for an omitted port in the reconfigure flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_DEVICE_ID, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitsubishi_wf_rac.const import (
    CONF_AIRCO_ID,
    CONF_FIRMWARE_UPDATE_CHECK,
    CONF_OPERATOR_ID,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def bypass_entry_setup():
    """Keep a successful reconfigure reload from opening a real connection."""
    with patch("custom_components.mitsubishi_wf_rac.async_setup_entry", return_value=True):
        yield


async def test_reconfigure_omitted_port_preserves_current_port(hass: HomeAssistant):
    """An optional omitted port must not turn into an unexpected_error."""
    current_port = 51444
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Living Room AC",
            CONF_PORT: current_port,
            CONF_AIRCO_ID: "airco-1",
            CONF_OPERATOR_ID: "operator-1",
            CONF_DEVICE_ID: "device-1",
        },
        options={
            "host": "192.168.1.50",
            CONF_FIRMWARE_UPDATE_CHECK: False,
        },
    )
    entry.add_to_hass(hass)

    repo = AsyncMock()
    repo.get_airco_id.return_value = "airco-1"
    repo.update_account_info.return_value = {"result": 0}

    with patch(
        "custom_components.mitsubishi_wf_rac.config_flow.Repository",
        return_value=repo,
    ) as repository_cls:
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Living Room AC",
                "host": "192.168.1.60",
                # CONF_PORT intentionally omitted.
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == current_port
    assert entry.options["host"] == "192.168.1.60"
    repository_cls.assert_called_once_with(
        hass,
        "192.168.1.60",
        current_port,
        "operator-1",
        "device-1",
    )

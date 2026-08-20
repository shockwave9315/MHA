"""Regression coverage for reconfigure airco identity checks."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_BASE, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitsubishi_wf_rac.const import (
    CONF_AIRCO_ID,
    CONF_FIRMWARE_UPDATE_CHECK,
    CONF_OPERATOR_ID,
    DOMAIN,
)


async def test_reconfigure_rejects_different_airco_before_registration(
    hass: HomeAssistant,
) -> None:
    """A changed host must still resolve to the entry's original WF-RAC unit."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Living Room AC",
            "port": 51443,
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

    repository = AsyncMock()
    repository.get_airco_id.return_value = "airco-2"

    with patch(
        "custom_components.mitsubishi_wf_rac.config_flow.Repository",
        return_value=repository,
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Living Room AC",
                "host": "192.168.1.60",
                "port": 51443,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {CONF_BASE: "cannot_connect"}
    assert "different WF-RAC unit" in result["description_placeholders"]["reason"]

    # The identity mismatch must be rejected before account registration or
    # before the existing entry can be repointed to the other unit.
    repository.update_account_info.assert_not_awaited()
    assert entry.data[CONF_AIRCO_ID] == "airco-1"
    assert entry.options["host"] == "192.168.1.50"

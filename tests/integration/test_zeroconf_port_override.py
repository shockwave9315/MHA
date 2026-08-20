"""Regression test for correcting a bogus zeroconf-advertised API port."""

import ipaddress
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.mitsubishi_wf_rac.const import DOMAIN


@pytest.fixture(autouse=True)
def bypass_entry_setup():
    """Keep the config-flow regression test off the real device path."""
    with patch(
        "custom_components.mitsubishi_wf_rac.async_setup_entry",
        return_value=True,
    ):
        yield


async def test_zeroconf_discovery_port_can_be_overridden(hass: HomeAssistant):
    """Allow correcting an mDNS port such as 5353 to the API default 51443."""
    repo = AsyncMock()
    repo.get_airco_id.return_value = "airco-1"
    repo.update_account_info.return_value = {"result": 0}

    discovery = ZeroconfServiceInfo(
        ip_address=ipaddress.ip_address("192.168.1.50"),
        ip_addresses=[ipaddress.ip_address("192.168.1.50")],
        hostname="ac-living-room.local.",
        name="ac-living-room._beaver._tcp.local.",
        port=5353,
        properties={},
        type="_beaver._tcp.local.",
    )

    with patch(
        "custom_components.mitsubishi_wf_rac.config_flow.Repository",
        return_value=repo,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Living Room AC", "port": 51443},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["port"] == 51443
    assert result["options"]["host"] == "192.168.1.50"

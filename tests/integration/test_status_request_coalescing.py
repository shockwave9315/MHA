"""Regression tests for read-only status requests vs. the write queue.

Read-only status flags must never be coalesced with a real climate/Home Leave
write. The fork additionally preserves SET -> STATUS ordering when a write was
already waiting in the consolidation window.
"""

import base64
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitsubishi_wf_rac.const import DOMAIN
from custom_components.mitsubishi_wf_rac.wfrac import device as device_module
from custom_components.mitsubishi_wf_rac.wfrac.fork_device import ForkDevice
from custom_components.mitsubishi_wf_rac.wfrac.fork_parser import ForkRacParser
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import (
    AirconCommands,
    HomeLeaveModeSetting,
)

from ..unit.live_captures import LIVE_CAPTURES

ON_COOL_PAYLOAD, _ = LIVE_CAPTURES["on_cool"]


@pytest.fixture
async def device(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
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
    dev._airco = ForkRacParser().translate_bytes(ON_COOL_PAYLOAD)
    return dev


def _capture_sender(sent: list[str]):
    async def _send(_airco_id, command):
        sent.append(command)
        return ON_COOL_PAYLOAD

    return _send


def _command_bytes(command: str) -> bytes:
    return base64.b64decode(command)


async def test_home_leave_status_does_not_swallow_pending_climate_write(
    device, monkeypatch
):
    """A pending climate write is sent first, then STATUS separately."""
    monkeypatch.setattr(
        device_module,
        "UPDATE_CONSOLIDATION_PERIOD",
        timedelta(milliseconds=10),
    )
    sent: list[str] = []
    device._api.send_airco_command = AsyncMock(side_effect=_capture_sender(sent))

    await device.async_queue_command({AirconCommands.PresetTemp: 24.0})
    await device.async_request_home_leave_mode_status()

    assert len(sent) == 2

    climate = _command_bytes(sent[0])
    status = _command_bytes(sent[1])

    assert climate[4] == int(24.0 / 0.5) + 128
    assert climate[2] & 0x02
    assert climate[4] & 0x80

    assert status[2] == 0
    assert status[3] == 0
    assert status[4] == 0
    assert status[18] == 6
    assert list(status[19:23]) == [248, 255, 27, 0]


async def test_home_leave_status_runs_after_pending_home_leave_write(
    device, monkeypatch
):
    """SET -> STATUS preserves call order and never loses the SET."""
    monkeypatch.setattr(
        device_module,
        "UPDATE_CONSOLIDATION_PERIOD",
        timedelta(milliseconds=10),
    )
    sent: list[str] = []
    device._api.send_airco_command = AsyncMock(side_effect=_capture_sender(sent))

    cooling = HomeLeaveModeSetting(TempRule=35.0, TempSetting=33.0, AirFlow=2)
    heating = HomeLeaveModeSetting(TempRule=0.0, TempSetting=10.0, AirFlow=1)

    await device.async_set_home_leave_mode(cooling, heating)
    await device.async_request_home_leave_mode_status()

    assert len(sent) == 2

    write = _command_bytes(sent[0])
    status = _command_bytes(sent[1])

    assert write[2] & 0x02
    assert write[18] == 6
    assert list(write[19:23]) == [248, 0, 27, 70]

    assert status[2] == 0
    assert status[3] == 0
    assert status[4] == 0
    assert status[18] == 6
    assert list(status[19:23]) == [248, 255, 27, 0]

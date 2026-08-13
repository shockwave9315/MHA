"""Regression tests for read-only status requests vs. the write queue.

PR #6 made Home Leave status requests truly read-only at the protocol layer.
A status flag must therefore never be coalesced into the same AirconStat as a
real climate/Home Leave write, or the parser will correctly choose the
read-only command block and the write will disappear.
"""

import base64
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.mitsubishi_wf_rac.wfrac import device as device_module
from custom_components.mitsubishi_wf_rac.wfrac.device import Device
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import (
    AirconCommands,
    HomeLeaveModeSetting,
)
from custom_components.mitsubishi_wf_rac.wfrac.rac_parser import RacParser

from ..unit.live_captures import LIVE_CAPTURES

ON_COOL_PAYLOAD, _ = LIVE_CAPTURES["on_cool"]


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
    dev._airco = RacParser().translate_bytes(ON_COOL_PAYLOAD)
    return dev


def _capture_sender(sent: list[str]):
    async def _send(_airco_id, command):
        sent.append(command)
        # The exact response contents are irrelevant here; returning a real
        # status payload keeps set_airco() on its normal parse/update path.
        return ON_COOL_PAYLOAD

    return _send


def _command_bytes(command: str) -> bytes:
    return base64.b64decode(command)


async def test_home_leave_status_does_not_swallow_pending_climate_write(
    device, monkeypatch
):
    """A climate write already inside the 500 ms window is sent first and the
    Home Leave status request follows as a separate read-only transaction.
    """
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

    # First transaction is the real write: target temperature 24 C and SET
    # bits are present in the command block.
    assert climate[4] == int(24.0 / 0.5) + 128
    assert climate[2] & 0x02
    assert climate[4] & 0x80

    # Second transaction is the read-only Home Leave request: no climate SET
    # bits, with the six Tag-248 status segments in its trailer.
    assert status[2] == 0
    assert status[3] == 0
    assert status[4] == 0
    assert status[18] == 6
    assert list(status[19:23]) == [248, 255, 27, 0]


async def test_home_leave_status_runs_after_pending_home_leave_write(
    device, monkeypatch
):
    """SET -> STATUS preserves call order instead of letting the read-only
    request overtake or absorb the Home Leave write.
    """
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

    # Home Leave SET is a real write and uses marker 0 in the Tag-248 trailer.
    assert write[2] & 0x02
    assert write[18] == 6
    assert list(write[19:23]) == [248, 0, 27, 70]

    # The following status request is a separate read-only frame with marker
    # 255, so it cannot erase or replace the write above.
    assert status[2] == 0
    assert status[3] == 0
    assert status[4] == 0
    assert status[18] == 6
    assert list(status[19:23]) == [248, 255, 27, 0]

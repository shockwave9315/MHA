"""Regression coverage for fork protocol fixes kept across upstream syncs."""

from base64 import b64decode

import pytest

from custom_components.mitsubishi_wf_rac.wfrac.fork_parser import ForkRacParser
from custom_components.mitsubishi_wf_rac.wfrac.models.aircon import (
    Aircon,
    AirconStat,
    HomeLeaveModeSetting,
)
from custom_components.mitsubishi_wf_rac.wfrac.rac_parser import (
    SERVICE_DATA_COMPRESSOR_FREQ,
)


def _base_stat(**overrides) -> AirconStat:
    defaults = dict(
        Operation=True,
        OperationMode=1,
        AirFlow=0,
        WindDirectionUD=0,
        WindDirectionLR=0,
        PresetTemp=22.0,
        Entrust=False,
        ModelNr=1,
        Vacant=False,
        CoolHotJudge=True,
        IsSelfCleanOperation=False,
        IsSelfCleanReset=False,
    )
    defaults.update(overrides)
    return AirconStat(**defaults)


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"ServiceDataStatusRequest": (SERVICE_DATA_COMPRESSOR_FREQ,)},
        {"HomeLeaveModeStatusRequest": True},
    ],
)
def test_status_requests_carry_no_setting_set_bits(request_kwargs):
    parser = ForkRacParser()
    stat = _base_stat(Operation=True, PresetTemp=24.0, **request_kwargs)

    block = b64decode(parser.to_base64(stat))[:18]

    assert block == parser.status_request_to_byte(stat)
    assert list(block) == [0, 0, 0, 0, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def test_status_request_still_carries_cool_hot_judge_byte():
    parser = ForkRacParser()
    assert parser.status_request_to_byte(_base_stat(CoolHotJudge=False))[8] & 8 == 8
    assert parser.status_request_to_byte(_base_stat(CoolHotJudge=True))[8] & 8 == 0


def test_normal_climate_command_still_writes_full_state():
    parser = ForkRacParser()
    stat = _base_stat(Operation=True, PresetTemp=24.0)

    block = b64decode(parser.to_base64(stat))[:18]

    assert block == parser.command_to_byte(stat)
    assert block[2] & 2
    assert block[4] & 128


def test_home_leave_set_stays_a_real_write():
    parser = ForkRacParser()
    setting = HomeLeaveModeSetting(TempRule=10.0, TempSetting=10.0, AirFlow=0)
    stat = _base_stat(
        HomeLeaveModeForCooling=setting,
        HomeLeaveModeForHeating=setting,
    )

    block = b64decode(parser.to_base64(stat))[:18]

    assert block == parser.command_to_byte(stat)
    assert block[2] & 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (47, 5.5),
        (93, 23.2),
        (128, 33.8),
        (152, 40.7),
        (170, 45.8),
    ],
)
def test_indoor_coil_uses_ntc_curve_through_heating_range(raw, expected):
    parser = ForkRacParser()
    ac = Aircon()

    parser._parse_temperatures(ac, [0x81 - 256, 0x20, raw, 0])

    assert ac.IndoorCoilRaw == raw
    assert ac.IndoorCoilTemp == pytest.approx(expected)


def test_indoor_coil_zero_byte_keeps_raw_but_temperature_unknown():
    parser = ForkRacParser()
    ac = Aircon()

    parser._parse_temperatures(ac, [0x81 - 256, 0x20, 0, 0])

    assert ac.IndoorCoilRaw == 0
    assert ac.IndoorCoilTemp is None


def test_signed_home_leave_temperatures_are_preserved():
    """Protect signed Home Leave temperatures while syncing upstream parser code."""
    parser = ForkRacParser()
    ac = Aircon()
    vals = []
    for sub, value in zip(
        (27, 28, 29, 30, 31, 32),
        (20, -10, 18, -6, 3, 7),
    ):
        vals += [-8, 16, sub, value]

    parser._parse_temperatures(ac, vals)

    assert ac.HomeLeaveModeForCooling == HomeLeaveModeSetting(
        TempRule=10.0,
        TempSetting=9.0,
        AirFlow=1,
    )
    assert ac.HomeLeaveModeForHeating == HomeLeaveModeSetting(
        TempRule=-5.0,
        TempSetting=-3.0,
        AirFlow=3,
    )

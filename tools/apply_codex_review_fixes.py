from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, got {count}")
    p.write_text(text.replace(old, new, 1))


# 1) Persisted protocol: recover stale HTTP/HTTPS in the same request instead
# of clearing only the temporary Repository and recreating it with the same
# stale ConfigEntry value on every HA retry.
replace_once(
    "custom_components/mitsubishi_wf_rac/wfrac/repository.py",
    '''                except AirconApiError:\n                    # The unit may have rebooted, changed protocol, or the\n                    # persisted method from a previous run may simply be stale -\n                    # reset so the next request rediscovers instead of wedging\n                    # itself permanently against a method that no longer works.\n                    _LOGGER.info(\n                        "Request with stored method %r failed; "\n                        "resetting so the next request rediscovers",\n                        self._method,\n                    )\n                    self._method = None\n                    raise\n''',
    '''                except AirconConnectionError:\n                    # A persisted method can become stale across restarts (for\n                    # example after firmware switches the unit from HTTP to\n                    # HTTPS). Retrying on a fresh ConfigEntry would otherwise\n                    # recreate this Repository with the same stale method on\n                    # every HA setup attempt, so probe the alternate protocol\n                    # now and keep the recovered method on this Device.\n                    failed_method = self._method\n                    alternate_method = "https" if failed_method == "http" else "http"\n                    _LOGGER.info(\n                        "Request with stored method %r failed; trying %s",\n                        failed_method,\n                        alternate_method.upper(),\n                    )\n                    try:\n                        json_response = await _execute_request(alternate_method)\n                    except AirconCommandError:\n                        # The alternate transport answered, so it is the valid\n                        # protocol even though this command itself was refused.\n                        self._method = alternate_method\n                        raise\n                    except AirconConnectionError:\n                        # Neither transport answered. Forget the hint so a\n                        # later request can perform normal discovery again.\n                        self._method = None\n                        raise\n                    else:\n                        self._method = alternate_method\n                        _LOGGER.info(\n                            "Recovered communication method: %s",\n                            alternate_method.upper(),\n                        )\n''',
)

# 2) Home Leave signed temperatures: translate_bytes() has already made bytes
# signed. Only airflow subcodes are raw unsigned protocol values.
replace_once(
    "custom_components/mitsubishi_wf_rac/wfrac/rac_parser.py",
    "                home_leave_mode_raw[vals[i + 2] & 0xFF] = vals[i + 3] & 0xFF\n",
    '''                subcode = vals[i + 2] & 0xFF\n                value = vals[i + 3]\n                if subcode in (31, 32):\n                    value &= 0xFF\n                home_leave_mode_raw[subcode] = value\n''',
)

# 3) Home Leave number entities: match the documented action ranges by both
# mode and field instead of exposing 10..50 C for all four controls.
replace_once(
    "custom_components/mitsubishi_wf_rac/number.py",
    '''# Same bounds as the temp_rule_*/temp_setting_* fields in services.yaml's\n# set_home_leave_mode action.\nHOME_LEAVE_TEMP_MIN = 10.0\nHOME_LEAVE_TEMP_MAX = 50.0\nHOME_LEAVE_TEMP_STEP = 0.5\n''',
    '''# Same bounds as the temp_rule_*/temp_setting_* fields in services.yaml's\n# set_home_leave_mode action.\nHOME_LEAVE_TEMP_BOUNDS = {\n    ("cooling", "TempRule"): (10.0, 50.0),\n    ("cooling", "TempSetting"): (10.0, 50.0),\n    ("heating", "TempRule"): (-20.0, 30.0),\n    ("heating", "TempSetting"): (0.0, 30.0),\n}\nHOME_LEAVE_TEMP_STEP = 0.5\n''',
)
replace_once(
    "custom_components/mitsubishi_wf_rac/number.py",
    '''    _attr_native_min_value = HOME_LEAVE_TEMP_MIN\n    _attr_native_max_value = HOME_LEAVE_TEMP_MAX\n    _attr_native_step = HOME_LEAVE_TEMP_STEP\n''',
    '''    _attr_native_step = HOME_LEAVE_TEMP_STEP\n''',
)
replace_once(
    "custom_components/mitsubishi_wf_rac/number.py",
    '''        self._mode = mode\n        self._attribute = attribute\n        slug = "temp_rule" if attribute == "TempRule" else "temp_setting"\n''',
    '''        self._mode = mode\n        self._attribute = attribute\n        self._attr_native_min_value, self._attr_native_max_value = HOME_LEAVE_TEMP_BOUNDS[\n            (mode, attribute)\n        ]\n        slug = "temp_rule" if attribute == "TempRule" else "temp_setting"\n''',
)

# 4) One shared mode-aware target-offset resolver for climate and the optional
# target-temperature sensor.
Path("custom_components/mitsubishi_wf_rac/target_offset.py").write_text('''"""Shared target-temperature offset resolution."""\n\nfrom collections.abc import Mapping\nfrom typing import Any\n\nfrom homeassistant.components.climate.const import HVACMode\n\nfrom .const import (\n    CONF_TARGET_OFFSET,\n    CONF_TARGET_OFFSET_COOL,\n    CONF_TARGET_OFFSET_HEAT,\n    HVAC_TRANSLATION,\n)\n\n\ndef resolve_target_offset(options: Mapping[str, Any], hvac_mode: HVACMode) -> float:\n    """Resolve the effective target offset for one HVAC mode."""\n    base_offset = float(options.get(CONF_TARGET_OFFSET, 0.0))\n    if hvac_mode in (HVACMode.COOL, HVACMode.DRY):\n        override = options.get(CONF_TARGET_OFFSET_COOL)\n    elif hvac_mode == HVACMode.HEAT:\n        override = options.get(CONF_TARGET_OFFSET_HEAT)\n    else:\n        override = None\n    return base_offset if override is None else float(override)\n\n\ndef resolve_target_offset_from_operation(\n    options: Mapping[str, Any], operation_mode: int\n) -> float:\n    """Resolve from the WF-RAC numeric OperationMode value."""\n    hvac_mode = list(HVAC_TRANSLATION.keys())[operation_mode]\n    return resolve_target_offset(options, hvac_mode)\n''')

replace_once(
    "custom_components/mitsubishi_wf_rac/climate.py",
    "from .wfrac.models.aircon import AirconCommands, HomeLeaveModeSetting\n",
    "from .wfrac.models.aircon import AirconCommands, HomeLeaveModeSetting\nfrom .target_offset import resolve_target_offset\n",
)
replace_once(
    "custom_components/mitsubishi_wf_rac/climate.py",
    '''    CONF_INDOOR_OFFSET,\n    CONF_TARGET_OFFSET,\n    CONF_TARGET_OFFSET_COOL,\n    CONF_TARGET_OFFSET_HEAT,\n''',
    '''    CONF_INDOOR_OFFSET,\n''',
)
replace_once(
    "custom_components/mitsubishi_wf_rac/climate.py",
    '''        options = self._device.config_entry.options\n        base_offset = options.get(CONF_TARGET_OFFSET, 0.0)\n        if hvac_mode in (HVACMode.COOL, HVACMode.DRY):\n            override = options.get(CONF_TARGET_OFFSET_COOL)\n        elif hvac_mode == HVACMode.HEAT:\n            override = options.get(CONF_TARGET_OFFSET_HEAT)\n        else:\n            override = None\n        return base_offset if override is None else override\n''',
    '''        return resolve_target_offset(self._device.config_entry.options, hvac_mode)\n''',
)

replace_once(
    "custom_components/mitsubishi_wf_rac/sensor.py",
    "from .wfrac.device import Device\n",
    "from .wfrac.device import Device\nfrom .target_offset import resolve_target_offset_from_operation\n",
)
replace_once(
    "custom_components/mitsubishi_wf_rac/sensor.py",
    "    CONF_TARGET_OFFSET,\n",
    "",
)
replace_once(
    "custom_components/mitsubishi_wf_rac/sensor.py",
    '''        elif self._custom_type == ATTR_TARGET_TEMPERATURE:\n            # Kept symmetric with climate.py's target_temperature - see the\n            # comment in ClimateEntity._update_state().\n            target_offset = self._device.config_entry.options.get(CONF_TARGET_OFFSET, 0.0)\n            self._attr_native_value = self._device.airco.PresetTemp + target_offset\n''',
    '''        elif self._custom_type == ATTR_TARGET_TEMPERATURE:\n            # Use the exact same mode-aware resolver as climate.py so the\n            # optional target sensor cannot disagree with the climate entity.\n            target_offset = resolve_target_offset_from_operation(\n                self._device.config_entry.options, self._device.airco.OperationMode\n            )\n            self._attr_native_value = self._device.airco.PresetTemp + target_offset\n''',
)

# Regression tests for stale persisted protocol recovery.
replace_once(
    "tests/integration/test_repository.py",
    '''async def test_unreachable_unit_resets_the_discovered_method(repository):\n    """A dead transport says nothing about which protocol is right, so the\n    stored one is dropped and the next request rediscovers.\n    """\n    repo, _ = repository([ClientConnectionError("boom")])\n\n    with pytest.raises(AirconConnectionError):\n        await repo.get_aircon_stats("airco-id")\n    assert repo.method is None\n\n\n''',
    '''async def test_unreachable_unit_resets_the_discovered_method(repository):\n    """If neither stored nor alternate protocol answers, forget the hint."""\n    repo, session = repository(\n        [ClientConnectionError("http down"), ClientConnectionError("https down")]\n    )\n\n    with pytest.raises(AirconConnectionError):\n        await repo.get_aircon_stats("airco-id")\n    assert repo.method is None\n    assert session.urls == [\n        "http://127.0.0.1:51443/beaver/command/getAirconStat",\n        "https://127.0.0.1:51443/beaver/command/getAirconStat",\n    ]\n\n\nasync def test_stale_persisted_method_recovers_in_same_call(repository):\n    """A stale ConfigEntry protocol must not wedge every HA setup retry."""\n    repo, session = repository(\n        [ClientConnectionError("http stale"), _FakeResponse(200, _OK_BODY)]\n    )\n\n    result = await repo.get_aircon_stats("airco-id")\n\n    assert result == {"airconId": "airco-id"}\n    assert repo.method == "https"\n    assert session.urls == [\n        "http://127.0.0.1:51443/beaver/command/getAirconStat",\n        "https://127.0.0.1:51443/beaver/command/getAirconStat",\n    ]\n\n\n''',
)

# Regression tests for signed Home Leave temperatures.
replace_once(
    "tests/unit/test_rac_parser.py",
    '''def test_parse_temperatures_home_leave_mode_partial_does_not_commit(parser):\n''',
    '''def test_parse_temperatures_home_leave_mode_preserves_negative_heating_rule(parser):\n    ac = Aircon()\n    vals = []\n    for sub, value in zip((27, 28, 29, 30, 31, 32), (70, -40, 66, 20, 3, 7)):\n        vals += [-8, 16, sub, value]\n    parser._parse_temperatures(ac, vals)\n    assert ac.HomeLeaveModeForHeating == HomeLeaveModeSetting(\n        TempRule=-20.0, TempSetting=10.0, AirFlow=3\n    )\n\n\ndef test_parse_temperatures_home_leave_mode_partial_does_not_commit(parser):\n''',
)
replace_once(
    "tests/unit/test_rac_parser.py",
    "        vals += [signed(tag), 16, sub, value]\n",
    "        vals += [signed(tag), 16, sub, signed(value)]\n",
)
replace_once(
    "tests/unit/test_rac_parser.py",
    '''def test_service_data_trailer_status_request(parser):\n''',
    '''def test_home_leave_mode_negative_heating_rule_round_trip(parser):\n    stat = _base_stat(\n        HomeLeaveModeForCooling=HomeLeaveModeSetting(TempRule=35.0, TempSetting=33.0, AirFlow=2),\n        HomeLeaveModeForHeating=HomeLeaveModeSetting(TempRule=-20.0, TempSetting=10.0, AirFlow=1),\n    )\n    trailer = parser._variable_trailer(stat)\n    signed = lambda b: b - 256 if b > 127 else b\n    groups = [trailer[1 + i * 4:5 + i * 4] for i in range(6)]\n    vals = []\n    for group in groups:\n        tag, _marker, sub, value = group\n        vals += [signed(tag), 16, sub, signed(value)]\n\n    ac = Aircon()\n    parser._parse_temperatures(ac, vals)\n    assert ac.HomeLeaveModeForCooling == stat.HomeLeaveModeForCooling\n    assert ac.HomeLeaveModeForHeating == stat.HomeLeaveModeForHeating\n\n\ndef test_service_data_trailer_status_request(parser):\n''',
)

Path("tests/integration/test_number.py").write_text('''"""Regression tests for Home Leave number ranges."""\n\nfrom unittest.mock import AsyncMock\n\nimport pytest\n\nfrom custom_components.mitsubishi_wf_rac.number import HomeLeaveModeNumber\nfrom custom_components.mitsubishi_wf_rac.wfrac.device import Device\n\n\n@pytest.fixture\nasync def device(hass):\n    dev = Device(\n        hass, "Test AC", "127.0.0.1", 51443, "device-id", "operator-id", "airco-id",\n        create_swing_mode_select=True,\n    )\n    dev._api = AsyncMock()\n    return dev\n\n\n@pytest.mark.parametrize(\n    "mode,attribute,minimum,maximum",\n    [\n        ("cooling", "TempRule", 10.0, 50.0),\n        ("cooling", "TempSetting", 10.0, 50.0),\n        ("heating", "TempRule", -20.0, 30.0),\n        ("heating", "TempSetting", 0.0, 30.0),\n    ],\n)\nasync def test_home_leave_number_uses_mode_specific_bounds(\n    device, mode, attribute, minimum, maximum\n):\n    entity = HomeLeaveModeNumber(device, mode, attribute)\n\n    assert entity._attr_native_min_value == minimum\n    assert entity._attr_native_max_value == maximum\n''')

Path("tests/integration/test_temperature_sensor.py").write_text('''"""Regression tests for the target-temperature sensor offset."""\n\nfrom types import SimpleNamespace\nfrom unittest.mock import AsyncMock\n\nimport pytest\nfrom homeassistant.components.climate.const import HVACMode\n\nfrom custom_components.mitsubishi_wf_rac.const import (\n    ATTR_TARGET_TEMPERATURE,\n    CONF_TARGET_OFFSET,\n    CONF_TARGET_OFFSET_COOL,\n    CONF_TARGET_OFFSET_HEAT,\n    HVAC_TRANSLATION,\n)\nfrom custom_components.mitsubishi_wf_rac.sensor import TemperatureSensor\nfrom custom_components.mitsubishi_wf_rac.wfrac.device import Device\n\n\n@pytest.fixture\nasync def device(hass):\n    dev = Device(\n        hass, "Test AC", "127.0.0.1", 51443, "device-id", "operator-id", "airco-id",\n        create_swing_mode_select=True,\n    )\n    dev._api = AsyncMock()\n    dev.config_entry = SimpleNamespace(options={})\n    return dev\n\n\n@pytest.mark.parametrize(\n    "hvac_mode,expected_offset",\n    [\n        (HVACMode.COOL, 2.0),\n        (HVACMode.DRY, 2.0),\n        (HVACMode.HEAT, -1.5),\n        (HVACMode.AUTO, 0.5),\n    ],\n)\nasync def test_target_sensor_uses_same_mode_aware_offset(device, hvac_mode, expected_offset):\n    device.config_entry.options.update(\n        {\n            CONF_TARGET_OFFSET: 0.5,\n            CONF_TARGET_OFFSET_COOL: 2.0,\n            CONF_TARGET_OFFSET_HEAT: -1.5,\n        }\n    )\n    device.airco.OperationMode = HVAC_TRANSLATION[hvac_mode]\n    device.airco.PresetTemp = 21.0\n\n    entity = TemperatureSensor(device, "Target", ATTR_TARGET_TEMPERATURE, False)\n\n    assert entity._attr_native_value == 21.0 + expected_offset\n''')

# Remove the one-shot machinery from the final commit.
Path("tools/apply_codex_review_fixes.py").unlink()
Path(".github/workflows/apply-codex-review-fixes.yml").unlink()

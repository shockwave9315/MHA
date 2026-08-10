"""Shared target-temperature offset resolution."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate.const import HVACMode

from .const import (
    CONF_TARGET_OFFSET,
    CONF_TARGET_OFFSET_COOL,
    CONF_TARGET_OFFSET_HEAT,
    HVAC_TRANSLATION,
)


def resolve_target_offset(options: Mapping[str, Any], hvac_mode: HVACMode) -> float:
    """Resolve the effective target offset for one HVAC mode."""
    base_offset = float(options.get(CONF_TARGET_OFFSET, 0.0))
    if hvac_mode in (HVACMode.COOL, HVACMode.DRY):
        override = options.get(CONF_TARGET_OFFSET_COOL)
    elif hvac_mode == HVACMode.HEAT:
        override = options.get(CONF_TARGET_OFFSET_HEAT)
    else:
        override = None
    return base_offset if override is None else float(override)


def resolve_target_offset_from_operation(
    options: Mapping[str, Any], operation_mode: int
) -> float:
    """Resolve from the WF-RAC numeric OperationMode value."""
    hvac_mode = list(HVAC_TRANSLATION.keys())[operation_mode]
    return resolve_target_offset(options, hvac_mode)

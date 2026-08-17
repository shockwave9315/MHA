"""Fork sensor shim over the upstream 2026.9.5 sensor platform.

The upstream platform is kept verbatim in sensor_upstream.py. Only the fork's
energy-total reset accounting is layered here, so future upstream syncs stay
small and reviewable.
"""

from . import sensor_upstream as _upstream
from .sensor_upstream import *  # noqa: F403


class EnergyTotalSensor(_upstream.EnergyTotalSensor):
    """Preserve the first non-zero reading after the unit resets its run counter."""

    def _update_state(self) -> None:
        raw = self._device.airco.Electric
        if raw is None:
            return
        if self._last_raw is not None:
            if raw >= self._last_raw:
                # Normal progression inside one run.
                self._total += raw - self._last_raw
            else:
                # Power-on resets the unit's per-run counter. The first poll of
                # the new run can already be non-zero; count it instead of
                # silently dropping that consumed energy while re-anchoring.
                self._total += raw
        self._last_raw = raw
        self._attr_native_value = round(self._total, 2)


# async_setup_entry() is defined in the upstream module, so make its global
# EnergyTotalSensor reference point at the fork subclass before exposing it.
_upstream.EnergyTotalSensor = EnergyTotalSensor
async_setup_entry = _upstream.async_setup_entry

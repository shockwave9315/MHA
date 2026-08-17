"""Fork sensor shim over the upstream 2026.9.5 sensor platform.

The upstream platform is kept verbatim in sensor_upstream.py. Only the fork's
energy-total reset accounting is layered here, so future upstream syncs stay
small and reviewable.
"""

from typing import Any

from . import sensor_upstream as _upstream

# Public classes/helpers used by tests and integrations are explicit. The
# module-level __getattr__ below forwards anything else unchanged.
DiagnosticsSensor = _upstream.DiagnosticsSensor
TemperatureSensor = _upstream.TemperatureSensor
EnergySensor = _upstream.EnergySensor
EnergyTotalExtraStoredData = _upstream.EnergyTotalExtraStoredData
ServiceDataSensor = _upstream.ServiceDataSensor
_async_set_energy_total = _upstream._async_set_energy_total
_async_remove_home_leave_mode_sensors = _upstream._async_remove_home_leave_mode_sensors


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


# async_setup_entry() lives in the upstream module and resolves
# EnergyTotalSensor from its own module globals at call time. Patch that one
# name through setattr so its entity construction uses the fork subclass.
setattr(_upstream, "EnergyTotalSensor", EnergyTotalSensor)
async_setup_entry = _upstream.async_setup_entry


def __getattr__(name: str) -> Any:
    """Forward upstream sensor helpers not overridden by the fork."""
    return getattr(_upstream, name)

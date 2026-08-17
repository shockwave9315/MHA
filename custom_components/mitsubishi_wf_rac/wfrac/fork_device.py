"""Fork-specific Device hardening layered on top of upstream behavior."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from .device import (
    SERVICE_DATA_DERIVED_FROM,
    SERVICE_DATA_FIELDS,
    SERVICE_DATA_MAX_AGE,
    Device,
)
from .fork_parser import ForkRacParser
from .models.aircon import Aircon, AirconCommands
from .rac_parser import SERVICE_DATA_CODE_BY_FIELD, SERVICE_DATA_CODES

_LOGGER = logging.getLogger(__name__)


class ForkDevice(Device):
    """Upstream Device plus fork regressions that are not upstream yet."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._parser = ForkRacParser()
        self._last_service_data_response_by_field: dict[str, datetime] = {}

    def _active_service_data_fields(self) -> set[str]:
        """Return fields backed by operation-data codes currently requested."""
        active_codes = set(self.async_contexts()).intersection(SERVICE_DATA_CODES)
        return {
            field
            for field, code in SERVICE_DATA_CODE_BY_FIELD.items()
            if code in active_codes
        }

    def _carry_forward_service_data(self, new_airco: Aircon) -> None:
        """Carry one-shot operation data while expiring each field separately.

        Upstream 2026.9.5 requests operation-data segments on demand. Freshness
        therefore follows the active codes too: a live compressor-frequency
        segment must not keep a missing current/EEV/temperature value alive,
        and disabled sensors must not generate stale-data warnings.
        """
        if self._airco is None:
            return

        active_fields = self._active_service_data_fields()
        if not active_fields:
            return

        now = datetime.now()
        fresh_fields: list[str] = []
        for name in active_fields:
            if getattr(new_airco, name) is not None:
                self._last_service_data_response_by_field[name] = now
                fresh_fields.append(name)

        if fresh_fields and self._service_data_expired:
            self._service_data_expired = False
            _LOGGER.info(
                "Operation data from [%s] is being reported again",
                self.device_name,
            )

        latest_response = max(
            (
                timestamp
                for field, timestamp in self._last_service_data_response_by_field.items()
                if field in active_fields
            ),
            default=None,
        )
        if not fresh_fields and (
            latest_response is None or now - latest_response > SERVICE_DATA_MAX_AGE
        ):
            self._note_service_data_expired(now)

        for name in SERVICE_DATA_FIELDS:
            if name not in active_fields:
                continue
            if getattr(new_airco, name) is not None:
                continue
            source = SERVICE_DATA_DERIVED_FROM.get(name)
            if source is not None and getattr(new_airco, source) is not None:
                # The segment arrived but its converted value is not usable.
                continue
            last_response = self._last_service_data_response_by_field.get(name)
            if last_response is None or now - last_response > SERVICE_DATA_MAX_AGE:
                continue
            setattr(new_airco, name, getattr(self._airco, name))

    def _note_service_data_expired(self, now: datetime) -> None:
        """Warn once when all currently active operation data has gone stale."""
        if self._service_data_expired:
            return

        active_fields = self._active_service_data_fields()
        latest_response = max(
            (
                timestamp
                for field, timestamp in self._last_service_data_response_by_field.items()
                if field in active_fields
            ),
            default=None,
        )
        anchor = latest_response or self._last_service_data_request
        if anchor is None or now - anchor <= SERVICE_DATA_MAX_AGE:
            return

        self._service_data_expired = True
        _LOGGER.warning(
            "No operation data from [%s] for over %.0fs; active diagnostic "
            "sensors now report unknown",
            self.device_name,
            SERVICE_DATA_MAX_AGE.total_seconds(),
        )

    async def async_request_home_leave_mode_status(self) -> None:
        """Send STATUS separately and preserve any already queued SET first."""
        pending_write = self._consolidation_task
        if pending_write is not None:
            # Cancellation of the status action must never cancel a user's
            # climate/Home Leave write that was already queued before it.
            await asyncio.shield(pending_write)

        await self.set_airco({AirconCommands.HomeLeaveModeStatusRequest: True})
        # Preserve the immediate coordinator notification the old queued path
        # provided instead of waiting up to one poll interval for UI refresh.
        self.async_set_updated_data(self._airco)

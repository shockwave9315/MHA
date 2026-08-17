"""Fork compatibility shim over the upstream 2026.9.5 RAC parser."""

from typing import Any, cast

from . import rac_parser_upstream as _upstream
from .models.aircon import AirconStat

# Runtime imports used by the integration itself are explicit so mypy can
# validate them. Less common protocol constants used by tests/tools are
# forwarded through __getattr__ below.
SERVICE_DATA_CODES = _upstream.SERVICE_DATA_CODES
SERVICE_DATA_CODE_BY_FIELD = _upstream.SERVICE_DATA_CODE_BY_FIELD
HOME_LEAVE_MODE_READ_MARKER = _upstream.HOME_LEAVE_MODE_READ_MARKER
HOME_LEAVE_MODE_TAG_SIGNED = _upstream.HOME_LEAVE_MODE_TAG_SIGNED


class RacParser(_upstream.RacParser):
    """Keep compatibility with the pre-9.5 all-service-data request flag."""

    @classmethod
    def _variable_trailer(cls, aircon_stat: AirconStat) -> bytearray:
        request = cast(Any, aircon_stat.ServiceDataStatusRequest)
        if request is True:
            # Pre-9.5 ``True`` meant "all known codes" in declaration order.
            # The new tuple path sorts requested codes for deterministic
            # demand-driven requests; keep the legacy flag's byte-for-byte
            # order for compatibility with existing callers/tests.
            return cls._build_trailer(
                [(code, 255, 255, 255) for code in _upstream.SERVICE_DATA_CODES]
            )
        return super()._variable_trailer(aircon_stat)


def __getattr__(name: str) -> Any:
    """Forward upstream protocol constants/helpers not overridden by the fork."""
    return getattr(_upstream, name)

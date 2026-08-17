"""Fork compatibility shim over the upstream 2026.9.5 RAC parser."""

from dataclasses import replace
from typing import Any, cast

from . import rac_parser_upstream as _upstream
from .rac_parser_upstream import *  # noqa: F403
from .models.aircon import AirconStat


class RacParser(_upstream.RacParser):
    """Keep compatibility with the pre-9.5 all-service-data request flag."""

    @classmethod
    def _variable_trailer(cls, aircon_stat: AirconStat) -> bytearray:
        request = cast(Any, aircon_stat.ServiceDataStatusRequest)
        if request is True:
            aircon_stat = replace(
                aircon_stat,
                ServiceDataStatusRequest=tuple(_upstream.SERVICE_DATA_CODES),
            )
        return super()._variable_trailer(aircon_stat)

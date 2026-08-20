"""Fork-specific parser hardening layered on top of the upstream parser."""

from .models.aircon import Aircon
from .rac_parser import (
    HOME_LEAVE_MODE_READ_MARKER,
    HOME_LEAVE_MODE_TAG_SIGNED,
    SERVICE_DATA_CODES,
    RacParser,
)
from .utils import indoorTempList, outdoorTempList


class ForkRacParser(RacParser):
    """Keep fork protocol fixes that are not present upstream yet."""

    def _parse_temperatures(self, ac_device: Aircon, vals: list[int]) -> None:
        """Parse extension segments while preserving signed Home Leave temps.

        ``translate_bytes`` has already converted bytes above 127 to signed
        integers. Home Leave temperature sub-codes 27-30 are signed values and
        must stay signed; only the two airflow sub-codes are unsigned bytes.
        """
        ac_device.Electric = None
        home_leave_mode_raw: dict[int, int] = {}

        for i in range(0, len(vals) - 3, 4):
            if vals[i] == -128:
                if vals[i + 1] == 16:
                    ac_device.OutdoorTemp = outdoorTempList[vals[i + 2] & 0xFF]
                elif vals[i + 1] == 32:
                    ac_device.IndoorTemp = indoorTempList[vals[i + 2] & 0xFF]
                else:
                    self._log_unknown_segment(vals, i)
            elif vals[i] == -108 and vals[i + 1] == 16:
                ac_device.Electric = self._calculate_electric(vals[i + 2:i + 4])
            elif (
                vals[i] == HOME_LEAVE_MODE_TAG_SIGNED
                and vals[i + 1] == HOME_LEAVE_MODE_READ_MARKER
            ):
                sub_code = vals[i + 2] & 0xFF
                raw_value = vals[i + 3]
                home_leave_mode_raw[sub_code] = (
                    raw_value if sub_code in (27, 28, 29, 30) else raw_value & 0xFF
                )
            elif (vals[i] & 0xFF) in SERVICE_DATA_CODES:
                self._apply_service_data_segment(
                    ac_device,
                    vals[i] & 0xFF,
                    vals[i + 1] & 0xFF,
                    vals[i + 2] & 0xFF,
                )
            else:
                self._log_unknown_segment(vals, i)

        self._apply_home_leave_mode(ac_device, home_leave_mode_raw)

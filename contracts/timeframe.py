from __future__ import annotations

from datetime import timedelta
import re


DURATION_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[mhd])$")


class TimeframeError(ValueError):
    pass


def timeframe_to_timedelta(value: str) -> timedelta:
    match = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise TimeframeError(f"Unsupported timeframe: {value}")

    amount = int(match.group("value"))
    if amount <= 0:
        raise TimeframeError(f"Timeframe must be greater than zero: {value}")
    unit = match.group("unit")
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise TimeframeError(f"Unsupported timeframe: {value}")


def horizon_to_steps(timeframe: str, horizon: str) -> int:
    timeframe_delta = timeframe_to_timedelta(timeframe)
    horizon_delta = timeframe_to_timedelta(horizon)
    timeframe_seconds = int(timeframe_delta.total_seconds())
    horizon_seconds = int(horizon_delta.total_seconds())
    if horizon_seconds % timeframe_seconds != 0:
        raise TimeframeError(
            f"Horizon {horizon} is not an integer multiple of timeframe {timeframe}"
        )
    return horizon_seconds // timeframe_seconds

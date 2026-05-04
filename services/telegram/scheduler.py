from __future__ import annotations

from datetime import datetime


class ScheduleError(ValueError):
    pass



def should_run(cron_expression: str, current_time: datetime) -> bool:
    fields = cron_expression.split()
    if len(fields) != 5:
        raise ScheduleError(f"Unsupported cron expression: {cron_expression}")
    minute, hour, day_of_month, month, day_of_week = fields
    cron_day_of_week = (current_time.weekday() + 1) % 7
    minute_match = _matches_field(minute, current_time.minute, 0, 59)
    hour_match = _matches_field(hour, current_time.hour, 0, 23)
    day_of_month_match = _matches_field(day_of_month, current_time.day, 1, 31)
    month_match = _matches_field(month, current_time.month, 1, 12)
    day_of_week_match = _matches_day_of_week(day_of_week, cron_day_of_week)

    if day_of_month != "*" and day_of_week != "*":
        day_match = day_of_month_match or day_of_week_match
    else:
        day_match = day_of_month_match and day_of_week_match

    return minute_match and hour_match and month_match and day_match



def _matches_field(expression: str, value: int, minimum: int, maximum: int) -> bool:
    return value in _expand_expression(expression, minimum, maximum, normalize_sunday=False)



def _matches_day_of_week(expression: str, value: int) -> bool:
    return value in _expand_expression(expression, 0, 7, normalize_sunday=True)



def _expand_expression(expression: str, minimum: int, maximum: int, normalize_sunday: bool) -> set[int]:
    if expression == "*":
        return set(range(minimum, maximum + 1))

    values: set[int] = set()
    for part in expression.split(","):
        part = part.strip()
        if not part:
            raise ScheduleError(f"Unsupported cron field: {expression}")
        if part.startswith("*/"):
            step = int(part[2:])
            if step <= 0:
                raise ScheduleError(f"Unsupported cron field: {expression}")
            values.update(range(minimum, maximum + 1, step))
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = _normalize_value(int(start_text), normalize_sunday)
            end = _normalize_value(int(end_text), normalize_sunday)
            if start > end:
                raise ScheduleError(f"Unsupported cron field: {expression}")
            _validate_bounds(start, minimum, maximum, expression)
            _validate_bounds(end, minimum, maximum, expression)
            values.update(range(start, end + 1))
            continue
        value = _normalize_value(int(part), normalize_sunday)
        _validate_bounds(value, minimum, maximum, expression)
        values.add(value)
    return values



def _normalize_value(value: int, normalize_sunday: bool) -> int:
    if normalize_sunday and value == 7:
        return 0
    return value



def _validate_bounds(value: int, minimum: int, maximum: int, expression: str) -> None:
    if value < minimum or value > maximum:
        raise ScheduleError(f"Unsupported cron field: {expression}")

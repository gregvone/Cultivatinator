"""Weekly wall-clock scheduling with an unambiguous UTC occurrence identity."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_SCHEDULE = {
    "enabled": True,
    "weekday": 6,
    "time": "03:00",
    "timezone": "America/New_York",
    "retention": 12,
}


def validate_schedule(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_SCHEDULE):
        raise ValueError("Supply enabled, weekday, time, timezone and retention")
    if (
        type(value["enabled"]) is not bool
        or type(value["weekday"]) is not int
        or not 0 <= value["weekday"] <= 6
    ):
        raise ValueError("Choose a valid weekday and enabled state")
    clock = value["time"]
    if (
        not isinstance(clock, str)
        or len(clock) != 5
        or clock[2] != ":"
        or not clock.replace(":", "").isdigit()
    ):
        raise ValueError("Time must be HH:MM")
    hour, minute = map(int, clock.split(":"))
    if hour > 23 or minute > 59:
        raise ValueError("Time must be a valid local time")
    if type(value["retention"]) is not int or not 1 <= value["retention"] <= 52:
        raise ValueError("Retention must be between 1 and 52 automatic backups")
    try:
        ZoneInfo(value["timezone"])
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("Choose an installed IANA time zone") from exc
    return dict(value)


def occurrence(day, clock, zone):
    """Fall overlap: first occurrence; spring gap: first valid minute after gap."""
    hour, minute = map(int, clock.split(":"))
    wall = datetime(day.year, day.month, day.day, hour, minute)
    for _ in range(181):
        local = wall.replace(tzinfo=zone, fold=0)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == wall:
            return utc
        wall += timedelta(minutes=1)
    raise ValueError("Could not resolve schedule in this time zone")


def bounds(schedule, now):
    zone = ZoneInfo(schedule["timezone"])
    today = now.astimezone(zone).date()
    day = today - timedelta(days=(today.weekday() - schedule["weekday"]) % 7)
    previous = occurrence(day, schedule["time"], zone)
    if previous > now:
        day -= timedelta(days=7)
        previous = occurrence(day, schedule["time"], zone)
    return previous, occurrence(day + timedelta(days=7), schedule["time"], zone)

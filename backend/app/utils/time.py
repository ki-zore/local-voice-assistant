"""Timezone and time-slot utility functions using zoneinfo."""

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_zone_info(tz_name: str) -> ZoneInfo:
    """Return a ZoneInfo instance for the given timezone name or UTC as fallback."""
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def now_utc() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_in_tz(tz_name: str) -> datetime:
    """Return current timezone-aware datetime in the specified business timezone."""
    tz = get_zone_info(tz_name)
    return datetime.now(tz)


def parse_date_str(date_str: str) -> date:
    """Parse 'YYYY-MM-DD' string into a date object."""
    return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()


def parse_time_str(time_str: str) -> time:
    """Parse 'HH:MM' string into a time object."""
    return datetime.strptime(time_str.strip(), "%H:%M").time()


def build_local_datetime(date_val: date, time_val: time, tz_name: str) -> datetime:
    """Combine date and time with business timezone into an aware datetime."""
    tz = get_zone_info(tz_name)
    return datetime.combine(date_val, time_val).replace(tzinfo=tz)


def local_to_utc(local_dt: datetime) -> datetime:
    """Convert an aware local datetime into an aware UTC datetime."""
    if local_dt.tzinfo is None:
        raise ValueError("local_dt must be timezone-aware")
    return local_dt.astimezone(timezone.utc)


def utc_to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """Convert an aware UTC datetime into the business timezone."""
    if utc_dt.tzinfo is None:
        # If naive, treat as UTC
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    tz = get_zone_info(tz_name)
    return utc_dt.astimezone(tz)


def is_slot_aligned(dt: datetime, slot_minutes: int) -> bool:
    """Check if the datetime falls on a valid slot boundary (e.g. 00, 30 for 30m; 00 for 60m)."""
    if slot_minutes <= 0 or slot_minutes > 1440:
        return False
    return (
        dt.minute % slot_minutes == 0
        and dt.second == 0
        and dt.microsecond == 0
    )


def generate_day_slots(
    open_time_str: str,
    close_time_str: str,
    slot_minutes: int,
) -> List[str]:
    """Generate all valid slot start times (e.g. ['08:00', '09:00', ...]) fitting within open and close."""
    open_t = parse_time_str(open_time_str)
    close_t = parse_time_str(close_time_str)

    open_dt = datetime.combine(date.today(), open_t)
    close_dt = datetime.combine(date.today(), close_t)
    slot_delta = timedelta(minutes=slot_minutes)

    slots: List[str] = []
    current_dt = open_dt

    while current_dt + slot_delta <= close_dt:
        slots.append(current_dt.strftime("%H:%M"))
        current_dt += slot_delta

    return slots


def find_nearest_alternative_slots(
    requested_time_str: str,
    available_slots: List[str],
    max_count: int = 3,
) -> List[str]:
    """Sort available slots by proximity to requested time and return up to max_count."""
    if not available_slots:
        return []

    req_t = parse_time_str(requested_time_str)
    req_mins = req_t.hour * 60 + req_t.minute

    def slot_distance(slot_str: str) -> int:
        slot_t = parse_time_str(slot_str)
        slot_mins = slot_t.hour * 60 + slot_t.minute
        return abs(slot_mins - req_mins)

    sorted_slots = sorted(available_slots, key=slot_distance)
    return sorted_slots[:max_count]

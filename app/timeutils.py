from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Working hours are defined in the clinic's local time; everything is stored in UTC.
CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Convert to UTC. Naive values are treated as UTC (SQLite drops tzinfo)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_clinic_time(value: datetime) -> datetime:
    return as_utc(value).astimezone(CLINIC_TZ)

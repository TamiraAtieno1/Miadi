"""Shared helpers for the HTTP-level tests.

These use the real clock, so slots are computed relative to today: always a
weekday at least a few days ahead (comfortably past the 1-hour notice rule).
"""

from datetime import datetime, timedelta

from app.timeutils import CLINIC_TZ


def future_slot(hour: int = 9, minute: int = 0, min_days: int = 3) -> datetime:
    """A clinic-time slot on a weekday at least `min_days` from today."""
    day = datetime.now(CLINIC_TZ).date() + timedelta(days=min_days)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CLINIC_TZ)


def next_saturday() -> datetime:
    """A Saturday 10:00 clinic-time slot a few days ahead (the doctors are off)."""
    day = datetime.now(CLINIC_TZ).date() + timedelta(days=3)
    while day.weekday() != 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=CLINIC_TZ)


def book(client, start, doctor_id=1, patient_id=1):
    """POST /appointments for the given start time."""
    return client.post(
        "/appointments",
        json={
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "start_time": start.isoformat(),
        },
    )


def starts(response):
    """The slot start times from an availability response."""
    return [datetime.fromisoformat(s["start"]) for s in response.json()["slots"]]

"""Shared helpers for the booking service tests.

Time is injected via `now`, so these tests don't depend on the real clock.
Reference calendar: 2030-01-04 is a Friday, so 7 Jan is a Monday and 5 Jan a
Saturday. The test doctor works Mon-Fri 09:00-17:00 clinic time (EAT).
"""

from datetime import UTC, datetime

from app.services import booking
from app.timeutils import CLINIC_TZ

NOW = datetime(2030, 1, 4, 9, 0, tzinfo=UTC)  # Friday
MON, TUE, SAT = 7, 8, 5


def local(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in January 2030 expressed in clinic time."""
    return datetime(2030, 1, day, hour, minute, tzinfo=CLINIC_TZ)


def book(db, world, start, patient=None, now=NOW):
    """Book `start` for the test doctor (patient one unless given)."""
    return booking.book_appointment(db, world.doctor.id, (patient or world.p1).id, start, now=now)

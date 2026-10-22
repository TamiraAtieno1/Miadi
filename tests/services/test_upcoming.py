"""A patient's upcoming appointments."""

import pytest

from app.errors import (
    NotFoundError,
)
from app.services import availability, booking
from tests.services.helpers import MON, NOW, TUE, book, local


def test_upcoming_are_sorted_and_exclude_cancelled_and_other_patients(db, world):
    later = book(db, world, local(TUE, 10))
    sooner = book(db, world, local(MON, 11))
    cancelled = book(db, world, local(MON, 12))
    booking.cancel_appointment(db, cancelled.id, "x", cancelled.version, now=NOW)
    book(db, world, local(MON, 14), patient=world.p2)

    upcoming = availability.list_upcoming_for_patient(db, world.p1.id, now=NOW)
    assert [a.id for a in upcoming] == [sooner.id, later.id]


def test_upcoming_includes_rescheduled_appointments(db, world):
    moved = book(db, world, local(MON, 9))
    booking.reschedule_appointment(db, moved.id, local(MON, 11), moved.version, now=NOW)

    upcoming = availability.list_upcoming_for_patient(db, world.p1.id, now=NOW)
    assert [a.id for a in upcoming] == [moved.id]


def test_upcoming_excludes_appointments_already_started(db, world):
    book(db, world, local(MON, 9))
    kept = book(db, world, local(MON, 14))

    upcoming = availability.list_upcoming_for_patient(db, world.p1.id, now=local(MON, 9, 30))
    assert [a.id for a in upcoming] == [kept.id]


def test_upcoming_for_unknown_patient(db, world):
    with pytest.raises(NotFoundError):
        availability.list_upcoming_for_patient(db, 999, now=NOW)

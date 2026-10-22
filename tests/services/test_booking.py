"""Booking rules: valid slots, working hours, notice and conflicts."""

from datetime import UTC, datetime, time

import pytest

from app.errors import (
    InvalidSlotError,
    NotFoundError,
    SlotUnavailableError,
)
from app.models import STATUS_BOOKED, Doctor, WorkingHours
from app.services import booking, lookups
from app.timeutils import as_utc
from tests.services.helpers import MON, NOW, SAT, book, local


def test_books_a_valid_slot(db, world):
    appt = book(db, world, local(MON, 9))
    assert appt.status == STATUS_BOOKED
    assert as_utc(appt.start_time) == local(MON, 9).astimezone(UTC)
    assert (as_utc(appt.end_time) - as_utc(appt.start_time)).seconds == 30 * 60


def test_last_slot_of_the_day_is_bookable(db, world):
    book(db, world, local(MON, 16, 30))  # ends exactly at 17:00


@pytest.mark.parametrize("hour,minute", [(9, 15), (9, 45), (10, 1)])
def test_rejects_slots_not_on_the_half_hour(db, world, hour, minute):
    with pytest.raises(InvalidSlotError, match="half hour"):
        book(db, world, local(MON, hour, minute))


def test_rejects_slots_in_the_past(db, world):
    later = datetime(2030, 1, 8, 0, 0, tzinfo=UTC)
    with pytest.raises(InvalidSlotError, match="past"):
        book(db, world, local(MON, 9), now=later)


def test_rejects_slots_within_one_hour(db, world):
    now = local(MON, 8, 30)  # slot is 30 minutes away
    with pytest.raises(InvalidSlotError, match="1 hour"):
        book(db, world, local(MON, 9), now=now)


def test_exactly_one_hour_ahead_is_allowed(db, world):
    now = local(MON, 8, 0)
    book(db, world, local(MON, 9), now=now)


@pytest.mark.parametrize("hour,minute", [(8, 30), (17, 0), (18, 0), (0, 0)])
def test_rejects_slots_outside_working_hours(db, world, hour, minute):
    with pytest.raises(InvalidSlotError, match="working hours"):
        book(db, world, local(MON, hour, minute))


def test_rejects_days_the_doctor_does_not_work(db, world):
    with pytest.raises(InvalidSlotError, match="does not work"):
        book(db, world, local(SAT, 10))


def test_rejects_a_slot_that_is_already_taken(db, world):
    book(db, world, local(MON, 9))
    with pytest.raises(SlotUnavailableError, match="already booked"):
        book(db, world, local(MON, 9), patient=world.p2)


def test_same_time_with_a_different_doctor_is_fine(db, world):
    other = Doctor(name="Dr. Other")
    other.working_hours = [WorkingHours(weekday=0, start_time=time(9, 0), end_time=time(17, 0))]
    db.add(other)
    db.commit()

    book(db, world, local(MON, 9))
    booking.book_appointment(db, other.id, world.p2.id, local(MON, 9), now=NOW)


def test_database_constraint_backs_up_the_application_check(db, world, monkeypatch):
    """Simulate the race: two requests both pass the 'is it free?' check.

    The check is bypassed, so only the partial unique index can stop the
    second insert. The service must turn that into a clean 409-style error.
    """
    start = local(MON, 9)
    book(db, world, start)

    monkeypatch.setattr(booking, "validate_slot", lambda db, doctor_id, start, now: as_utc(start))
    with pytest.raises(SlotUnavailableError, match="just taken"):
        book(db, world, start, patient=world.p2)

    # The session is still usable after the failed insert.
    assert lookups.get_doctor(db, world.doctor.id) is not None


def test_unknown_doctor_or_patient(db, world):
    with pytest.raises(NotFoundError, match="doctor"):
        booking.book_appointment(db, 999, world.p1.id, local(MON, 9), now=NOW)
    with pytest.raises(NotFoundError, match="patient"):
        booking.book_appointment(db, world.doctor.id, 999, local(MON, 9), now=NOW)

"""Unit tests for the booking rules (no HTTP involved).

Time is injected via `now`, so these tests don't depend on the real clock.
Reference calendar: 2030-01-04 is a Friday, so 7 Jan is a Monday and 5 Jan a
Saturday. The test doctor works Mon-Fri 09:00-17:00 clinic time (EAT).
"""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest

from app.errors import (
    InvalidSlotError,
    InvalidStateError,
    NotFoundError,
    SlotUnavailableError,
)
from app.models import STATUS_BOOKED, STATUS_CANCELLED, Doctor, Patient, WorkingHours
from app.services import booking
from app.timeutils import CLINIC_TZ, as_utc

NOW = datetime(2030, 1, 4, 9, 0, tzinfo=UTC)  # Friday
MON, TUE, SAT = 7, 8, 5


def local(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in January 2030 expressed in clinic time."""
    return datetime(2030, 1, day, hour, minute, tzinfo=CLINIC_TZ)


@pytest.fixture()
def world(db):
    doctor = Doctor(name="Dr. Test")
    doctor.working_hours = [
        WorkingHours(weekday=d, start_time=time(9, 0), end_time=time(17, 0)) for d in range(5)
    ]
    one, two = Patient(name="Pat One"), Patient(name="Pat Two")
    db.add_all([doctor, one, two])
    db.commit()
    return SimpleNamespace(doctor=doctor, p1=one, p2=two)


def book(db, world, start, patient=None, now=NOW):
    return booking.book_appointment(db, world.doctor.id, (patient or world.p1).id, start, now=now)


# --- booking ---------------------------------------------------------------


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
    assert booking.get_doctor(db, world.doctor.id) is not None


def test_unknown_doctor_or_patient(db, world):
    with pytest.raises(NotFoundError, match="Doctor"):
        booking.book_appointment(db, 999, world.p1.id, local(MON, 9), now=NOW)
    with pytest.raises(NotFoundError, match="Patient"):
        booking.book_appointment(db, world.doctor.id, 999, local(MON, 9), now=NOW)


# --- cancelling ------------------------------------------------------------


def test_cancel_marks_cancelled_and_frees_the_slot(db, world):
    appt = book(db, world, local(MON, 9))
    cancelled = booking.cancel_appointment(db, appt.id, "Feeling better", now=NOW)

    assert cancelled.status == STATUS_CANCELLED
    assert cancelled.cancel_reason == "Feeling better"
    assert cancelled.cancelled_at is not None

    # Someone else can now take the same slot.
    book(db, world, local(MON, 9), patient=world.p2)


def test_cancelling_twice_is_an_error(db, world):
    appt = book(db, world, local(MON, 9))
    booking.cancel_appointment(db, appt.id, "first", now=NOW)
    with pytest.raises(InvalidStateError, match="already cancelled"):
        booking.cancel_appointment(db, appt.id, "second", now=NOW)


def test_cannot_cancel_an_appointment_that_already_started(db, world):
    appt = book(db, world, local(MON, 9))
    with pytest.raises(InvalidStateError, match="already started"):
        booking.cancel_appointment(db, appt.id, "too late", now=local(MON, 9, 30))


def test_cancel_unknown_appointment(db, world):
    with pytest.raises(NotFoundError):
        booking.cancel_appointment(db, 999, "x", now=NOW)


# --- rescheduling ----------------------------------------------------------


def test_reschedule_moves_the_appointment_and_frees_the_old_slot(db, world):
    appt = book(db, world, local(MON, 9))
    moved = booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)

    assert moved.id == appt.id
    assert as_utc(moved.start_time) == local(MON, 10).astimezone(UTC)
    assert as_utc(moved.end_time) == local(MON, 10, 30).astimezone(UTC)

    # Old slot is available again.
    book(db, world, local(MON, 9), patient=world.p2)


def test_reschedule_to_a_taken_slot_leaves_the_original_untouched(db, world):
    mine = book(db, world, local(MON, 9))
    book(db, world, local(MON, 10), patient=world.p2)

    with pytest.raises(SlotUnavailableError):
        booking.reschedule_appointment(db, mine.id, local(MON, 10), now=NOW)

    db.refresh(mine)
    assert as_utc(mine.start_time) == local(MON, 9).astimezone(UTC)
    assert mine.status == STATUS_BOOKED


def test_reschedule_validates_like_a_fresh_booking(db, world):
    appt = book(db, world, local(MON, 9))
    for bad in (local(MON, 9, 15), local(MON, 18), local(SAT, 10)):
        with pytest.raises(InvalidSlotError):
            booking.reschedule_appointment(db, appt.id, bad, now=NOW)

    db.refresh(appt)
    assert as_utc(appt.start_time) == local(MON, 9).astimezone(UTC)


def test_cannot_reschedule_a_cancelled_appointment(db, world):
    appt = book(db, world, local(MON, 9))
    booking.cancel_appointment(db, appt.id, "x", now=NOW)
    with pytest.raises(InvalidStateError, match="cancelled"):
        booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)


def test_rescheduling_to_the_same_slot_is_rejected(db, world):
    appt = book(db, world, local(MON, 9))
    with pytest.raises(SlotUnavailableError, match="already at that time"):
        booking.reschedule_appointment(db, appt.id, local(MON, 9), now=NOW)


def test_reschedule_unknown_appointment(db, world):
    with pytest.raises(NotFoundError):
        booking.reschedule_appointment(db, 999, local(MON, 10), now=NOW)


def test_cannot_reschedule_an_appointment_that_already_started(db, world):
    appt = book(db, world, local(MON, 9))
    with pytest.raises(InvalidStateError, match="already started"):
        booking.reschedule_appointment(db, appt.id, local(MON, 10), now=local(MON, 9, 30))


def test_reschedule_race_is_caught_by_the_database_constraint(db, world, monkeypatch):
    """Two clients move into the same free slot at once.

    The 'is it free?' check is bypassed to simulate both passing it; only the
    partial unique index can stop the second one. The service must report a
    clean conflict and leave the original booking untouched.
    """
    mine = book(db, world, local(MON, 9))
    book(db, world, local(MON, 10), patient=world.p2)

    monkeypatch.setattr(booking, "validate_slot", lambda db, doctor_id, start, now: as_utc(start))
    with pytest.raises(SlotUnavailableError, match="just taken"):
        booking.reschedule_appointment(db, mine.id, local(MON, 10), now=NOW)

    db.refresh(mine)
    assert as_utc(mine.start_time) == local(MON, 9).astimezone(UTC)
    assert mine.status == STATUS_BOOKED


# --- availability ----------------------------------------------------------


def test_full_day_has_sixteen_slots(db, world):
    slots = booking.get_availability(db, world.doctor.id, date(2030, 1, 7), now=NOW)
    assert len(slots) == 16
    assert slots[0][0] == local(MON, 9)
    assert slots[-1][0] == local(MON, 16, 30)
    assert slots[-1][1] == local(MON, 17)


def test_booked_slot_is_removed_and_returns_after_cancelling(db, world):
    appt = book(db, world, local(MON, 10))

    slots = booking.get_availability(db, world.doctor.id, date(2030, 1, 7), now=NOW)
    assert len(slots) == 15
    assert local(MON, 10) not in [start for start, _ in slots]

    booking.cancel_appointment(db, appt.id, "x", now=NOW)
    slots = booking.get_availability(db, world.doctor.id, date(2030, 1, 7), now=NOW)
    assert len(slots) == 16


def test_availability_hides_slots_that_can_no_longer_be_booked(db, world):
    now = local(MON, 10, 15)  # bookable from 11:15 -> first slot is 11:30
    slots = booking.get_availability(db, world.doctor.id, date(2030, 1, 7), now=now)
    assert slots[0][0] == local(MON, 11, 30)
    assert len(slots) == 11


def test_no_slots_on_a_day_off(db, world):
    assert booking.get_availability(db, world.doctor.id, date(2030, 1, 5), now=NOW) == []


def test_availability_for_unknown_doctor(db, world):
    with pytest.raises(NotFoundError):
        booking.get_availability(db, 999, date(2030, 1, 7), now=NOW)


# --- a patient's upcoming appointments -------------------------------------


def test_upcoming_are_sorted_and_exclude_cancelled_and_other_patients(db, world):
    later = book(db, world, local(TUE, 10))
    sooner = book(db, world, local(MON, 11))
    cancelled = book(db, world, local(MON, 12))
    booking.cancel_appointment(db, cancelled.id, "x", now=NOW)
    book(db, world, local(MON, 14), patient=world.p2)

    upcoming = booking.list_upcoming_for_patient(db, world.p1.id, now=NOW)
    assert [a.id for a in upcoming] == [sooner.id, later.id]


def test_upcoming_excludes_appointments_already_started(db, world):
    book(db, world, local(MON, 9))
    kept = book(db, world, local(MON, 14))

    upcoming = booking.list_upcoming_for_patient(db, world.p1.id, now=local(MON, 9, 30))
    assert [a.id for a in upcoming] == [kept.id]


def test_upcoming_for_unknown_patient(db, world):
    with pytest.raises(NotFoundError):
        booking.list_upcoming_for_patient(db, 999, now=NOW)

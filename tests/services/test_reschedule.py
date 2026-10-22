"""Rescheduling appointments."""

from datetime import UTC

import pytest

from app.errors import (
    InvalidSlotError,
    InvalidStateError,
    NotFoundError,
    SlotUnavailableError,
)
from app.models import STATUS_BOOKED, STATUS_CANCELLED, STATUS_RESCHEDULED
from app.services import booking
from app.timeutils import as_utc
from tests.services.helpers import MON, NOW, SAT, book, local


def test_reschedule_moves_the_appointment_and_frees_the_old_slot(db, world):
    appt = book(db, world, local(MON, 9))
    moved = booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)

    assert moved.id == appt.id
    assert as_utc(moved.start_time) == local(MON, 10).astimezone(UTC)
    assert as_utc(moved.end_time) == local(MON, 10, 30).astimezone(UTC)

    assert moved.status == STATUS_RESCHEDULED

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


def test_a_rescheduled_appointment_still_holds_its_new_slot(db, world):
    appt = book(db, world, local(MON, 9))
    booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)

    with pytest.raises(SlotUnavailableError, match="already booked"):
        book(db, world, local(MON, 10), patient=world.p2)


def test_a_rescheduled_appointment_can_be_rescheduled_again(db, world):
    appt = book(db, world, local(MON, 9))
    booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)
    again = booking.reschedule_appointment(db, appt.id, local(MON, 11), now=NOW)

    assert again.status == STATUS_RESCHEDULED
    assert as_utc(again.start_time) == local(MON, 11).astimezone(UTC)


def test_a_rescheduled_appointment_can_be_cancelled_and_frees_the_slot(db, world):
    appt = book(db, world, local(MON, 9))
    booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)
    cancelled = booking.cancel_appointment(db, appt.id, "Changed my mind", now=NOW)

    assert cancelled.status == STATUS_CANCELLED
    book(db, world, local(MON, 10), patient=world.p2)  # the slot is free again

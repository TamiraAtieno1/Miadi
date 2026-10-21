"""Cancelling appointments."""

import pytest

from app.errors import (
    InvalidStateError,
    NotFoundError,
)
from app.models import STATUS_CANCELLED
from app.services import booking
from tests.services.helpers import MON, NOW, book, local


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

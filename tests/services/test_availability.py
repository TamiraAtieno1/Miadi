"""Availability: which slots are still free."""

from datetime import date

import pytest

from app.errors import (
    NotFoundError,
)
from app.services import booking
from tests.services.helpers import MON, NOW, book, local


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

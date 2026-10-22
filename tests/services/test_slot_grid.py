"""Availability and booking must agree, even when working hours are off the 30-minute grid."""

from datetime import date, time

import pytest

from app.errors import InvalidSlotError
from app.models import Doctor, Patient, WorkingHours
from app.services import availability, booking
from app.services.slots import first_slot_start
from tests.services.helpers import MON, NOW, local


def doctor_with_hours(db, start: time, end: time) -> tuple[Doctor, Patient]:
    doctor = Doctor(name="Dr. Odd Hours")
    doctor.working_hours = [WorkingHours(weekday=0, start_time=start, end_time=end)]
    patient = Patient(name="Pat Grid")
    db.add_all([doctor, patient])
    db.commit()
    return doctor, patient


@pytest.mark.parametrize(
    ("opening", "expected"),
    [
        (time(9, 0), time(9, 0)),
        (time(9, 15), time(9, 30)),
        (time(9, 30), time(9, 30)),
        (time(9, 31), time(10, 0)),
        (time(9, 45), time(10, 0)),
        (time(8, 0, 1), time(8, 30)),
        (time(0, 0), time(0, 0)),
    ],
)
def test_first_slot_start_rounds_up_to_the_grid(opening, expected):
    assert first_slot_start(
        local(MON, opening.hour, opening.minute).replace(second=opening.second)
    ).timetz() == (local(MON, expected.hour, expected.minute).timetz())


def test_opening_at_09_15_first_offers_09_30(db):
    doctor, _ = doctor_with_hours(db, time(9, 15), time(12, 0))
    slots = availability.get_availability(db, doctor.id, date(2030, 1, 7), now=NOW)
    assert [start for start, _ in slots] == [
        local(MON, 9, 30),
        local(MON, 10),
        local(MON, 10, 30),
        local(MON, 11),
        local(MON, 11, 30),
    ]


def test_a_closing_time_off_the_grid_drops_the_partial_slot(db):
    doctor, _ = doctor_with_hours(db, time(9, 0), time(10, 10))
    slots = availability.get_availability(db, doctor.id, date(2030, 1, 7), now=NOW)
    assert [start for start, _ in slots] == [local(MON, 9), local(MON, 9, 30)]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [(time(9, 15), time(12, 10)), (time(8, 50), time(11, 40))],
)
def test_every_offered_slot_can_be_booked(db, opening, closing):
    """The promise: availability only lists times that booking accepts."""
    doctor, patient = doctor_with_hours(db, opening, closing)
    slots = availability.get_availability(db, doctor.id, date(2030, 1, 7), now=NOW)
    assert slots  # the doctor is not a no-show for the whole day
    for start, _ in slots:
        booking.book_appointment(db, doctor.id, patient.id, start, now=NOW)


def test_the_time_before_the_first_grid_slot_is_not_bookable(db):
    doctor, patient = doctor_with_hours(db, time(9, 15), time(12, 0))
    with pytest.raises(InvalidSlotError):
        booking.book_appointment(db, doctor.id, patient.id, local(MON, 9), now=NOW)


def test_a_doctor_with_no_whole_slot_in_their_hours_has_none_free(db):
    doctor, _ = doctor_with_hours(db, time(9, 10), time(9, 50))  # grid slots: 09:30 ends 10:00
    assert availability.get_availability(db, doctor.id, date(2030, 1, 7), now=NOW) == []

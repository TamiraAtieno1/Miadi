from datetime import timedelta

from app.models import STATUS_CANCELLED, Appointment
from app.services import schedule
from app.services.booking import cancel_appointment
from tests.services.helpers import MON, NOW, TUE, book, local

WED, THU = 9, 10


def test_patient_appointments_split_into_upcoming_and_history(db, world):
    soon = book(db, world, local(MON, 9))
    later = book(db, world, local(TUE, 9))
    cancelled = book(db, world, local(WED, 9))
    cancel_appointment(db, cancelled.id, "Changed plans", now=NOW)
    past = Appointment(
        doctor_id=world.doctor.id,
        patient_id=world.p1.id,
        start_time=NOW - timedelta(days=2),
        end_time=NOW - timedelta(days=2) + timedelta(minutes=30),
        status="booked",
    )
    db.add(past)
    db.commit()

    upcoming, history = schedule.patient_appointments(db, world.p1.id, now=NOW)

    assert [a.id for a in upcoming] == [soon.id, later.id]
    assert [a.id for a in history] == [cancelled.id, past.id]  # most recent first
    assert history[0].status == STATUS_CANCELLED


def test_doctor_appointments_lists_only_upcoming_active_ones(db, world):
    keep = book(db, world, local(MON, 10))
    gone = book(db, world, local(MON, 11))
    cancel_appointment(db, gone.id, "Unwell", now=NOW)

    assert [a.id for a in schedule.doctor_appointments(db, world.doctor.id, now=NOW)] == [keep.id]


def test_all_appointments_can_be_filtered_by_status(db, world):
    first = book(db, world, local(MON, 9))
    second = book(db, world, local(TUE, 9))
    cancel_appointment(db, second.id, "Unwell", now=NOW)

    assert [a.id for a in schedule.all_appointments(db)] == [second.id, first.id]  # latest first
    assert [a.id for a in schedule.all_appointments(db, STATUS_CANCELLED)] == [second.id]


def test_appointment_counts(db, world):
    book(db, world, local(MON, 9))
    gone = book(db, world, local(TUE, 9))
    cancel_appointment(db, gone.id, "Unwell", now=NOW)

    assert schedule.appointment_counts(db, now=NOW) == {"upcoming": 1, "cancelled": 1, "total": 2}

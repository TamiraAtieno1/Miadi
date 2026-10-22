"""The database itself refuses data that breaks a business rule, even if the app code is bypassed.

These run on whichever database the tests use (SQLite locally, PostgreSQL in CI).
"""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Appointment, Doctor, Patient, User, WorkingHours

START = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


@pytest.fixture()
def people(db):
    doctor = Doctor(name="Dr. Rule", email="rule@example.com")
    patient = Patient(name="Pat Rule", email="pat@example.com")
    db.add_all([doctor, patient])
    db.commit()
    return doctor, patient


def refuses(db, *rows):
    """Adding these rows must fail, and the session must be usable afterwards."""
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def appointment(people, **overrides):
    doctor, patient = people
    fields = {
        "doctor_id": doctor.id,
        "patient_id": patient.id,
        "start_time": START,
        "end_time": START + timedelta(minutes=30),
        "status": "booked",
    }
    return Appointment(**{**fields, **overrides})


@pytest.mark.parametrize("status", ["booked", "rescheduled", "cancelled"])
def test_known_statuses_are_accepted(db, people, status):
    db.add(appointment(people, status=status))
    db.commit()


@pytest.mark.parametrize("status", ["pending", "Booked", "", "done"])
def test_unknown_statuses_are_refused(db, people, status):
    refuses(db, appointment(people, status=status))


@pytest.mark.parametrize("minutes", [0, 15, 29, 31, 45, 60, -30])
def test_only_thirty_minute_appointments_are_accepted(db, people, minutes):
    refuses(db, appointment(people, end_time=START + timedelta(minutes=minutes)))


def test_a_thirty_minute_appointment_is_accepted(db, people):
    db.add(appointment(people))
    db.commit()


@pytest.mark.parametrize("weekday", [-1, 7, 12])
def test_weekdays_outside_monday_to_sunday_are_refused(db, people, weekday):
    doctor, _ = people
    refuses(
        db,
        WorkingHours(doctor_id=doctor.id, weekday=weekday, start_time=time(9), end_time=time(17)),
    )


@pytest.mark.parametrize(("start", "end"), [(time(17), time(9)), (time(9), time(9))])
def test_working_hours_must_end_after_they_start(db, people, start, end):
    doctor, _ = people
    refuses(db, WorkingHours(doctor_id=doctor.id, weekday=1, start_time=start, end_time=end))


def test_valid_working_hours_are_accepted(db, people):
    doctor, _ = people
    db.add(WorkingHours(doctor_id=doctor.id, weekday=6, start_time=time(9), end_time=time(17)))
    db.commit()


def test_two_doctors_cannot_share_an_email(db, people):
    refuses(db, Doctor(name="Dr. Copy", email="rule@example.com"))


def test_a_doctor_needs_an_email(db):
    refuses(db, Doctor(name="Dr. Nobody", email=None))


def test_two_patients_cannot_share_an_email(db, people):
    refuses(db, Patient(name="Copy", email="pat@example.com"))


def test_patients_without_an_email_do_not_clash(db, people):
    db.add_all([Patient(name="One"), Patient(name="Two", email=None)])
    db.commit()


@pytest.mark.parametrize(
    ("role", "doctor", "patient"),
    [("admin", False, False), ("doctor", True, False), ("patient", False, True)],
)
def test_a_login_matching_its_role_is_accepted(db, people, role, doctor, patient):
    d, p = people
    db.add(
        User(
            email=f"{role}@example.com",
            password_hash="h",
            role=role,
            doctor_id=d.id if doctor else None,
            patient_id=p.id if patient else None,
        )
    )
    db.commit()


@pytest.mark.parametrize(
    ("role", "doctor", "patient"),
    [
        ("admin", True, False),
        ("admin", False, True),
        ("doctor", False, False),
        ("doctor", False, True),
        ("doctor", True, True),
        ("patient", False, False),
        ("patient", True, False),
        ("owner", False, False),
    ],
)
def test_a_login_that_does_not_match_its_role_is_refused(db, people, role, doctor, patient):
    d, p = people
    refuses(
        db,
        User(
            email="odd@example.com",
            password_hash="h",
            role=role,
            doctor_id=d.id if doctor else None,
            patient_id=p.id if patient else None,
        ),
    )

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import STATUS_BOOKED, STATUS_CANCELLED, Appointment, Doctor, Patient

# 09:00 EAT (06:00 UTC) on a Monday.
SLOT = datetime(2030, 1, 7, 6, 0, tzinfo=timezone.utc)


def _make_people(db):
    doctor = Doctor(name="Dr. Test")
    patient = Patient(name="Pat Test")
    db.add_all([doctor, patient])
    db.commit()
    return doctor, patient


def _appt(doctor, patient, status=STATUS_BOOKED):
    return Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_time=SLOT,
        end_time=SLOT + timedelta(minutes=30),
        status=status,
    )


def test_database_rejects_double_booking(db):
    doctor, patient = _make_people(db)
    db.add(_appt(doctor, patient))
    db.commit()

    db.add(_appt(doctor, patient))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cancelled_slot_can_be_booked_again(db):
    doctor, patient = _make_people(db)
    db.add(_appt(doctor, patient, status=STATUS_CANCELLED))
    db.commit()

    db.add(_appt(doctor, patient, status=STATUS_BOOKED))
    db.commit()  # must not raise


def test_many_cancelled_rows_may_share_a_slot(db):
    doctor, patient = _make_people(db)
    db.add_all(
        [
            _appt(doctor, patient, status=STATUS_CANCELLED),
            _appt(doctor, patient, status=STATUS_CANCELLED),
        ]
    )
    db.commit()  # must not raise

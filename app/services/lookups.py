"""Looking things up: each function returns the row or raises `NotFoundError`.

These are the database checks the other services build on.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import (
    NotFoundError,
)
from app.models import (
    Appointment,
    Doctor,
    Patient,
    WorkingHours,
)


def get_doctor(db: Session, doctor_id: int) -> Doctor:
    """Return the doctor or raise `NotFoundError`."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise NotFoundError(f"We couldn't find a doctor with ID {doctor_id}.")
    return doctor


def get_patient(db: Session, patient_id: int) -> Patient:
    """Return the patient or raise `NotFoundError`."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"We couldn't find a patient with ID {patient_id}.")
    return patient


def get_appointment(db: Session, appointment_id: int) -> Appointment:
    """Return the appointment or raise `NotFoundError`."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFoundError(f"We couldn't find an appointment with ID {appointment_id}.")
    return appointment


def get_working_hours(db: Session, doctor_id: int, weekday: int) -> WorkingHours | None:
    """The doctor's working hours for a weekday (0 = Monday), or None if they are off."""
    return db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id, WorkingHours.weekday == weekday
        )
    )

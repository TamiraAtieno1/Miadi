"""Booking commands: book, cancel and reschedule an appointment.

Everything about *whether* a slot may be booked lives in `slots.py`, so it can
be tested without HTTP. These functions change the database.
"""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import (
    InvalidStateError,
    SlotUnavailableError,
)
from app.models import (
    STATUS_BOOKED,
    STATUS_CANCELLED,
    Appointment,
)
from app.services.lookups import get_appointment, get_doctor, get_patient
from app.services.slots import SLOT_LENGTH, validate_slot
from app.timeutils import as_utc, utcnow


def book_appointment(
    db: Session,
    doctor_id: int,
    patient_id: int,
    start_time: datetime,
    now: datetime | None = None,
) -> Appointment:
    """Book a slot for a patient.

    Raises `NotFoundError` for an unknown doctor or patient, `InvalidSlotError`
    for a slot that is not bookable and `SlotUnavailableError` if it is taken,
    including when another request wins a race for the same slot.
    """
    now = now or utcnow()
    get_doctor(db, doctor_id)
    get_patient(db, patient_id)
    start_utc = validate_slot(db, doctor_id, start_time, now)

    appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_time=start_utc,
        end_time=start_utc + SLOT_LENGTH,
        status=STATUS_BOOKED,
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError as error:
        # Two requests passed the check at the same moment; the partial unique
        # index let exactly one through.
        db.rollback()
        raise SlotUnavailableError(
            "Sorry, that slot was just taken by someone else. Please choose another time."
        ) from error
    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session, appointment_id: int, reason: str, now: datetime | None = None
) -> Appointment:
    """Cancel an appointment (soft delete), which frees its slot.

    Raises `InvalidStateError` if it is already cancelled or has already started.
    """
    now = now or utcnow()
    appointment = get_appointment(db, appointment_id)

    if appointment.status == STATUS_CANCELLED:
        raise InvalidStateError("This appointment is already cancelled.")
    if as_utc(appointment.start_time) <= now:
        raise InvalidStateError(
            "This appointment has already started, so it can no longer be cancelled."
        )

    appointment.status = STATUS_CANCELLED
    appointment.cancel_reason = reason
    appointment.cancelled_at = now
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session,
    appointment_id: int,
    new_start: datetime,
    now: datetime | None = None,
) -> Appointment:
    """Move an appointment to a new slot with the same doctor.

    The new slot gets exactly the validation a fresh booking gets. It is one
    transaction: if the new slot is invalid or taken, nothing changes and the
    original booking stays in place. Updating the row (rather than cancelling
    and re-creating) frees the old slot automatically.
    """
    now = now or utcnow()
    appointment = get_appointment(db, appointment_id)

    if appointment.status == STATUS_CANCELLED:
        raise InvalidStateError(
            "A cancelled appointment can't be rescheduled. Please book a new slot instead."
        )
    if as_utc(appointment.start_time) <= now:
        raise InvalidStateError(
            "This appointment has already started, so it can no longer be rescheduled."
        )
    if as_utc(new_start) == as_utc(appointment.start_time):
        raise SlotUnavailableError(
            "The appointment is already at that time. Please choose a different time."
        )

    new_start_utc = validate_slot(db, appointment.doctor_id, new_start, now)

    appointment.start_time = new_start_utc
    appointment.end_time = new_start_utc + SLOT_LENGTH
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise SlotUnavailableError(
            "Sorry, that slot was just taken by someone else. Please choose another time."
        ) from error
    db.refresh(appointment)
    return appointment

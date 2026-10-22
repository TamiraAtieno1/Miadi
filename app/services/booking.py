"""Booking commands: book, cancel and reschedule an appointment.

Everything about *whether* a slot may be booked lives in `slots.py`, so it can
be tested without HTTP. These functions change the database.
"""

from datetime import datetime
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.errors import (
    ConcurrentChangeError,
    InvalidStateError,
    SlotUnavailableError,
)
from app.models import (
    STATUS_BOOKED,
    STATUS_CANCELLED,
    STATUS_RESCHEDULED,
    Appointment,
)
from app.services.lookups import get_appointment, get_doctor, get_patient
from app.services.slots import SLOT_LENGTH, validate_slot
from app.timeutils import as_utc, utcnow

SLOT_INDEX = "uq_active_slot"
# SQLite does not name the index in its error, only the columns it covers.
SQLITE_SLOT_COLUMNS = "appointments.doctor_id, appointments.start_time"


def is_slot_conflict(error: IntegrityError) -> bool:
    """True only when the error is the "one active appointment per doctor per time" index."""
    diagnostics = getattr(error.orig, "diag", None)  # PostgreSQL names the violated index
    if diagnostics is not None:
        return diagnostics.constraint_name == SLOT_INDEX
    return SQLITE_SLOT_COLUMNS in str(error.orig)


def _report_integrity_error(db: Session, error: IntegrityError) -> NoReturn:
    """Roll back, then explain the failure.

    A clash on the active-slot index means someone else got the slot first. Any other
    integrity failure (a missing doctor, a check constraint) is a different problem, so
    it is raised unchanged rather than blamed on a taken slot.
    """
    db.rollback()
    if is_slot_conflict(error):
        raise SlotUnavailableError(
            "Sorry, that slot was just taken by someone else. Please choose another time."
        ) from error
    raise error


def _commit_or_report_concurrent_change(db: Session) -> None:
    """Commit, turning "someone else changed this row first" into a clean 409.

    The appointment row carries a version number. Our UPDATE only matches if the
    version is still the one we read; otherwise another request got there first.
    """
    try:
        db.commit()
    except StaleDataError as error:
        db.rollback()
        raise ConcurrentChangeError(
            "Someone else just changed this appointment. Please reload it and try again."
        ) from error


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
        _report_integrity_error(db, error)
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
    _commit_or_report_concurrent_change(db)
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
    appointment.status = STATUS_RESCHEDULED
    try:
        _commit_or_report_concurrent_change(db)
    except IntegrityError as error:
        _report_integrity_error(db, error)
    db.refresh(appointment)
    return appointment

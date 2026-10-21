"""Booking rules.

Everything about *whether* a slot may be booked lives here, so it can be tested
without HTTP. The database enforces the final guarantee (the partial unique
index on active appointments); the checks here give friendly errors first.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import (
    InvalidSlotError,
    InvalidStateError,
    NotFoundError,
    SlotUnavailableError,
)
from app.models import (
    STATUS_BOOKED,
    STATUS_CANCELLED,
    Appointment,
    Doctor,
    Patient,
    WorkingHours,
)
from app.timeutils import CLINIC_TZ, as_utc, utcnow

SLOT_LENGTH = timedelta(minutes=30)
MIN_NOTICE = timedelta(hours=1)


# --- lookups ---------------------------------------------------------------


def get_doctor(db: Session, doctor_id: int) -> Doctor:
    """Return the doctor or raise `NotFoundError`."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise NotFoundError(f"Doctor {doctor_id} not found.")
    return doctor


def get_patient(db: Session, patient_id: int) -> Patient:
    """Return the patient or raise `NotFoundError`."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found.")
    return patient


def get_appointment(db: Session, appointment_id: int) -> Appointment:
    """Return the appointment or raise `NotFoundError`."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFoundError(f"Appointment {appointment_id} not found.")
    return appointment


def _working_hours(db: Session, doctor_id: int, weekday: int) -> WorkingHours | None:
    """The doctor's working hours for a weekday (0 = Monday), or None if they are off."""
    return db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id, WorkingHours.weekday == weekday
        )
    )


# --- validation ------------------------------------------------------------


def validate_slot(db: Session, doctor_id: int, start: datetime, now: datetime) -> datetime:
    """Check that `start` is a bookable slot for the doctor. Returns it in UTC."""
    start_utc = as_utc(start)
    local = start_utc.astimezone(CLINIC_TZ)

    if local.minute not in (0, 30) or local.second or local.microsecond:
        raise InvalidSlotError("Appointments start on the hour or half hour (e.g. 09:00 or 09:30).")

    if start_utc < now:
        raise InvalidSlotError("Cannot book a slot in the past.")
    if start_utc < now + MIN_NOTICE:
        raise InvalidSlotError("Appointments must be booked at least 1 hour in advance.")

    hours = _working_hours(db, doctor_id, local.weekday())
    if hours is None:
        raise InvalidSlotError(f"The doctor does not work on {local:%A}s.")

    local_end = local + SLOT_LENGTH
    inside_hours = (
        hours.start_time <= local.time()
        and local_end.date() == local.date()
        and local_end.time() <= hours.end_time
    )
    if not inside_hours:
        raise InvalidSlotError(
            f"Slot is outside the doctor's working hours on {local:%A} "
            f"({hours.start_time:%H:%M}-{hours.end_time:%H:%M})."
        )

    taken = db.scalar(
        select(Appointment.id).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time == start_utc,
            Appointment.status == STATUS_BOOKED,
        )
    )
    if taken is not None:
        raise SlotUnavailableError("That slot is already booked.")

    return start_utc


# --- commands --------------------------------------------------------------


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
        raise SlotUnavailableError("That slot was just taken by someone else.") from error
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
        raise InvalidStateError("Appointment is already cancelled.")
    if as_utc(appointment.start_time) <= now:
        raise InvalidStateError("Cannot cancel an appointment that has already started.")

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
        raise InvalidStateError("Cannot reschedule a cancelled appointment.")
    if as_utc(appointment.start_time) <= now:
        raise InvalidStateError("Cannot reschedule an appointment that has already started.")
    if as_utc(new_start) == as_utc(appointment.start_time):
        raise SlotUnavailableError("The appointment is already at that time.")

    new_start_utc = validate_slot(db, appointment.doctor_id, new_start, now)

    appointment.start_time = new_start_utc
    appointment.end_time = new_start_utc + SLOT_LENGTH
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise SlotUnavailableError("That slot was just taken by someone else.") from error
    db.refresh(appointment)
    return appointment


# --- queries ---------------------------------------------------------------


def get_availability(
    db: Session, doctor_id: int, day: date, now: datetime | None = None
) -> list[tuple[datetime, datetime]]:
    """Free 30-minute slots for a doctor on a clinic-local calendar date.

    Slots are computed from working hours minus booked appointments (nothing is
    pre-generated). Slots a patient could not book right now (past, or inside
    the 1-hour notice window) are left out so the list only contains slots that
    POST /appointments would accept.
    """
    now = now or utcnow()
    get_doctor(db, doctor_id)

    hours = _working_hours(db, doctor_id, day.weekday())
    if hours is None:
        return []

    day_start = datetime.combine(day, time.min, tzinfo=CLINIC_TZ).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    booked = {
        as_utc(start)
        for start in db.scalars(
            select(Appointment.start_time).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == STATUS_BOOKED,
                Appointment.start_time >= day_start,
                Appointment.start_time < day_end,
            )
        )
    }

    earliest = now + MIN_NOTICE
    current = datetime.combine(day, hours.start_time, tzinfo=CLINIC_TZ)
    closing = datetime.combine(day, hours.end_time, tzinfo=CLINIC_TZ)

    slots: list[tuple[datetime, datetime]] = []
    while current + SLOT_LENGTH <= closing:
        current_utc = current.astimezone(UTC)
        if current_utc >= earliest and current_utc not in booked:
            slots.append((current, current + SLOT_LENGTH))
        current += SLOT_LENGTH
    return slots


def list_upcoming_for_patient(
    db: Session, patient_id: int, now: datetime | None = None
) -> list[Appointment]:
    """Booked appointments that haven't started yet, soonest first."""
    now = now or utcnow()
    get_patient(db, patient_id)
    return list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == STATUS_BOOKED,
                Appointment.start_time >= now,
            )
            .order_by(Appointment.start_time)
        )
    )

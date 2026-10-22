"""Read-only queries: free slots for a doctor and a patient's upcoming appointments."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ACTIVE_STATUSES,
    Appointment,
)
from app.services.lookups import get_doctor, get_patient, get_working_hours
from app.services.slots import MIN_NOTICE, SLOT_LENGTH, first_slot_start
from app.timeutils import CLINIC_TZ, as_utc, utcnow


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

    hours = get_working_hours(db, doctor_id, day.weekday())
    if hours is None:
        return []

    day_start = datetime.combine(day, time.min, tzinfo=CLINIC_TZ).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    booked = {
        as_utc(start)
        for start in db.scalars(
            select(Appointment.start_time).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.start_time >= day_start,
                Appointment.start_time < day_end,
            )
        )
    }

    earliest = now + MIN_NOTICE
    current = first_slot_start(datetime.combine(day, hours.start_time, tzinfo=CLINIC_TZ))
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
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.start_time >= now,
            )
            .order_by(Appointment.start_time)
        )
    )

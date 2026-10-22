"""Appointment lists for the web pages: one patient, one doctor, or everyone."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import ACTIVE_STATUSES, STATUS_CANCELLED, Appointment
from app.timeutils import as_utc, utcnow


def _with_people():
    """Load the doctor and patient together with each appointment."""
    return (joinedload(Appointment.doctor), joinedload(Appointment.patient))


def patient_appointments(
    db: Session, patient_id: int, now: datetime | None = None
) -> tuple[list[Appointment], list[Appointment]]:
    """A patient's appointments as (upcoming, history).

    Upcoming ones are active and have not started, soonest first. Everything
    else (cancelled or already past) is history, most recent first.
    """
    now = now or utcnow()
    rows = db.scalars(
        select(Appointment)
        .options(*_with_people())
        .where(Appointment.patient_id == patient_id)
        .order_by(Appointment.start_time)
    ).all()
    upcoming = [a for a in rows if a.status in ACTIVE_STATUSES and as_utc(a.start_time) >= now]
    history = [a for a in reversed(rows) if a not in upcoming]
    return upcoming, history


def doctor_appointments(
    db: Session, doctor_id: int, now: datetime | None = None
) -> list[Appointment]:
    """A doctor's active appointments that have not started yet, soonest first."""
    now = now or utcnow()
    return list(
        db.scalars(
            select(Appointment)
            .options(*_with_people())
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.start_time >= now,
            )
            .order_by(Appointment.start_time)
        )
    )


def all_appointments(db: Session, status: str | None = None, limit: int = 200) -> list[Appointment]:
    """Every appointment, latest start first, optionally only one status."""
    query = select(Appointment).options(*_with_people())
    if status:
        query = query.where(Appointment.status == status)
    return list(db.scalars(query.order_by(Appointment.start_time.desc()).limit(limit)))


def appointment_counts(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Headline numbers for the admin page."""
    now = now or utcnow()

    def count(*conditions) -> int:
        return db.scalar(select(func.count(Appointment.id)).where(*conditions)) or 0

    return {
        "upcoming": count(Appointment.status.in_(ACTIVE_STATUSES), Appointment.start_time >= now),
        "cancelled": count(Appointment.status == STATUS_CANCELLED),
        "total": count(),
    }

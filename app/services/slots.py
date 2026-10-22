"""Slot validation: is this a time a patient may book?

The checks here give friendly errors first. The database still has the final
say through the partial unique index on active appointments.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import (
    InvalidSlotError,
    SlotUnavailableError,
)
from app.models import (
    ACTIVE_STATUSES,
    Appointment,
)
from app.services.lookups import get_working_hours
from app.timeutils import CLINIC_TZ, as_utc

SLOT_LENGTH = timedelta(minutes=30)
MIN_NOTICE = timedelta(hours=1)


def first_slot_start(opening: datetime) -> datetime:
    """The first bookable start at or after a doctor's opening time.

    Bookings only start on the hour or half hour. If a doctor opens at 09:15 their
    first slot is 09:30, so availability never offers a time that booking would refuse.
    """
    midnight = opening.replace(hour=0, minute=0, second=0, microsecond=0)
    grid = SLOT_LENGTH.total_seconds()
    seconds = (opening - midnight).total_seconds()
    return midnight + timedelta(seconds=-(-seconds // grid) * grid)


def validate_slot(db: Session, doctor_id: int, start: datetime, now: datetime) -> datetime:
    """Check that `start` is a bookable slot for the doctor. Returns it in UTC."""
    start_utc = as_utc(start)
    local = start_utc.astimezone(CLINIC_TZ)

    if local.minute not in (0, 30) or local.second or local.microsecond:
        raise InvalidSlotError(
            "Appointments start on the hour or half hour, for example 09:00 or 09:30."
        )

    if start_utc < now:
        raise InvalidSlotError("That slot is in the past. Please choose a future time.")
    if start_utc < now + MIN_NOTICE:
        raise InvalidSlotError("Appointments must be booked at least 1 hour in advance.")

    hours = get_working_hours(db, doctor_id, local.weekday())
    if hours is None:
        raise InvalidSlotError(
            f"The doctor does not work on {local:%A}s. Please choose a day they work."
        )

    local_end = local + SLOT_LENGTH
    inside_hours = (
        hours.start_time <= local.time()
        and local_end.date() == local.date()
        and local_end.time() <= hours.end_time
    )
    if not inside_hours:
        raise InvalidSlotError(
            f"That time is outside the doctor's working hours on {local:%A} "
            f"({hours.start_time:%H:%M}-{hours.end_time:%H:%M}). Please choose a time within them."
        )

    taken = db.scalar(
        select(Appointment.id).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time == start_utc,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    )
    if taken is not None:
        raise SlotUnavailableError(
            "Sorry, that slot is already booked. Please choose another time."
        )

    return start_utc

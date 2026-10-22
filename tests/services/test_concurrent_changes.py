"""Two people changing the same appointment at once: the second one is told, not overwritten.

Each appointment row carries a version. The stale write is simulated by
changing the row behind the session's back after it has loaded the appointment
(a plain UPDATE that bumps the version, bypassing the ORM's in-memory copy).
"""

import pytest
from sqlalchemy import update

from app.errors import ConcurrentChangeError
from app.models import STATUS_BOOKED, Appointment
from app.services import booking
from tests.services.helpers import MON, NOW, book, local


def _change_behind_the_sessions_back(db, appointment_id, **values):
    """Another request's committed change, which this session has not seen."""
    db.execute(
        update(Appointment)
        .where(Appointment.id == appointment_id)
        .values(version=Appointment.version + 1, **values)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def test_new_appointments_start_at_version_one(db, world):
    assert book(db, world, local(MON, 9)).version == 1


def test_every_change_bumps_the_version(db, world):
    appt = book(db, world, local(MON, 9))
    moved = booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)
    assert moved.version == 2
    cancelled = booking.cancel_appointment(db, appt.id, "x", now=NOW)
    assert cancelled.version == 3


def test_cancelling_a_stale_appointment_is_reported_not_applied(db, world):
    appt = book(db, world, local(MON, 9))
    _change_behind_the_sessions_back(db, appt.id, cancel_reason="someone else was here")

    with pytest.raises(ConcurrentChangeError, match="Someone else just changed"):
        booking.cancel_appointment(db, appt.id, "mine", now=NOW)

    row = db.execute(Appointment.__table__.select().where(Appointment.id == appt.id)).one()
    assert row.status == STATUS_BOOKED  # our cancel was not applied
    assert row.cancel_reason == "someone else was here"  # their change was not overwritten


def test_rescheduling_a_stale_appointment_is_reported_not_applied(db, world):
    appt = book(db, world, local(MON, 9))
    _change_behind_the_sessions_back(db, appt.id, cancel_reason="someone else was here")

    with pytest.raises(ConcurrentChangeError):
        booking.reschedule_appointment(db, appt.id, local(MON, 10), now=NOW)

    # The rejected move left the original slot in place and the session usable.
    book(db, world, local(MON, 10), patient=world.p2)

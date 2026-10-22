"""Real race: one client cancels while another reschedules the same appointment.

Needs concurrent connections, so it only runs on Postgres (CI always does).

Both clients are held right after loading the appointment until BOTH have
loaded it, so each starts from the same version. Exactly one write can then
succeed; the other must be rejected instead of silently overwriting it. Remove
the version column and this test fails: both writes "succeed" and one change is lost.
"""

from datetime import UTC, datetime, time
from threading import Barrier, Thread

import pytest

from app.database import SessionLocal, engine
from app.errors import ConcurrentChangeError
from app.models import Appointment, Doctor, Patient, WorkingHours
from app.services import booking
from app.timeutils import CLINIC_TZ

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="needs concurrent connections (Postgres)",
)

NOW = datetime(2030, 1, 4, 9, 0, tzinfo=UTC)
FIRST = datetime(2030, 1, 7, 9, 0, tzinfo=CLINIC_TZ)  # Monday 09:00 clinic time
SECOND = datetime(2030, 1, 7, 10, 0, tzinfo=CLINIC_TZ)


def test_cancel_and_reschedule_at_the_same_time_cannot_both_win(db, monkeypatch):
    doctor = Doctor(name="Dr. Race")
    doctor.working_hours = [WorkingHours(weekday=0, start_time=time(9, 0), end_time=time(17, 0))]
    patient = Patient(name="Pat Race")
    db.add_all([doctor, patient])
    db.commit()
    appointment = booking.book_appointment(db, doctor.id, patient.id, FIRST, now=NOW)
    appointment_id = appointment.id

    both_loaded = Barrier(2, timeout=20)
    real_get = booking.get_appointment

    def load_then_wait(session, appt_id):
        loaded = real_get(session, appt_id)  # both clients read the same version...
        both_loaded.wait()  # ...and neither writes until both have read it
        return loaded

    monkeypatch.setattr(booking, "get_appointment", load_then_wait)

    outcomes: dict[str, object] = {}

    def cancel() -> None:
        with SessionLocal() as session:
            try:
                booking.cancel_appointment(session, appointment_id, "Cannot come", now=NOW)
                outcomes["cancel"] = "ok"
            except ConcurrentChangeError as error:
                outcomes["cancel"] = error

    def reschedule() -> None:
        with SessionLocal() as session:
            try:
                booking.reschedule_appointment(session, appointment_id, SECOND, now=NOW)
                outcomes["reschedule"] = "ok"
            except ConcurrentChangeError as error:
                outcomes["reschedule"] = error

    threads = [Thread(target=cancel), Thread(target=reschedule)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [name for name, result in outcomes.items() if result == "ok"]
    losers = [
        name for name, result in outcomes.items() if isinstance(result, ConcurrentChangeError)
    ]
    assert len(winners) == 1
    assert len(losers) == 1

    db.expire_all()
    final = db.get(Appointment, appointment_id)
    assert final.version == 2  # exactly one change was applied
    if winners == ["cancel"]:
        assert final.status == "cancelled"
    else:
        assert final.status == "rescheduled"

"""Real concurrency test: many clients fight for the same slot at once.

Needs a database with real concurrent connections, so it only runs on
Postgres (CI always does; locally set DATABASE_URL to a Postgres URL).

To make the race deterministic (rather than hoping threads interleave), every
client is held right after its "is the slot free?" check until ALL clients
have passed that check. From that point only the database's partial unique
index can stop the extra inserts. Remove the index and this test fails.
"""

from datetime import UTC, datetime, time
from threading import Barrier, Thread

import pytest

from app.database import SessionLocal, engine
from app.errors import SlotUnavailableError
from app.models import STATUS_BOOKED, Appointment, Doctor, Patient, WorkingHours
from app.services import booking
from app.timeutils import CLINIC_TZ

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="needs concurrent connections (Postgres)",
)

NOW = datetime(2030, 1, 4, 9, 0, tzinfo=UTC)
SLOT = datetime(2030, 1, 7, 9, 0, tzinfo=CLINIC_TZ)  # Monday 09:00 clinic time
CLIENTS = 10


def test_only_one_of_many_simultaneous_bookings_wins(db, monkeypatch):
    doctor = Doctor(name="Dr. Race")
    doctor.working_hours = [WorkingHours(weekday=0, start_time=time(9, 0), end_time=time(17, 0))]
    patients = [Patient(name=f"Patient {i}") for i in range(CLIENTS)]
    db.add_all([doctor, *patients])
    db.commit()
    doctor_id = doctor.id
    patient_ids = [p.id for p in patients]

    all_checked = Barrier(CLIENTS, timeout=20)
    real_validate = booking.validate_slot

    def validate_then_wait(db, doctor_id, start, now):
        result = real_validate(db, doctor_id, start, now)  # every client sees "free"
        all_checked.wait()  # ...and nobody inserts until everyone has seen that
        return result

    monkeypatch.setattr(booking, "validate_slot", validate_then_wait)

    booked: list[int] = []
    rejected: list[str] = []

    def attempt(patient_id: int) -> None:
        with SessionLocal() as session:  # each client has its own connection
            try:
                booking.book_appointment(session, doctor_id, patient_id, SLOT, now=NOW)
                booked.append(patient_id)
            except SlotUnavailableError as error:
                rejected.append(error.message)

    threads = [Thread(target=attempt, args=(pid,)) for pid in patient_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(booked) == 1
    assert len(rejected) == CLIENTS - 1
    # They all got past the application check, so each rejection came from the
    # database constraint and was translated into a clean error.
    assert all("just taken" in message for message in rejected)

    db.expire_all()
    active = (
        db.query(Appointment)
        .filter(Appointment.doctor_id == doctor_id, Appointment.status == STATUS_BOOKED)
        .count()
    )
    assert active == 1

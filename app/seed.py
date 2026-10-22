"""Demo data: five doctors and a demo patient.

Run it as an explicit step, after the migrations:  `python -m app.seed`
(entrypoint.sh does this when the container starts). The web app itself never writes demo
data while it starts up.
"""

from datetime import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Doctor, Patient, WorkingHours

# An arbitrary number that identifies "the seeding lock" to PostgreSQL.
SEED_LOCK_ID = 7_240_511

# Placeholder demo data. Adjust names/hours to taste (and note it in the README).
DOCTORS = [
    ("Dr. Amina Wanjiru", "General Practice"),
    ("Dr. Brian Otieno", "Paediatrics"),
    ("Dr. Celine Mutua", "Dermatology"),
    ("Dr. David Kamau", "Internal Medicine"),
    ("Dr. Esther Njeri", "Gynaecology"),
]


def seed_if_empty(db: Session) -> None:
    """Add the demo data when there are no doctors yet. Safe to run repeatedly and in parallel.

    On PostgreSQL a transaction-level advisory lock makes two seeders take turns: the second
    waits until the first has committed, then finds doctors and does nothing. Without it, two
    instances starting together could both see an empty table and both insert the data.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(SEED_LOCK_ID)))  # held until commit/rollback

    if db.scalar(select(Doctor.id).limit(1)) is not None:
        db.rollback()  # nothing to write; this also releases the lock
        return

    for name, specialty in DOCTORS:
        doctor = Doctor(name=name, specialty=specialty)
        # Mon-Fri 09:00-17:00 clinic local time; weekends off.
        doctor.working_hours = [
            WorkingHours(weekday=day, start_time=time(9, 0), end_time=time(17, 0))
            for day in range(5)
        ]
        db.add(doctor)

    db.add(Patient(name="Demo Patient", email="demo@example.com"))
    db.commit()


def main() -> None:
    """Command-line entry point: seed the database configured by DATABASE_URL."""
    with SessionLocal() as db:
        seed_if_empty(db)


if __name__ == "__main__":
    main()

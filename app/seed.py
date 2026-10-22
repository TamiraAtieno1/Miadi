"""Demo data: five doctors, a demo patient and a login for the admin, each doctor and the patient.

Run it as an explicit step, after the migrations:  `python -m app.seed`
(entrypoint.sh does this when the container starts). The web app itself never writes demo
data while it starts up.
"""

import os
import re
from datetime import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT, Doctor, Patient, WorkingHours
from app.services.accounts import ensure_user

DEFAULT_DEMO_PASSWORD = "miadi-demo"
ADMIN_EMAIL = "admin@example.com"

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
        doctor = Doctor(name=name, specialty=specialty, email=doctor_email(name))
        # Mon-Fri 09:00-17:00 clinic local time; weekends off.
        doctor.working_hours = [
            WorkingHours(weekday=day, start_time=time(9, 0), end_time=time(17, 0))
            for day in range(5)
        ]
        db.add(doctor)

    db.add(Patient(name="Demo Patient", email="demo@example.com"))
    db.commit()


def demo_password() -> str:
    """Password for the demo accounts. Set DEMO_PASSWORD to keep it private."""
    return os.environ.get("DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD


def doctor_email(name: str) -> str:
    """Login email for a doctor: "Dr. Amina Wanjiru" becomes amina.wanjiru@example.com."""
    words = re.sub(r"^dr\.?\s+", "", name.strip(), flags=re.IGNORECASE).lower().split()
    return ".".join(words) + "@example.com"


def seed_users_if_missing(db: Session) -> None:
    """Create a login for the admin, each doctor and the demo patient. Safe to repeat."""
    password = demo_password()
    ensure_user(db, ADMIN_EMAIL, password, ROLE_ADMIN)
    for doctor in db.scalars(select(Doctor).order_by(Doctor.id)):
        ensure_user(db, doctor.email, password, ROLE_DOCTOR, doctor_id=doctor.id)
    demo = db.scalar(select(Patient).where(Patient.email == "demo@example.com"))
    if demo is not None:
        ensure_user(db, demo.email, password, ROLE_PATIENT, patient_id=demo.id)


def main() -> None:
    """Command-line entry point: seed the database configured by DATABASE_URL."""
    with SessionLocal() as db:
        seed_if_empty(db)
        seed_users_if_missing(db)


if __name__ == "__main__":
    main()

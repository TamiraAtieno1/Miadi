from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, Patient, WorkingHours

# Placeholder demo data. Adjust names/hours to taste (and note it in the README).
DOCTORS = [
    ("Dr. Amina Wanjiru", "General Practice"),
    ("Dr. Brian Otieno", "Paediatrics"),
    ("Dr. Celine Mutua", "Dermatology"),
    ("Dr. David Kamau", "Internal Medicine"),
    ("Dr. Esther Njeri", "Gynaecology"),
]


def seed_if_empty(db: Session) -> None:
    """Idempotent: only seeds when there are no doctors yet."""
    if db.scalar(select(Doctor.id).limit(1)) is not None:
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

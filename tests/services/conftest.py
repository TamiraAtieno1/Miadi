from datetime import time
from types import SimpleNamespace

import pytest

from app.models import Doctor, Patient, WorkingHours


@pytest.fixture()
def world(db):
    """A doctor working Mon-Fri 09:00-17:00 and two patients."""
    doctor = Doctor(name="Dr. Test", email="test@example.com")
    doctor.working_hours = [
        WorkingHours(weekday=d, start_time=time(9, 0), end_time=time(17, 0)) for d in range(5)
    ]
    one, two = Patient(name="Pat One"), Patient(name="Pat Two")
    db.add_all([doctor, one, two])
    db.commit()
    return SimpleNamespace(doctor=doctor, p1=one, p2=two)

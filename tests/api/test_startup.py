"""App startup: tables are created and demo data is seeded exactly once."""

from fastapi.testclient import TestClient

from app.main import app
from app.models import Doctor, Patient
from app.seed import seed_if_empty


def test_startup_seeds_doctors_and_a_demo_patient(db):
    # Entering the client as a context manager runs the app's startup code.
    with TestClient(app) as client:
        doctors = client.get("/doctors").json()

    assert len(doctors) == 5
    assert all(len(d["working_hours"]) == 5 for d in doctors)  # Mon-Fri
    assert db.query(Patient).count() == 1


def test_seeding_twice_does_not_duplicate_data(db):
    seed_if_empty(db)
    seed_if_empty(db)  # second call must be a no-op

    assert db.query(Doctor).count() == 5
    assert db.query(Patient).count() == 1

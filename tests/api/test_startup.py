"""App startup writes nothing; demo data comes from the explicit seed command."""

import runpy

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.main import app
from app.models import Doctor, Patient


def test_starting_the_app_does_not_seed_anything(db):
    # Entering the client as a context manager runs the app's startup code.
    with TestClient(app) as client:
        assert client.get("/doctors").json() == []
        assert client.get("/health").status_code == 200

    assert db.query(Doctor).count() == 0
    assert db.query(Patient).count() == 0


def test_the_seed_command_adds_doctors_and_a_demo_patient(db):
    seed.main()

    assert db.query(Patient).count() == 1
    with TestClient(app) as client:
        doctors = client.get("/doctors").json()
    assert len(doctors) == 5
    assert all(len(d["working_hours"]) == 5 for d in doctors)  # Mon-Fri


def test_running_the_command_twice_does_not_duplicate_data(db):
    seed.main()
    seed.main()

    assert db.query(Doctor).count() == 5
    assert db.query(Patient).count() == 1


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_can_be_run_as_a_command(db):
    """`python -m app.seed` runs main()."""
    runpy.run_module("app.seed", run_name="__main__")

    assert db.query(Doctor).count() == 5

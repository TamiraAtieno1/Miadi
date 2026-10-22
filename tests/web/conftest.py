from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import ADMIN_EMAIL, DEFAULT_DEMO_PASSWORD, seed_if_empty, seed_users_if_missing
from app.timeutils import CLINIC_TZ, utcnow

DEMO_PATIENT = "demo@example.com"
DOCTOR_ONE = "amina.wanjiru@example.com"
DOCTOR_TWO = "brian.otieno@example.com"
PASSWORD = DEFAULT_DEMO_PASSWORD
__all__ = ["ADMIN_EMAIL", "DEMO_PATIENT", "DOCTOR_ONE", "DOCTOR_TWO", "PASSWORD"]


def future_monday(weeks: int = 2, hour: int = 9, minute: int = 0) -> datetime:
    """A Monday at least a week ahead, in clinic time, so every booking rule is satisfied."""
    today = utcnow().astimezone(CLINIC_TZ).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 + 7 * weeks)
    return datetime(monday.year, monday.month, monday.day, hour, minute, tzinfo=CLINIC_TZ)


@pytest.fixture()
def web(db):
    """A browser-like client (it keeps cookies) with the seeded clinic and its demo logins."""
    seed_if_empty(db)
    seed_users_if_missing(db)
    return TestClient(app, follow_redirects=False)


def sign_in(client, email, password=PASSWORD):
    """Sign in through the real form."""
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def as_patient(web):
    sign_in(web, DEMO_PATIENT)
    return web


@pytest.fixture()
def as_doctor(web):
    sign_in(web, DOCTOR_ONE)
    return web


@pytest.fixture()
def as_admin(web):
    sign_in(web, ADMIN_EMAIL)
    return web


def book_slot(client, start: datetime, doctor_id: int = 1):
    """Book through the patient page."""
    return client.post(
        "/portal/patient/book", data={"doctor_id": doctor_id, "start_time": start.isoformat()}
    )

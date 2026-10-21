"""HTTP-level tests: status codes, error bodies and response shapes.

These use the real clock, so slots are computed relative to today: always a
weekday at least a few days ahead (comfortably past the 1-hour notice rule).
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed_if_empty
from app.timeutils import CLINIC_TZ


@pytest.fixture()
def client(db):
    seed_if_empty(db)  # doctors 1-5 (Mon-Fri 09:00-17:00) and patient 1
    return TestClient(app)


def future_slot(hour: int = 9, minute: int = 0, min_days: int = 3) -> datetime:
    """A clinic-time slot on a weekday at least `min_days` from today."""
    day = datetime.now(CLINIC_TZ).date() + timedelta(days=min_days)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CLINIC_TZ)


def next_saturday() -> datetime:
    day = datetime.now(CLINIC_TZ).date() + timedelta(days=3)
    while day.weekday() != 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=CLINIC_TZ)


def book(client, start, doctor_id=1, patient_id=1):
    return client.post(
        "/appointments",
        json={
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "start_time": start.isoformat(),
        },
    )


def starts(response):
    return [datetime.fromisoformat(s["start"]) for s in response.json()["slots"]]


# --- booking ---------------------------------------------------------------


def test_booking_returns_201_with_clinic_local_times(client):
    start = future_slot(9)
    response = book(client, start)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "booked"
    assert datetime.fromisoformat(body["start_time"]) == start
    assert body["start_time"].endswith("+03:00")
    assert datetime.fromisoformat(body["end_time"]) == start + timedelta(minutes=30)


def test_double_booking_returns_409_with_a_code(client):
    start = future_slot(9)
    assert book(client, start).status_code == 201

    response = book(client, start)
    assert response.status_code == 409
    assert response.json()["code"] == "slot_unavailable"
    assert "already booked" in response.json()["detail"]


def test_timestamp_without_an_offset_is_rejected(client):
    naive = future_slot(9).replace(tzinfo=None)
    response = client.post(
        "/appointments",
        json={"doctor_id": 1, "patient_id": 1, "start_time": naive.isoformat()},
    )
    assert response.status_code == 422


def test_slot_in_the_past_returns_422(client):
    past = datetime(2020, 1, 6, 9, 0, tzinfo=CLINIC_TZ)
    response = book(client, past)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_slot"


def test_misaligned_and_out_of_hours_slots_return_422(client):
    assert book(client, future_slot(9, 15)).status_code == 422
    assert book(client, future_slot(18, 0)).status_code == 422
    assert book(client, next_saturday()).status_code == 422


def test_unknown_doctor_and_patient_return_404(client):
    assert book(client, future_slot(9), doctor_id=999).status_code == 404
    assert book(client, future_slot(9), patient_id=999).status_code == 404


# --- availability ----------------------------------------------------------


def test_availability_lists_free_slots_and_drops_booked_ones(client):
    start = future_slot(10)
    day = start.date().isoformat()

    before = client.get(f"/doctors/1/availability?date={day}")
    assert before.status_code == 200
    assert before.json()["timezone"] == "Africa/Nairobi"
    assert len(before.json()["slots"]) == 16
    assert start in starts(before)

    book(client, start)
    after = client.get(f"/doctors/1/availability?date={day}")
    assert len(after.json()["slots"]) == 15
    assert start not in starts(after)


def test_availability_is_empty_on_a_day_off(client):
    day = next_saturday().date().isoformat()
    response = client.get(f"/doctors/1/availability?date={day}")
    assert response.status_code == 200
    assert response.json()["slots"] == []


def test_availability_errors(client):
    day = future_slot().date().isoformat()
    assert client.get(f"/doctors/999/availability?date={day}").status_code == 404
    assert client.get("/doctors/1/availability?date=not-a-date").status_code == 422
    assert client.get("/doctors/1/availability").status_code == 422


# --- cancelling ------------------------------------------------------------


def test_cancel_frees_the_slot_and_cannot_be_repeated(client):
    start = future_slot(11)
    appt_id = book(client, start).json()["id"]

    response = client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "Can't make it"})
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancel_reason"] == "Can't make it"

    again = client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "again"})
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_state"

    day = start.date().isoformat()
    slots = client.get(f"/doctors/1/availability?date={day}")
    assert start in starts(slots)
    assert book(client, start).status_code == 201


def test_cancel_requires_a_reason_and_a_real_appointment(client):
    appt_id = book(client, future_slot(11)).json()["id"]
    assert client.patch(f"/appointments/{appt_id}/cancel", json={}).status_code == 422
    assert client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "  "}).status_code == 422
    assert client.patch("/appointments/999/cancel", json={"reason": "x"}).status_code == 404


# --- rescheduling ----------------------------------------------------------


def test_reschedule_moves_the_appointment(client):
    old, new = future_slot(9), future_slot(14)
    appt_id = book(client, old).json()["id"]

    response = client.patch(
        f"/appointments/{appt_id}/reschedule", json={"start_time": new.isoformat()}
    )
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["start_time"]) == new

    slots = client.get(f"/doctors/1/availability?date={old.date().isoformat()}")
    assert old in starts(slots)
    assert new not in starts(slots)


def test_reschedule_conflicts_and_cancelled_return_409(client):
    first, second = future_slot(9), future_slot(10)
    appt_id = book(client, first).json()["id"]
    book(client, second, patient_id=1)

    taken = client.patch(
        f"/appointments/{appt_id}/reschedule", json={"start_time": second.isoformat()}
    )
    assert taken.status_code == 409

    client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "x"})
    cancelled = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": future_slot(15).isoformat()},
    )
    assert cancelled.status_code == 409


def test_reschedule_to_an_invalid_slot_returns_422(client):
    appt_id = book(client, future_slot(9)).json()["id"]
    response = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": future_slot(18).isoformat()},
    )
    assert response.status_code == 422
    assert (
        client.patch(
            "/appointments/999/reschedule",
            json={"start_time": future_slot(10).isoformat()},
        ).status_code
        == 404
    )


# --- patients and doctors --------------------------------------------------


def test_patient_upcoming_appointments_are_sorted_and_exclude_cancelled(client):
    late, early, dropped = future_slot(15), future_slot(9), future_slot(11)
    book(client, late)
    book(client, early)
    dropped_id = book(client, dropped).json()["id"]
    client.patch(f"/appointments/{dropped_id}/cancel", json={"reason": "x"})

    response = client.get("/patients/1/appointments")
    assert response.status_code == 200
    got = [datetime.fromisoformat(a["start_time"]) for a in response.json()]
    assert got == [early, late]

    assert client.get("/patients/999/appointments").status_code == 404


def test_create_patient_and_list_doctors(client):
    created = client.post("/patients", json={"name": "Amina", "phone": "0700000000"})
    assert created.status_code == 201
    assert created.json()["name"] == "Amina"
    assert client.post("/patients", json={"name": ""}).status_code == 422

    doctors = client.get("/doctors")
    assert doctors.status_code == 200
    assert len(doctors.json()) == 5
    assert len(doctors.json()[0]["working_hours"]) == 5

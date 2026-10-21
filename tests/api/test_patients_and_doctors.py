"""Patient and doctor endpoints."""

from datetime import datetime

from tests.api.helpers import book, future_slot


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

"""Booking over HTTP: status codes and error bodies."""

from datetime import datetime, timedelta

from app.timeutils import CLINIC_TZ
from tests.api.helpers import book, future_slot, next_saturday


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

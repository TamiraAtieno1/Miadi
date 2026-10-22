"""Rescheduling over HTTP."""

from datetime import datetime

from tests.api.helpers import book, future_slot, starts


def test_reschedule_moves_the_appointment(client):
    old, new = future_slot(9), future_slot(14)
    appt_id = book(client, old).json()["id"]

    response = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": new.isoformat(), "expected_version": 1},
    )
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["start_time"]) == new
    assert response.json()["status"] == "rescheduled"

    slots = client.get(f"/doctors/1/availability?date={old.date().isoformat()}")
    assert old in starts(slots)
    assert new not in starts(slots)


def test_reschedule_conflicts_and_cancelled_return_409(client):
    first, second = future_slot(9), future_slot(10)
    appt_id = book(client, first).json()["id"]
    book(client, second, patient_id=1)

    taken = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": second.isoformat(), "expected_version": 1},
    )
    assert taken.status_code == 409

    client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "x", "expected_version": 1})
    cancelled = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": future_slot(15).isoformat(), "expected_version": 2},
    )
    assert cancelled.status_code == 409


def test_reschedule_to_an_invalid_slot_returns_422(client):
    appt_id = book(client, future_slot(9)).json()["id"]
    response = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": future_slot(18).isoformat(), "expected_version": 1},
    )
    assert response.status_code == 422
    assert (
        client.patch(
            "/appointments/999/reschedule",
            json={"start_time": future_slot(10).isoformat(), "expected_version": 1},
        ).status_code
        == 404
    )

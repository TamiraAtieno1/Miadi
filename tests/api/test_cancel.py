"""Cancelling over HTTP."""

from tests.api.helpers import book, future_slot, starts


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

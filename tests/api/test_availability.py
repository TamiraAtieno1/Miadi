"""Availability endpoint."""

from tests.api.helpers import book, future_slot, next_saturday, starts


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

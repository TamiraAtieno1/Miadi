"""A change made from an out-of-date copy of an appointment is refused."""

from tests.api.helpers import book, future_slot


def cancel(client, appt_id, version, reason="x"):
    return client.patch(
        f"/appointments/{appt_id}/cancel", json={"reason": reason, "expected_version": version}
    )


def reschedule(client, appt_id, version, start):
    return client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"start_time": start.isoformat(), "expected_version": version},
    )


def test_a_new_appointment_starts_at_version_one(client):
    assert book(client, future_slot(9)).json()["version"] == 1


def test_every_change_raises_the_version(client):
    created = book(client, future_slot(9)).json()
    moved = reschedule(client, created["id"], created["version"], future_slot(10)).json()
    assert moved["version"] == created["version"] + 1
    cancelled = cancel(client, created["id"], moved["version"]).json()
    assert cancelled["version"] == moved["version"] + 1


def test_the_patient_list_shows_the_version_too(client):
    book(client, future_slot(9))
    assert client.get("/patients/1/appointments").json()[0]["version"] == 1


def test_cancelling_from_a_stale_screen_is_refused_and_changes_nothing(client):
    created = book(client, future_slot(9)).json()
    seen = created["version"]  # two people open the appointment at version 1...
    assert (
        reschedule(client, created["id"], seen, future_slot(10)).status_code == 200
    )  # ...one moves it

    stale = cancel(client, created["id"], seen)  # ...the other cancels from the old screen

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"
    assert "reload" in stale.json()["detail"]
    current = client.get("/patients/1/appointments").json()[0]
    assert current["status"] == "rescheduled"  # still booked, not cancelled


def test_rescheduling_from_a_stale_screen_is_refused(client):
    created = book(client, future_slot(9)).json()
    cancel(client, created["id"], 1)

    stale = reschedule(client, created["id"], 1, future_slot(11))

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"


def test_reloading_and_sending_the_new_version_works(client):
    created = book(client, future_slot(9)).json()
    reschedule(client, created["id"], 1, future_slot(10))
    latest = client.get("/patients/1/appointments").json()[0]["version"]

    assert cancel(client, created["id"], latest).status_code == 200


def test_the_expected_version_is_required_and_must_be_positive(client):
    created = book(client, future_slot(9)).json()
    url = f"/appointments/{created['id']}/cancel"

    missing = client.patch(url, json={"reason": "x"})
    assert missing.status_code == 422
    assert "expected version" in missing.json()["detail"]
    assert client.patch(url, json={"reason": "x", "expected_version": 0}).status_code == 422
    assert client.patch(url, json={"reason": "x", "expected_version": "one"}).status_code == 422

    no_version = client.patch(
        f"/appointments/{created['id']}/reschedule",
        json={"start_time": future_slot(10).isoformat()},
    )
    assert no_version.status_code == 422

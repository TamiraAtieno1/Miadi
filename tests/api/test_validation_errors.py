"""Bad input gets one plain sentence, in the same shape as every other error."""

import pytest

from app.validation import describe_errors
from tests.api.helpers import future_slot


def error_of(response):
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], str)
    return body["detail"]


def test_missing_fields_are_named_in_plain_words(client):
    detail = error_of(client.post("/appointments", json={"doctor_id": 1}))
    assert "Please provide the patient ID." in detail
    assert "Please provide the start time." in detail


def test_timestamp_without_an_offset_explains_what_to_send(client):
    start = future_slot().replace(tzinfo=None).isoformat()
    detail = error_of(
        client.post("/appointments", json={"doctor_id": 1, "patient_id": 1, "start_time": start})
    )
    assert "timezone offset" in detail
    assert "+03:00" in detail


def test_text_where_a_number_is_expected(client):
    detail = error_of(
        client.patch("/appointments/abc/cancel", json={"reason": "x", "expected_version": 1})
    )
    assert detail == "The appointment ID must be a whole number."


def test_blank_and_oversized_text(client):
    assert error_of(client.post("/patients", json={"name": "   "})) == "The name cannot be empty."
    assert error_of(client.post("/patients", json={"name": "x" * 101})) == "The name is too long."


@pytest.mark.parametrize("value", ["notadate", "2030-13-45"])
def test_bad_date_in_the_query(client, value):
    detail = error_of(client.get(f"/doctors/1/availability?date={value}"))
    assert detail == "The date must be a date like 2030-01-07."


def test_bad_datetime_in_the_body(client):
    body = {"doctor_id": 1, "patient_id": 1, "start_time": "garbage"}
    assert "date and time like" in error_of(client.post("/appointments", json=body))


def test_invalid_json_body(client):
    response = client.post(
        "/appointments", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert error_of(response) == "The request body is not valid JSON."


def test_other_problems_get_a_generic_sentence(client):
    detail = error_of(
        client.patch("/appointments/1/cancel", json={"reason": ["a", "b"], "expected_version": 1})
    )
    assert detail == "The reason is not valid."


def test_the_same_problem_is_not_repeated():
    error = {"type": "missing", "loc": ("body", "doctor_id")}
    assert describe_errors([error, error]) == "Please provide the doctor ID."

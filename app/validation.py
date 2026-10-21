"""Plain-language messages for request validation errors.

FastAPI's default 422 body is a list of technical objects. Clients (and people
reading the docs page) are better served by one short sentence per problem,
in the same `{"detail": ..., "code": ...}` shape as every other error.
"""

EXAMPLE_DATE = "2030-01-07"
EXAMPLE_DATETIME = "2030-01-07T09:00:00+03:00"

FIELD_LABELS = {
    "doctor_id": "doctor ID",
    "patient_id": "patient ID",
    "appointment_id": "appointment ID",
    "start_time": "start time",
}


def describe_error(error: dict) -> str:
    """One friendly sentence for a single Pydantic/FastAPI validation error."""
    location = error.get("loc", ())
    field = str(location[-1]) if location else "request"
    label = FIELD_LABELS.get(field, field.replace("_", " "))
    kind = error.get("type", "")

    if kind == "json_invalid":
        return "The request body is not valid JSON."
    if kind == "missing":
        return f"Please provide the {label}."
    if kind == "timezone_aware":
        return f"The {label} needs a timezone offset, for example {EXAMPLE_DATETIME}."
    if kind in ("int_parsing", "int_type"):
        return f"The {label} must be a whole number."
    if kind == "string_too_short":
        return f"The {label} cannot be empty."
    if kind == "string_too_long":
        return f"The {label} is too long."
    if kind.startswith("date_") or kind == "date_type":
        return f"The {label} must be a date like {EXAMPLE_DATE}."
    if kind.startswith("datetime_"):
        return f"The {label} must be a date and time like {EXAMPLE_DATETIME}."
    return f"The {label} is not valid."


def describe_errors(errors: list[dict]) -> str:
    """Join the messages for all problems, without repeating the same sentence."""
    messages: list[str] = []
    for error in errors:
        message = describe_error(error)
        if message not in messages:
            messages.append(message)
    return " ".join(messages)

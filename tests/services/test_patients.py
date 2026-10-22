from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.errors import EmailTakenError
from app.services import patients


def error_with(message: str, constraint: str | None = None) -> IntegrityError:
    original = Exception(message)
    if constraint is not None:
        original.diag = SimpleNamespace(constraint_name=constraint)
    return IntegrityError("INSERT ...", {}, original)


def test_only_the_patient_email_rule_counts_as_an_email_clash():
    assert patients._is_email_clash(error_with("duplicate key", "uq_patients_email"))
    assert patients._is_email_clash(error_with("UNIQUE constraint failed: patients.email"))
    assert not patients._is_email_clash(error_with("violates check", "ck_something"))
    assert not patients._is_email_clash(error_with("NOT NULL constraint failed: patients.name"))


def test_other_integrity_errors_are_not_reported_as_a_taken_email(db, monkeypatch):
    def commit_fails():
        raise error_with("NOT NULL constraint failed: patients.name")

    monkeypatch.setattr(db, "commit", commit_fails)
    with pytest.raises(IntegrityError):
        patients.create_patient(db, "Pat", email="pat@example.com")


def test_a_duplicate_email_is_reported_as_taken(db):
    patients.create_patient(db, "First", email="same@example.com")
    with pytest.raises(EmailTakenError):
        patients.create_patient(db, "Second", email="same@example.com")

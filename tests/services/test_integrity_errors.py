"""Only a clash on the active-slot index means "slot taken"; other integrity errors are not."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.errors import SlotUnavailableError
from app.models import Appointment
from app.services import booking
from tests.services.helpers import MON, NOW, TUE, book, local


def error_with(message: str, constraint: str | None = None) -> IntegrityError:
    """An IntegrityError shaped like the ones SQLite (no diag) and PostgreSQL (diag) raise."""
    original = Exception(message)
    if constraint is not None:
        original.diag = SimpleNamespace(constraint_name=constraint)
    return IntegrityError("INSERT ...", {}, original)


def test_postgres_slot_index_is_a_slot_conflict():
    assert booking.is_slot_conflict(error_with("duplicate key", "uq_active_slot"))


def test_other_postgres_constraints_are_not_slot_conflicts():
    assert not booking.is_slot_conflict(
        error_with("violates foreign key", "appointments_doctor_id_fkey")
    )
    assert not booking.is_slot_conflict(error_with("violates check", "ck_appointments_status"))


def test_sqlite_slot_clash_is_recognised_by_its_columns():
    message = "UNIQUE constraint failed: appointments.doctor_id, appointments.start_time"
    assert booking.is_slot_conflict(error_with(message))


def test_other_sqlite_failures_are_not_slot_conflicts():
    assert not booking.is_slot_conflict(error_with("FOREIGN KEY constraint failed"))
    assert not booking.is_slot_conflict(
        error_with("NOT NULL constraint failed: appointments.status")
    )
    assert not booking.is_slot_conflict(error_with("UNIQUE constraint failed: users.email"))


def test_real_database_errors_are_told_apart(db, world):
    """Uses whichever database the tests run on (SQLite locally, PostgreSQL in CI)."""
    book(db, world, local(MON, 9))
    start = local(MON, 9).astimezone(NOW.tzinfo)

    def insert(**overrides):
        fields = {
            "doctor_id": world.doctor.id,
            "patient_id": world.p2.id,
            "start_time": start,
            "end_time": start + timedelta(minutes=30),
            "status": "booked",
        }
        db.add(Appointment(**{**fields, **overrides}))
        with pytest.raises(IntegrityError) as caught:
            db.commit()
        db.rollback()
        return caught.value

    assert booking.is_slot_conflict(insert())  # same doctor, same time, both active
    assert not booking.is_slot_conflict(
        insert(end_time=None, start_time=start + timedelta(days=1))
    )  # a missing required value


def test_booking_blames_a_taken_slot_only_for_the_slot_index(db, world, monkeypatch):
    def commit_fails():
        raise error_with(
            "UNIQUE constraint failed: appointments.doctor_id, appointments.start_time"
        )

    monkeypatch.setattr(db, "commit", commit_fails)
    with pytest.raises(SlotUnavailableError):
        booking.book_appointment(db, world.doctor.id, world.p1.id, local(MON, 9), now=NOW)


def test_booking_lets_other_integrity_errors_through_unchanged(db, world, monkeypatch):
    def commit_fails():
        raise error_with("FOREIGN KEY constraint failed")

    monkeypatch.setattr(db, "commit", commit_fails)
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        booking.book_appointment(db, world.doctor.id, world.p1.id, local(MON, 9), now=NOW)


def test_rescheduling_follows_the_same_rule(db, world, monkeypatch):
    appointment = book(db, world, local(MON, 9))
    real_commit = db.commit

    def commit_fails_once(message):
        def fail():
            monkeypatch.setattr(db, "commit", real_commit)
            raise error_with(message)

        return fail

    monkeypatch.setattr(
        db,
        "commit",
        commit_fails_once(
            "UNIQUE constraint failed: appointments.doctor_id, appointments.start_time"
        ),
    )
    with pytest.raises(SlotUnavailableError):
        booking.reschedule_appointment(db, appointment.id, local(TUE, 9), now=NOW)

    monkeypatch.setattr(db, "commit", commit_fails_once("CHECK constraint failed: status"))
    with pytest.raises(IntegrityError, match="CHECK"):
        booking.reschedule_appointment(db, appointment.id, local(TUE, 9), now=NOW)

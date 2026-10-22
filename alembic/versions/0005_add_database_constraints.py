"""enforce business rules in the database

Adds unique emails for doctors and patients, and CHECK constraints for the allowed
appointment statuses, the 30-minute appointment length, weekdays, working-hour order and
the link between a login and its doctor or patient.

Existing rows are tidied first where that is safe:
  * every doctor gets an email (made from the name, e.g. amina.wanjiru@example.com);
  * patient emails are trimmed and lower-cased, and when several patients share an email
    the first keeps it and the others have it cleared;
and the migration stops with a clear message if any other row breaks a new rule.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_RULE = "status IN ('booked', 'rescheduled', 'cancelled')"
WEEKDAY_RULE = "weekday BETWEEN 0 AND 6"
HOURS_RULE = "start_time < end_time"
USER_LINK_RULE = (
    "(role = 'admin' AND doctor_id IS NULL AND patient_id IS NULL)"
    " OR (role = 'doctor' AND doctor_id IS NOT NULL AND patient_id IS NULL)"
    " OR (role = 'patient' AND patient_id IS NOT NULL AND doctor_id IS NULL)"
)
SLOT_INDEX_RULE = sa.text("status IN ('booked', 'rescheduled')")


def _duration_rule(dialect: str) -> str:
    """SQL for "the appointment lasts exactly 30 minutes" (date maths differs per database)."""
    if dialect == "postgresql":
        return "end_time - start_time = interval '30 minutes'"
    return "strftime('%s', end_time) - strftime('%s', start_time) = 1800"


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_check_constraints(table))


def _has_unique(table: str, name: str) -> bool:
    return any(u["name"] == name for u in _inspector().get_unique_constraints(table))


def _has_column(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_columns(table))


def _refuse_if_any(description: str, query: str) -> None:
    """Stop the migration, naming the problem, when existing rows already break a new rule."""
    count = op.get_bind().execute(sa.text(query)).scalar() or 0
    if count:
        raise RuntimeError(
            f"Cannot add the new database rule: {count} existing row(s) {description}. "
            "Fix or remove those rows, then run the migration again."
        )


def _doctor_email(name: str) -> str:
    """ "Dr. Amina Wanjiru" becomes amina.wanjiru@example.com."""
    words = re.sub(r"^dr\.?\s+", "", name.strip(), flags=re.IGNORECASE).lower().split()
    local = re.sub(r"[^a-z0-9.]", "", ".".join(words)) or "doctor"
    return f"{local}@example.com"


def _give_every_doctor_an_email() -> None:
    bind = op.get_bind()
    taken = {
        row[0] for row in bind.execute(sa.text("SELECT email FROM doctors WHERE email IS NOT NULL"))
    }
    for doctor_id, name in bind.execute(
        sa.text("SELECT id, name FROM doctors WHERE email IS NULL ORDER BY id")
    ).fetchall():
        email = _doctor_email(name)
        if email in taken:  # same name twice: make the second one different
            email = email.replace("@", f".{doctor_id}@")
        taken.add(email)
        bind.execute(
            sa.text("UPDATE doctors SET email = :email WHERE id = :id"),
            {"email": email, "id": doctor_id},
        )


def _tidy_patient_emails() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE patients SET email = lower(trim(email)) WHERE email IS NOT NULL"))
    bind.execute(sa.text("UPDATE patients SET email = NULL WHERE email = ''"))
    seen: set[str] = set()
    for patient_id, email in bind.execute(
        sa.text("SELECT id, email FROM patients WHERE email IS NOT NULL ORDER BY id")
    ).fetchall():
        if email in seen:
            bind.execute(
                sa.text("UPDATE patients SET email = NULL WHERE id = :id"), {"id": patient_id}
            )
        seen.add(email)


def _restore_slot_index_on_sqlite() -> None:
    """SQLite rebuilds a table to add a constraint; make sure the partial index survived."""
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute("DROP INDEX IF EXISTS uq_active_slot")
    op.create_index(
        "uq_active_slot",
        "appointments",
        ["doctor_id", "start_time"],
        unique=True,
        sqlite_where=SLOT_INDEX_RULE,
    )


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    duration_rule = _duration_rule(dialect)

    # --- stop early, with a clear message, if existing data already breaks a new rule
    _refuse_if_any(
        "have a status other than booked, rescheduled or cancelled",
        "SELECT count(*) FROM appointments WHERE NOT (" + STATUS_RULE + ")",
    )
    _refuse_if_any(
        "do not last exactly 30 minutes",
        "SELECT count(*) FROM appointments WHERE NOT (" + duration_rule + ")",
    )
    _refuse_if_any(
        "have a weekday outside 0-6",
        "SELECT count(*) FROM working_hours WHERE NOT (" + WEEKDAY_RULE + ")",
    )
    _refuse_if_any(
        "have working hours that end before they start",
        "SELECT count(*) FROM working_hours WHERE NOT (" + HOURS_RULE + ")",
    )
    _refuse_if_any(
        "link a login to the wrong doctor or patient for its role",
        "SELECT count(*) FROM users WHERE NOT (" + USER_LINK_RULE + ")",
    )

    # --- doctors: an email for each, then unique
    if not _has_column("doctors", "email"):
        with op.batch_alter_table("doctors") as batch:
            batch.add_column(sa.Column("email", sa.String(length=255), nullable=True))
    _give_every_doctor_an_email()
    with op.batch_alter_table("doctors") as batch:
        batch.alter_column("email", existing_type=sa.String(length=255), nullable=False)
        if not _has_unique("doctors", "uq_doctors_email"):
            batch.create_unique_constraint("uq_doctors_email", ["email"])

    # --- patients: unique email
    _tidy_patient_emails()
    if not _has_unique("patients", "uq_patients_email"):
        with op.batch_alter_table("patients") as batch:
            batch.create_unique_constraint("uq_patients_email", ["email"])

    # --- appointments
    with op.batch_alter_table("appointments") as batch:
        if not _has_check("appointments", "ck_appointments_status"):
            batch.create_check_constraint("ck_appointments_status", STATUS_RULE)
        if not _has_check("appointments", "ck_appointments_duration"):
            batch.create_check_constraint("ck_appointments_duration", duration_rule)
    _restore_slot_index_on_sqlite()

    # --- working hours
    with op.batch_alter_table("working_hours") as batch:
        if not _has_check("working_hours", "ck_working_hours_weekday"):
            batch.create_check_constraint("ck_working_hours_weekday", WEEKDAY_RULE)
        if not _has_check("working_hours", "ck_working_hours_order"):
            batch.create_check_constraint("ck_working_hours_order", HOURS_RULE)

    # --- logins
    with op.batch_alter_table("users") as batch:
        if not _has_check("users", "ck_users_role_link"):
            batch.create_check_constraint("ck_users_role_link", USER_LINK_RULE)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_role_link", type_="check")
    with op.batch_alter_table("working_hours") as batch:
        batch.drop_constraint("ck_working_hours_order", type_="check")
        batch.drop_constraint("ck_working_hours_weekday", type_="check")
    with op.batch_alter_table("appointments") as batch:
        batch.drop_constraint("ck_appointments_duration", type_="check")
        batch.drop_constraint("ck_appointments_status", type_="check")
    _restore_slot_index_on_sqlite()
    with op.batch_alter_table("patients") as batch:
        batch.drop_constraint("uq_patients_email", type_="unique")
    with op.batch_alter_table("doctors") as batch:
        batch.drop_constraint("uq_doctors_email", type_="unique")
        batch.drop_column("email")

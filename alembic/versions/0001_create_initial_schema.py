"""create initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-20 23:35:13.329662
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# What the first deployment's tables looked like (it used create_all() before Alembic existed):
# for each table, every column with whether it may be NULL.
EXPECTED_COLUMNS: dict[str, dict[str, bool]] = {
    "doctors": {"id": False, "name": False, "specialty": False},
    "patients": {"id": False, "name": False, "phone": True, "email": True},
    "appointments": {
        "id": False,
        "doctor_id": False,
        "patient_id": False,
        "start_time": False,
        "end_time": False,
        "status": False,
        "cancel_reason": True,
        "cancelled_at": True,
        "created_at": False,
        "updated_at": False,
    },
    "working_hours": {
        "id": False,
        "doctor_id": False,
        "weekday": False,
        "start_time": False,
        "end_time": False,
    },
}
# (table, column, table it must point to)
EXPECTED_FOREIGN_KEYS = [
    ("appointments", "doctor_id", "doctors"),
    ("appointments", "patient_id", "patients"),
    ("working_hours", "doctor_id", "doctors"),
]


def _schema_problems(inspector: sa.engine.reflection.Inspector) -> list[str]:
    """Everything that stops an existing database from being adopted as the initial schema.

    Columns that later migrations add (such as version or email) are allowed to be there
    already; what matters is that everything this migration would have created is.
    """
    problems = []
    for table, columns in EXPECTED_COLUMNS.items():
        if not inspector.has_table(table):
            problems.append(f"table '{table}' is missing")
            continue
        found = {c["name"]: c["nullable"] for c in inspector.get_columns(table)}
        for name, nullable in columns.items():
            if name not in found:
                problems.append(f"table '{table}' has no column '{name}'")
            elif found[name] != nullable:
                wanted = "allow" if nullable else "refuse"
                problems.append(f"column '{table}.{name}' should {wanted} NULL")

    for table, column, target in EXPECTED_FOREIGN_KEYS:
        if inspector.has_table(table) and not any(
            fk["constrained_columns"] == [column] and fk["referred_table"] == target
            for fk in inspector.get_foreign_keys(table)
        ):
            problems.append(f"column '{table}.{column}' is not a foreign key to '{target}'")

    if inspector.has_table("appointments"):
        slot_index = [
            i
            for i in inspector.get_indexes("appointments")
            if i["name"] == "uq_active_slot"
            and i["unique"]
            and list(i["column_names"]) == ["doctor_id", "start_time"]
        ]
        if not slot_index:
            problems.append("table 'appointments' has no unique index 'uq_active_slot'")
    if inspector.has_table("working_hours"):
        weekday_rule = [
            u
            for u in inspector.get_unique_constraints("working_hours")
            if list(u["column_names"]) == ["doctor_id", "weekday"]
        ]
        if not weekday_rule:
            problems.append("table 'working_hours' has no unique rule on (doctor_id, weekday)")
    return problems


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # The first deployment created its tables with create_all() before Alembic was
    # introduced. Adopt that database, but only after checking it really is that schema:
    # finding one table is not proof that the rest, or their constraints, are right.
    if any(inspector.has_table(table) for table in EXPECTED_COLUMNS):
        problems = _schema_problems(inspector)
        if problems:
            raise RuntimeError(
                "This database already has some Miadi tables, but they don't match what the "
                "first migration expects, so nothing was changed. Problems found:\n  - "
                + "\n  - ".join(problems)
                + "\nFix the schema by hand, or point DATABASE_URL at an empty database."
            )
        return

    op.create_table(
        "doctors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("specialty", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctors.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_appointments_doctor_id"), "appointments", ["doctor_id"], unique=False)
    op.create_index(
        op.f("ix_appointments_patient_id"), "appointments", ["patient_id"], unique=False
    )
    op.create_index(
        "uq_active_slot",
        "appointments",
        ["doctor_id", "start_time"],
        unique=True,
        postgresql_where=sa.text("status = 'booked'"),
        sqlite_where=sa.text("status = 'booked'"),
    )
    op.create_table(
        "working_hours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctors.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "weekday", name="uq_doctor_weekday"),
    )


def downgrade() -> None:
    op.drop_table("working_hours")
    op.drop_index(
        "uq_active_slot",
        table_name="appointments",
        postgresql_where=sa.text("status = 'booked'"),
        sqlite_where=sa.text("status = 'booked'"),
    )
    op.drop_index(op.f("ix_appointments_patient_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_doctor_id"), table_name="appointments")
    op.drop_table("appointments")
    op.drop_table("patients")
    op.drop_table("doctors")

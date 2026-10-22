"""The first migration adopts an existing database only if it really is the original schema."""

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command


@pytest.fixture()
def legacy(tmp_path):
    """(config, engine) for an empty SQLite database that has no Alembic history."""
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    engine = sa.create_engine(url)
    yield cfg, engine
    engine.dispose()


def build_original_schema(
    engine,
    *,
    patients=True,
    working_hours=True,
    appointment_foreign_keys=True,
    status="NOT NULL",
    weekday_rule=True,
    slot_index=True,
    cancel_reason=True,
):
    """Create the tables as the first deployment's create_all() did, with optional damage."""
    reason = "cancel_reason VARCHAR(500)," if cancel_reason else ""
    foreign_keys = (
        ", FOREIGN KEY(doctor_id) REFERENCES doctors (id)"
        ", FOREIGN KEY(patient_id) REFERENCES patients (id)"
        if appointment_foreign_keys
        else ""
    )
    unique = ", CONSTRAINT uq_doctor_weekday UNIQUE (doctor_id, weekday)" if weekday_rule else ""
    statements = [
        "CREATE TABLE doctors (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(100) NOT NULL,"
        " specialty VARCHAR(100) NOT NULL)",
    ]
    if patients:
        statements.append(
            "CREATE TABLE patients (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(100) NOT NULL,"
            " phone VARCHAR(30), email VARCHAR(255))"
        )
    statements.append(
        "CREATE TABLE appointments (id INTEGER NOT NULL PRIMARY KEY, doctor_id INTEGER NOT NULL,"
        " patient_id INTEGER NOT NULL, start_time DATETIME NOT NULL, end_time DATETIME NOT NULL,"
        f" status VARCHAR(20) {status}, {reason} cancelled_at DATETIME,"
        f" created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL{foreign_keys})"
    )
    if slot_index:
        statements.append(
            "CREATE UNIQUE INDEX uq_active_slot ON appointments (doctor_id, start_time)"
            " WHERE status = 'booked'"
        )
    if working_hours:
        statements.append(
            "CREATE TABLE working_hours (id INTEGER NOT NULL PRIMARY KEY,"
            " doctor_id INTEGER NOT NULL, weekday SMALLINT NOT NULL, start_time TIME NOT NULL,"
            f" end_time TIME NOT NULL, FOREIGN KEY(doctor_id) REFERENCES doctors (id){unique})"
        )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))


def current_revision(engine):
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def test_the_original_schema_is_adopted(legacy):
    cfg, engine = legacy
    build_original_schema(engine)

    command.upgrade(cfg, "head")

    assert current_revision(engine) == "0005"
    assert "users" in sa.inspect(engine).get_table_names()


def test_a_database_built_by_the_migrations_themselves_is_also_adopted(legacy):
    """Same result when the first revision is replayed over tables it created earlier."""
    cfg, engine = legacy
    command.upgrade(cfg, "0001")
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE alembic_version"))  # as if Alembic had never run

    command.upgrade(cfg, "head")

    assert current_revision(engine) == "0005"


DAMAGED = [
    ({"patients": False}, "table 'patients' is missing"),
    ({"working_hours": False}, "table 'working_hours' is missing"),
    ({"cancel_reason": False}, "table 'appointments' has no column 'cancel_reason'"),
    ({"status": ""}, "column 'appointments.status' should refuse NULL"),
    (
        {"appointment_foreign_keys": False},
        "column 'appointments.doctor_id' is not a foreign key to 'doctors'",
    ),
    ({"slot_index": False}, "no unique index 'uq_active_slot'"),
    ({"weekday_rule": False}, "no unique rule on (doctor_id, weekday)"),
]


@pytest.mark.parametrize(("damage", "message"), DAMAGED, ids=[m for _, m in DAMAGED])
def test_a_database_that_does_not_match_is_refused_untouched(legacy, damage, message):
    cfg, engine = legacy
    build_original_schema(engine, **damage)

    with pytest.raises(RuntimeError, match="don't match what the first migration expects") as error:
        command.upgrade(cfg, "head")

    assert message in str(error.value)
    assert "users" not in sa.inspect(engine).get_table_names()  # nothing was built or changed
    assert current_revision(engine) is None


def test_every_problem_is_listed_not_just_the_first(legacy):
    cfg, engine = legacy
    build_original_schema(engine, patients=False, slot_index=False, weekday_rule=False)

    with pytest.raises(RuntimeError) as error:
        command.upgrade(cfg, "head")

    message = str(error.value)
    assert "table 'patients' is missing" in message
    assert "uq_active_slot" in message
    assert "(doctor_id, weekday)" in message

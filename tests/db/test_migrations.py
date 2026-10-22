"""The Alembic migrations must build exactly the schema the models describe."""

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command
from app import models  # noqa: F401
from app.database import Base


@pytest.fixture()
def alembic_cfg(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg, url


def test_upgrade_creates_the_schema_the_models_describe(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []  # no drift between models and migrations

    inspector = sa.inspect(engine)
    assert {"doctors", "patients", "appointments", "working_hours", "users"} <= set(
        inspector.get_table_names()
    )
    assert "uq_active_slot" in {i["name"] for i in inspector.get_indexes("appointments")}
    engine.dispose()


def test_downgrade_removes_everything(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(url)
    assert set(sa.inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()


def test_upgrade_adopts_a_database_created_before_alembic(alembic_cfg):
    cfg, url = alembic_cfg
    engine = sa.create_engine(url)
    Base.metadata.create_all(engine)  # how the first deployment built its tables

    command.upgrade(cfg, "head")  # must not fail with "table already exists"

    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == "0005"
    engine.dispose()


def _insert_appointment(conn, status, doctor_id=1):
    conn.execute(
        sa.text(
            "INSERT INTO appointments (doctor_id, patient_id, start_time, end_time, status,"
            " created_at, updated_at) VALUES (:d, 1, '2030-01-07 06:00:00', '2030-01-07 06:30:00',"
            " :s, '2030-01-01 00:00:00', '2030-01-01 00:00:00')"
        ),
        {"d": doctor_id, "s": status},
    )


def _seed_people(conn, doctor_email=None):
    """Insert one doctor and one patient. Doctors only have an email from revision 0005 on."""
    if doctor_email:
        conn.execute(
            sa.text("INSERT INTO doctors (name, specialty, email) VALUES ('Dr. T', 'GP', :email)"),
            {"email": doctor_email},
        )
    else:
        conn.execute(sa.text("INSERT INTO doctors (name, specialty) VALUES ('Dr. T', 'GP')"))
    conn.execute(sa.text("INSERT INTO patients (name) VALUES ('Pat T')"))


def test_rescheduled_appointments_hold_their_slot_after_upgrading(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "0001")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        _seed_people(conn)
        _insert_appointment(conn, "booked")

    command.upgrade(cfg, "head")  # existing data survives the index change

    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE appointments SET status = 'rescheduled'"))
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        _insert_appointment(conn, "booked")  # same slot as the rescheduled one
    engine.dispose()


def test_downgrade_turns_rescheduled_appointments_back_into_booked(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        _seed_people(conn, doctor_email="t@example.com")
        _insert_appointment(conn, "rescheduled")

    command.downgrade(cfg, "0001")

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT status FROM appointments")).scalar() == "booked"
    engine.dispose()


def test_existing_appointments_get_version_one_when_upgrading(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "0002")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        _seed_people(conn)
        _insert_appointment(conn, "booked")

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT version FROM appointments")).scalar() == 1
    engine.dispose()


def test_downgrade_removes_the_version_column(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")

    engine = sa.create_engine(url)
    columns = {c["name"] for c in sa.inspect(engine).get_columns("appointments")}
    assert "version" not in columns
    engine.dispose()

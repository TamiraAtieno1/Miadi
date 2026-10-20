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
    assert {"doctors", "patients", "appointments", "working_hours"} <= set(
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
        assert MigrationContext.configure(conn).get_current_revision() == "0001"
    engine.dispose()

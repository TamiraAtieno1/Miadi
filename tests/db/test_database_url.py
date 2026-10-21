import pytest

from app.database import _database_url


@pytest.mark.parametrize(
    "raw",
    [
        "postgres://user:pw@host:5432/db",
        "postgresql://user:pw@host:5432/db",
    ],
)
def test_postgres_urls_use_psycopg2_driver(monkeypatch, raw):
    monkeypatch.setenv("DATABASE_URL", raw)
    assert _database_url() == "postgresql+psycopg2://user:pw@host:5432/db"


def test_explicit_driver_is_left_alone(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h/db")
    assert _database_url() == "postgresql+psycopg2://u:p@h/db"


def test_sqlite_url_is_unchanged(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert _database_url() == "sqlite://"

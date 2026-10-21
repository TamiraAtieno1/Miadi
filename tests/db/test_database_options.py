from sqlalchemy.pool import StaticPool

from app.database import _engine_options


def test_postgres_needs_no_extra_engine_options():
    assert _engine_options("postgresql+psycopg2://u:p@host/db") == {}


def test_file_based_sqlite_allows_use_across_threads():
    options = _engine_options("sqlite:///./clinic.db")
    assert options == {"connect_args": {"check_same_thread": False}}


def test_in_memory_sqlite_shares_a_single_connection():
    for url in ("sqlite://", "sqlite:///:memory:"):
        options = _engine_options(url)
        assert options["poolclass"] is StaticPool
        assert options["connect_args"] == {"check_same_thread": False}

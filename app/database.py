import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


def _database_url() -> str:
    """Read DATABASE_URL (default: local SQLite) and name the psycopg2 driver for Postgres."""
    url = os.environ.get("DATABASE_URL", "sqlite:///./clinic.db")
    # Render/Heroku-style URLs use "postgres://", which SQLAlchemy rejects.
    # Also name the driver explicitly: a bare "postgresql://" may default to
    # psycopg (v3) in newer SQLAlchemy, but this project installs psycopg2.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix) :]
    return url


def _engine_options(url: str) -> dict:
    """Extra create_engine() arguments needed for a given database URL."""
    options: dict = {}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # In-memory SQLite needs one shared connection.
            options["poolclass"] = StaticPool
    return options


DATABASE_URL = _database_url()

engine = create_engine(DATABASE_URL, **_engine_options(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base class that all ORM models inherit from."""


def get_db():
    """FastAPI dependency that yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

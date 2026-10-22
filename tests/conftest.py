import os

# Tests default to in-memory SQLite; CI overrides with a real Postgres URL.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402

from tests.db_safety import assert_safe_test_database  # noqa: E402

# The fixtures below drop every table. Stop before anything connects if the URL
# (for example one left in the shell from development) points at a real database.
try:
    assert_safe_test_database(os.environ["DATABASE_URL"])
except ValueError as error:
    pytest.exit(str(error), returncode=2)

from app import models  # noqa: E402,F401
from app.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

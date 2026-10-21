import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed_if_empty


@pytest.fixture()
def client(db):
    """A test client with doctors 1-5 (Mon-Fri 09:00-17:00) and patient 1 seeded."""
    seed_if_empty(db)
    return TestClient(app)

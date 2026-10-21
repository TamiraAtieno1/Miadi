from fastapi.testclient import TestClient

from app.main import app


def test_health_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_answers_head_requests_for_uptime_monitors():
    client = TestClient(app)
    response = client.head("/health")
    assert response.status_code == 200

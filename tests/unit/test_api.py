import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from fastapi.testclient import TestClient

from backend.app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

def test_empty_complexes_are_honest():
    with TestClient(app) as client:
        assert client.get("/api/v1/complexes").json() == []

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


def test_hydrology_source_status_never_exposes_key_values():
    with TestClient(app) as client:
        response = client.get("/api/v1/seoul/hydrology-sources")
        assert response.status_code == 200
        configuration = response.json()["configuration"]
        assert len(configuration) == 4
        for item in configuration.values():
            assert "api_key_configured" in item
            assert "api_url_configured" in item
            assert "api_key" not in item

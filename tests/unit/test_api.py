import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from fastapi.testclient import TestClient

from backend.app.api.v1.router import _safe_failure_reason
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
        assert "mois_flood_trace_api" in configuration
        for item in configuration.values():
            assert "api_key_configured" in item
            assert "api_url_configured" in item
            assert "api_key" not in item


def test_frontend_config_only_exposes_browser_safe_values(monkeypatch):
    monkeypatch.setenv("NAVER_MAP_CLIENT_ID", "public-client-id")
    monkeypatch.setenv("NAVER_MAP_CLIENT_SECRET", "must-not-leak")
    with TestClient(app) as client:
        response = client.get("/api/v1/frontend-config")
        assert response.status_code == 200
        payload = response.json()
        assert payload["naver_map_client_id"] == "public-client-id"
        assert "secret" not in " ".join(payload).lower()
        assert "must-not-leak" not in response.text


def test_failure_reason_is_bounded_and_does_not_return_sql_payload():
    reason = "IntegrityError: duplicate row\n[SQL: INSERT INTO source_records ...]" + "x" * 1000
    assert _safe_failure_reason(reason) == "IntegrityError: duplicate row"
    assert len(_safe_failure_reason("x" * 1000)) == 500

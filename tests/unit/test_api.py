import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api.v1.router import _safe_failure_reason
from backend.app.db.base import Complex, SeoulComplexProfile
from backend.app.db.session import SessionLocal
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


def test_cascade_api_returns_evidence_graph_contract():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.merge(Complex(complex_id="cascade-api",complex_name="검증단지",address="서울특별시",latitude=None,longitude=None,source_name="test",source_url=None,collected_at=now,observed_at=None,data_version="test",validation_status="valid",collection_run_id="test"))
            db.merge(SeoulComplexProfile(complex_id="cascade-api",complex_name="검증단지",address="서울특별시",normalized_address="서울특별시",latitude=None,longitude=None,district=None,household_count=None,building_count=None,completion_date=None,building_age_years=None,kapt_code=None,analysis_eligible=True,eligibility_reason="test",validation_status="ADDRESS_ONLY",source_name="test",data_version="test",updated_at=now)); db.commit()
        response = client.get("/api/v1/seoul/complexes/cascade-api/cascade")
        assert response.status_code == 200
        body = response.json()
        assert body["method_type"] == "evidence_graph"
        assert body["method_version"] == "cascade-v1"
        assert all("evidence" in node and "missing_evidence" in node for node in body["nodes"])


def test_hydrology_endpoint_is_honest_when_feature_build_is_missing():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.merge(Complex(complex_id="hydrology-api",complex_name="검증단지",address="서울특별시",latitude=None,longitude=None,source_name="test",source_url=None,collected_at=now,observed_at=None,data_version="test",validation_status="valid",collection_run_id="test"))
            db.merge(SeoulComplexProfile(complex_id="hydrology-api",complex_name="검증단지",address="서울특별시",normalized_address="서울특별시",latitude=None,longitude=None,district=None,household_count=None,building_count=None,completion_date=None,building_age_years=None,kapt_code=None,analysis_eligible=False,eligibility_reason="좌표 미확보",validation_status="ADDRESS_ONLY",source_name="test",data_version="test",updated_at=now))
            db.commit()
        response = client.get("/api/v1/seoul/complexes/hydrology-api/hydrology")
        assert response.status_code == 200
        assert response.json()["status"] == "NOT_READY"

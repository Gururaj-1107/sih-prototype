"""
Integration tests for FastAPI endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app, _seed_default_users


@pytest.fixture(scope="module")
def client():
    _seed_default_users()
    with TestClient(app) as c:
        yield c


def test_auth_login_and_me(client):
    """Test login flow and token validation."""
    resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["role"] == "investigator"

    token = data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "investigator"


def test_overview_metrics(client):
    """Test dashboard stats endpoint."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]

    resp = client.get("/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    stats = resp.json()
    assert "active_alerts" in stats
    assert "complaints_processed" in stats
    assert "predictions_generated" in stats


def test_predictions_and_evidence(client):
    """Test prediction listing and evidence retrieval."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]

    preds = client.get("/predictions", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(preds) > 0
    first_pred_id = preds[0]["prediction_id"]

    detail = client.get(f"/predictions/{first_pred_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert detail["prediction_id"] == first_pred_id
    assert "candidates" in detail
    assert len(detail["candidates"]) > 0
    assert "evidence" in detail["candidates"][0]


def test_audit_verify_endpoint(client):
    """Test cryptographic audit chain verification endpoint."""
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    resp = client.post("/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    res = resp.json()
    assert res["is_valid"] is True

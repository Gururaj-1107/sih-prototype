"""
Unit and integration tests for Tactical Interception, 1930 Cyber Freeze,
Syndicate Community Detection, and System Settings.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app, _seed_default_users, _seed_default_police_stations
from backend.database.connection import init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    _seed_default_users()
    _seed_default_police_stations()
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", json={"username": "investigator", "password": "inv123"})
        token = login_resp.json()["access_token"]
        c.post("/demo/run", headers={"Authorization": f"Bearer {token}"})
        yield c


def test_jurisdictions_and_police_stations(client):
    """Verify police stations directory lookup."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/jurisdictions/police-stations", headers=headers)
    assert resp.status_code == 200
    stations = resp.json()
    assert len(stations) >= 5
    assert any(s["city"] == "Mumbai" for s in stations)


def test_interception_dispatch_lifecycle(client):
    """Verify tactical advisory dispatch to Cyber Police Station and status update."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Dispatch unit
    disp_resp = client.post("/interceptions/dispatch", headers=headers, json={
        "prediction_id": "DEMO_AHM_MUM",
        "location_id": "M17",
        "station_id": "PS-MUM-BKC-01",
        "priority": "CRITICAL"
    })
    assert disp_resp.status_code == 200
    disp_data = disp_resp.json()
    assert disp_data["status"] == "success"
    assert "verification_token" in disp_data
    dispatch_id = disp_data["dispatch_id"]

    # Check active list
    list_resp = client.get("/interceptions/active", headers=headers)
    assert list_resp.status_code == 200
    assert any(d["dispatch_id"] == dispatch_id for d in list_resp.json())

    # Update status to ON_SCENE
    status_resp = client.post(f"/interceptions/{dispatch_id}/status", headers=headers, json={
        "status": "PATROL_ACTIVE",
        "notes": "Patrol vehicle 104 deployed to BKC ATM cluster."
    })
    assert status_resp.status_code == 200
    assert status_resp.json()["new_status"] == "PATROL_ACTIVE"


def test_1930_emergency_cyber_freeze(client):
    """Verify 1930 / I4C emergency cyber-freeze simulation on mule account."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch an account from DB
    accs_resp = client.get("/accounts", headers=headers)
    acc_id = accs_resp.json()[0]["account_id"]

    # Freeze account
    freeze_resp = client.post(f"/accounts/{acc_id}/freeze", headers=headers, json={
        "amount": 250000.0,
        "reason": "Test 1930 Emergency Freeze"
    })
    assert freeze_resp.status_code == 200
    f_data = freeze_resp.json()
    assert f_data["status"] == "success"
    assert f_data["is_frozen"] is True
    assert f_data["frozen_amount"] == 250000.0

    # Query frozen accounts
    frozen_list_resp = client.get("/accounts/frozen", headers=headers)
    assert frozen_list_resp.status_code == 200
    assert frozen_list_resp.json()["total_frozen_accounts"] >= 1

    # Unfreeze account
    unfreeze_resp = client.post(f"/accounts/{acc_id}/unfreeze", headers=headers)
    assert unfreeze_resp.status_code == 200
    assert unfreeze_resp.json()["is_frozen"] is False


def test_bulk_complaint_ingest_and_syndicate_clustering(client):
    """Verify bulk NCRP complaint ingestion and graph community clustering."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Bulk ingest
    ingest_resp = client.post("/complaints/bulk-ingest", headers=headers, json={
        "complaints": [
            {"crime_type": "UPI Fraud", "amount": 90000.0, "victim_bank": "SBI", "scenario_tag": "BATCH_01"},
            {"crime_type": "Job Scam", "amount": 120000.0, "victim_bank": "HDFC", "scenario_tag": "BATCH_01"}
        ]
    })
    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["ingested_count"] >= 1

    # Query syndicates
    syn_resp = client.get("/complaints/syndicates", headers=headers)
    assert syn_resp.status_code == 200
    syn_data = syn_resp.json()
    assert "total_syndicates_detected" in syn_data
    assert "syndicates" in syn_data


def test_system_settings_tuning(client):
    """Verify operational threshold configuration."""
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    get_resp = client.get("/settings", headers=headers)
    assert get_resp.status_code == 200
    assert "mule_risk_threshold" in get_resp.json()

    post_resp = client.post("/settings", headers=headers, json={"mule_risk_threshold": 0.88})
    assert post_resp.status_code == 200
    assert post_resp.json()["settings"]["mule_risk_threshold"] == 0.88

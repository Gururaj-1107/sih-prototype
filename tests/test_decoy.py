"""
Comprehensive unit and integration tests for the Controlled Decoy & Synthetic Mule
Intelligence Layer (Pure Simulation Mode for Hackathon Prototype).
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database.models import Base, Decoy, DecoyInteraction, Complaint, Transaction, Account, User, Location
from backend.database.connection import init_db
from backend.decoy.engine import DecoyIntelligenceEngine
from backend.graph.builder import TransactionGraph
from backend.audit.audit_chain import create_audit_record, verify_chain_integrity
from backend.main import app, _seed_default_users


@pytest.fixture
def memory_db():
    """Create an isolated in-memory SQLite database for unit tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client():
    """Test client with initialized database and seeded default users."""
    init_db()
    _seed_default_users()
    with TestClient(app) as c:
        # Run demo scenario to populate predictions, alerts, decoys, etc.
        login_resp = c.post("/auth/login", json={"username": "investigator", "password": "inv123"})
        token = login_resp.json()["access_token"]
        c.post("/demo/run", headers={"Authorization": f"Bearer {token}"})
        yield c


# ==============================================================================
# 1. DISPERSAL PATTERN DETECTION UNIT TESTS
# ==============================================================================
def test_detect_dispersal_pattern(memory_db):
    """Verify rapid fan-out dispersal detection logic and scoring."""
    engine = DecoyIntelligenceEngine(mule_threshold=0.80, dispersal_threshold=0.70)

    # Seed source mule account
    acc_mule = Account(
        account_id="ACC_MULE_1",
        city="Ahmedabad",
        risk_label="mule",
        mule_risk_score=0.92
    )
    # Seed destination accounts in Mumbai
    acc_d1 = Account(account_id="ACC_D1", city="Mumbai", risk_label="suspect", mule_risk_score=0.5)
    acc_d2 = Account(account_id="ACC_D2", city="Mumbai", risk_label="suspect", mule_risk_score=0.5)
    acc_d3 = Account(account_id="ACC_D3", city="Mumbai", risk_label="suspect", mule_risk_score=0.5)
    memory_db.add_all([acc_mule, acc_d1, acc_d2, acc_d3])

    # Incoming transfer: ₹250,000
    t_in = Transaction(
        transaction_id="TX_IN_1",
        source_account_id="ACC_VICTIM",
        dest_account_id="ACC_MULE_1",
        amount=250000.0,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    # Outgoing fan-out transfers
    t_out1 = Transaction(transaction_id="TX_OUT_1", source_account_id="ACC_MULE_1", dest_account_id="ACC_D1", amount=80000.0, timestamp=datetime.now(timezone.utc).isoformat())
    t_out2 = Transaction(transaction_id="TX_OUT_2", source_account_id="ACC_MULE_1", dest_account_id="ACC_D2", amount=85000.0, timestamp=datetime.now(timezone.utc).isoformat())
    t_out3 = Transaction(transaction_id="TX_OUT_3", source_account_id="ACC_MULE_1", dest_account_id="ACC_D3", amount=80000.0, timestamp=datetime.now(timezone.utc).isoformat())
    memory_db.add_all([t_in, t_out1, t_out2, t_out3])
    memory_db.commit()

    is_triggered, dispersal_score, signals = engine.detect_dispersal_pattern(
        account_id="ACC_MULE_1",
        db=memory_db
    )

    assert is_triggered is True
    assert dispersal_score >= 0.70
    assert signals["fan_out"] == 3
    assert signals["unique_destinations"] == 3
    assert signals["pass_through_ratio"] >= 0.95
    assert signals["is_cross_city"] is True


# ==============================================================================
# 2. DECOY ARMING & SIMULATION UNIT TESTS
# ==============================================================================
def test_arm_controlled_decoys(memory_db):
    """Verify synthetic decoy generation when mule risk exceeds threshold."""
    engine = DecoyIntelligenceEngine()

    decoys = engine.arm_controlled_decoys(
        case_id="CMP-TEST-001",
        scenario_id="SCENARIO_AHMEDABAD_MUMBAI",
        trigger_account_id="ACC_MULE_1",
        target_city="Mumbai",
        activation_reason="Dispersal detected (3 hops to Mumbai)",
        db=memory_db,
        user_id="investigator"
    )

    assert len(decoys) == 3
    for d in decoys:
        assert d.is_synthetic is True
        assert d.status == "ARMED"
        assert d.city == "Mumbai"
        assert d.synthetic_account_id.startswith("SYN_")
        assert d.case_id == "CMP-TEST-001"

    # Verify queryable from DB
    db_decoys = memory_db.query(Decoy).filter(Decoy.case_id == "CMP-TEST-001").all()
    assert len(db_decoys) == 3


def test_simulate_interaction_event_isolation(memory_db):
    """Verify synthetic telemetry recording without corrupting real transaction table."""
    engine = DecoyIntelligenceEngine()

    # Arm a decoy
    d = Decoy(
        decoy_id="D-TEST-1",
        decoy_type="CONTROLLED_ACCOUNT",
        synthetic_account_id="SYN_ACC_999",
        city="Mumbai",
        status="ARMED",
        case_id="CMP-ISO-01",
        scenario_id="SCENARIO_1",
        activation_reason="Test activation",
        interaction_count=0,
        is_synthetic=True
    )
    memory_db.add(d)
    memory_db.commit()

    # Simulate interaction event
    event = engine.simulate_interaction_event(
        decoy_id="D-TEST-1",
        source_account_id="ACC_MULE_1",
        synthetic_amount=75000.0,
        originating_city="Ahmedabad",
        destination_city="Mumbai",
        interaction_type="SIMULATED_WITHDRAWAL_PROBE",
        hop_number=2,
        case_id="CMP-ISO-01",
        scenario_id="SCENARIO_1",
        db=memory_db,
        user_id="investigator"
    )

    assert event.is_synthetic is True
    assert event.decoy_id == "D-TEST-1"
    assert event.synthetic_amount == 75000.0
    assert event.destination_city == "Mumbai"

    # Check decoy state transition
    updated_decoy = memory_db.query(Decoy).filter(Decoy.decoy_id == "D-TEST-1").first()
    assert updated_decoy.status == "INTERACTION_DETECTED"
    assert updated_decoy.interaction_count == 1

    # Verify real transaction table remains untouched (0 real transactions)
    real_txns = memory_db.query(Transaction).all()
    assert len(real_txns) == 0


def test_compute_decoy_score(memory_db):
    """Verify combined decoy risk/confidence calculation."""
    engine = DecoyIntelligenceEngine()

    # Before interactions
    score_0, bullets_0 = engine.compute_decoy_score(case_id="C-EMPTY", scenario_id=None, db=memory_db)
    assert score_0 == 0.0

    # First create parent decoy
    d = Decoy(
        decoy_id="D-001-1",
        decoy_type="CONTROLLED_ACCOUNT",
        synthetic_account_id="SYN_ACC_101",
        city="Mumbai",
        status="ARMED",
        case_id="C-ACTIVE",
        is_synthetic=True
    )
    memory_db.add(d)
    memory_db.commit()

    # Add decoy interaction
    d_int = DecoyInteraction(
        interaction_id="DEC_INT_001",
        decoy_id="D-001-1",
        source_account_id="ACC_MULE",
        synthetic_amount=50000.0,
        destination_city="Mumbai",
        interaction_type="SIMULATED_PROBE",
        timestamp=datetime.now(timezone.utc).isoformat(),
        case_id="C-ACTIVE",
        is_synthetic=True
    )
    memory_db.add(d_int)
    memory_db.commit()

    score_1, bullets_1 = engine.compute_decoy_score(case_id="C-ACTIVE", scenario_id=None, db=memory_db)
    assert score_1 >= 0.65
    assert len(bullets_1) > 0
    assert any("Mumbai" in b for b in bullets_1)


# ==============================================================================
# 3. GRAPH & AUDIT LEDGER INTEGRATION
# ==============================================================================
def test_graph_builder_includes_decoys(memory_db):
    """Verify that NetworkX graph builder injects Decoy nodes and interaction edges."""
    acc1 = Account(account_id="ACC_SRC", city="Ahmedabad", risk_label="mule", mule_risk_score=0.88)
    acc2 = Account(account_id="ACC_DEST", city="Mumbai", risk_label="suspect", mule_risk_score=0.6)
    memory_db.add_all([acc1, acc2])

    d = Decoy(
        decoy_id="D-GRP-1",
        decoy_type="CONTROLLED_ACCOUNT",
        synthetic_account_id="SYN_ACC_GRP",
        city="Mumbai",
        status="INTERACTION_DETECTED",
        interaction_count=1,
        is_synthetic=True
    )
    memory_db.add(d)
    memory_db.commit()

    interaction = DecoyInteraction(
        interaction_id="EVT-GRP-1",
        decoy_id="D-GRP-1",
        source_account_id="ACC_SRC",
        synthetic_amount=50000.0,
        destination_city="Mumbai",
        interaction_type="SIMULATED_PROBE",
        timestamp=datetime.now(timezone.utc).isoformat(),
        is_synthetic=True
    )
    memory_db.add(interaction)
    memory_db.commit()

    # Build graph
    builder = TransactionGraph()
    builder.build_from_db(memory_db)
    G = builder.graph
    assert G.has_node("D-GRP-1")
    node_data = G.nodes["D-GRP-1"]
    assert node_data.get("is_decoy") is True
    assert node_data.get("node_type") == "decoy"
    assert node_data.get("status") == "INTERACTION_DETECTED"

    # Edge from source account to decoy
    assert G.has_edge("ACC_SRC", "D-GRP-1")
    edge_data = G.edges["ACC_SRC", "D-GRP-1"]
    assert edge_data.get("edge_type") == "decoy_simulation"


def test_audit_ledger_decoy_logging(memory_db):
    """Verify SHA-256 audit ledger cryptographic linking for decoy actions."""
    r1 = create_audit_record(
        memory_db,
        event_type="DECOY_ACTIVATED",
        event_data={"decoy_id": "D-001", "target_mule_id": "MULE_1", "case_id": "C-1"},
        user_id="officer_cyber"
    )
    r2 = create_audit_record(
        memory_db,
        event_type="DECOY_INTERACTION_SIMULATED",
        event_data={"decoy_id": "D-001", "destination_city": "Mumbai", "amount": 50000.0},
        user_id="system"
    )

    assert r1.sequence_number == 1
    assert r2.sequence_number == 2
    assert r2.previous_hash == r1.current_hash

    # Chain verification
    res = verify_chain_integrity(memory_db)
    assert res["is_valid"] is True
    assert res["n_records"] == 2


# ==============================================================================
# 4. FASTAPI DECOY INTELLIGENCE ENDPOINTS
# ==============================================================================
def test_api_decoy_lifecycle_and_endpoints(client):
    """Test full HTTP API lifecycle for Decoy Intelligence Layer."""
    # 1. Login as investigator
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Activate Decoy for Case DEMO_AHM_MUM
    act_resp = client.post("/cases/DEMO_AHM_MUM/decoy/activate", headers=headers)
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["status"] == "armed"
    assert len(act_data["activated_decoys"]) > 0
    decoy_id = act_data["activated_decoys"][0]["decoy_id"]

    # 3. Simulate interaction event on the activated decoy
    sim_resp = client.post(
        f"/cases/DEMO_AHM_MUM/decoy/simulate",
        headers=headers,
        json={
            "decoy_id": decoy_id,
            "source_account_id": "ACC_MULE_1",
            "synthetic_amount": 75000.0,
            "originating_city": "Ahmedabad",
            "destination_city": "Mumbai",
            "interaction_type": "SIMULATED_WITHDRAWAL_PROBE",
            "hop_number": 2
        }
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["status"] == "success"
    assert sim_data["interaction"]["decoy_id"] == decoy_id

    # 4. Fetch Decoy Evidence for Case DEMO_AHM_MUM
    ev_resp = client.get("/cases/DEMO_AHM_MUM/decoy/evidence", headers=headers)
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert ev_data["case_id"] == "DEMO_AHM_MUM"
    assert "active_decoys" in ev_data
    assert "interactions" in ev_data
    assert ev_data["is_simulation_only"] is True

    # 5. Fetch Decoys List
    list_resp = client.get("/decoys", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) > 0

    # 6. Fetch Decoy Intelligence Summary
    summary_resp = client.get("/decoy-intelligence/summary", headers=headers)
    assert summary_resp.status_code == 200
    s_data = summary_resp.json()
    assert "total_decoys" in s_data
    assert "armed" in s_data
    assert "interaction_detected" in s_data

    # 7. Test AI Assistant Query on Decoy Intelligence
    ast_resp = client.post(
        "/assistant/query",
        headers=headers,
        json={"question": "What is the status of synthetic decoys and detected interactions?"}
    )
    assert ast_resp.status_code == 200
    ast_data = ast_resp.json()
    assert "answer" in ast_data
    assert "decoy" in ast_data["answer"].lower() or "synthetic" in ast_data["answer"].lower()


def test_api_demo_run_scenario(client):
    """Test the complete Ahmedabad to Mumbai CashOut & Decoy demo pipeline."""
    login_resp = client.post("/auth/login", json={"username": "investigator", "password": "inv123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/demo/run", headers=headers)
    assert resp.status_code == 200
    demo_data = resp.json()

    assert demo_data["status"] == "success"
    assert "prediction_id" in demo_data
    assert "alert_id" in demo_data
    assert len(demo_data["armed_decoys"]) > 0
    assert "simulated_interaction" in demo_data
    assert len(demo_data["top_k_results"]) > 0

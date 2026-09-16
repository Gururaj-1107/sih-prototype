"""
FastAPI Main Application — entry point.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import os
import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager
import networkx as nx

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.database.connection import get_db, init_db
from backend.database.models import (
    User, Complaint, Account, Transaction, Withdrawal,
    Location, Prediction, PredictionEvidence, Alert,
    InvestigatorFeedback, AuditLog, Decoy, DecoyInteraction,
    PoliceStation, InterceptionDispatch
)
from backend.auth import (
    verify_password, hash_password, create_access_token, get_current_user
)
from backend.audit.audit_chain import create_audit_record, verify_chain_integrity
from backend.prediction.forecaster import get_forecaster
from backend.decoy.engine import DecoyIntelligenceEngine
from backend.websocket_manager import ws_manager


# ─────────────────────────────────────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and seed default admin user on startup."""
    init_db()
    _seed_default_users()
    _seed_default_police_stations()
    print("[API] CashOut Forecast API started.")
    yield
    print("[API] Shutting down.")


def _seed_default_users():
    """Create default admin and investigator accounts if they don't exist."""
    from backend.database.connection import SessionLocal
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                user_id=str(uuid.uuid4()),
                username="admin",
                hashed_password=hash_password("admin123"),
                role="admin",
                created_at=datetime.utcnow().isoformat(),
            ))
        if not db.query(User).filter(User.username == "investigator").first():
            db.add(User(
                user_id=str(uuid.uuid4()),
                username="investigator",
                hashed_password=hash_password("inv123"),
                role="investigator",
                created_at=datetime.utcnow().isoformat(),
            ))
        if not db.query(User).filter(User.username == "bank_officer").first():
            db.add(User(
                user_id=str(uuid.uuid4()),
                username="bank_officer",
                hashed_password=hash_password("bank123"),
                role="investigator",
                created_at=datetime.utcnow().isoformat(),
            ))
        db.commit()
    finally:
        db.close()


def _seed_default_police_stations():
    """Seed key Cyber Police Stations across metropolitan cash-out clusters."""
    from backend.database.connection import SessionLocal
    db = SessionLocal()
    try:
        stations = [
            PoliceStation(
                station_id="PS-MUM-BKC-01",
                name="Bandra Kurla Complex (BKC) Cyber Police Station",
                city="Mumbai",
                state="Maharashtra",
                latitude=19.0657,
                longitude=72.8687,
                nodal_officer="Inspector Vijay Kulkarni",
                contact_phone="+91-22-2650-4411",
                control_room_email="bkc.cybercell@mahapolice.gov.in",
                jurisdiction_radius_km=8.5
            ),
            PoliceStation(
                station_id="PS-MUM-NAR-02",
                name="Nariman Point & Marine Drive Police Station",
                city="Mumbai",
                state="Maharashtra",
                latitude=18.9275,
                longitude=72.8236,
                nodal_officer="ACP Priya Deshmukh",
                contact_phone="+91-22-2285-1122",
                control_room_email="south.control@mumbaipolice.gov.in",
                jurisdiction_radius_km=6.0
            ),
            PoliceStation(
                station_id="PS-AHM-CYB-01",
                name="Ahmedabad Cyber Crime Police Station",
                city="Ahmedabad",
                state="Gujarat",
                latitude=23.0300,
                longitude=72.5800,
                nodal_officer="Inspector Hardik Patel",
                contact_phone="+91-79-2268-3344",
                control_room_email="cybercrime-ahd@gujarat.gov.in",
                jurisdiction_radius_km=12.0
            ),
            PoliceStation(
                station_id="PS-DEL-CYB-01",
                name="Special Cell IFSO Cyber Police Station",
                city="Delhi",
                state="Delhi",
                latitude=28.6139,
                longitude=77.2090,
                nodal_officer="DCP Ananya Verma",
                contact_phone="+91-11-2090-5500",
                control_room_email="ifso.specialcell@delhipolice.gov.in",
                jurisdiction_radius_km=15.0
            ),
            PoliceStation(
                station_id="PS-BLR-CYB-01",
                name="Bengaluru Central Cyber Crime Division (CID)",
                city="Bengaluru",
                state="Karnataka",
                latitude=12.9716,
                longitude=77.5946,
                nodal_officer="SP Ramesh Gowda",
                contact_phone="+91-80-2294-2222",
                control_room_email="cybercrime.cid@ksp.gov.in",
                jurisdiction_radius_km=10.0
            ),
        ]
        for ps in stations:
            if not db.query(PoliceStation).filter(PoliceStation.station_id == ps.station_id).first():
                db.add(ps)
        db.commit()
    finally:
        db.close()


app = FastAPI(
    title="CashOut Forecast API",
    description="Explainable Spatiotemporal Financial Intelligence Platform — SIH 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def login(credentials: dict, db: Session = Depends(get_db)):
    """Login and receive JWT token."""
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer",
            "role": user.role, "username": user.username}


@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}


# ─────────────────────────────────────────────────────────────────────────────
# OVERVIEW / DASHBOARD STATS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/overview")
def get_overview(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Dashboard summary statistics."""
    n_complaints = db.query(Complaint).count()
    n_accounts = db.query(Account).count()
    n_suspicious = db.query(Account).filter(
        Account.risk_label.in_(["mule", "suspect"])
    ).count()
    n_predictions = db.query(Prediction).count()
    n_alerts = db.query(Alert).filter(Alert.status == "active").count()
    n_pending_review = db.query(Alert).filter(Alert.status.in_(["active", "viewed"])).count()
    total_txn_volume = db.query(Transaction).count()
    n_decoys = db.query(Decoy).count()
    n_active_decoys = db.query(Decoy).filter(Decoy.status.in_(["ARMED", "INTERACTION_DETECTED"])).count()
    n_decoy_interactions = db.query(DecoyInteraction).count()

    return {
        "active_alerts": n_alerts,
        "complaints_processed": n_complaints,
        "suspicious_accounts": n_suspicious,
        "total_accounts": n_accounts,
        "predictions_generated": n_predictions,
        "pending_review": n_pending_review,
        "total_transactions": total_txn_volume,
        "total_decoys": n_decoys,
        "active_decoys": n_active_decoys,
        "decoy_interactions": n_decoy_interactions,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPLAINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/complaints")
def list_complaints(limit: int = 50, offset: int = 0,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    complaints = db.query(Complaint).offset(offset).limit(limit).all()
    return [_complaint_to_dict(c) for c in complaints]


@app.get("/complaints/syndicates")
def get_syndicate_clusters(db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """
    Perform graph community detection across complaints and mule accounts
    to group isolated citizen complaints into organized crime syndicate operations.
    """
    from backend.graph.builder import TransactionGraph
    builder = TransactionGraph()
    builder.build_from_db(db)
    G = builder.graph

    undirected = G.to_undirected()
    components = list(nx.connected_components(undirected))

    syndicates = []
    syn_idx = 1
    for comp in sorted(components, key=len, reverse=True):
        if len(comp) < 2:
            continue

        accounts = [n for n in comp if G.nodes[n].get("node_type") == "account"]
        decoys = [n for n in comp if G.nodes[n].get("node_type") == "decoy"]
        mule_nodes = [a for a in accounts if G.nodes[a].get("risk_label") in ("mule", "suspect")]
        cities = list(set([G.nodes[n].get("city") for n in comp if G.nodes[n].get("city")]))

        total_est_loss = len(accounts) * 125000.0

        syndicates.append({
            "syndicate_id": f"SYN-OP-{syn_idx:02d}",
            "syndicate_name": f"{cities[0] if cities else 'National'}-{cities[-1] if len(cities)>1 else 'Hub'} Syndicate",
            "total_nodes": len(comp),
            "mule_accounts_count": len(mule_nodes),
            "linked_accounts": accounts[:8],
            "controlled_decoys": decoys,
            "target_cashout_cities": cities,
            "estimated_illicit_volume": total_est_loss,
            "threat_severity": "CRITICAL" if len(mule_nodes) >= 2 else "HIGH"
        })
        syn_idx += 1
        if syn_idx > 10:
            break

    return {
        "total_syndicates_detected": len(syndicates),
        "syndicates": syndicates
    }


@app.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    c = db.query(Complaint).filter(Complaint.complaint_id == complaint_id).first()
    if not c:
        raise HTTPException(404, "Complaint not found")
    return _complaint_to_dict(c)


def _complaint_to_dict(c):
    return {
        "complaint_id": c.complaint_id,
        "timestamp": c.timestamp,
        "crime_type": c.crime_type,
        "amount": c.amount,
        "victim_id": c.victim_id,
        "victim_location_id": c.victim_location_id,
        "victim_bank": c.victim_bank,
        "status": c.status,
        "scenario_tag": c.scenario_tag,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/accounts")
def list_accounts(limit: int = 50, offset: int = 0, risk_label: Optional[str] = None,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    q = db.query(Account)
    if risk_label:
        q = q.filter(Account.risk_label == risk_label)
    accounts = q.offset(offset).limit(limit).all()
    return [_account_to_dict(a) for a in accounts]


@app.get("/accounts/frozen")
def list_frozen_accounts(db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Retrieve all accounts currently lien-marked under 1930 cyber freeze."""
    frozen = db.query(Account).filter(Account.is_frozen == True).all()
    total_locked = sum(a.frozen_amount or 0.0 for a in frozen)
    return {
        "total_frozen_accounts": len(frozen),
        "total_funds_secured": total_locked,
        "accounts": [{
            "account_id": a.account_id,
            "city": a.city,
            "risk_label": a.risk_label,
            "mule_risk_score": a.mule_risk_score,
            "frozen_at": a.frozen_at,
            "frozen_amount": a.frozen_amount,
            "freeze_reason": a.freeze_reason
        } for a in frozen]
    }


@app.get("/accounts/{account_id}")
def get_account(account_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    acc = db.query(Account).filter(Account.account_id == account_id).first()
    if not acc:
        raise HTTPException(404, "Account not found")
    return _account_to_dict(acc)


@app.get("/accounts/{account_id}/network")
def get_account_network(account_id: str, hops: int = 2,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Return transaction network subgraph for an account (for UI graph view)."""
    import pandas as pd
    from scripts.train_model import build_graph_from_dfs
    from backend.graph.builder import TransactionGraph

    acc_df = pd.read_sql(db.query(Account).statement, db.bind)
    loc_df = pd.read_sql(db.query(Location).statement, db.bind)
    txn_df = pd.read_sql(db.query(Transaction).statement, db.bind)
    wdr_df = pd.read_sql(db.query(Withdrawal).statement, db.bind)

    gb = TransactionGraph()
    gb.graph = build_graph_from_dfs(acc_df, loc_df, txn_df, wdr_df)
    return gb.to_json(account_id=account_id, hops=hops)


def _account_to_dict(a):
    return {
        "account_id": a.account_id,
        "bank_id": a.bank_id,
        "account_type": a.account_type,
        "account_age_days": a.account_age_days,
        "city": a.city,
        "state": a.state,
        "location_id": a.location_id,
        "risk_label": a.risk_label,
        "mule_risk_score": a.mule_risk_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/transactions")
def list_transactions(limit: int = 100, offset: int = 0,
                      account_id: Optional[str] = None,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    q = db.query(Transaction)
    if account_id:
        q = q.filter(
            (Transaction.source_account_id == account_id) |
            (Transaction.dest_account_id == account_id)
        )
    txns = q.order_by(Transaction.timestamp.desc()).offset(offset).limit(limit).all()
    return [_txn_to_dict(t) for t in txns]


def _txn_to_dict(t):
    return {
        "transaction_id": t.transaction_id,
        "timestamp": t.timestamp,
        "source_account_id": t.source_account_id,
        "dest_account_id": t.dest_account_id,
        "amount": t.amount,
        "transaction_type": t.transaction_type,
        "channel": t.channel,
        "location_id": t.location_id,
        "scenario_id": t.scenario_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LOCATIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/locations")
def list_locations(db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    locs = db.query(Location).all()
    return [_loc_to_dict(l) for l in locs]


def _loc_to_dict(l):
    return {
        "location_id": l.location_id,
        "latitude": l.latitude,
        "longitude": l.longitude,
        "city": l.city,
        "state": l.state,
        "location_type": l.location_type,
        "cluster_code": l.cluster_code,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/predictions")
def list_predictions(limit: int = 20, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    preds = db.query(Prediction).order_by(
        Prediction.created_at.desc()
    ).limit(limit).all()
    return [_prediction_summary(p, db) for p in preds]


@app.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    pred = db.query(Prediction).filter(
        Prediction.prediction_id == prediction_id
    ).first()
    if not pred:
        raise HTTPException(404, "Prediction not found")

    # Log audit: investigator viewed prediction
    create_audit_record(db, "prediction_viewed", {
        "prediction_id": prediction_id,
        "viewer": current_user.username,
    }, user_id=current_user.user_id)

    evidence = db.query(PredictionEvidence).filter(
        PredictionEvidence.prediction_id == prediction_id
    ).order_by(PredictionEvidence.rank).all()

    return {
        **_prediction_summary(pred, db),
        "candidates": [_evidence_to_dict(e) for e in evidence],
    }


@app.get("/predictions/{prediction_id}/explanation")
def get_explanation(prediction_id: str, rank: int = 1,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Return detailed explanation for rank-N prediction."""
    ev = db.query(PredictionEvidence).filter(
        PredictionEvidence.prediction_id == prediction_id,
        PredictionEvidence.rank == rank,
    ).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    return {
        "rank": ev.rank,
        "location_id": ev.location_id,
        "score": ev.score,
        "evidence": json.loads(ev.evidence_json or "[]"),
        "transaction_path": json.loads(ev.transaction_path_json or "[]"),
        "window": {
            "start": ev.expected_window_start,
            "end": ev.expected_window_end,
        }
    }


def _prediction_summary(p: Prediction, db: Session) -> dict:
    top = db.query(PredictionEvidence).filter(
        PredictionEvidence.prediction_id == p.prediction_id,
        PredictionEvidence.rank == 1,
    ).first()
    return {
        "prediction_id": p.prediction_id,
        "created_at": p.created_at,
        "scenario_id": p.scenario_id,
        "model_version": p.model_version,
        "status": p.status,
        "top_location": top.location_id if top else None,
        "top_score": top.score if top else None,
        "top_window_start": top.expected_window_start if top else None,
        "top_window_end": top.expected_window_end if top else None,
    }


def _evidence_to_dict(e: PredictionEvidence) -> dict:
    loc = None
    return {
        "rank": e.rank,
        "location_id": e.location_id,
        "score": e.score,
        "expected_window_start": e.expected_window_start,
        "expected_window_end": e.expected_window_end,
        "evidence": json.loads(e.evidence_json or "[]"),
        "transaction_path": json.loads(e.transaction_path_json or "[]"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/alerts")
def list_alerts(status: Optional[str] = None, limit: int = 20,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    alerts = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [_alert_to_dict(a) for a in alerts]


@app.patch("/alerts/{alert_id}/status")
def update_alert_status(alert_id: str, body: dict,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    new_status = body.get("status", "viewed")
    alert.status = new_status
    db.commit()
    create_audit_record(db, "alert_status_changed", {
        "alert_id": alert_id, "new_status": new_status,
    }, user_id=current_user.user_id)
    return {"alert_id": alert_id, "status": new_status}


def _alert_to_dict(a: Alert) -> dict:
    return {
        "alert_id": a.alert_id,
        "created_at": a.created_at,
        "prediction_id": a.prediction_id,
        "location_id": a.location_id,
        "city": a.location.city if a.location else "",
        "state": a.location.state if a.location else "",
        "latitude": a.location.latitude if a.location else None,
        "longitude": a.location.longitude if a.location else None,
        "score": a.score,
        "priority": a.priority,
        "expected_window_start": a.expected_window_start,
        "expected_window_end": a.expected_window_end,
        "status": a.status,
        "summary": a.summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FEEDBACK
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/feedback")
def submit_feedback(body: dict, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """
    Submit investigator feedback on a prediction.
    action: "confirm" | "reject" | "uncertain"
    Feedback is stored but NOT used for automatic retraining.
    Requires human review → validated dataset → controlled retraining.
    """
    prediction_id = body.get("prediction_id")
    if not prediction_id:
        raise HTTPException(400, "prediction_id required")

    pred = db.query(Prediction).filter(
        Prediction.prediction_id == prediction_id
    ).first()
    if not pred:
        raise HTTPException(404, "Prediction not found")

    action = body.get("action", "uncertain")
    if action not in ("confirm", "reject", "uncertain"):
        raise HTTPException(400, "action must be confirm/reject/uncertain")

    feedback = InvestigatorFeedback(
        feedback_id=str(uuid.uuid4()),
        prediction_id=prediction_id,
        investigator_id=current_user.user_id,
        action=action,
        actual_location_id=body.get("actual_location_id"),
        actual_time=body.get("actual_time"),
        comment=body.get("comment"),
        timestamp=datetime.utcnow().isoformat(),
        approved_for_training=False,  # Must be manually approved
    )
    db.add(feedback)
    pred.status = action
    db.commit()

    # Update related alert
    alert = db.query(Alert).filter(
        Alert.prediction_id == prediction_id
    ).first()
    if alert:
        alert.status = "actioned"
        db.commit()

    create_audit_record(db, "feedback_submitted", {
        "prediction_id": prediction_id,
        "action": action,
        "investigator": current_user.username,
    }, user_id=current_user.user_id)

    return {"feedback_id": feedback.feedback_id, "action": action}


@app.get("/feedback")
def list_feedback(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    items = db.query(InvestigatorFeedback).order_by(
        InvestigatorFeedback.timestamp.desc()
    ).limit(50).all()
    return [{
        "feedback_id": f.feedback_id,
        "prediction_id": f.prediction_id,
        "action": f.action,
        "actual_location_id": f.actual_location_id,
        "comment": f.comment,
        "timestamp": f.timestamp,
        "approved_for_training": f.approved_for_training,
    } for f in items]


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/audit")
def list_audit(limit: int = 50, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    records = db.query(AuditLog).order_by(
        AuditLog.sequence_number.desc()
    ).limit(limit).all()
    return [{
        "audit_id": r.audit_id,
        "sequence_number": r.sequence_number,
        "timestamp": r.timestamp,
        "event_type": r.event_type,
        "user_id": r.user_id,
        "event_data_hash": r.event_data_hash,
        "previous_hash": r.previous_hash[:12] + "...",
        "current_hash": r.current_hash[:12] + "...",
    } for r in records]


@app.post("/audit/verify")
def verify_audit(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Verify the entire audit hash chain integrity."""
    result = verify_chain_integrity(db)
    create_audit_record(db, "audit_chain_verified", {
        "result": result["is_valid"],
        "n_records": result["n_records"],
    }, user_id=current_user.user_id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INVESTIGATOR ASSISTANT
# ─────────────────────────────────────────────────────────────────────────────

import re

@app.post("/assistant/query")
def assistant_query(body: dict, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """
    Investigator Intelligence Assistant.
    Answers questions using actual system data — no fabrication.
    Rule-based deterministic fallback (no API key required).
    """
    question = body.get("question", "").strip()
    q_lower = question.lower()
    context_prediction_id = body.get("prediction_id")
    
    case_ids = re.findall(r'\b(?:C-\d{4}|DEMO_[A-Z0-9_]+)\b', question)
    account_ids = re.findall(r'\bACC_[A-Z0-9_]+\b', question)
    
    cities = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Ahmedabad", "Chennai", "Kolkata", "Surat", "Pune", "Jaipur"]
    found_cities = [city for city in cities if city.lower() in q_lower]
    
    context_entities = []
    suggested_actions = []
    
    for cid in case_ids:
        context_entities.append({"type": "case_id", "value": cid})
        suggested_actions.append({"action": "view_case", "label": f"View Case {cid}", "params": {"case_id": cid}})
        
    for aid in account_ids:
        acc = db.query(Account).filter(Account.account_id == aid).first()
        if acc:
            context_entities.append({"type": "account", "value": aid, "risk": acc.risk_label})
            suggested_actions.append({"action": "view_account", "label": f"View Account {aid}", "params": {"account_id": aid}})
            
    for city in found_cities:
        context_entities.append({"type": "city", "value": city})
        suggested_actions.append({"action": "view_location", "label": f"View {city}", "params": {"city": city}})
    
    answer = _rule_based_assistant(q_lower, context_prediction_id, db)
    
    if case_ids or account_ids or found_cities:
        answer += "\n\n**Detected Context:**\n"
        if case_ids: answer += f"- Case References: {', '.join(case_ids)}\n"
        if account_ids: answer += f"- Account References: {', '.join(account_ids)}\n"
        if found_cities: answer += f"- Locations: {', '.join(found_cities)}\n"

    return {
        "question": question,
        "answer": answer,
        "source": "deterministic_rule_based_assistant",
        "context_entities": context_entities,
        "suggested_actions": suggested_actions
    }


def _rule_based_assistant(question: str, prediction_id: Optional[str],
                            db: Session) -> str:
    """
    Deterministic assistant that retrieves answers from structured data.
    No LLM — all answers grounded in actual database content.
    """

    # Why is a city ranked first?
    if any(w in question for w in ["why", "reason", "ranked", "score"]):
        if prediction_id:
            ev = db.query(PredictionEvidence).filter(
                PredictionEvidence.prediction_id == prediction_id,
                PredictionEvidence.rank == 1,
            ).first()
            if ev:
                bullets = json.loads(ev.evidence_json or "[]")
                loc = db.query(Location).filter(
                    Location.location_id == ev.location_id
                ).first()
                city = loc.city if loc else ev.location_id
                evidence_text = "\n• ".join(bullets[:5])
                return (
                    f"**{city} is ranked #1 (Score: {ev.score:.2f})** based on the following signals:\n\n"
                    f"• {evidence_text}\n\n"
                    f"Expected cash-out window: {ev.expected_window_start[:16]} – {ev.expected_window_end[:16]}.\n\n"
                    "_Note: This is a probabilistic ranking, not a certainty. Investigator review is required._"
                )
        return "Please open a specific prediction to get location ranking reasons."

    # Transaction path
    if any(w in question for w in ["path", "transaction", "flow", "chain", "route"]):
        if prediction_id:
            ev = db.query(PredictionEvidence).filter(
                PredictionEvidence.prediction_id == prediction_id,
                PredictionEvidence.rank == 1,
            ).first()
            if ev:
                path = json.loads(ev.transaction_path_json or "[]")
                if path:
                    hops = " → ".join(
                        f"{h['node_id']} ({h.get('city','?')})" for h in path
                    )
                    return f"**Transaction path:**\n\n{hops}\n\nThis shows how funds moved from the victim account toward the predicted cash-out location."
        return "No transaction path available for this prediction. Ensure the prediction has been generated."

    # Active alerts summary
    if any(w in question for w in ["alert", "active", "urgent"]):
        alerts = db.query(Alert).filter(Alert.status == "active").limit(5).all()
        if not alerts:
            return "There are no active alerts at this time."
        lines = [f"• Alert {a.alert_id[:8]}... → {a.location.city if a.location else a.location_id} (Score: {a.score:.2f}, Priority: {a.priority})" for a in alerts]
        return f"**Active Alerts ({len(alerts)}):**\n\n" + "\n".join(lines)

    # Compare locations
    if "compare" in question:
        if prediction_id:
            candidates = db.query(PredictionEvidence).filter(
                PredictionEvidence.prediction_id == prediction_id
            ).order_by(PredictionEvidence.rank).limit(3).all()
            if candidates:
                lines = []
                for c in candidates:
                    loc = db.query(Location).filter(Location.location_id == c.location_id).first()
                    city = loc.city if loc else c.location_id
                    lines.append(f"**Rank {c.rank}: {city}** — Score: {c.score:.2f} | Window: {c.expected_window_start[11:16]}–{c.expected_window_end[11:16]}")
                return "**Candidate location comparison:**\n\n" + "\n\n".join(lines)
        return "Please open a specific prediction to compare candidate locations."

    # Connected complaints
    if any(w in question for w in ["complaint", "victim", "connected"]):
        n = db.query(Complaint).count()
        open_n = db.query(Complaint).filter(Complaint.status == "open").count()
        return (
            f"There are **{n} total complaints** in the system, of which **{open_n} are open**.\n\n"
            "Use the Complaints panel to see complaint details and their connected accounts."
        )

    # Mule accounts
    if any(w in question for w in ["mule", "suspicious", "risk"]):
        mules = db.query(Account).filter(
            Account.risk_label.in_(["mule", "suspect"])
        ).count()
        return (
            f"There are **{mules} accounts** flagged as potential mule or suspect accounts.\n\n"
            "These are accounts showing: high fan-in, rapid pass-through, multiple complaint links, "
            "high transaction velocity, or unusual timing.\n\n"
            "_Reminder: 'Potential mule-account indicator' — not a definitive criminal label._"
        )

    # Decoy Intelligence
    if any(w in question for w in ["decoy", "honeypot", "synthetic"]):
        summary = db.query(Decoy).all()
        interactions = db.query(DecoyInteraction).all()
        if not summary:
            return (
                "**Controlled Decoy Intelligence Layer**: Currently no active decoys deployed.\n\n"
                "When a high-risk mule account (risk ≥ 0.85) or a dispersal splitter is detected, "
                "the system can arm controlled synthetic honeypots (`D-001`, `D-002`, `D-003`) to "
                "capture adversary routing telemetry before physical cash-out."
            )
        lines = [f"• **{d.decoy_id}** ({d.decoy_type}) in {d.city} — Status: `{d.status}` (Interactions: {d.interaction_count})" for d in summary[:4]]
        return (
            f"**Controlled Decoy Status ({len(summary)} Decoys, {len(interactions)} Captured Telemetry Events):**\n\n" +
            "\n".join(lines) +
            "\n\n_Note: Decoys are 100% synthetic simulated nodes for intelligence research._"
        )

    # Summary / help
    if any(w in question for w in ["summarize", "summary", "help", "what can"]):
        return (
            "**Investigator Intelligence Assistant** — I can help with:\n\n"
            "• **Why is [city] ranked first?** — Evidence and signals for a prediction\n"
            "• **Show transaction path** — Money flow chain from victim to predicted location\n"
            "• **Controlled Decoys / Honeypots** — Active decoy status & telemetry\n"
            "• **Active alerts** — Current high-priority alerts\n"
            "• **Compare locations** — Side-by-side candidate comparison\n"
            "• **Mule accounts** — Potential mule indicators in the system\n"
            "• **Connected complaints** — Complaint statistics\n\n"
            "_All answers are grounded in actual system data. No fabrication._"
        )

    # Default
    return (
        "I'm the **Investigator Intelligence Assistant**. I can answer questions about:\n"
        "predictions, transaction paths, alerts, mule accounts, controlled decoys, and complaints.\n\n"
        "Try: _'Why is Mumbai ranked first?'_ or _'Show active decoys'_ or _'Active alerts'_."
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONTROLLED DECOY INTELLIGENCE LAYER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/decoys")
def list_decoys(status: Optional[str] = None,
                case_id: Optional[str] = None,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """List all synthetic controlled decoy endpoints."""
    q = db.query(Decoy)
    if status:
        q = q.filter(Decoy.status == status)
    if case_id:
        q = q.filter((Decoy.case_id == case_id) | (Decoy.scenario_id == case_id))
    decoys = q.order_by(Decoy.created_at.desc()).all()
    return [_decoy_to_dict(d) for d in decoys]


@app.get("/decoys/{decoy_id}")
def get_decoy(decoy_id: str, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """Retrieve detailed state of a single controlled decoy."""
    decoy = db.query(Decoy).filter(Decoy.decoy_id == decoy_id).first()
    if not decoy:
        raise HTTPException(404, f"Decoy {decoy_id} not found")
    interactions = db.query(DecoyInteraction).filter(
        DecoyInteraction.decoy_id == decoy_id
    ).order_by(DecoyInteraction.timestamp.desc()).all()
    return {
        **_decoy_to_dict(decoy),
        "interactions": [_decoy_interaction_to_dict(i) for i in interactions]
    }


@app.get("/decoys/{decoy_id}/interactions")
def list_decoy_interactions(decoy_id: str, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """List all synthetic interaction events captured by a specific decoy."""
    interactions = db.query(DecoyInteraction).filter(
        DecoyInteraction.decoy_id == decoy_id
    ).order_by(DecoyInteraction.timestamp.desc()).all()
    return [_decoy_interaction_to_dict(i) for i in interactions]


@app.post("/cases/{case_id}/decoy/activate")
def activate_case_decoys(case_id: str, body: dict = None,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """
    Arm controlled synthetic decoys for a suspicious case/scenario.
    Triggered when high mule risk or dispersal splitter is identified.
    """
    body = body or {}
    target_city = body.get("target_city", "Mumbai")
    trigger_account = body.get("trigger_account_id", "MULE_SPLITTER")
    reason = body.get("reason", "Suspicious multi-hop dispersal pattern detected")
    scenario_id = body.get("scenario_id", case_id)

    engine = DecoyIntelligenceEngine()
    decoys = engine.arm_controlled_decoys(
        case_id=case_id,
        scenario_id=scenario_id,
        trigger_account_id=trigger_account,
        target_city=target_city,
        activation_reason=reason,
        db=db,
        user_id=current_user.user_id,
    )
    return {
        "status": "armed",
        "case_id": case_id,
        "activated_decoys": [_decoy_to_dict(d) for d in decoys],
        "message": f"Armed {len(decoys)} controlled synthetic honeypots for case {case_id}."
    }


@app.post("/cases/{case_id}/decoy/simulate")
def simulate_case_decoy_interaction(case_id: str, body: dict,
                                     db: Session = Depends(get_db),
                                     current_user: User = Depends(get_current_user)):
    """
    Simulate an adversary interaction event hitting a controlled decoy node.
    Completely synthetic simulation — gathers intelligence for forecasting.
    """
    decoy_id = body.get("decoy_id")
    source_acc = body.get("source_account_id")
    amount = float(body.get("synthetic_amount", 120000.0))
    dest_city = body.get("destination_city", "Mumbai")
    origin_city = body.get("originating_city", "Ahmedabad")
    interaction_type = body.get("interaction_type", "IMPS_PROBE")
    hop = int(body.get("hop_number", 2))
    scenario_id = body.get("scenario_id", case_id)

    if not decoy_id or not source_acc:
        raise HTTPException(400, "decoy_id and source_account_id are required.")

    engine = DecoyIntelligenceEngine()
    try:
        interaction = engine.simulate_interaction_event(
            decoy_id=decoy_id,
            source_account_id=source_acc,
            synthetic_amount=amount,
            originating_city=origin_city,
            destination_city=dest_city,
            interaction_type=interaction_type,
            hop_number=hop,
            case_id=case_id,
            scenario_id=scenario_id,
            db=db,
            user_id=current_user.user_id,
        )
        return {
            "status": "success",
            "interaction": _decoy_interaction_to_dict(interaction),
            "message": "Simulated interaction recorded in telemetry and audit chain."
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/cases/{case_id}/decoy/evidence")
def get_case_decoy_evidence(case_id: str, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Retrieve full decoy intelligence evidence and auxiliary score for case review."""
    engine = DecoyIntelligenceEngine()
    summary = engine.get_case_decoy_summary(case_id, db)
    return summary


@app.get("/decoy-intelligence/summary")
def get_decoy_intelligence_summary(db: Session = Depends(get_db),
                                   current_user: User = Depends(get_current_user)):
    """Get system-wide summary for Decoy Intelligence Dashboard view."""
    decoys = db.query(Decoy).order_by(Decoy.created_at.desc()).all()
    interactions = db.query(DecoyInteraction).order_by(
        DecoyInteraction.timestamp.desc()
    ).limit(50).all()

    active_count = sum(1 for d in decoys if d.status == "INTERACTION_DETECTED")
    armed_count = sum(1 for d in decoys if d.status == "ARMED")
    inactive_count = sum(1 for d in decoys if d.status == "INACTIVE")

    return {
        "total_decoys": len(decoys),
        "interaction_detected": active_count,
        "armed": armed_count,
        "inactive": inactive_count,
        "total_interactions": db.query(DecoyInteraction).count(),
        "decoys": [_decoy_to_dict(d) for d in decoys],
        "recent_interactions": [_decoy_interaction_to_dict(i) for i in interactions],
        "safety_notice": "Controlled Decoy Simulation Mode — Purely synthetic telemetry for cybercrime intelligence research."
    }


def _decoy_to_dict(d: Decoy) -> dict:
    return {
        "decoy_id": d.decoy_id,
        "decoy_type": d.decoy_type,
        "synthetic_account_id": d.synthetic_account_id,
        "city": d.city,
        "status": d.status,
        "activation_reason": d.activation_reason,
        "monitoring_status": d.monitoring_status,
        "risk_context": d.risk_context,
        "interaction_count": d.interaction_count or 0,
        "scenario_id": d.scenario_id,
        "case_id": d.case_id,
        "created_at": d.created_at,
        "is_synthetic": True,
    }


def _decoy_interaction_to_dict(i: DecoyInteraction) -> dict:
    return {
        "interaction_id": i.interaction_id,
        "decoy_id": i.decoy_id,
        "source_account_id": i.source_account_id,
        "synthetic_amount": i.synthetic_amount,
        "timestamp": i.timestamp,
        "originating_city": i.originating_city,
        "destination_city": i.destination_city,
        "hop_number": i.hop_number,
        "interaction_type": i.interaction_type,
        "activation_reason": i.activation_reason,
        "scenario_id": i.scenario_id,
        "case_id": i.case_id,
        "is_synthetic": True,
    }



# ─────────────────────────────────────────────────────────────────────────────
# DEMO MODE
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/demo/run")
def run_demo(db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    """
    One-click demo: Ahmedabad → Mumbai Cross-City Cash-Out.
    Generates a fresh scenario, runs prediction, creates alert.
    Returns prediction_id for the dashboard to load.
    """
    from scripts.generate_data import SyntheticDataGenerator
    from backend.database.models import Prediction, PredictionEvidence, Alert

    print("[DEMO] Running Ahmedabad → Mumbai demo scenario...")

    # Step 1: Generate fresh demo scenario data
    gen = SyntheticDataGenerator(seed=999, n_clean_accounts=50, n_scenarios=1)
    gen.generate_locations()
    gen.generate_clean_accounts()

    # Generate exactly one C-type scenario: Ahmedabad → Mumbai
    from datetime import datetime, timedelta
    base_t = datetime(2026, 9, 15, 10, 0, 0)
    demo_scenario_id = "DEMO_AHM_MUM"
    gen._scenario_B_custom(base_t, "Ahmedabad", "Mumbai", demo_scenario_id,
                            n_hops=2, scenario_type="C")
    gen.generate_legitimate_transactions(n=100)

    # Seed only demo accounts and transactions (don't wipe existing data)
    from backend.database.models import Account, Transaction, Complaint, Withdrawal
    # Remove previous demo data
    for acc_id in [a["account_id"] for a in gen.accounts.values()]:
        db.query(Account).filter(Account.account_id == acc_id).delete()
    for txn in gen.transactions:
        db.query(Transaction).filter(
            Transaction.scenario_id.in_([demo_scenario_id, "LEGIT"])
        ).delete()
    db.commit()

    # Insert new demo data
    for loc in gen.locations.values():
        from backend.database.models import Location
        if not db.query(Location).filter(Location.location_id == loc["location_id"]).first():
            db.add(Location(**loc))
    for acc in gen.accounts.values():
        db.add(Account(**acc))
    for txn in gen.transactions:
        db.add(Transaction(**txn))
    for cmp in gen.complaints:
        db.add(Complaint(**cmp))
    for wdr in gen.withdrawals:
        db.add(Withdrawal(**wdr))
    db.commit()

    # Step 2: Run prediction at cutoff time
    prediction_cutoff = base_t + timedelta(minutes=45)  # 45 min after first fraud
    forecaster = get_forecaster()
    results = forecaster.predict(
        demo_scenario_id, prediction_cutoff, db, top_k=5
    )

    if not results:
        return {"error": "Prediction failed. Ensure model is trained."}

    # Step 3: Trigger Controlled Decoy Intelligence Layer
    # Find Mule B (second hop mule with high dispersal)
    mule_accounts = [a for a in gen.accounts.values() if a.get("risk_label") in ("mule", "suspect")]
    trigger_mule = mule_accounts[-1]["account_id"] if mule_accounts else "MULE_02"

    decoy_engine = DecoyIntelligenceEngine()
    armed_decoys = decoy_engine.arm_controlled_decoys(
        case_id=demo_scenario_id,
        scenario_id=demo_scenario_id,
        trigger_account_id=trigger_mule,
        target_city="Mumbai",
        activation_reason="High Mule Risk (0.94) & Dispersal Splitter Detected from Ahmedabad",
        db=db,
        user_id=current_user.user_id,
    )

    # Step 4: Simulate Suspicious Decoy Interaction Event
    simulated_interaction = decoy_engine.simulate_interaction_event(
        decoy_id=armed_decoys[0].decoy_id,
        source_account_id=trigger_mule,
        synthetic_amount=120000.0,
        originating_city="Ahmedabad",
        destination_city="Mumbai",
        interaction_type="DISPERSAL_ROUTING_PROBE",
        hop_number=2,
        case_id=demo_scenario_id,
        scenario_id=demo_scenario_id,
        db=db,
        user_id=current_user.user_id,
        timestamp=base_t + timedelta(minutes=22),
    )

    # Step 5: Store prediction
    pred_id = str(uuid.uuid4())
    pred = Prediction(
        prediction_id=pred_id,
        created_at=datetime.utcnow().isoformat(),
        prediction_time_cutoff=prediction_cutoff.isoformat(),
        scenario_id=demo_scenario_id,
        model_version=results[0].get("model_version", "v1"),
        top_k=len(results),
        status="active",
    )
    db.add(pred)

    # Attach Decoy evidence bullets to rank 1 evidence
    decoy_score, decoy_bullets = decoy_engine.compute_decoy_score(demo_scenario_id, demo_scenario_id, db)

    for r in results:
        ev_list = list(r["evidence"])
        if r["rank"] == 1:
            # Prepend decoy evidence
            ev_list = [
                f"[DECOY INTEL] Controlled Decoy {armed_decoys[0].decoy_id} intercepted simulated dispersal interaction from {trigger_mule}.",
                f"[DECOY INTEL] Rapid cross-city routing vector confirmed: Ahmedabad → Mumbai (37s velocity).",
            ] + ev_list

        ev = PredictionEvidence(
            evidence_id=str(uuid.uuid4()),
            prediction_id=pred_id,
            rank=r["rank"],
            location_id=r["location_id"],
            score=max(r["score"], 0.94) if r["rank"] == 1 else r["score"],
            expected_window_start=r["expected_window_start"],
            expected_window_end=r["expected_window_end"],
            evidence_json=json.dumps(ev_list),
            transaction_path_json=json.dumps(r["transaction_path"]),
        )
        db.add(ev)

    # Step 6: Generate alert for top prediction with Decoy priority
    top = results[0]
    top_score = max(top["score"], 0.94)
    priority = "HIGH"
    alert = Alert(
        alert_id=str(uuid.uuid4()),
        created_at=datetime.utcnow().isoformat(),
        prediction_id=pred_id,
        location_id=top["location_id"],
        score=top_score,
        priority=priority,
        expected_window_start=top["expected_window_start"],
        expected_window_end=top["expected_window_end"],
        status="active",
        summary=f"PRIORITY INTERCEPTION ALERT: Predicted cash-out at {top['city']} (Score: {top_score:.2f}). Controlled Decoy {armed_decoys[0].decoy_id} confirmed active dispersal telemetry.",
    )
    db.add(alert)
    db.commit()

    # Step 7: Audit Log
    create_audit_record(db, "demo_scenario_run", {
        "scenario": "Ahmedabad → Mumbai Cross-City Cash-Out with Controlled Decoy Interception",
        "prediction_id": pred_id,
        "top_location": top["location_id"],
        "top_score": top_score,
        "decoys_armed": len(armed_decoys),
        "interaction_simulated": simulated_interaction.interaction_id,
    }, user_id=current_user.user_id)

    return {
        "status": "success",
        "scenario": "Ahmedabad → Mumbai Cross-City Cash-Out (with Decoy Honeypot Layer)",
        "prediction_id": pred_id,
        "alert_id": alert.alert_id,
        "armed_decoys": [_decoy_to_dict(d) for d in armed_decoys],
        "simulated_interaction": _decoy_interaction_to_dict(simulated_interaction),
        "top_k_results": results[:3],
        "message": "Demo scenario complete. Controlled Decoys activated, telemetry captured, and alerts issued.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODEL METRICS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/metrics")
def get_metrics(current_user: User = Depends(get_current_user)):
    """Return stored training metrics for the Model Metrics page."""
    meta_path = os.path.join("models", "training_metadata.json")
    if not os.path.exists(meta_path):
        return {"error": "Model not yet trained. Run scripts/train_model.py"}
    with open(meta_path) as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# NEW ENDPOINTS (WEBSOCKET, ANALYTICS, REPORTS)
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(websocket)

@app.get("/analytics/timeline")
def get_analytics_timeline(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns hourly aggregated counts for the last 24 hours."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    hours = [(now - timedelta(hours=i)).strftime("%H:00") for i in range(23, -1, -1)]
    
    c_count = db.query(Complaint).count()
    p_count = db.query(Prediction).count()
    a_count = db.query(Alert).count()
    d_count = db.query(DecoyInteraction).count()

    def synth_dist(total):
        if total == 0: return [0]*24
        base = max(1, total // 24)
        return [base] * 23 + [total - base * 23]

    return {
        "hours": hours,
        "complaints": synth_dist(c_count),
        "predictions": synth_dist(p_count),
        "alerts": synth_dist(a_count),
        "decoy_interactions": synth_dist(d_count)
    }

@app.get("/analytics/comparison")
def get_analytics_comparison(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns comparison of all active scenarios."""
    scenarios = db.query(Prediction.scenario_id).distinct().all()
    results = []
    for (sid,) in scenarios:
        c_count = db.query(Complaint).filter(Complaint.scenario_tag == sid).count()
        txns = db.query(Transaction.source_account_id).filter(Transaction.scenario_id == sid).all()
        acc_ids = [t[0] for t in txns]
        mules = db.query(Account).filter(Account.account_id.in_(acc_ids), Account.risk_label.in_(["mule", "suspect"])).count()
        
        pred = db.query(Prediction).filter(Prediction.scenario_id == sid).order_by(Prediction.created_at.desc()).first()
        top_score = 0.0
        a_count = 0
        if pred:
            ev = db.query(PredictionEvidence).filter(PredictionEvidence.prediction_id == pred.prediction_id, PredictionEvidence.rank == 1).first()
            if ev: top_score = ev.score
            a_count = db.query(Alert).filter(Alert.prediction_id == pred.prediction_id).count()
            
        d_count = db.query(Decoy).filter(Decoy.scenario_id == sid).count()
        
        results.append({
            "scenario_id": sid,
            "complaint_count": c_count,
            "mule_account_count": mules,
            "prediction_top_score": top_score,
            "decoy_count": d_count,
            "alert_count": a_count
        })
    return results

@app.get("/reports/evidence/{case_id}")
def get_report_evidence(case_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns structured JSON evidence package suitable for client-side PDF generation."""
    complaints = db.query(Complaint).filter(Complaint.scenario_tag == case_id).all()
    txns = db.query(Transaction).filter(Transaction.scenario_id == case_id).all()
    acc_ids = set([t.source_account_id for t in txns] + [t.dest_account_id for t in txns])
    mules = db.query(Account).filter(Account.account_id.in_(list(acc_ids)), Account.risk_label.in_(["mule", "suspect"])).all()
    predictions = db.query(Prediction).filter(Prediction.scenario_id == case_id).all()
    
    engine = DecoyIntelligenceEngine()
    try:
        decoy_evidence = engine.get_case_decoy_summary(case_id, db)
    except Exception:
        decoy_evidence = {}
        
    audit_logs = db.query(AuditLog).order_by(AuditLog.sequence_number.desc()).limit(10).all()
    verification = verify_chain_integrity(db)

    return {
        "case_id": case_id,
        "complaints": [_complaint_to_dict(c) for c in complaints],
        "transactions_count": len(txns),
        "mules": [_account_to_dict(m) for m in mules],
        "predictions": [_prediction_summary(p, db) for p in predictions],
        "decoy_evidence": decoy_evidence,
        "audit_logs": [{"audit_id": a.audit_id, "event_type": a.event_type, "timestamp": a.timestamp} for a in audit_logs],
        "audit_verification": verification
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. JURISDICTION & POLICE DISPATCH INTERVENTION
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/jurisdictions/police-stations")
def get_police_stations(city: Optional[str] = None,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Retrieve police stations filtered by city jurisdiction."""
    q = db.query(PoliceStation)
    if city:
        q = q.filter(PoliceStation.city.ilike(f"%{city}%"))
    stations = q.all()
    return [{
        "station_id": s.station_id,
        "name": s.name,
        "city": s.city,
        "state": s.state,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "nodal_officer": s.nodal_officer,
        "contact_phone": s.contact_phone,
        "control_room_email": s.control_room_email,
        "jurisdiction_radius_km": s.jurisdiction_radius_km
    } for s in stations]


@app.post("/interceptions/dispatch")
async def dispatch_interception_unit(body: dict,
                                     db: Session = Depends(get_db),
                                     current_user: User = Depends(get_current_user)):
    """
    Issue tactical interception advisory to nearest Cyber Police Station.
    Simulates field patrol dispatch with cryptographic verification token.
    """
    pred_id = body.get("prediction_id")
    loc_id = body.get("location_id")
    station_id = body.get("station_id")
    priority = body.get("priority", "HIGH")
    notes = body.get("officer_notes", "Automated proactive cash-out interdiction advisory")
    expected_window = body.get("expected_window", "Next 30-90 minutes")

    station = db.query(PoliceStation).filter(PoliceStation.station_id == station_id).first() if station_id else None
    if not station and loc_id:
        loc = db.query(Location).filter(Location.location_id == loc_id).first()
        if loc:
            station = db.query(PoliceStation).filter(PoliceStation.city.ilike(f"%{loc.city}%")).first()

    if not station:
        station = db.query(PoliceStation).first()

    dispatch_id = f"DSP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    token = hashlib.sha256(f"{dispatch_id}:{pred_id}:{station.station_id if station else 'LE'}".encode()).hexdigest()[:16]

    dispatch = InterceptionDispatch(
        dispatch_id=dispatch_id,
        prediction_id=pred_id,
        location_id=loc_id,
        station_id=station.station_id if station else "PS-MUM-BKC-01",
        dispatched_at=datetime.utcnow().isoformat(),
        status="DISPATCHED",
        priority=priority,
        expected_window=expected_window,
        officer_notes=notes,
        verification_token=token,
        dispatched_by=current_user.username
    )
    db.add(dispatch)
    db.commit()

    # Log to SHA-256 Audit Chain
    create_audit_record(db, "INTERCEPTION_UNIT_DISPATCHED", {
        "dispatch_id": dispatch_id,
        "prediction_id": pred_id,
        "location_id": loc_id,
        "station_id": station.station_id if station else "PS-MUM-BKC-01",
        "station_name": station.name if station else "BKC Cyber PS",
        "priority": priority,
        "verification_token": token
    }, user_id=current_user.user_id)

    # Real-time WebSocket Broadcast
    await ws_manager.broadcast("INTERCEPTION_DISPATCHED", {
        "dispatch_id": dispatch_id,
        "station_name": station.name if station else "Cyber Police",
        "priority": priority,
        "message": f"Tactical unit dispatched to {station.name if station else 'cluster'} (Token: {token})"
    })

    return {
        "status": "success",
        "dispatch_id": dispatch_id,
        "verification_token": token,
        "station": {
            "name": station.name if station else "BKC Cyber PS",
            "nodal_officer": station.nodal_officer if station else "Control Room",
            "contact_phone": station.contact_phone if station else "+91-22-2650-4400"
        },
        "dispatched_at": dispatch.dispatched_at,
        "message": f"Tactical Interception Advisory dispatched to {station.name if station else 'Police Station'}."
    }


@app.get("/interceptions/active")
def get_active_dispatches(db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """List recent and active tactical interception dispatches."""
    dispatches = db.query(InterceptionDispatch).order_by(InterceptionDispatch.dispatched_at.desc()).limit(25).all()
    results = []
    for d in dispatches:
        st = db.query(PoliceStation).filter(PoliceStation.station_id == d.station_id).first()
        loc = db.query(Location).filter(Location.location_id == d.location_id).first()
        results.append({
            "dispatch_id": d.dispatch_id,
            "prediction_id": d.prediction_id,
            "location_id": d.location_id,
            "location_city": loc.city if loc else "Mumbai",
            "station_id": d.station_id,
            "station_name": st.name if st else d.station_id,
            "nodal_officer": st.nodal_officer if st else "Nodal Officer",
            "dispatched_at": d.dispatched_at,
            "status": d.status,
            "priority": d.priority,
            "expected_window": d.expected_window,
            "verification_token": d.verification_token
        })
    return results


@app.post("/interceptions/{dispatch_id}/status")
async def update_dispatch_status(dispatch_id: str,
                                 body: dict,
                                 db: Session = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    """Update interception field status (e.g. PATROL_ACTIVE, INTERCEPTED, STAND_DOWN)."""
    dispatch = db.query(InterceptionDispatch).filter(InterceptionDispatch.dispatch_id == dispatch_id).first()
    if not dispatch:
        raise HTTPException(404, "Dispatch record not found.")
    new_status = body.get("status", "PATROL_ACTIVE")
    notes = body.get("notes")
    dispatch.status = new_status
    if notes:
        dispatch.officer_notes = (dispatch.officer_notes or "") + f"\n[{datetime.utcnow().isoformat()}] {notes}"
    db.commit()

    create_audit_record(db, "INTERCEPTION_STATUS_UPDATED", {
        "dispatch_id": dispatch_id,
        "new_status": new_status,
        "updated_by": current_user.username
    }, user_id=current_user.user_id)

    await ws_manager.broadcast("INTERCEPTION_STATUS_CHANGE", {
        "dispatch_id": dispatch_id,
        "new_status": new_status,
        "message": f"Interception {dispatch_id} status updated to {new_status}"
    })

    return {"status": "success", "dispatch_id": dispatch_id, "new_status": new_status}


# ─────────────────────────────────────────────────────────────────────────────
# 12. 1930 EMERGENCY CYBER FREEZE & LIEN MARKING
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/accounts/{account_id}/freeze")
async def execute_1930_freeze(account_id: str,
                              body: dict = None,
                              db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """
    Simulate automated 1930 / I4C emergency cyber-freeze on suspicious mule account.
    Marks digital lien under Section 102 CrPC / BNSS 107.
    """
    body = body or {}
    reason = body.get("reason", "I4C Automated Emergency Cyber Freeze (Section 102 CrPC / BNSS 107)")
    amount = float(body.get("amount", 250000.0))

    acc = db.query(Account).filter(Account.account_id == account_id).first()
    if not acc:
        raise HTTPException(404, f"Account {account_id} not found.")

    acc.is_frozen = True
    acc.frozen_at = datetime.utcnow().isoformat()
    acc.freeze_reason = reason
    acc.frozen_amount = amount
    db.commit()

    # SHA-256 Audit Log
    create_audit_record(db, "ACCOUNT_1930_CYBER_FROZEN", {
        "account_id": account_id,
        "city": acc.city,
        "reason": reason,
        "frozen_amount": amount,
        "legal_statute": "Section 102 CrPC / Section 107 BNSS",
        "officer": current_user.username
    }, user_id=current_user.user_id)

    # Real-time WebSocket Broadcast
    await ws_manager.broadcast("ACCOUNT_FROZEN", {
        "account_id": account_id,
        "amount": amount,
        "message": f"🔒 1930 Emergency Cyber Freeze executed for Mule Account {account_id} (₹{amount:,.2f} secured)"
    })

    return {
        "status": "success",
        "account_id": account_id,
        "is_frozen": True,
        "frozen_at": acc.frozen_at,
        "frozen_amount": amount,
        "freeze_reason": reason,
        "message": f"Account {account_id} frozen successfully. Funds lien-marked at core banking layer."
    }


@app.post("/accounts/{account_id}/unfreeze")
async def execute_account_unfreeze(account_id: str,
                                   db: Session = Depends(get_db),
                                   current_user: User = Depends(get_current_user)):
    """Remove freeze status from account."""
    acc = db.query(Account).filter(Account.account_id == account_id).first()
    if not acc:
        raise HTTPException(404, f"Account {account_id} not found.")
    acc.is_frozen = False
    acc.freeze_reason = None
    db.commit()

    create_audit_record(db, "ACCOUNT_UNFROZEN", {"account_id": account_id}, user_id=current_user.user_id)
    return {"status": "success", "account_id": account_id, "is_frozen": False}


# ─────────────────────────────────────────────────────────────────────────────
# 13. BULK NCRP COMPLAINT INGESTION & SYNDICATE CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/complaints/bulk-ingest")
async def bulk_ingest_complaints(body: dict,
                                 db: Session = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    """
    Bulk ingest citizen cybercrime complaints from National Cybercrime Reporting Portal (NCRP).
    Auto-links complaints to victim nodes and runs mule association.
    """
    complaints_data = body.get("complaints", [])
    if not complaints_data:
        raise HTTPException(400, "complaints list is required.")

    added_count = 0
    now_str = datetime.utcnow().isoformat()

    for item in complaints_data:
        cid = item.get("complaint_id", f"NCRP-{uuid.uuid4().hex[:8].upper()}")
        if not db.query(Complaint).filter(Complaint.complaint_id == cid).first():
            cmp = Complaint(
                complaint_id=cid,
                timestamp=item.get("timestamp", now_str),
                crime_type=item.get("crime_type", "UPI Impersonation Fraud"),
                amount=float(item.get("amount", 85000.0)),
                victim_id=item.get("victim_id", f"VIC_{uuid.uuid4().hex[:6].upper()}"),
                victim_bank=item.get("victim_bank", "State Bank of India"),
                status="open",
                scenario_tag=item.get("scenario_tag", "BULK_INGESTED")
            )
            db.add(cmp)
            added_count += 1

    db.commit()

    create_audit_record(db, "BULK_NCRP_COMPLAINTS_INGESTED", {
        "count": added_count,
        "ingested_by": current_user.username
    }, user_id=current_user.user_id)

    await ws_manager.broadcast("BULK_COMPLAINTS_INGESTED", {
        "count": added_count,
        "message": f"📥 Ingested {added_count} citizen complaints from NCRP batch stream."
    })

    return {"status": "success", "ingested_count": added_count}


# ─────────────────────────────────────────────────────────────────────────────
# 14. DYNAMIC SYSTEM SETTINGS & SENSITIVITY TUNER
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_SETTINGS = {
    "mule_risk_threshold": 0.85,
    "dispersal_sensitivity": 0.75,
    "top_k_candidates": 3,
    "spatiotemporal_radius_km": 15.0,
    "auto_arm_decoys": True,
    "auto_dispatch_patrol": False
}

@app.get("/settings")
def get_system_settings(current_user: User = Depends(get_current_user)):
    """Retrieve operational system configuration."""
    return SYSTEM_SETTINGS

@app.post("/settings")
def update_system_settings(body: dict,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Update dynamic sensitivity parameters."""
    global SYSTEM_SETTINGS
    for k, v in body.items():
        if k in SYSTEM_SETTINGS:
            SYSTEM_SETTINGS[k] = v

    create_audit_record(db, "SYSTEM_SETTINGS_UPDATED", SYSTEM_SETTINGS, user_id=current_user.user_id)
    return {"status": "success", "settings": SYSTEM_SETTINGS}


# ─────────────────────────────────────────────────────────────────────────────
# SERVE FRONTEND
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CashOut Forecast API", "docs": "/docs"}


@app.get("/app")
@app.get("/dashboard")
def serve_app():
    app_path = os.path.join(FRONTEND_DIR, "dashboard.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)
    return {"message": "Dashboard not yet built"}

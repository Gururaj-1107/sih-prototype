"""
FastAPI Main Application — entry point.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import os
import json
import uuid
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.database.connection import get_db, init_db
from backend.database.models import (
    User, Complaint, Account, Transaction, Withdrawal,
    Location, Prediction, PredictionEvidence, Alert,
    InvestigatorFeedback, AuditLog
)
from backend.auth import (
    verify_password, hash_password, create_access_token, get_current_user
)
from backend.audit.audit_chain import create_audit_record, verify_chain_integrity
from backend.prediction.forecaster import get_forecaster


# ─────────────────────────────────────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and seed default admin user on startup."""
    init_db()
    _seed_default_users()
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

    return {
        "active_alerts": n_alerts,
        "complaints_processed": n_complaints,
        "suspicious_accounts": n_suspicious,
        "total_accounts": n_accounts,
        "predictions_generated": n_predictions,
        "pending_review": n_pending_review,
        "total_transactions": total_txn_volume,
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

@app.post("/assistant/query")
def assistant_query(body: dict, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """
    Investigator Intelligence Assistant.
    Answers questions using actual system data — no fabrication.
    Rule-based deterministic fallback (no API key required).
    """
    question = body.get("question", "").lower().strip()
    context_prediction_id = body.get("prediction_id")
    answer = _rule_based_assistant(question, context_prediction_id, db)
    return {"question": body.get("question"), "answer": answer,
            "source": "deterministic_rule_based_assistant"}


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

    # Summary / help
    if any(w in question for w in ["summarize", "summary", "help", "what can"]):
        return (
            "**Investigator Intelligence Assistant** — I can help with:\n\n"
            "• **Why is [city] ranked first?** — Evidence and signals for a prediction\n"
            "• **Show transaction path** — Money flow chain from victim to predicted location\n"
            "• **Active alerts** — Current high-priority alerts\n"
            "• **Compare locations** — Side-by-side candidate comparison\n"
            "• **Mule accounts** — Potential mule indicators in the system\n"
            "• **Connected complaints** — Complaint statistics\n\n"
            "_All answers are grounded in actual system data. No fabrication._"
        )

    # Default
    return (
        "I'm the **Investigator Intelligence Assistant**. I can answer questions about:\n"
        "predictions, transaction paths, alerts, mule accounts, and complaints.\n\n"
        "Try: _'Why is Mumbai ranked first?'_ or _'Show transaction path'_ or _'Active alerts'_."
    )


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
    from datetime import datetime
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

    # Step 3: Store prediction
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

    for r in results:
        ev = PredictionEvidence(
            evidence_id=str(uuid.uuid4()),
            prediction_id=pred_id,
            rank=r["rank"],
            location_id=r["location_id"],
            score=r["score"],
            expected_window_start=r["expected_window_start"],
            expected_window_end=r["expected_window_end"],
            evidence_json=json.dumps(r["evidence"]),
            transaction_path_json=json.dumps(r["transaction_path"]),
        )
        db.add(ev)

    # Step 4: Generate alert for top prediction
    top = results[0]
    priority = "HIGH" if top["score"] >= 0.6 else ("MEDIUM" if top["score"] >= 0.35 else "LOW")
    alert = Alert(
        alert_id=str(uuid.uuid4()),
        created_at=datetime.utcnow().isoformat(),
        prediction_id=pred_id,
        location_id=top["location_id"],
        score=top["score"],
        priority=priority,
        expected_window_start=top["expected_window_start"],
        expected_window_end=top["expected_window_end"],
        status="active",
        summary=f"Potential cash-out predicted at {top['city']} (Score: {top['score']:.2f}). Multiple Ahmedabad fraud complaints linked to account network moving toward Mumbai.",
    )
    db.add(alert)
    db.commit()

    # Step 5: Audit
    create_audit_record(db, "demo_scenario_run", {
        "scenario": "Ahmedabad → Mumbai Cross-City Cash-Out",
        "prediction_id": pred_id,
        "top_location": top["location_id"],
        "top_score": top["score"],
    }, user_id=current_user.user_id)

    return {
        "status": "success",
        "scenario": "Ahmedabad → Mumbai Cross-City Cash-Out",
        "prediction_id": pred_id,
        "alert_id": alert.alert_id,
        "top_k_results": results[:3],
        "message": "Demo scenario complete. See Predictions and Alerts panels.",
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
# SERVE FRONTEND
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CashOut Forecast API", "docs": "/docs"}


@app.get("/app")
def serve_app():
    app_path = os.path.join(FRONTEND_DIR, "dashboard.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)
    return {"message": "Dashboard not yet built"}

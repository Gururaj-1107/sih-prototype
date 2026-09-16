"""
Seed Demo Script — Pre-generates initial predictions and alerts for immediate display.

Runs predictions for several scenarios already in the database and creates:
  - Predictions
  - PredictionEvidence with rankings, scores, evidence bullets, and transaction paths
  - Alerts for high/medium priority predictions
  - Audit log entries
"""
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import init_db, SessionLocal
from backend.database.models import (
    Complaint, Account, Transaction, Location,
    Prediction, PredictionEvidence, Alert, AuditLog
)
from backend.prediction.forecaster import CashOutForecaster
from backend.audit.audit_chain import create_audit_record


def seed_initial_predictions():
    init_db()
    db = SessionLocal()
    try:
        print("[SEED] Checking existing predictions...")
        existing_count = db.query(Prediction).count()
        if existing_count > 0:
            print(f"[SEED] Already found {existing_count} predictions in DB.")
            return

        print("[SEED] Generating predictions for initial scenarios...")
        forecaster = CashOutForecaster()

        # Find distinct scenario tags from complaints
        complaints = db.query(Complaint).all()
        scenarios = list(set(c.scenario_tag for c in complaints if c.scenario_tag))
        print(f"[SEED] Found {len(scenarios)} unique scenario tags: {scenarios[:8]}")

        # Pick up to 5 diverse scenarios to seed
        target_scenarios = scenarios[:6] if scenarios else ["SCENARIO_1"]

        for idx, sc_id in enumerate(target_scenarios):
            # Get latest complaint time for this scenario
            c_for_sc = [c for c in complaints if c.scenario_tag == sc_id]
            if c_for_sc:
                t_base = datetime.fromisoformat(c_for_sc[0].timestamp)
            else:
                t_base = datetime.utcnow() - timedelta(hours=3)

            prediction_cutoff = t_base + timedelta(minutes=45)
            print(f"[SEED] Predicting for scenario {sc_id} at cutoff {prediction_cutoff}...")

            results = forecaster.predict(sc_id, prediction_cutoff, db, top_k=4)
            if not results:
                print(f"  Warning: No results for {sc_id}")
                continue

            pred_id = str(uuid.uuid4())
            pred = Prediction(
                prediction_id=pred_id,
                created_at=(prediction_cutoff + timedelta(minutes=5)).isoformat(),
                prediction_time_cutoff=prediction_cutoff.isoformat(),
                scenario_id=sc_id,
                model_version=results[0].get("model_version", "v1"),
                top_k=len(results),
                status="active" if idx < 3 else "viewed",
            )
            db.add(pred)

            for r in results:
                ev = PredictionEvidence(
                    evidence_id=str(uuid.uuid4()),
                    prediction_id=pred_id,
                    rank=r["rank"],
                    location_id=r["location_id"],
                    score=float(r["score"]),
                    expected_window_start=r["expected_window_start"],
                    expected_window_end=r["expected_window_end"],
                    evidence_json=json.dumps(r.get("evidence", [])),
                    transaction_path_json=json.dumps(r.get("transaction_path", [])),
                )
                db.add(ev)

            # Create Alert for top prediction
            top = results[0]
            score_val = float(top["score"])
            priority = "HIGH" if score_val >= 0.55 else ("MEDIUM" if score_val >= 0.35 else "LOW")

            loc_obj = db.query(Location).filter(Location.location_id == top["location_id"]).first()
            loc_city = loc_obj.city if loc_obj else top.get("city", top["location_id"])

            alert = Alert(
                alert_id=str(uuid.uuid4()),
                created_at=(prediction_cutoff + timedelta(minutes=5)).isoformat(),
                prediction_id=pred_id,
                location_id=top["location_id"],
                score=score_val,
                priority=priority,
                expected_window_start=top["expected_window_start"],
                expected_window_end=top["expected_window_end"],
                status="active" if idx < 4 else "viewed",
                summary=f"Imminent Cash-Out Risk at {loc_city} (Score: {score_val:.2f}). Money flow chain active across connected accounts for scenario {sc_id}.",
            )
            db.add(alert)
            db.commit()

            create_audit_record(db, "prediction_generated", {
                "prediction_id": pred_id,
                "scenario_id": sc_id,
                "top_location": top["location_id"],
                "score": score_val,
            }, user_id="system_engine")

        print(f"[SEED] Successfully seeded initial predictions, alerts, and audit records.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_initial_predictions()

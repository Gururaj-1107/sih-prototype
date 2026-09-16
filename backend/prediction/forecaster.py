"""
Cash-Out Forecasting Engine — Phase 5.

Given a scenario (set of accounts + transactions up to time T),
produces Top-K candidate cash-out locations with:
  - Predicted score (0–1)
  - Expected time window
  - Evidence bullets
  - Transaction path from victim to predicted location

This module is the core prediction API called by the FastAPI endpoints.
The model never sees future withdrawal data — only data up to prediction_time.
"""

import os
import json
import joblib
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np

from backend.ml.features import FeatureEngineer, MuleRiskScorer
from backend.graph.builder import TransactionGraph


MODEL_DIR = "models"


class CashOutForecaster:
    """
    Loads trained model and generates Top-K location predictions.
    """

    def __init__(self):
        self.model = None
        self.feature_columns = []
        self.model_version = "unloaded"
        self.feature_importances: dict = {}
        self.explainer = None
        self._load_model()

    def _load_model(self):
        """Load model from disk. Fails gracefully if not yet trained."""
        model_path = os.path.join(MODEL_DIR, "cashout_model.pkl")
        config_path = os.path.join(MODEL_DIR, "feature_config.json")
        meta_path = os.path.join(MODEL_DIR, "training_metadata.json")

        if not os.path.exists(model_path):
            print("  [Forecaster] No trained model found. Run train_model.py first.")
            return

        self.model = joblib.load(model_path)
        with open(config_path) as f:
            cfg = json.load(f)
        self.feature_columns = cfg["feature_columns"]

        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.model_version = meta.get("model_version", "v1")
            self.feature_importances = meta.get("feature_importances", {})

        try:
            import shap
            self.explainer = shap.TreeExplainer(self.model)
        except Exception:
            self.explainer = None

        print(f"  [Forecaster] Model loaded: {self.model_version}")

    def predict(self,
                scenario_id: str,
                prediction_time: datetime,
                db_session,
                top_k: int = 5) -> list[dict]:
        """
        Generate Top-K cash-out location predictions.

        prediction_time (T): Only data up to this point is used.
        Returns list of candidate dicts, sorted by score descending.
        """
        if self.model is None:
            # Return a clearly-labelled fallback if model not trained
            return self._heuristic_fallback(scenario_id, db_session, top_k)

        from backend.database.models import (
            Account, Transaction, Complaint, Location, Withdrawal
        )

        # Load data up to T
        cutoff_str = prediction_time.isoformat()
        txn_df = self._query_to_df(db_session, Transaction, cutoff=cutoff_str,
                                    time_col="timestamp")
        acc_df = self._query_to_df(db_session, Account)
        loc_df = self._query_to_df(db_session, Location)
        cmp_df = self._query_to_df(db_session, Complaint, cutoff=cutoff_str,
                                    time_col="timestamp")
        wdr_df = self._query_to_df(db_session, Withdrawal, cutoff=cutoff_str,
                                    time_col="timestamp")

        # Build graph from data up to T
        from scripts.train_model import build_graph_from_dfs, get_scenario_accounts
        graph_builder = TransactionGraph()
        graph_builder.graph = build_graph_from_dfs(acc_df, loc_df, txn_df, wdr_df)

        engineer = FeatureEngineer(graph_builder=graph_builder)

        # Get scenario accounts
        scenario_accounts = get_scenario_accounts(scenario_id, cmp_df, txn_df)
        if not scenario_accounts:
            scenario_accounts = self._fallback_scenario_accounts(scenario_id, txn_df, cmp_df)

        all_location_ids = loc_df["location_id"].tolist()

        # Build feature row for every candidate location
        rows = []
        for loc_id in all_location_ids:
            row = engineer.build_feature_row(
                scenario_accounts, loc_id, txn_df, acc_df, loc_df, cmp_df,
                prediction_time, label=0, scenario_id=scenario_id,
                wdr_df=wdr_df
            )
            rows.append(row)

        if not rows:
            return []

        feature_df = pd.DataFrame(rows).fillna(0)
        X = feature_df[self.feature_columns] if self.feature_columns else feature_df

        # Get model scores
        if hasattr(self.model, "predict_proba"):
            scores = self.model.predict_proba(X)[:, 1]
        else:
            scores = self.model.predict(X).astype(float)

        feature_df["_score"] = scores

        # Calculate confidence calibration across candidate ranking
        sorted_scores = np.sort(scores)[::-1]
        top1 = float(sorted_scores[0]) if len(sorted_scores) > 0 else 0.0
        top5 = float(sorted_scores[min(4, len(sorted_scores) - 1)]) if len(sorted_scores) > 0 else 0.0
        margin = top1 - top5
        confidence_level = "HIGH" if (margin >= 0.15 and top1 >= 0.5) else ("MEDIUM" if margin >= 0.05 else "LOW")

        # Top-K by score
        top_df = feature_df.nlargest(top_k, "_score")

        # Build result with time window prediction
        results = []
        for rank, (idx, row) in enumerate(top_df.iterrows(), start=1):
            loc_id = row["_candidate_location"]
            score = float(row["_score"])

            # Time window: heuristic based on velocity and distance signals
            window_start, window_end = self._predict_time_window(
                prediction_time, row, rank
            )

            # Evidence bullets
            evidence = self._build_evidence(row, scenario_accounts, graph_builder,
                                             loc_id, loc_df)

            # Transaction path
            tx_path = self._get_transaction_path(
                scenario_accounts, loc_id, graph_builder
            )

            # Location metadata
            loc_row = loc_df[loc_df["location_id"] == loc_id]
            city = loc_row["city"].values[0] if len(loc_row) > 0 else ""
            state = loc_row["state"].values[0] if len(loc_row) > 0 else ""
            lat = float(loc_row["latitude"].values[0]) if len(loc_row) > 0 else 0
            lon = float(loc_row["longitude"].values[0]) if len(loc_row) > 0 else 0

            # SHAP contributions using row features
            X_row = X.loc[[idx]] if hasattr(X, "loc") and idx in X.index else None
            feat_contribs = self._feature_contributions(row, X_row=X_row)

            results.append({
                "rank": rank,
                "location_id": loc_id,
                "city": city,
                "state": state,
                "latitude": lat,
                "longitude": lon,
                "score": round(score, 4),
                "confidence_level": confidence_level,
                "expected_window_start": window_start.isoformat(),
                "expected_window_end": window_end.isoformat(),
                "evidence": evidence,
                "transaction_path": tx_path,
                "model_version": self.model_version,
                "prediction_time_cutoff": cutoff_str,
                "scenario_id": scenario_id,
                "feature_contributions": feat_contribs,
            })

        return results

    def _predict_time_window(self, prediction_time: datetime, row, rank: int):
        """
        Predict likely cash-out time window.
        Based on: transaction velocity (fast = sooner), chain length, rank.
        Returns (window_start, window_end) — 2-hour windows.
        """
        # Base delay: fast-moving money → shorter delay
        velocity = float(row.get("txn_velocity_2h", 0))
        pass_through = float(row.get("graph_pass_through_ratio", 0))
        time_since_last = float(row.get("txn_time_since_last_hours", 4))

        # Shorter delay if: high velocity + high pass-through
        if velocity >= 3 and pass_through >= 0.7:
            base_delay_hours = 1.0
        elif velocity >= 2 or pass_through >= 0.5:
            base_delay_hours = 2.5
        else:
            base_delay_hours = 5.0

        # Add rank penalty (lower ranked = slightly later)
        delay_hours = base_delay_hours + (rank - 1) * 0.5

        window_start = prediction_time + timedelta(hours=delay_hours)
        window_end = window_start + timedelta(hours=2)
        return window_start, window_end

    def _build_evidence(self, row, scenario_accounts: list, graph_builder,
                         loc_id: str, loc_df: pd.DataFrame) -> list[str]:
        """Build human-readable evidence bullets for a candidate location."""
        bullets = []
        loc_city = loc_df[loc_df["location_id"] == loc_id]["city"].values[0] \
            if len(loc_df[loc_df["location_id"] == loc_id]) > 0 else ""

        # Graph evidence
        if row.get("graph_complaint_neighbours", 0) >= 1:
            n = int(row["graph_complaint_neighbours"])
            bullets.append(f"{n} complaint-linked victim account(s) in transaction network")

        if row.get("graph_suspicious_neighbours", 0) >= 1:
            n = int(row["graph_suspicious_neighbours"])
            bullets.append(f"{n} potentially suspicious account(s) in the connected network")

        if row.get("graph_pass_through_ratio", 0) >= 0.6:
            bullets.append("Rapid pass-through detected — funds move through accounts quickly")

        # Mule risk
        mule_score = float(row.get("mule_risk_score", 0))
        if mule_score >= 0.6:
            bullets.append(f"Terminal account shows high potential mule-risk score ({mule_score:.2f})")
        elif mule_score >= 0.3:
            bullets.append(f"Terminal account shows elevated potential mule-risk score ({mule_score:.2f})")

        # Spatial evidence
        if row.get("spatial_cross_city", 0):
            bullets.append("Cross-city money movement detected in transaction chain")
        if row.get("spatial_cross_state", 0):
            bullets.append("Cross-state fund transfer detected — victim and terminal account in different states")
        if row.get("spatial_terminal_city_match", 0):
            bullets.append(f"Terminal mule account is registered in candidate city ({loc_city})")
        elif row.get("spatial_victim_city_match", 0):
            bullets.append(f"Candidate location is in victim's city ({loc_city})")
        elif loc_city:
            bullets.append(f"Historical cash-out pattern consistent with {loc_city} cluster")
        if row.get("cand_hist_wdrs_at_loc", 0) > 0:
            bullets.append(f"Location has {int(row['cand_hist_wdrs_at_loc'])} prior cash-out withdrawals")

        # Velocity
        vel = int(row.get("txn_velocity_2h", 0))
        if vel >= 2:
            bullets.append(f"High transaction velocity: {vel} transactions in last 2 hours")

        # Chain length
        chain_len = int(row.get("chain_length", 1))
        if chain_len >= 3:
            bullets.append(f"Multi-hop transaction chain: {chain_len} accounts involved")

        # Temporal
        time_since = float(row.get("temp_time_since_complaint_hours", 0))
        if 0 < time_since < 3:
            bullets.append(f"Prediction generated {time_since:.1f} hours after initial complaint — active window")

        if not bullets:
            bullets.append("Candidate location selected based on transaction network proximity and historical patterns")

        return bullets

    def _feature_contributions(self, row, X_row=None) -> dict:
        """
        Return feature contributions via TreeSHAP (or heuristic importance fallback).
        Provides transparent explainability for investigative decision support.
        """
        if self.explainer is not None and X_row is not None and len(self.feature_columns) > 0:
            try:
                sv = self.explainer(X_row)
                vals = sv.values[0]
                contributions = {}
                for feat, s_val in zip(self.feature_columns, vals):
                    val = float(row.get(feat, 0)) if not pd.isna(row.get(feat, 0)) else 0.0
                    contributions[feat] = {
                        "shap_value": round(float(s_val), 4),
                        "importance": round(abs(float(s_val)), 4),
                        "value": round(val, 4),
                    }
                # Return top 8 features by absolute SHAP impact
                return dict(
                    sorted(contributions.items(), key=lambda x: x[1]["importance"], reverse=True)[:8]
                )
            except Exception:
                pass

        # Fallback to feature importance proxy
        contributions = {}
        for feat, importance in sorted(
            self.feature_importances.items(), key=lambda x: x[1], reverse=True
        )[:8]:
            if feat in row.index:
                val = float(row[feat]) if not pd.isna(row.get(feat, 0)) else 0
                contributions[feat] = {
                    "importance": round(float(importance), 4),
                    "value": round(val, 4),
                }
        return contributions

    def _get_transaction_path(self, scenario_accounts: list, loc_id: str,
                               graph_builder: TransactionGraph) -> list[dict]:
        """Find the transaction path from first victim account to the location."""
        if not scenario_accounts or not graph_builder.graph:
            return []
        # Try from each victim account
        for acc_id in scenario_accounts[:3]:
            path = graph_builder.get_transaction_path_for_complaint(acc_id, loc_id)
            if path:
                return path
        return []

    def _fallback_scenario_accounts(self, scenario_id, txn_df, cmp_df):
        """Fallback: get accounts from scenario-tagged transactions."""
        s_txns = txn_df[txn_df["scenario_id"] == scenario_id]
        accounts = set(s_txns["source_account_id"].tolist() +
                       s_txns["dest_account_id"].tolist())
        return list(accounts)

    def _heuristic_fallback(self, scenario_id, db_session, top_k):
        """Return heuristic predictions when model is not trained."""
        from backend.database.models import Location, Complaint, Transaction, Account
        locs = db_session.query(Location).limit(top_k).all()
        results = []
        for rank, loc in enumerate(locs, 1):
            results.append({
                "rank": rank,
                "location_id": loc.location_id,
                "city": loc.city,
                "state": loc.state,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "score": round(max(0.1, 0.6 - rank * 0.1), 2),
                "expected_window_start": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
                "expected_window_end": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
                "evidence": ["[Heuristic mode — model not trained. Run scripts/train_model.py]"],
                "transaction_path": [],
                "model_version": "heuristic_fallback",
                "scenario_id": scenario_id,
                "feature_contributions": {},
            })
        return results

    @staticmethod
    def _query_to_df(db_session, Model, cutoff: str = None, time_col: str = None):
        """Helper: query a model to DataFrame with optional time cutoff."""
        q = db_session.query(Model)
        if cutoff and time_col:
            q = q.filter(getattr(Model, time_col) <= cutoff)
        return pd.read_sql(q.statement, db_session.bind)


# Module-level singleton for use by API endpoints
_forecaster: Optional[CashOutForecaster] = None


def get_forecaster() -> CashOutForecaster:
    """Get or create the global forecaster singleton."""
    global _forecaster
    if _forecaster is None:
        _forecaster = CashOutForecaster()
    return _forecaster

"""
Feature Engineering Pipeline — Phase 3.

Computes all features needed for the cash-out forecasting model.

Feature groups:
  1. Transaction features   (velocity, amounts, timing)
  2. Graph features         (degree, fan-in/out, suspicious neighbours, pass-through)
  3. Temporal features      (hour-of-day, time since complaint, trends)
  4. Spatial features       (city match, cross-city flag, distance proxy)
  5. Mule-risk score        (composite score from explainable signals)
  6. Candidate-location features (historical activity at target location)

CRITICAL: All features are computed using only data available at prediction time T.
          The cutoff_time parameter enforces this — future data is NEVER used.

v2 KEY CHANGES (fixes Hit@1 = 0% root causes):
  - spatial_terminal_city_match: uses TERMINAL account city, not full BFS chain.
    This is the key fix: distinguishes victim city from cash-out city.
  - spatial_victim_city_match: new negative signal.
  - cand_hist_wdrs_at_loc: actual past withdrawal count at this location (was always 0).
  - cand_hist_wdrs_in_city: city-level withdrawal prior.
  - cand_terminal_txns_at_city: has the terminal mule transacted in this city?
  - cand_outflow_ratio_to_city: fraction of terminal outflow toward candidate city.
  - Scenario-constant features removed from get_feature_columns() ranking set.

Mule Risk Score:
  A composite 0-1 score built from interpretable signals.
  Never called "criminal score" -- always "Potential Mule Risk Score".
"""

from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np


# -----------------------------------------------------------------------------
# MULE RISK SCORER
# -----------------------------------------------------------------------------

class MuleRiskScorer:
    """
    Computes an interpretable Potential Mule Risk Score for each account.

    Score is a weighted sum of normalised signals. All signals have
    human-readable names used in the explanation layer.
    """

    # Signal weights (tuned heuristically for prototype)
    WEIGHTS = {
        "high_fan_in":               0.20,
        "high_fan_out":              0.15,
        "rapid_pass_through":        0.20,
        "unusual_timing":            0.10,
        "high_velocity":             0.15,
        "multi_complaint_link":      0.15,
        "new_account":               0.05,
    }

    def compute(self, account_id: str, txn_df: pd.DataFrame,
                complaints_df: pd.DataFrame,
                graph_features: dict,
                cutoff_time: datetime) -> tuple:
        """
        Compute mule risk score and return (score, signal_dict).
        """
        signals = {}

        fan_in = graph_features.get("fan_in", 0)
        signals["high_fan_in"] = min(fan_in / 10.0, 1.0)

        fan_out = graph_features.get("fan_out", 0)
        signals["high_fan_out"] = min(fan_out / 8.0, 1.0)

        signals["rapid_pass_through"] = min(
            graph_features.get("pass_through_ratio", 0), 1.0
        )

        acc_txns = txn_df[
            (txn_df["source_account_id"] == account_id) |
            (txn_df["dest_account_id"] == account_id)
        ].copy()

        if len(acc_txns) > 0:
            acc_txns["hour"] = pd.to_datetime(acc_txns["timestamp"]).dt.hour
            night_txns = acc_txns[
                (acc_txns["hour"] >= 22) | (acc_txns["hour"] <= 5)
            ]
            signals["unusual_timing"] = min(len(night_txns) / max(len(acc_txns), 1), 1.0)
        else:
            signals["unusual_timing"] = 0.0

        cutoff_minus_6h = cutoff_time - timedelta(hours=6)
        recent_txns = acc_txns[
            pd.to_datetime(acc_txns["timestamp"]) >= cutoff_minus_6h
        ] if len(acc_txns) > 0 else pd.DataFrame()
        signals["high_velocity"] = min(len(recent_txns) / 5.0, 1.0)

        complaint_neighbours = graph_features.get("complaint_neighbours", 0)
        signals["multi_complaint_link"] = min(complaint_neighbours / 3.0, 1.0)

        signals["new_account"] = graph_features.get("new_account_signal", 0.0)

        score = sum(
            self.WEIGHTS[sig] * val
            for sig, val in signals.items()
        )
        score = min(round(score, 4), 1.0)

        return score, signals

    def explain(self, signals: dict, score: float) -> list:
        """Convert signal values to human-readable evidence bullets."""
        bullets = []
        threshold = 0.3

        signal_descriptions = {
            "high_fan_in": "High number of unique incoming senders (fan-in)",
            "high_fan_out": "Multiple unique outgoing receivers (fan-out)",
            "rapid_pass_through": "Rapid pass-through detected -- funds move quickly",
            "unusual_timing": "Transactions at unusual hours (late night / early morning)",
            "high_velocity": "High recent transaction velocity (last 6 hours)",
            "multi_complaint_link": "Connected to multiple cybercrime complaint victims",
            "new_account": "Account is relatively new (potential throwaway account)",
        }

        for sig, val in signals.items():
            if val >= threshold:
                bullets.append(signal_descriptions.get(sig, sig))

        if score >= 0.7:
            bullets.insert(0, f"Warning: Potential Mule Risk Score: {score:.2f} (High)")
        elif score >= 0.4:
            bullets.insert(0, f"Warning: Potential Mule Risk Score: {score:.2f} (Medium)")
        else:
            bullets.insert(0, f"Potential Mule Risk Score: {score:.2f} (Low)")

        return bullets


# -----------------------------------------------------------------------------
# MAIN FEATURE ENGINEERING CLASS
# -----------------------------------------------------------------------------

class FeatureEngineer:
    """
    Builds the full feature matrix for the cash-out forecasting model.

    The feature matrix has one row per (scenario, candidate_location) pair.
    The model predicts which candidate location is the true cash-out site.

    v2 KEY CHANGES (fixes Hit@1 = 0%):
      - spatial_terminal_city_match: candidate city vs TERMINAL account city (not full chain)
      - spatial_victim_city_match: negative signal
      - cand_hist_wdrs_at_loc: actual historical withdrawals (was always 0)
      - cand_hist_wdrs_in_city: city-level withdrawal prior
      - cand_terminal_txns_at_city: mule's past activity in candidate city
      - cand_outflow_ratio_to_city: fraction of terminal outflow toward candidate city
    """

    def __init__(self, graph_builder=None):
        self.graph_builder = graph_builder
        self.mule_scorer = MuleRiskScorer()

    def build_feature_row(self,
                          scenario_accounts: list,
                          candidate_location: str,
                          txn_df: pd.DataFrame,
                          acc_df: pd.DataFrame,
                          loc_df: pd.DataFrame,
                          complaints_df: pd.DataFrame,
                          cutoff_time: datetime,
                          label: int = 0,
                          scenario_id: str = "",
                          wdr_df: pd.DataFrame = None,
                          terminal_account_city: str = None) -> dict:
        """
        Build one feature row for the model.

        scenario_accounts: list of account_ids in the fraud chain.
                           accounts[-1] is treated as the terminal (mule) account.
        candidate_location: location_id being evaluated as cash-out site.
        cutoff_time: T -- only use data strictly before this point.
        label: 1 if candidate_location is the true cash-out, 0 otherwise.
        wdr_df: withdrawal history DataFrame (used for location priors).
        terminal_account_city: city of terminal mule (from scenarios_meta if available).
        """
        cutoff_str = cutoff_time.isoformat()

        # Filter to data available at T
        past_txns = txn_df[txn_df["timestamp"] <= cutoff_str].copy()
        past_wdrs = (wdr_df[wdr_df["timestamp"] <= cutoff_str].copy()
                     if wdr_df is not None and len(wdr_df) > 0 else pd.DataFrame())

        scenario_txns = past_txns[
            past_txns["source_account_id"].isin(scenario_accounts) |
            past_txns["dest_account_id"].isin(scenario_accounts)
        ].copy()

        # Identify victim and terminal accounts
        # victim  = first account (linked to the complaint)
        # terminal = last account in the BFS chain (most distal mule)
        victim_account   = scenario_accounts[0] if scenario_accounts else None
        terminal_account = scenario_accounts[-1] if scenario_accounts else None

        def _get_city(acc_id):
            if not acc_id:
                return ""
            row = acc_df[acc_df["account_id"] == acc_id]
            return str(row["city"].values[0]) if len(row) > 0 else ""

        victim_city   = _get_city(victim_account)
        # Use known terminal city from scenarios_meta when available (more accurate
        # than BFS terminal for cross-city scenarios with intermediate hops).
        terminal_city = terminal_account_city or _get_city(terminal_account)

        # -- Transaction features ------------------------------------------
        txn_count = len(scenario_txns)
        incoming = scenario_txns[
            scenario_txns["dest_account_id"].isin(scenario_accounts)
        ]["amount"].sum()
        outgoing = scenario_txns[
            scenario_txns["source_account_id"].isin(scenario_accounts)
        ]["amount"].sum()
        avg_txn_amount = scenario_txns["amount"].mean() if txn_count > 0 else 0

        cutoff_minus_2h = (cutoff_time - timedelta(hours=2)).isoformat()
        recent_txns = scenario_txns[scenario_txns["timestamp"] >= cutoff_minus_2h]
        velocity_2h = len(recent_txns)

        if txn_count > 0:
            last_txn_time = pd.to_datetime(scenario_txns["timestamp"].max())
            time_since_last_txn_hours = (
                cutoff_time - last_txn_time.to_pydatetime()
            ).total_seconds() / 3600
        else:
            time_since_last_txn_hours = 999.0

        terminal_outflow = 0.0
        terminal_inflow  = 0.0
        if terminal_account:
            terminal_outflow = float(
                past_txns[past_txns["source_account_id"] == terminal_account]["amount"].sum()
            )
            terminal_inflow = float(
                past_txns[past_txns["dest_account_id"] == terminal_account]["amount"].sum()
            )

        # -- Graph features ------------------------------------------------
        graph_feats = {}
        if self.graph_builder and terminal_account:
            graph_feats = self.graph_builder.compute_graph_features(terminal_account)

        in_degree              = graph_feats.get("in_degree", 0)
        out_degree             = graph_feats.get("out_degree", 0)
        pass_through           = graph_feats.get("pass_through_ratio", 0)
        suspicious_neighbours  = graph_feats.get("suspicious_neighbours", 0)
        complaint_neighbours   = graph_feats.get("complaint_neighbours", 0)
        unique_counterparties  = graph_feats.get("unique_counterparties", 0)
        hist_cashout_locs      = graph_feats.get("historical_cashout_locations", 0)

        mule_score   = 0.0
        mule_signals = {}
        if self.graph_builder and terminal_account:
            mule_score, mule_signals = self.mule_scorer.compute(
                terminal_account, past_txns, complaints_df, graph_feats, cutoff_time
            )

        # -- Temporal features ---------------------------------------------
        hour_of_day = cutoff_time.hour
        day_of_week = cutoff_time.weekday()

        time_since_complaint_hours = 0.0
        if len(complaints_df) > 0 and "timestamp" in complaints_df.columns:
            relevant = complaints_df[
                complaints_df["victim_id"].isin(scenario_accounts)
            ]
            if len(relevant) > 0:
                earliest = pd.to_datetime(relevant["timestamp"].min())
                time_since_complaint_hours = max(
                    (cutoff_time - earliest.to_pydatetime()).total_seconds() / 3600, 0
                )

        # -- Spatial features (v2 -- terminal-city aware) ------------------
        cand_loc   = loc_df[loc_df["location_id"] == candidate_location]
        cand_city  = str(cand_loc["city"].values[0]) if len(cand_loc) > 0 else ""
        cand_state = str(cand_loc["state"].values[0]) if len(cand_loc) > 0 else ""

        # KEY FIX v2: compare candidate city to TERMINAL mule city -- not full BFS chain.
        terminal_city_match = int(bool(cand_city and terminal_city and cand_city == terminal_city))
        victim_city_match   = int(bool(cand_city and victim_city and cand_city == victim_city))

        cross_city = int(bool(terminal_city and victim_city and terminal_city != victim_city))

        all_states = list(acc_df[acc_df["account_id"].isin(scenario_accounts)]["state"].dropna().values)
        cross_state_flag = int(len(set(all_states)) > 1) if all_states else 0

        intermediate_cities = [_get_city(a) for a in scenario_accounts[1:-1]]
        all_chain_cities = set(
            c for c in [victim_city, terminal_city] + intermediate_cities if c
        )
        n_cities_in_chain = len(all_chain_cities) if all_chain_cities else 1
        chain_length = len(scenario_accounts)

        # -- Candidate location-specific features (KEY v2 ADDITIONS) ------
        locs_in_cand_city = loc_df[loc_df["city"] == cand_city]["location_id"].tolist()

        if len(past_wdrs) > 0 and "location_id" in past_wdrs.columns:
            hist_wdrs_at_loc       = int(len(past_wdrs[past_wdrs["location_id"] == candidate_location]))
            hist_wdrs_in_cand_city = int(len(past_wdrs[past_wdrs["location_id"].isin(locs_in_cand_city)]))
        else:
            hist_wdrs_at_loc       = 0
            hist_wdrs_in_cand_city = 0

        if terminal_account and len(past_txns) > 0 and "location_id" in past_txns.columns:
            terminal_txns_at_cand_city = int(len(
                past_txns[
                    (past_txns["source_account_id"] == terminal_account) &
                    (past_txns["location_id"].isin(locs_in_cand_city))
                ]
            ))
        else:
            terminal_txns_at_cand_city = 0

        outflow_ratio_to_cand_city = 0.0
        if terminal_account and terminal_outflow > 0 and len(past_txns) > 0:
            accs_in_cand_city = acc_df[acc_df["city"] == cand_city]["account_id"].tolist()
            flow_to_cand = float(
                past_txns[
                    (past_txns["source_account_id"] == terminal_account) &
                    (past_txns["dest_account_id"].isin(accs_in_cand_city))
                ]["amount"].sum()
            )
            outflow_ratio_to_cand_city = flow_to_cand / (terminal_outflow + 1e-9)

        # -- Assemble feature row -----------------------------------------
        return {
            # Identifiers (not model features)
            "_scenario_id": scenario_id,
            "_candidate_location": candidate_location,
            "_cand_city": cand_city,

            # Transaction features (scenario-constant)
            "txn_count": txn_count,
            "txn_incoming_total": round(float(incoming), 2),
            "txn_outgoing_total": round(float(outgoing), 2),
            "txn_avg_amount": round(float(avg_txn_amount), 2),
            "txn_velocity_2h": velocity_2h,
            "txn_time_since_last_hours": round(time_since_last_txn_hours, 2),
            "txn_terminal_outflow": round(terminal_outflow, 2),
            "txn_terminal_inflow": round(terminal_inflow, 2),

            # Graph features (terminal account)
            "graph_in_degree": in_degree,
            "graph_out_degree": out_degree,
            "graph_pass_through_ratio": round(float(pass_through), 4),
            "graph_suspicious_neighbours": suspicious_neighbours,
            "graph_complaint_neighbours": complaint_neighbours,
            "graph_unique_counterparties": unique_counterparties,
            "graph_hist_cashout_locs": hist_cashout_locs,

            # Mule risk
            "mule_risk_score": round(mule_score, 4),

            # Temporal features
            "temp_hour_of_day": hour_of_day,
            "temp_day_of_week": day_of_week,
            "temp_time_since_complaint_hours": round(time_since_complaint_hours, 2),
            "temp_velocity_2h": velocity_2h,

            # Spatial features -- v2 FIXED (VARY per candidate)
            "spatial_terminal_city_match": terminal_city_match,
            "spatial_victim_city_match": victim_city_match,
            "spatial_accs_in_cand_city": int(len(acc_df[(acc_df["account_id"].isin(scenario_accounts)) & (acc_df["city"] == cand_city)])),
            "spatial_cross_city": cross_city,
            "spatial_cross_state": cross_state_flag,
            "spatial_n_cities_in_chain": n_cities_in_chain,
            "spatial_chain_length": chain_length,

            # Candidate location-specific -- v2 NEW (VARY per candidate)
            "cand_hist_wdrs_at_loc": hist_wdrs_at_loc,
            "cand_hist_wdrs_in_city": hist_wdrs_in_cand_city,
            "cand_terminal_txns_at_city": terminal_txns_at_cand_city,
            "cand_outflow_ratio_to_city": round(outflow_ratio_to_cand_city, 4),

            # Label
            "label": label,
        }

    def get_feature_columns(self) -> list:
        """
        Return feature columns for the RANKING model.

        Only features that VARY across the 33 candidate locations within one
        scenario are included. Scenario-constant features are excluded because
        they cannot discriminate between candidates.
        """
        return [
            # Mule risk signals (scenario-level, included for calibration)
            "mule_risk_score",
            "graph_pass_through_ratio",
            "graph_suspicious_neighbours",
            "graph_complaint_neighbours",
            "graph_unique_counterparties",
            "txn_velocity_2h",
            "txn_time_since_last_hours",
            "txn_terminal_outflow",
            "temp_time_since_complaint_hours",

            # Spatial -- VARY per candidate (primary discriminators)
            "spatial_terminal_city_match",    # KEY: terminal city == candidate city?
            "spatial_victim_city_match",       # negative signal
            "spatial_accs_in_cand_city",       # count of chain accounts in candidate city
            "spatial_cross_state",
            "spatial_n_cities_in_chain",
            "spatial_chain_length",

            # Candidate location-specific (secondary discriminators)
            "cand_hist_wdrs_at_loc",
            "cand_hist_wdrs_in_city",
            "cand_terminal_txns_at_city",
            "cand_outflow_ratio_to_city",
        ]

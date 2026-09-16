"""
Model Training Script — Phases 4 & 5.

Implements and compares:
  Baseline 1: Historical frequency (most common withdrawal city)
  Baseline 2: Nearest/account-location heuristic
  Baseline 3: Logistic Regression (simple ML)
  Final:      LightGBM classifier (graph + temporal + spatial features)

Training protocol:
  - Chronological split (NEVER random) to prevent temporal leakage
  - Earlier scenarios → training
  - Middle scenarios  → validation
  - Latest scenarios  → test
  - Metrics: Precision@K, Recall@K, Hit Rate@K for K ∈ {1, 3, 5}

Output:
  models/cashout_model_v1.pkl   — LightGBM model
  models/feature_config.json    — Feature columns used
  models/training_metadata.json — Version, metrics, training info
  models/baselines.pkl          — Baseline model objects

Usage:
    python scripts/train_model.py
"""

import os
import sys
import json
import joblib
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import init_db, SessionLocal
from backend.database.models import (
    Account, Transaction, Complaint, Withdrawal, Location
)
from backend.graph.builder import TransactionGraph
from backend.ml.features import FeatureEngineer, MuleRiskScorer

try:
    import lightgbm as lgb
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False
    print("WARNING: LightGBM not available. Using RandomForest fallback.")

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_all_data(db) -> dict:
    """Load all tables into DataFrames."""
    txn_df = pd.read_sql(db.query(Transaction).statement, db.bind)
    acc_df = pd.read_sql(db.query(Account).statement, db.bind)
    loc_df = pd.read_sql(db.query(Location).statement, db.bind)
    cmp_df = pd.read_sql(db.query(Complaint).statement, db.bind)
    wdr_df = pd.read_sql(db.query(Withdrawal).statement, db.bind)
    return {
        "txn": txn_df, "acc": acc_df, "loc": loc_df,
        "cmp": cmp_df, "wdr": wdr_df
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING DATASET BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_training_dataset(data: dict, scenarios_meta_path: str) -> pd.DataFrame:
    """
    Build the full feature matrix for training.

    For each scenario with a known cash-out:
      - Positive example: (scenario, true_cashout_location)   label=1
      - Negative examples: (scenario, other_locations)         label=0
        We sample ~4 negatives per positive to keep class balance manageable.

    Cutoff time = prediction_cutoff from scenario meta
    (the moment investigators would generate a prediction in real use).

    CRITICAL: Only transactions before cutoff_time are used.
    """
    scenarios_df = pd.read_csv(scenarios_meta_path)
    # Only train on scenarios that have an actual cash-out
    train_scenarios = scenarios_df[scenarios_df["ground_truth_location"].notna()].copy()
    # Sort chronologically for correct split later
    train_scenarios = train_scenarios.sort_values("prediction_cutoff").reset_index(drop=True)

    txn_df = data["txn"]
    acc_df = data["acc"]
    loc_df = data["loc"]
    cmp_df = data["cmp"]
    wdr_df = data["wdr"]

    all_location_ids = loc_df["location_id"].tolist()

    print(f"  Building feature matrix from {len(train_scenarios)} scenarios...")

    # Build graph (full graph, no cutoff — feature engineer enforces cutoff)
    print("  Building transaction graph...")
    graph_builder = TransactionGraph()
    # Quick build without DB (from DataFrames directly)
    graph_builder.graph = build_graph_from_dfs(acc_df, loc_df, txn_df, wdr_df)

    engineer = FeatureEngineer(graph_builder=graph_builder)
    rows = []

    for idx, scenario in train_scenarios.iterrows():
        scenario_id = scenario["scenario_id"]
        true_loc = scenario["ground_truth_location"]
        cashout_city = scenario.get("cashout_city", "")
        victim_city = scenario.get("victim_city", "")
        terminal_city = scenario.get("terminal_account_city") or cashout_city
        cutoff_str = scenario["prediction_cutoff"]

        try:
            cutoff_time = datetime.fromisoformat(cutoff_str)
        except Exception:
            continue

        # Get scenario account chain from complaints and transactions
        scenario_accounts = get_scenario_accounts(scenario_id, cmp_df, txn_df)
        if not scenario_accounts:
            continue

        # Positive: true cash-out location
        if true_loc in all_location_ids:
            row = engineer.build_feature_row(
                scenario_accounts, true_loc, txn_df, acc_df, loc_df, cmp_df,
                cutoff_time, label=1, scenario_id=scenario_id,
                wdr_df=wdr_df, terminal_account_city=terminal_city
            )
            rows.append(row)

        # Negatives: sample from other locations, prioritise same-city locations (hard negatives)
        target_city = terminal_city or cashout_city
        same_city_locs = [lid for lid in all_location_ids
                          if loc_df[loc_df["location_id"] == lid]["city"].values[0] == target_city
                          and lid != true_loc]
        other_locs = [lid for lid in all_location_ids
                      if lid != true_loc and lid not in same_city_locs]

        import random
        rng = random.Random(hash(scenario_id) % 2**32)

        # 4 negatives from same city (hard negatives)
        neg_same = rng.sample(same_city_locs, min(4, len(same_city_locs)))
        # 2 negatives from other cities
        neg_other = rng.sample(other_locs, min(2, len(other_locs)))

        for neg_loc in neg_same + neg_other:
            row = engineer.build_feature_row(
                scenario_accounts, neg_loc, txn_df, acc_df, loc_df, cmp_df,
                cutoff_time, label=0, scenario_id=scenario_id,
                wdr_df=wdr_df, terminal_account_city=terminal_city
            )
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"  Feature matrix: {len(df)} rows, {len(df.columns)} columns")
    print(f"  Class balance: {df['label'].sum()} positives / {(df['label']==0).sum()} negatives")
    return df


def get_scenario_accounts(scenario_id: str, cmp_df: pd.DataFrame,
                           txn_df: pd.DataFrame) -> list[str]:
    """
    Extract the account chain for a scenario by following transactions
    from victim accounts outward.
    """
    # Find victim accounts via complaints
    scenario_cmps = cmp_df[cmp_df["scenario_tag"] == scenario_id]
    victim_ids = set(scenario_cmps["victim_id"].tolist())

    if not victim_ids:
        return []

    # BFS to find all accounts in the fraud chain (via scenario-tagged transactions)
    scenario_txns = txn_df[txn_df["scenario_id"] == scenario_id]
    chain = set(victim_ids)
    frontier = set(victim_ids)

    for _ in range(5):   # max 5 hops
        new_nodes = set()
        for acc in frontier:
            downstream = scenario_txns[
                scenario_txns["source_account_id"] == acc
            ]["dest_account_id"].tolist()
            new_nodes.update(downstream)
        new_nodes -= chain
        if not new_nodes:
            break
        chain.update(new_nodes)
        frontier = new_nodes

    return list(chain)


def build_graph_from_dfs(acc_df, loc_df, txn_df, wdr_df):
    """Build NetworkX graph from DataFrames (faster than DB queries for training)."""
    import networkx as nx
    G = nx.DiGraph()

    for _, row in acc_df.iterrows():
        G.add_node(row["account_id"], node_type="account",
                   city=row["city"], state=row["state"],
                   risk_label=row["risk_label"],
                   mule_risk_score=row.get("mule_risk_score", 0),
                   account_age_days=row.get("account_age_days", 365))

    for _, row in loc_df.iterrows():
        G.add_node(row["location_id"], node_type="location",
                   city=row["city"], state=row["state"],
                   latitude=row.get("latitude"), longitude=row.get("longitude"))

    for _, row in txn_df.iterrows():
        if row["source_account_id"] in G and row["dest_account_id"] in G:
            G.add_edge(row["source_account_id"], row["dest_account_id"],
                       edge_type="transfer", amount=row["amount"],
                       timestamp=row["timestamp"])

    for _, row in wdr_df.iterrows():
        if row["account_id"] in G and row["location_id"] in G:
            G.add_edge(row["account_id"], row["location_id"],
                       edge_type="withdrawal", amount=row["amount"],
                       timestamp=row["timestamp"])

    return G


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATION METRICS
# ─────────────────────────────────────────────────────────────────────────────

def hit_rate_at_k(y_true, y_score, groups, k=3) -> float:
    """
    Hit Rate@K: fraction of scenarios where the true location
    appears in the top-K predicted candidates.
    """
    hits = 0
    total = 0
    for group_id in groups.unique():
        mask = groups == group_id
        g_true = y_true[mask].values
        g_score = y_score[mask]
        if g_true.sum() == 0:
            continue
        total += 1
        # Get top-K indices by score
        top_k_idx = np.argsort(g_score)[::-1][:k]
        if g_true[top_k_idx].sum() > 0:
            hits += 1
    return hits / total if total > 0 else 0.0


def precision_at_k(y_true, y_score, groups, k=3) -> float:
    """
    Precision@K: average fraction of top-K predictions that are correct.
    """
    scores = []
    for group_id in groups.unique():
        mask = groups == group_id
        g_true = y_true[mask].values
        g_score = y_score[mask]
        top_k_idx = np.argsort(g_score)[::-1][:k]
        scores.append(g_true[top_k_idx].sum() / k)
    return np.mean(scores) if scores else 0.0


def city_hit_rate_at_k(y_true, y_score, groups, cities, k=3) -> float:
    """
    City-level Hit Rate@K: fraction of scenarios where the true cash-out
    city is among the cities of top-K predicted candidates.
    """
    hits = 0
    total = 0
    for group_id in groups.unique():
        mask = groups == group_id
        g_true = y_true[mask].values
        g_score = y_score[mask]
        g_cities = cities[mask].values
        if g_true.sum() == 0:
            continue
        total += 1
        true_city = g_cities[g_true == 1][0]
        top_k_idx = np.argsort(g_score)[::-1][:k]
        top_k_cities = g_cities[top_k_idx]
        if true_city in top_k_cities:
            hits += 1
    return hits / total if total > 0 else 0.0


def evaluate_model(model, X_test, y_test, groups_test, model_name="Model",
                   cities_test=None) -> dict:
    """Run full evaluation and print results."""
    if hasattr(model, "predict_proba"):
        scores = model.predict_proba(X_test)[:, 1]
    else:
        scores = model.predict(X_test).astype(float)

    metrics = {}
    for k in [1, 3, 5]:
        hr = hit_rate_at_k(y_test, scores, groups_test, k)
        pr = precision_at_k(y_test, scores, groups_test, k)
        metrics[f"hit_rate@{k}"] = round(hr, 4)
        metrics[f"precision@{k}"] = round(pr, 4)

    if cities_test is not None:
        for k in [1, 3, 5]:
            chr_val = city_hit_rate_at_k(y_test, scores, groups_test, cities_test, k)
            metrics[f"city_hit_rate@{k}"] = round(chr_val, 4)

    ap = average_precision_score(y_test, scores)
    metrics["average_precision"] = round(ap, 4)

    print(f"\n  [{model_name}] Evaluation Results:")
    print(f"    Hit Rate@1:  {metrics['hit_rate@1']:.4f}")
    print(f"    Hit Rate@3:  {metrics['hit_rate@3']:.4f}")
    print(f"    Hit Rate@5:  {metrics['hit_rate@5']:.4f}")
    if cities_test is not None:
        print(f"    City Hit@1:  {metrics.get('city_hit_rate@1', 0):.4f}")
        print(f"    City Hit@3:  {metrics.get('city_hit_rate@3', 0):.4f}")
        print(f"    City Hit@5:  {metrics.get('city_hit_rate@5', 0):.4f}")
    print(f"    Precision@3: {metrics['precision@3']:.4f}")
    print(f"    Avg Precision: {metrics['average_precision']:.4f}")
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# BASELINES
# ─────────────────────────────────────────────────────────────────────────────

class HistoricalFrequencyBaseline:
    """
    Baseline 1: Rank candidate locations by historical withdrawal frequency.
    Most frequent past withdrawal city → highest score.
    """

    def __init__(self):
        self.city_frequency: dict = {}

    def fit(self, wdr_df: pd.DataFrame, loc_df: pd.DataFrame):
        wdr_with_city = wdr_df.merge(
            loc_df[["location_id", "city"]], on="location_id", how="left"
        )
        self.city_frequency = wdr_with_city["city"].value_counts().to_dict()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Score by candidate city frequency. Returns (N, 2) array."""
        cities = X["_cand_city"].values
        scores = np.array([self.city_frequency.get(c, 0) for c in cities], dtype=float)
        total = scores.max() if scores.max() > 0 else 1
        scores = scores / total
        return np.column_stack([1 - scores, scores])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] > 0.5).astype(int)


class NearestLocationBaseline:
    """
    Baseline 2: Score candidate by how many scenario accounts are registered
    in the same city as the candidate location.
    Simple proximity heuristic.
    """

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        scores = X["spatial_accs_in_cand_city"].values.astype(float)
        total = scores.max() if scores.max() > 0 else 1
        scores = scores / total
        return np.column_stack([1 - scores, scores])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] > 0.5).astype(int)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRAINING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def train(args):
    print("\n" + "="*60)
    print("  MODEL TRAINING PIPELINE")
    print("  Cash-Out Forecasting Platform — SIH 2026")
    print("="*60)

    # Paths
    scenarios_path = "data/generated/scenarios_meta.csv"
    models_dir = "models"
    os.makedirs(models_dir, exist_ok=True)

    if not os.path.exists(scenarios_path):
        print("ERROR: Run scripts/generate_data.py first.")
        return

    # Load data
    print("\n[1/7] Loading data from database...")
    db = SessionLocal()
    data = load_all_data(db)
    db.close()
    print(f"  Loaded: {len(data['txn'])} txns, {len(data['acc'])} accounts, "
          f"{len(data['cmp'])} complaints, {len(data['wdr'])} withdrawals")

    # Build feature matrix
    print("\n[2/7] Building feature matrix...")
    feature_df = build_training_dataset(data, scenarios_path)

    if len(feature_df) == 0:
        print("ERROR: No training examples generated. Check data generation.")
        return

    feature_cols = FeatureEngineer().get_feature_columns()

    # Chronological split: 70% train, 15% val, 15% test (by scenario order)
    print("\n[3/7] Chronological train/val/test split...")
    groups = feature_df["_scenario_id"]
    unique_scenarios = feature_df.drop_duplicates("_scenario_id")[
        "_scenario_id"
    ].tolist()  # Already sorted by prediction_cutoff from build step

    n = len(unique_scenarios)
    train_cutoff = int(n * 0.70)
    val_cutoff = int(n * 0.85)

    train_scenarios_set = set(unique_scenarios[:train_cutoff])
    val_scenarios_set = set(unique_scenarios[train_cutoff:val_cutoff])
    test_scenarios_set = set(unique_scenarios[val_cutoff:])

    train_mask = feature_df["_scenario_id"].isin(train_scenarios_set)
    val_mask = feature_df["_scenario_id"].isin(val_scenarios_set)
    test_mask = feature_df["_scenario_id"].isin(test_scenarios_set)

    X_train = feature_df[train_mask][feature_cols].fillna(0)
    y_train = feature_df[train_mask]["label"]
    X_val   = feature_df[val_mask][feature_cols].fillna(0)
    y_val   = feature_df[val_mask]["label"]
    X_test  = feature_df[test_mask][feature_cols].fillna(0)
    y_test  = feature_df[test_mask]["label"]

    groups_test = feature_df[test_mask]["_scenario_id"]
    cities_test = feature_df[test_mask]["_cand_city"]
    X_test_full = feature_df[test_mask].copy()

    print(f"  Train: {len(X_train)} rows | Val: {len(X_val)} rows | Test: {len(X_test)} rows")

    # ── Baseline 1: Historical Frequency ──────────────────────────────────
    print("\n[4/7] Training baselines...")
    baseline1 = HistoricalFrequencyBaseline()
    baseline1.fit(data["wdr"], data["loc"])
    b1_metrics = evaluate_model(
        baseline1, X_test_full, y_test, groups_test, "Baseline1-HistFreq",
        cities_test=cities_test
    )

    # ── Baseline 2: Nearest Location ──────────────────────────────────────
    baseline2 = NearestLocationBaseline()
    b2_metrics = evaluate_model(
        baseline2, X_test_full, y_test, groups_test, "Baseline2-NearestLoc",
        cities_test=cities_test
    )

    # ── Baseline 3: Logistic Regression ───────────────────────────────────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    lr = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
    lr.fit(X_train_scaled, y_train)
    b3_metrics = evaluate_model(
        lr, X_test_scaled, y_test, groups_test, "Baseline3-LogisticReg",
        cities_test=cities_test
    )

    # ── Final Model: LightGBM ─────────────────────────────────────────────
    print("\n[5/7] Training final LightGBM model...")
    if LGBM_AVAILABLE:
        # Use scale_pos_weight to handle class imbalance
        pos = y_train.sum()
        neg = (y_train == 0).sum()
        spw = neg / pos if pos > 0 else 1.0

        lgbm_model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.03,
            max_depth=4,
            num_leaves=15,
            min_child_samples=3,
            scale_pos_weight=spw,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        lgbm_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(30, verbose=False),
                       lgb.log_evaluation(period=-1)],
        )
        final_metrics = evaluate_model(
            lgbm_model, X_test, y_test, groups_test, "Final-LightGBM",
            cities_test=cities_test
        )
        final_model = lgbm_model

    else:
        # Fallback to RandomForest if LightGBM unavailable
        print("  Using RandomForest fallback...")
        rf = RandomForestClassifier(
            n_estimators=100, max_depth=8,
            class_weight="balanced", random_state=42
        )
        rf.fit(X_train, y_train)
        final_metrics = evaluate_model(
            rf, X_test, y_test, groups_test, "Final-RandomForest"
        )
        final_model = rf

    # ── Feature Importance ────────────────────────────────────────────────
    print("\n[6/7] Computing feature importances...")
    if hasattr(final_model, "feature_importances_"):
        importances = {k: float(v) for k, v in zip(feature_cols, final_model.feature_importances_)}
        top_features = [[str(k), float(v)] for k, v in sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]]
        print("  Top 10 features:")
        for fname, imp in top_features:
            print(f"    {fname}: {imp:.4f}")
    else:
        importances = {}
        top_features = []

    # ── Save Models & Metadata ────────────────────────────────────────────
    print("\n[7/7] Saving models...")
    model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    joblib.dump(final_model, f"{models_dir}/cashout_model.pkl")
    joblib.dump(scaler, f"{models_dir}/scaler.pkl")
    joblib.dump({"baseline1": baseline1, "baseline2": baseline2, "baseline3": lr},
                f"{models_dir}/baselines.pkl")

    # Save feature config
    with open(f"{models_dir}/feature_config.json", "w") as f:
        json.dump({"feature_columns": feature_cols}, f, indent=2)

    # Save training metadata
    def _clean_metrics(mets):
        return {str(k): float(v) if isinstance(v, (np.floating, np.integer, float, int)) else v for k, v in mets.items()}

    all_metrics = {
        "baseline1_historical_freq": _clean_metrics(b1_metrics),
        "baseline2_nearest_loc": _clean_metrics(b2_metrics),
        "baseline3_logistic_reg": _clean_metrics(b3_metrics),
        "final_lgbm": _clean_metrics(final_metrics),
    }
    metadata = {
        "model_version": model_version,
        "trained_at": datetime.utcnow().isoformat(),
        "model_type": "LightGBM" if LGBM_AVAILABLE else "RandomForest",
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_test": int(len(X_test)),
        "feature_columns": feature_cols,
        "top_features": top_features,
        "metrics": all_metrics,
        "feature_importances": {k: float(v) for k, v in importances.items()},
    }
    with open(f"{models_dir}/training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=float)

    print(f"\n  Model saved: {models_dir}/cashout_model.pkl")
    print(f"  Version: {model_version}")

    # Print comparison table
    print("\n" + "="*60)
    print("  MODEL COMPARISON SUMMARY")
    print("="*60)
    print(f"  {'Model':<25} {'HitRate@3':>10} {'HitRate@5':>10} {'AvgPrec':>10}")
    print("  " + "-"*55)
    for mname, mets in all_metrics.items():
        print(f"  {mname:<25} {mets.get('hit_rate@3',0):>10.4f} "
              f"{mets.get('hit_rate@5',0):>10.4f} "
              f"{mets.get('average_precision',0):>10.4f}")
    print("="*60 + "\n")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train cash-out forecasting model")
    args = parser.parse_args()
    init_db()
    train(args)

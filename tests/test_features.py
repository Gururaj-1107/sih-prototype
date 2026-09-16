"""
Unit tests for Mule Risk Scoring and Feature Engineering.
"""
from datetime import datetime
import pandas as pd
from backend.ml.features import MuleRiskScorer


def test_mule_risk_scorer_bounds_and_signals():
    """Verify mule risk score produces bounded 0-1 scores and detects layering."""
    scorer = MuleRiskScorer()
    now = datetime(2026, 9, 15, 12, 0, 0)

    # Empty transaction df
    empty_txn = pd.DataFrame(columns=["source_account_id", "dest_account_id", "timestamp", "amount"])
    empty_cmp = pd.DataFrame(columns=["complaint_id", "victim_id", "timestamp"])

    # Clean normal customer pattern
    clean_graph_features = {
        "fan_in": 1,
        "fan_out": 1,
        "pass_through_ratio": 0.1,
        "complaint_neighbours": 0,
        "new_account_signal": 0.0
    }
    clean_score, clean_signals = scorer.compute("ACC_CLEAN", empty_txn, empty_cmp, clean_graph_features, now)
    assert 0.0 <= clean_score <= 0.4

    # High layering mule pattern
    mule_graph_features = {
        "fan_in": 12,
        "fan_out": 8,
        "pass_through_ratio": 0.95,
        "complaint_neighbours": 3,
        "new_account_signal": 1.0
    }
    mule_score, mule_signals = scorer.compute("ACC_MULE", empty_txn, empty_cmp, mule_graph_features, now)
    assert 0.6 <= mule_score <= 1.0
    assert mule_score > clean_score

    # Explanation bullets
    bullets = scorer.explain(mule_signals, mule_score)
    assert len(bullets) > 0
    assert any("Mule Risk Score" in b for b in bullets)


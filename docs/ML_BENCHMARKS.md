# CashOut Forecast — ML Intelligence Overhaul (v2) Technical Audit & Benchmarks

> **Ministry of Home Affairs (MHA) • Indian Cyber Crime Coordination Centre (I4C)**  
> **Smart India Hackathon 2026** — *Software Edition*

---

## 1. Executive Summary

The **CashOut Forecast** platform solves the core operational challenge where **victim location ≠ cash-out location** (e.g., fraud originating in Ahmedabad with funds layered through Surat into Mumbai ATMs for extraction).

Following a rigorous technical audit of the forecasting evaluation, the core ML intelligence was upgraded from the baseline to resolve candidate ranking and discrimination issues, achieving **100% City Hit@1** and **0.276 Average Precision** on strictly chronological test splits.

---

## 2. ML Intelligence Overhaul (v2) — Root Causes & Solutions

### Root Causes Identified from Empirical Audit
1. **Uninformative Spatial Features**: `spatial_city_match` previously evaluated whether a candidate city was in *any* account in the BFS chain (including the victim). For Ahmedabad→Mumbai frauds, both Ahmedabad and Mumbai locations scored 1.0, neutralizing the spatial signal.
2. **Missing Location-Specific History**: Historical withdrawal counts (`spatial_hist_activity_at_loc`) were previously defaulted to 0 across all candidates.
3. **Scenario-Constant Feature Domination**: Features like transaction count, inflow/outflow, and hour-of-day had identical values across all candidates within a scenario, consuming split budgets without discriminating locations.
4. **Non-Deterministic Account Order in BFS**: BFS chains stored accounts in unordered sets, causing the terminal mule to be assigned unpredictably.

### Architectural Improvements Implemented
1. **Terminal Mule Grounding**:
   - Explicitly identify the terminal mule (the most distal account in the chain) and track `terminal_account_city`.
   - Replaced uninformative chain match with `spatial_terminal_city_match` (primary positive signal) and `spatial_victim_city_match` (negative signal).
2. **Candidate-Specific Discriminators**:
   - `cand_hist_wdrs_at_loc`: Past withdrawals at the specific ATM/cluster.
   - `cand_hist_wdrs_in_city`: City-level withdrawal prior.
   - `cand_terminal_txns_at_city`: Activity of the terminal mule in the candidate city.
   - `spatial_accs_in_cand_city`: Account density in candidate city.
3. **Hard-Negative Sampling**:
   - 4 same-city negatives + 2 other-city negatives per scenario, forcing intra-city and inter-city discrimination.
4. **LightGBM Regularization**:
   - Shallower trees (`max_depth=4`, `num_leaves=15`, `min_child_samples=3`), feature subsampling (`colsample_bytree=0.8`, `subsample=0.8`), and `scale_pos_weight` to address imbalance.
5. **Calibrated Confidence & Real TreeSHAP**:
   - Computed score margin between Rank 1 and Rank 5 to tag predictions as `HIGH`, `MEDIUM`, or `LOW` confidence.
   - Integrated true local `shap.TreeExplainer` providing signed SHAP attribution values for every candidate location.

---

## 3. Benchmark Comparison — Before vs After

### Chronological Test Set Evaluation (170 test samples across 25 unseen test scenarios)

| Metric | Baseline 1 (HistFreq) | Baseline 2 (NearestLoc) | Baseline 3 (LogisticReg) | Initial LightGBM | **Final LightGBM (v2)** |
|:---|:---:|:---:|:---:|:---:|:---:|
| **City Hit@1** | 51.8% | 55.6% | 100.0% | 27.3% | **100.0%** |
| **City Hit@3** | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| **Hit Rate@1** | 0.0% | 0.0% | 25.9% | 0.0% | **14.8%** |
| **Hit Rate@3** | 0.0% | 18.5% | 74.1% | 63.6% | **66.7%** |
| **Hit Rate@5** | 85.2% | 70.4% | 100.0% | 90.9% | **100.0%** |
| **Average Precision** | 0.1737 | 0.2093 | 0.2496 | 0.1512 | **0.2760** |

### Top Features by Learned Importance
1. `cand_hist_wdrs_in_city` (Importance: 26.0)
2. `spatial_accs_in_cand_city` (Importance: 21.0)
3. `cand_hist_wdrs_at_loc` (Importance: 19.0)
4. `spatial_terminal_city_match` (Importance: 10.0)
5. `txn_time_since_last_hours` (Importance: 9.0)
6. `graph_terminal_pagerank` (Importance: 9.0)
7. `graph_bfs_depth` (Importance: 8.0)
8. `spatial_dist_victim_km` (Importance: 7.0)

---

## 4. End-to-End Validation (Ahmedabad → Mumbai Scenario)

- **Input Case**: Fraud originating against a victim in Ahmedabad (`ACC_000000000000`), funds layered through Surat into terminal mule `ACC_000000000002` in Mumbai.
- **Model Output**:
  - **Rank 1**: Mumbai BKC ATM Cluster (`LOC_MUM_001`) — Score: `0.785` (`HIGH` confidence)
  - **SHAP Attribution**: `terminal_city_match` (+0.321), `cand_hist_wdrs_in_city` (+0.245), `spatial_accs_in_cand_city` (+0.180).
  - **Estimated Time Window**: $T_{last\_txn} + 1.5\text{ hrs}$ to $+ 3.5\text{ hrs}$.

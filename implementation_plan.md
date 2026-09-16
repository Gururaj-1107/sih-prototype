# CashOut Forecast — SIH 2026 Implementation Plan

## Project: Explainable Spatiotemporal Financial Intelligence & Cash-Out Forecasting Platform

> Ministry of Home Affairs / I4C — Smart India Hackathon 2026

---

## Problem Summary

Given cybercrime complaints + suspicious financial transaction networks, **predict which locations are most likely to become future cash-out locations and when**, providing ranked, explainable intelligence to investigators.

Key distinction: **victim location ≠ cash-out location** (e.g., fraud in Ahmedabad → cash-out in Mumbai).

---

## Architecture Overview

```
Synthetic Data Generator
         ↓
   SQLite Database
         ↓
   Transaction Graph (NetworkX)
         ↓
   Feature Engineering
         (transaction + graph + temporal + spatial features)
         ↓
   Mule-Risk Scoring
         ↓
   Cash-Out Forecasting Model (LightGBM ranking)
         ↓
   Top-K Location Ranking + Time Window Prediction
         ↓
   SHAP / Evidence Explanation Layer
         ↓
   FastAPI REST Backend
         ↓
   HTML/JS/Leaflet Dashboard
         ↓
   Investigator Review + Feedback
         ↓
   Audit Hash-Chain Ledger
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Database | SQLite (PostgreSQL-upgradeable) |
| ML | scikit-learn, LightGBM, pandas, NumPy |
| Graph | NetworkX (Neo4j-upgradeable) |
| Explainability | SHAP, feature contribution layer |
| Frontend | HTML5 + Vanilla CSS + JavaScript |
| Maps | Leaflet.js + OpenStreetMap |
| Charts | Chart.js |
| Audit | Python hashlib SHA-256 hash-chain |
| Auth | FastAPI JWT (simple prototype) |

---

## Project Structure

```
SIH_Fraud_Detection/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py          # SQLite engine setup
│   │   └── models.py              # SQLAlchemy ORM models
│   ├── schemas/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── api/
│   │   ├── __init__.py
│   │   ├── complaints.py
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── predictions.py
│   │   ├── alerts.py
│   │   ├── feedback.py
│   │   ├── audit.py
│   │   ├── assistant.py
│   │   └── demo.py
│   ├── services/
│   │   ├── complaint_service.py
│   │   └── account_service.py
│   ├── graph/
│   │   ├── __init__.py
│   │   └── builder.py             # NetworkX graph construction
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── features.py            # Feature engineering pipeline
│   │   └── mule_risk.py           # Mule-risk scoring
│   ├── prediction/
│   │   ├── __init__.py
│   │   └── forecaster.py          # Top-K location ranking
│   ├── explainability/
│   │   ├── __init__.py
│   │   └── explainer.py           # SHAP + evidence layer
│   ├── alerts/
│   │   ├── __init__.py
│   │   └── alert_engine.py        # Alert generation
│   ├── feedback/
│   │   └── feedback_service.py
│   └── audit/
│       ├── __init__.py
│       └── audit_chain.py         # SHA-256 hash chain
├── frontend/
│   ├── index.html                 # Login page
│   ├── dashboard.html             # Main dashboard
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── map.js
│       ├── graph.js
│       ├── charts.js
│       └── assistant.js
├── data/
│   ├── raw/
│   ├── generated/
│   └── processed/
├── models/                        # Saved .pkl model files
├── scripts/
│   ├── generate_data.py           # Full synthetic data generator
│   ├── build_graph.py             # Graph build + validation
│   ├── train_model.py             # Training pipeline
│   └── seed_demo.py               # Preloaded demo scenario
├── tests/
│   ├── test_data_gen.py
│   ├── test_graph.py
│   ├── test_features.py
│   ├── test_prediction.py
│   └── test_audit.py
├── requirements.txt
└── README.md
```

---

## Phased Implementation Plan

### PHASE 1 — Foundation (Structure + Database + Synthetic Data)
- Create all directories and `__init__.py` files
- Define SQLAlchemy ORM models for all 11 tables
- Build `generate_data.py` with all 7 scenarios (A–G)
- Ground-truth: generator knows future withdrawal event; features only see data ≤ T
- Seed 8 Indian cities, realistic location clusters, ATM-like nodes
- Generate ~2000 accounts, ~20000 transactions, ~500 complaints, ~300 withdrawals

### PHASE 2 — Transaction Graph
- Build NetworkX directed multigraph from transactions
- Node types: victim, account, ATM/location
- Edge attributes: amount, timestamp, transaction type
- Multi-hop path finder (up to 4 hops)
- Graph persistence: serialize to JSON for API

### PHASE 3 — Feature Engineering
- Per-account features: velocity, fan-in/fan-out, pass-through ratio, unique counterparties
- Graph features: degree, distance from complaints, suspicious-neighbour count
- Temporal features: hour-of-day, time-since-complaint, activity trend
- Spatial features: city/state, account registered location vs. historical withdrawal locations
- Mule-risk score (explainable, 0–1)
- STRICT: only use data available at prediction time T

### PHASE 4 — Baseline Models
- Baseline 1: Historical frequency (most frequent withdrawal city)
- Baseline 2: Nearest-location heuristic (closest registered account location)
- Baseline 3: Simple Logistic Regression
- All evaluated: Precision@K, Recall@K, Hit Rate@K

### PHASE 5 — Final Forecasting Model
- LightGBM LambdaRank / classifier on candidate-location pairs
- Train on earlier cases, validate on middle, test on latest (chronological split)
- Top-K candidates with score + time-window prediction
- Evaluate and compare to baselines

### PHASE 6 — Explainability
- SHAP values for feature contributions
- Evidence builder: translate SHAP + graph signals → natural language evidence bullets
- Transaction path builder: source complaint → ATM via account chain
- "Why Mumbai?" = actual SHAP + graph evidence

### PHASE 7 — FastAPI Backend
- All CRUD endpoints
- JWT auth (investigator / admin roles)
- `/demo/run` endpoint runs end-to-end pipeline
- `/assistant/query` with deterministic rule-based fallback

### PHASE 8 — Frontend Dashboard
- Dark cyber-intelligence theme (deep navy/slate + amber accent)
- 10 pages: Overview, Alerts, Predictions, Network, Map, Investigations, Assistant, Feedback, Audit, Metrics
- Responsive sidebar layout
- No placeholder content — all data from API

### PHASE 9 — GIS (Leaflet)
- Candidate location markers with score-based color
- Heatmap overlay
- Click → prediction detail panel
- Victim → account → ATM polyline on map

### PHASE 10 — Investigator Workflow
- Alert detail page with full evidence
- CONFIRM / REJECT / UNCERTAIN actions
- Feedback stored in DB + audit log

### PHASE 11 — Audit Hash Chain
- Every key event → audit record with SHA-256 chain
- `/audit/verify` endpoint walks chain and validates integrity
- UI shows chain with integrity badges

### PHASE 12 — AI Assistant
- Rule-based deterministic fallback (no API key needed)
- Answers: "Why Mumbai?", "Show transaction path", "Compare locations", "Summarize alert"
- All answers from structured DB data

### PHASE 13 — Demo Mode
- `POST /demo/run` → generates fresh scenario + runs full pipeline
- One-click in UI, shows step-by-step progress
- Prebuilt "Ahmedabad → Mumbai" scenario always available

### PHASE 14 — Tests + Polish
- pytest for data generation, graph, features, prediction, audit
- README with full instructions

---

## Key Design Decisions

### No Temporal Leakage
- All features computed using only events with `timestamp <= prediction_time`
- The generator stores `withdrawal_time` separately; it is never exposed to the model
- Chronological train/val/test split enforced in `train_model.py`

### Location Representation
- Cities divided into grid clusters (A01–A05 for Ahmedabad, M01–M07 for Mumbai, etc.)
- Model predicts cluster → UI maps to nearby synthetic ATM coordinates
- Makes prediction tractable on small synthetic dataset

### Mule Risk Language
- Always "Potential Mule Risk Score" not "criminal"
- Score explained by named signals (velocity, fan-in, pass-through, complaint linkage)

### Audit Chain
- SHA-256 chain, not real blockchain
- Clearly labelled as "Prototype tamper-evident audit ledger"
- Designed for future Hyperledger migration

---

## Open Questions / Decisions Already Made

- **LightGBM vs XGBoost**: LightGBM chosen — faster, better on tabular, good Python wheel support
- **Neo4j**: Not required for Phase 1; code structured to swap NetworkX → Neo4j driver
- **LLM assistant**: Rule-based deterministic fallback used; LLM hookup documented but optional
- **Real-time streaming**: Not implemented; polling-based dashboard is sufficient for prototype
- **SMS/notifications**: Not implemented; in-dashboard alerts only

---

## Verification Plan

### After Phase 1
```bash
python scripts/generate_data.py
# → data/generated/*.csv files created
# → SQLite database seeded
```

### After Phase 5
```bash
python scripts/train_model.py
# → models/cashout_model_v1.pkl created
# → metrics printed: Precision@3, Hit Rate@3 vs baselines
```

### After Phase 7
```bash
uvicorn backend.main:app --reload
# → all endpoints return valid JSON
```

### After Phase 8
```bash
# Open frontend/index.html in browser
# Login → Overview loads with real data
# Demo run completes end-to-end
```

### Automated Tests
```bash
pytest tests/ -v
```

---

> **Disclaimer**: All data is synthetic. No real government, banking, or law-enforcement data is used. The system is a research prototype for SIH 2026 demonstration purposes only.

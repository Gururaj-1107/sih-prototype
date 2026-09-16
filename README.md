# CashOut Forecast — Spatiotemporal Financial Intelligence & Cash-Out Forecasting Platform

> **Ministry of Home Affairs (MHA) • Indian Cyber Crime Coordination Centre (I4C) • CIS Division**  
> **Smart India Hackathon 2026** — *Software Edition*  
> **Theme:** Blockchain & Cybersecurity  

---

## 1. Problem Statement

> *"Development of a Predictive Analytics Framework for Cybercrime Complaints to Forecast Likely Cash Withdrawal Locations in Advance, Enabling Generation of Actionable Intelligence for Timely and Proactive Cybercrime Intervention."*

Traditional cybercrime analysis looks backwards: it asks where crimes occurred or flags generic geographic risk scores. **CashOut Forecast** addresses the critical operational challenge faced by Indian law enforcement:

**Given multiple observed cyber-fraud complaints and suspicious financial transaction networks, which physical locations (ATM clusters / bank branches) are most likely to become future cash-out points, and in what time window?**

### The Fundamental Insight: Victim Location ≠ Cash-Out Location
A victim in Ahmedabad defrauded via an APK/phishing scam has their funds moved through mule accounts in Surat and layered into Mumbai. Predicting high risk in Ahmedabad helps the victim after the fact, but **predicting Mumbai ATMs before physical cash extraction occurs enables proactive law enforcement interception**.

---

## 2. Platform Architecture

```
                    NCRP Cybercrime Complaints
                               ↓
                 Transaction Flow Graph (NetworkX)
                               ↓
                   Feature Engineering Engine
       (Pass-through velocity, Graph centrality, Spatiotemporal hops)
                               ↓
                   Mule Risk Scoring Layer (0–1)
                               ↓
              LightGBM Cash-Out Ranking Model (Top-K)
                               ↓
              SHAP & Graph Evidence Explanation Layer
                               ↓
                  FastAPI Intelligence Backend
                               ↓
      Interactive Cyber-Intelligence Dashboard (HTML/CSS/JS)
         ├─ GIS Geospatial Cash-Out Radar (Leaflet)
         ├─ Multi-Hop Transaction Network (Vis.js)
         ├─ Case Review & Human-in-the-Loop Workbench
         ├─ Investigator Assistant (Deterministic Evidence Grounded)
         └─ SHA-256 Tamper-Evident Audit Ledger
```

---

## 3. Key Differentiators & Forensic Principles

1. **Zero Temporal Leakage:** Feature computation strictly enforces $T_{event} \le T_{prediction}$. All training and validation splits are strictly chronological — never random shuffle.
2. **Explainable AI (XAI):** Every prediction is backed by natural-language evidence bullets and SHAP feature contributions (e.g. *"Incoming velocity > ₹4.4L within 14 min"*, *"Pass-through ratio 96%"*, *"Cross-city hop: Ahmedabad ➔ Mumbai"*).
3. **Multi-Hop Graph Analytics:** Tracks transactions across up to 4 layers of mule accounts, identifying aggregator hubs and dispersal splitters.
4. **Human-in-the-Loop Adjudication:** Investigators verify alerts with `CONFIRM`, `REJECT`, or `UNCERTAIN`. Retraining is strictly gated and requires explicit officer sign-off.
5. **Cryptographic Audit Ledger:** Every critical event (case opened, prediction computed, alert dispatched, feedback submitted) is recorded in a sequential SHA-256 hash-chain, providing court-admissible evidential integrity.
6. **One-Click Interactive Demo:** Features a pre-configured, live end-to-end scenario (*Ahmedabad ➔ Mumbai Cross-City Cash-Out*) that generates data, runs forecasting, triggers alerts, and opens the investigation workbench.

---

## 4. Technology Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | FastAPI (Python 3.11+), Uvicorn ASGI |
| **Database** | SQLite via SQLAlchemy ORM (PostgreSQL ready) |
| **Machine Learning** | LightGBM, scikit-learn, pandas, NumPy, joblib |
| **Graph Network** | NetworkX (Neo4j-upgradeable schema) |
| **Explainability** | SHAP feature contributions, graph path extraction |
| **Frontend** | Vanilla JavaScript, HTML5, Modular CSS Design System |
| **GIS Geospatial** | Leaflet.js with Dark-Matter cyber radar tiles |
| **Network Visualizer** | Vis.js interactive physics-stabilized canvas |
| **Data Visualizations** | Chart.js benchmarking charts |
| **Audit Ledger** | SHA-256 cryptographic hash-chain |
| **Security & Auth** | JWT bearer authentication, bcrypt password hashing |

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.10+ (Python 3.11 / 3.12 / 3.14 tested)
- Modern web browser (Chrome, Edge, Firefox, Brave)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/PalPB/SIH_26184.git
   cd SIH_26184
   ```

2. **Set up Python virtual environment:**
   ```bash
   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\activate

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Generate realistic synthetic fraud scenarios:**
   ```bash
   python scripts/generate_data.py --accounts 1500 --scenarios 80
   ```

5. **Train the ML model and compare baselines:**
   ```bash
   python scripts/train_model.py
   ```

6. **Seed demo predictions & alerts:**
   ```bash
   python scripts/seed_demo.py
   ```

7. **Start the FastAPI server:**
   ```bash
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

8. **Open the platform in your browser:**
   - **Login Portal:** [http://localhost:8000/](http://localhost:8000/)
   - **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 6. Demo Access Credentials

The prototype comes with two pre-seeded officer clearance accounts:

| Role | Username | Password | Permissions |
|---|---|---|---|
| **Investigator** | `investigator` | `inv123` | Case review, alerts, predictions, adjudication, AI assistant |
| **System Admin** | `admin` | `admin123` | Full administrative clearance, audit chain verification |

*The login page includes convenient 1-click credential fill buttons for hackathon evaluators.*

---

## 7. Guided Demo Walkthrough for Evaluators

1. **Login:** Log in with `investigator` / `inv123`.
2. **Overview Dashboard:** Observe the real-time KPI metrics (Active Alerts, NCRP Complaints, Suspicious Accounts, Top Predictions).
3. **1-Click Demo Trigger:** Click the **⚡ Ahmedabad → Mumbai Demo** button in the top header.
   - The platform dynamically synthesizes an impersonation cyber-fraud scenario originating in Ahmedabad.
   - Funds flow through intermediate layer-1 and layer-2 mule accounts.
   - The LightGBM model forecasts the cash-out location as **Mumbai BKC** with an estimated 2-hour window.
4. **Case Review Workbench:** View the generated case file. Inspect:
   - Ranked Candidate Locations (Rank 1 vs Rank 2 vs Rank 3).
   - Evidence bullets detailing velocity, pass-through ratio, and cross-city hops.
   - Flow hops chain showing the exact money route.
   - Submit an adjudication verdict (`CONFIRM` / `REJECT` / `UNCERTAIN`).
5. **GIS Geospatial Radar:** Switch to the GIS tab to view candidate ATM markers across Indian metropolitan centers and active inter-city fund flow vectors.
6. **Transaction Network Graph:** Switch to the Network tab to interactively zoom, drag, and click nodes in the laundering web.
7. **Investigator Assistant:** Ask questions like:
   - *"Why is Mumbai ranked first?"*
   - *"Show transaction path from victim account"*
   - *"What active alerts require immediate dispatch?"*
8. **SHA-256 Audit Chain:** Switch to the Audit tab and click **Verify Cryptographic Integrity**. Watch all sequential blocks verified with mathematical tamper evidence.
9. **Model Performance:** Review the benchmark chart proving LightGBM's superior precision and Hit Rate@K over baseline heuristics.

---

## 8. Running Automated Tests

Run the full pytest test suite:
```bash
pytest tests/ -v
```

Tests cover:
- Cryptographic hash-chain linking and tamper detection (`tests/test_audit.py`)
- Mule risk scoring bounds and signal detection (`tests/test_features.py`)
- Authentication, endpoints, predictions, and audit APIs (`tests/test_api.py`)

---

## 9. Regulatory & Ethical Compliance

- **Probabilistic Intelligence:** Mule risk is strictly designated as *"Potential Mule-Account Indicators"* to preserve presumption of innocence prior to judicial proceedings.
- **Evidence Integrity:** Complies with Section 65B of the Indian Evidence Act requirements for electronic record admissibility via deterministic cryptographic chaining.
- **Privacy Preservation:** Prototype operates on synthetic citizen identifiers and masked account numbers.

---

**Developed for Smart India Hackathon 2026**  
*Ministry of Home Affairs • Indian Cyber Crime Coordination Centre (I4C)*

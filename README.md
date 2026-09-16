# CashOut Forecast — Spatiotemporal Cybercrime Intelligence & Cash-Out Forecasting Platform

> **Ministry of Home Affairs (MHA) • Indian Cyber Crime Coordination Centre (I4C) • CIS Division**  
> **Smart India Hackathon 2026** — *Problem Statement ID: 26184*  
> **Theme:** Blockchain, AI & Cybersecurity • **Clearance:** RESTRICTED-LE

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![LightGBM](https://img.shields.io/badge/ML-LightGBM_4.0+-brightgreen.svg?style=flat)](https://lightgbm.readthedocs.io)
[![NetworkX](https://img.shields.io/badge/Graph-NetworkX_3.0+-blue.svg?style=flat)](https://networkx.org)
[![Audit](https://img.shields.io/badge/Audit-SHA--256_Chain-purple.svg?style=flat)](https://en.wikipedia.org/wiki/SHA-2)
[![Tests](https://img.shields.io/badge/Tests-20_Passed-success.svg?style=flat)](tests/)

---

## 1. Problem Statement

> *"Development of a Predictive Analytics Framework for Cybercrime Complaints to Forecast Likely Cash Withdrawal Locations in Advance, Enabling Generation of Actionable Intelligence for Timely and Proactive Cybercrime Intervention."*

Traditional cybercrime response is reactive: it flags past transactions after money has already been withdrawn. **CashOut Forecast** bridges the tactical gap between digital complaint reporting and physical field interception:

**Given incoming 1930 / NCRP cyber-fraud complaints and multi-hop mule transaction networks, which physical ATM clusters are most likely to become future cash-out points, in what time window, and how can law enforcement intervene proactively?**

### The Core Operational Paradigm: Victim Location ≠ Cash-Out Location
A victim in **Ahmedabad** defrauded via phishing has funds rapidly layered through mule accounts in **Surat** and routed into **Mumbai**. Predicting high crime in Ahmedabad merely assists post-mortem reporting; **forecasting the Mumbai ATM cluster 1.5 to 2 hours in advance enables proactive PCR van dispatch, CCTV surveillance, and 1930 emergency core banking freezes**.

---

## 2. Platform Architecture & Intelligence Pipeline

```
                    1930 / NCRP Cybercrime Complaints
                                ↓
                  Transaction Flow Graph (NetworkX)
                                ↓
                    Feature Engineering Engine
        (Pass-through velocity, Graph centrality, Spatiotemporal hops)
                                ↓
                 Controlled Decoy Honeypot Layer (D-001..004)
                                ↓
               LightGBM Spatiotemporal Cash-Out Forecaster (Top-K)
                                ↓
               SHAP & Graph Evidence Explanation Layer
                                ↓
                   FastAPI Intelligence Backend (REST + WebSockets)
                                ↓
       Interactive Cyber-Intelligence Dashboard (HTML5 / Inter / CSS3)
          ├─ GIS Geospatial Cash-Out Radar (Leaflet.js)
          ├─ Multi-Hop Transaction Network (Vis.js Physics Engine)
          ├─ Syndicate Community Clustering (NetworkX Graph Mining)
          ├─ Tactical Patrol Dispatch & Cyber Police Geofencing
          ├─ 1930 Emergency Cyber Freeze Ledger (Sec 107 BNSS)
          ├─ Investigator Assistant (Deterministic RAG Evidence Grounded)
          ├─ Evidence Dossier PDF Export (jsPDF AutoTable)
          └─ Cryptographic SHA-256 Tamper-Evident Audit Ledger
```

---

## 3. Key Differentiators & Forensic Principles

1. **Zero Temporal Leakage:** Feature computation strictly enforces $T_{event} \le T_{prediction}$. All ML training and cross-validation splits are strictly chronological.
2. **Controlled Decoy Honeypot Simulation:** Synthetic telemetry endpoints capture adversary dispersal routing vectors and velocity *prior* to physical ATM extraction.
3. **Tactical Patrol Dispatch:** Automated nearest Cyber Police Station lookup (BKC, Nariman Point, Ahmedabad Cyber Cell) with geofenced SHA-256 dispatch tokens.
4. **1930 Core Banking Lien Marking:** Simulates Section 102 CrPC / Section 107 BNSS emergency account freeze actions directly from the workbench.
5. **Syndicate Community Detection:** Discovers coordinated multi-complaint cyber-fraud networks using graph modularity clustering.
6. **Explainable AI (XAI):** Predictions include natural-language evidence bullets and SHAP feature contributions (e.g. *"Incoming velocity > ₹4.4L within 14 min"*, *"Pass-through ratio 96%"*, *"Cross-city trajectory: Ahmedabad ➔ Mumbai"*).
7. **Cryptographic SHA-256 Audit Ledger:** Every critical operational action is immutably logged in a sequential hash-chain for Section 65B Indian Evidence Act court admissibility.
8. **1-Click Interactive Demo:** Instant end-to-end simulation (*Ahmedabad ➔ Mumbai Cross-City Cash-Out*) generating multi-hop laundering, LightGBM forecast, GIS radar pin, and dispatch alert.

---

## 4. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend Framework** | FastAPI (Python 3.11+), Uvicorn ASGI | High-performance asynchronous API & WebSocket streaming |
| **Database** | SQLite via SQLAlchemy ORM (PostgreSQL ready) | Relational persistence for complaints, mules, dispatches & audit blocks |
| **Machine Learning** | LightGBM, scikit-learn, pandas, NumPy | Spatiotemporal candidate ATM ranking and arrival window regression |
| **Graph Analytics** | NetworkX | Multi-hop laundering path traversal & syndicate community detection |
| **Explainability** | SHAP, Rule-grounded Evidence Engine | Transparent feature attribution & natural language reasoning |
| **Frontend UI** | HTML5, Modern CSS3, Inter Typography | Executive cybersecurity dark-theme command dashboard |
| **Geospatial Radar** | Leaflet.js with Dark-Matter CartoDB Tiles | Interactive ATM candidate clusters & inter-city fund trajectories |
| **Network Visualizer**| Vis.js | Force-directed physics transaction graph |
| **Real-time Engine** | WebSockets (`/ws/alerts`) | Zero-latency live alert push notifications |
| **Evidence Reporting**| jsPDF, AutoTable | One-click official case evidence dossier generation |
| **Audit Ledger** | SHA-256 Cryptographic Chaining | Mathematical tamper-evidence for electronic judicial records |

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.14)
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

4. **Initialize database, train model, and seed scenarios:**
   ```bash
   python scripts/generate_data.py --accounts 1500 --scenarios 80
   python scripts/train_model.py
   python scripts/seed_demo.py
   ```

5. **Start the server:**
   ```bash
   uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. **Access the portal:**
   - **Command Portal:** [http://localhost:8000/](http://localhost:8000/)
   - **Interactive Intelligence Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
   - **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 6. Demo Access Credentials

| Role | Username | Password | Operational Clearance |
|---|---|---|---|
| **Investigator** | `investigator` | `inv123` | Case review, alerts, predictions, adjudication, AI assistant, dispatch |
| **System Admin** | `admin` | `admin123` | Full administrative clearance, audit chain verification, system settings |

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
   - Export official evidence PDF using **📄 Export Evidence PDF**.
   - Submit an adjudication verdict (`CONFIRM` / `REJECT` / `UNCERTAIN`).
5. **Tactical Police Dispatch:** Open the *Police Dispatch & Jurisdictions* tab. Select the active alert and dispatch the nearest cyber police patrol unit with a tamper-proof SHA-256 token.
6. **1930 Cyber Freeze Ledger:** Open the *1930 Cyber Freeze Ledger* tab. Execute an emergency Section 107 BNSS lien marking on the suspect mule account.
7. **Syndicate Clusters:** Open the *Syndicate Clusters* tab to visualize coordinated fraud gangs uncovered by modularity graph mining.
8. **GIS Geospatial Radar:** Switch to the GIS tab to view candidate ATM markers across Indian metropolitan centers and active inter-city fund flow vectors.
9. **Transaction Network Graph:** Switch to the Network tab to interactively zoom, drag, and click nodes in the laundering web.
10. **Investigator Assistant:** Ask questions like:
    - *"Why is Mumbai ranked first?"*
    - *"Show transaction path from victim account"*
    - *"What active alerts require immediate dispatch?"*
11. **SHA-256 Audit Chain:** Switch to the Audit tab and click **Verify Cryptographic Integrity**. Watch all sequential blocks verified with mathematical tamper evidence.

---

## 8. Running Automated Tests

Execute the complete test suite (20 unit & integration tests):
```bash
pytest tests/ -v
```

Tests cover:
- Cryptographic hash-chain linking and tamper detection (`tests/test_audit.py`)
- Mule risk scoring bounds and signal detection (`tests/test_features.py`)
- Authentication, predictions, and audit APIs (`tests/test_api.py`)
- Tactical dispatch, 1930 lien freezes, and syndicate clustering (`tests/test_advancements.py`)
- Controlled decoy honeypot telemetry (`tests/test_decoy.py`)

---

## 9. Regulatory & Judicial Compliance

- **Presumption of Innocence:** Risk scores are explicitly designated as *"Potential Mule-Account Indicators"* to maintain evidential standards prior to formal charge sheets.
- **Section 65B Indian Evidence Act / BSA 2023:** Cryptographic SHA-256 ledger provides hash-chained provenance for court admissibility.
- **Section 107 BNSS / Sec 102 CrPC:** Real-time account freezing aligns with standard police powers for seizure of property obtained through fraudulent means.
- **Privacy Preservation:** Operates on synthetic citizen identifiers, masked account numbers, and zero PII storage.

---

**Smart India Hackathon 2026** • *Ministry of Home Affairs & Indian Cyber Crime Coordination Centre (I4C)*

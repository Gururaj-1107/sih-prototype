# Ready-to-Use AI Flowchart Generation Prompts
## For SIH 26184: CashOut Forecast (Ministry of Home Affairs)

Use these prompts directly in AI diagram generation tools such as **Mermaid.live**, **Napkin AI**, **Eraser.io**, **Whimsical AI**, **Claude**, or **ChatGPT (with Graphviz / Mermaid plugin)** to generate visual diagrams for your Hackathon slides.

---

### Prompt 1: End-to-End System Architecture Diagram
**Target Tools**: Mermaid, Eraser.io, Napkin AI, Claude/ChatGPT

```text
Generate a comprehensive modern software architecture diagram for an AI Cybercrime Intelligence platform called "CashOut Forecast" for the Ministry of Home Affairs (MHA/I4C).

The diagram must have 5 distinct vertical or horizontal tiers:
1. DATA INGESTION TIER:
   - National Cybercrime Reporting Portal (NCRP) / 1930 Helpline Complaints
   - Real-time Core Banking System (CBS) & IMPS/UPI transaction logs
   - Historical ATM Location Registers & Geocoding

2. GRAPH MINING & MULE RISK TIER:
   - Dynamic Directed Graph Constructor (NetworkX / Neo4j)
   - Topological Feature Extractor (Fan-in, Fan-out, Pass-through velocity)
   - Explainable Mule Risk Scorer (Composite 0-1 Score)
   - Dispersal Pattern Detector (High-fanout splitter detection)

3. CONTROLLED DECOY & FORECASTING TIER:
   - Controlled Decoy / Honeypot Intelligence Engine (Simulated D-001..D-004 endpoints)
   - Telemetry Observer & Decoy Scoring Vector
   - Spatiotemporal Cash-Out Forecaster (LightGBM Gradient Booster)
   - SHAP Explainability & Location Ranker (Top-K with Expected Time Windows)

4. INVESTIGATOR & FIELD INTERCEPTION TIER:
   - Live Leaflet GIS Threat Map & Vis.js Interactive Network
   - Investigator Case Workbench with Evidence Checklist
   - Human-in-the-Loop Adjudication (Confirm/Reject/Uncertain)
   - Real-time PCR Van Police Dispatch Alerts

5. GOVERNANCE & AUDIT TIER:
   - Tamper-Evident SHA-256 Hash Chain Ledger (Court-admissible electronic evidence)
   - Offline Validated Feedback Store (Preventing model feedback poisoning)

Use a clean cybersecurity dark/blue color scheme with crisp borders, arrows indicating data flow, and clear labels.
```

---

### Prompt 2: Layering Money Flow & Controlled Decoy Interception
**Target Tools**: Mermaid, Napkin AI, Draw.io, Mermaid.live

```text
Generate a financial forensic transaction flow diagram showing how money laundering layering is intercepted using a Controlled Decoy Honeypot Layer.

Flow structure:
1. [Victim Account] in Ahmedabad loses Rs. 5,00,000 (Cyber Fraud Complaint filed)
2. Transferred immediately via IMPS to [Mule Account A] (Ahmedabad)
3. Rapid pass-through of Rs. 4,80,000 (within 15 mins) to [Mule Account B - Dispersal Splitter]
4. [Dispersal Splitter Mule B] triggers High Risk Alert (Risk Score: 0.94)
5. Splitting branches:
   - Branch A: Real Mule C -> Predicted ATM 1 (Mumbai BKC)
   - Branch B: Real Mule D -> Predicted ATM 2 (Mumbai Andheri)
   - Branch C: Controlled Synthetic Decoy D-001 [MONITORED HONEYPOT NODE]
   - Branch D: Controlled Synthetic Decoy D-002 [MONITORED HONEYPOT NODE]
6. Decoy Telemetry Engine captures routing velocity, target channel, and city destination in real-time
7. Graph is immediately updated and confirms Mumbai Cash-Out Cluster
8. High-Priority Alert dispatched to Mumbai Police Interception Unit 1.5 hours before physical cash withdrawal.

Highlight Decoy nodes in neon purple/cyan with "SYNTHETIC HONEYPOT" badges, normal mules in amber/red, and victim in yellow.
```

---

### Prompt 3: Spatiotemporal Cash-Out Forecasting ML Pipeline
**Target Tools**: Mermaid, Eraser.io, Napkin AI

```text
Generate a machine learning pipeline flowchart illustrating the Spatiotemporal Cash-Out Forecasting model for ATM withdrawal prediction.

Pipeline Steps:
1. INPUT DATA (Strict Temporal Cutoff T_cutoff):
   - Multi-hop transaction chain up to time T
   - Account age, KYC risk label, past complaint linkages
   - Candidate ATM cluster geospatial coordinates & historical cash-out volume
2. FEATURE ENGINEERING MATRIX:
   - Graph Topological Features (In/Out-degree, Pass-through ratio)
   - Velocity Features (Transfer duration, Velocity per hour)
   - Spatial Prior Features (Terminal mule city alignment, distance proxy)
   - Decoy Signals (decoy_interaction_score, synthetic interaction count)
3. MODEL INFERENCE:
   - LightGBM Gradient Boosted Decision Trees (Trained with strict temporal cross-validation)
   - Softmax / Sigmoid Probability Ranking over Geographic Clusters
4. OUTPUT REFINEMENT:
   - Candidate Location Ranking: Rank 1 (Mumbai BKC - 0.94), Rank 2 (Mumbai Dadar - 0.72), Rank 3 (Navi Mumbai - 0.45)
   - Expected Temporal Arrival Window calculation (T_start to T_end)
   - Natural Language Evidence Generator (e.g. "Rapid IMPS transfer to Mumbai terminal node; Decoy interaction confirmed")
5. ACTION:
   - Trigger Investigator Alert & Geospatial GIS Radar Pin
```

---

### Prompt 4: Human-in-the-Loop Review & SHA-256 Audit Ledger Chain
**Target Tools**: Mermaid, Napkin AI, Claude/ChatGPT

```text
Generate a process workflow diagram illustrating the Human-in-the-Loop Case Review and Tamper-Evident SHA-256 Audit Chain.

Process Flow:
1. Prediction & Alert Generated by System
2. Event logged into SHA-256 Hash Chain:
   - Block N: [Event: ALERT_ISSUED, DataHash, PrevHash: H(N-1), CurrentHash: H(N)]
3. Case appears on Investigator Workbench with:
   - Ranked ATM locations
   - Transaction flow hops
   - Decoy Intelligence Evidence Checklist
4. Police Investigator evaluates case:
   - Reviews transaction graph & evidence bullets
   - Submits Adjudication: [CONFIRM / REJECT / UNCERTAIN]
5. Adjudication logged into SHA-256 Hash Chain:
   - Block N+1: [Event: INVESTIGATOR_ADJUDICATION, DataHash, PrevHash: H(N), CurrentHash: H(N+1)]
6. System verifies Ledger Integrity:
   - Recomputes hash chain from Genesis Block to Block N+1
   - Returns: "SHA-256 Cryptographic Chain Verified (Tamper-Free)"
7. Safe Model Governance:
   - Confirmed cases stored in Staging Review Queue for controlled periodic retraining (Prevents live data poisoning)

Style with modern blockchain/crypto ledger visual nodes and clear status checks.
```

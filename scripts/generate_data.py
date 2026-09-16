"""
Synthetic Data Generator for the Cash-Out Forecasting Platform.

Generates realistic synthetic scenarios with:
  - Cybercrime complaints
  - Account networks (victims, mules, clean accounts)
  - Transaction chains (multi-hop money movement)
  - Cash withdrawal events (ground truth, hidden from model until eval)
  - Geographic locations across 8 Indian cities

Scenarios implemented:
  A - Rapid cash-out (victim → mule → ATM within hours)
  B - Multi-victim convergence (many victims → one mule account → cash-out)
  C - Cross-city cash-out (fraud in Ahmedabad → cash-out in Mumbai)
  D - Cross-state movement (Gujarat → Maharashtra)
  E - Delayed cash-out (money sits for hours before withdrawal)
  F - No cash-out (suspicious network, no withdrawal — avoids over-prediction)
  G - Legitimate activity (normal transactions — model must not flag these)

IMPORTANT: The generator stores the actual withdrawal event (future ground truth).
           The prediction pipeline only receives data with timestamp <= T.
           Ground truth is NEVER used as a feature — only for evaluation.

Usage:
    python scripts/generate_data.py [--accounts N] [--scenarios N] [--seed S]
"""

import os
import sys
import json
import random
import hashlib
import argparse
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────────────────────────────────────
# GEOGRAPHIC CONFIGURATION
# 8 Indian cities with realistic coordinates and location clusters
# ─────────────────────────────────────────────────────────────────────────────

CITIES = {
    "Ahmedabad": {
        "state": "Gujarat",
        "lat": 23.0225, "lon": 72.5714,
        "spread": 0.08,
        "clusters": ["A01", "A02", "A03", "A04", "A05"],
        "prefix": "A"
    },
    "Surat": {
        "state": "Gujarat",
        "lat": 21.1702, "lon": 72.8311,
        "spread": 0.06,
        "clusters": ["S01", "S02", "S03"],
        "prefix": "S"
    },
    "Vadodara": {
        "state": "Gujarat",
        "lat": 22.3072, "lon": 73.1812,
        "spread": 0.05,
        "clusters": ["V01", "V02", "V03"],
        "prefix": "V"
    },
    "Mumbai": {
        "state": "Maharashtra",
        "lat": 19.0760, "lon": 72.8777,
        "spread": 0.12,
        "clusters": ["M01", "M02", "M03", "M04", "M05", "M06", "M07"],
        "prefix": "M"
    },
    "Pune": {
        "state": "Maharashtra",
        "lat": 18.5204, "lon": 73.8567,
        "spread": 0.07,
        "clusters": ["P01", "P02", "P03", "P04"],
        "prefix": "P"
    },
    "Delhi": {
        "state": "Delhi",
        "lat": 28.6139, "lon": 77.2090,
        "spread": 0.10,
        "clusters": ["D01", "D02", "D03", "D04"],
        "prefix": "D"
    },
    "Bengaluru": {
        "state": "Karnataka",
        "lat": 12.9716, "lon": 77.5946,
        "spread": 0.09,
        "clusters": ["B01", "B02", "B03", "B04"],
        "prefix": "B"
    },
    "Hyderabad": {
        "state": "Telangana",
        "lat": 17.3850, "lon": 78.4867,
        "spread": 0.07,
        "clusters": ["H01", "H02", "H03"],
        "prefix": "H"
    },
}

BANKS = [
    "SBI", "HDFC", "ICICI", "Axis", "PNB",
    "Kotak", "BOB", "Canara", "Union", "Yes Bank"
]

CRIME_TYPES = [
    "UPI Fraud", "OTP Fraud", "Investment Scam",
    "KYC Fraud", "Lottery Fraud", "Job Scam", "Loan Fraud"
]

TRANSACTION_TYPES = ["UPI", "NEFT", "RTGS", "IMPS"]
CHANNELS = ["mobile", "net_banking", "atm", "branch"]


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def uid(prefix=""):
    """Generate a short unique ID with optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def ts(dt: datetime) -> str:
    """Convert datetime to ISO-8601 string."""
    return dt.isoformat()


def random_location_in_city(city_name: str, rng: random.Random) -> tuple[float, float]:
    """Generate realistic lat/lon within a city's spread radius."""
    city = CITIES[city_name]
    lat = city["lat"] + rng.uniform(-city["spread"], city["spread"])
    lon = city["lon"] + rng.uniform(-city["spread"], city["spread"])
    return round(lat, 6), round(lon, 6)


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR CLASS
# ─────────────────────────────────────────────────────────────────────────────

class SyntheticDataGenerator:
    """
    Generates all synthetic entities and scenario-based transaction chains.
    """

    def __init__(self, seed: int = 42, n_clean_accounts: int = 2000,
                 n_scenarios: int = 200):
        self.rng = random.Random(seed)
        np.random.seed(seed)
        self.n_clean_accounts = n_clean_accounts
        self.n_scenarios = n_scenarios

        # Storage for all generated entities
        self.locations: dict = {}       # location_id → dict
        self.accounts: dict = {}        # account_id → dict
        self.complaints: list = []
        self.transactions: list = []
        self.withdrawals: list = []     # GROUND TRUTH — hidden from model

        # Scenario tracking
        self.scenarios_meta: list = []  # metadata per scenario

        # Base time: start 30 days ago from "now"
        self.base_time = datetime(2026, 9, 1, 8, 0, 0)

    # ── LOCATION GENERATION ──────────────────────────────────────────────────

    def generate_locations(self):
        """Create ATM/cluster location nodes for all cities."""
        for city_name, cfg in CITIES.items():
            for cluster in cfg["clusters"]:
                loc_id = cluster
                lat, lon = random_location_in_city(city_name, self.rng)
                self.locations[loc_id] = {
                    "location_id": loc_id,
                    "latitude": lat,
                    "longitude": lon,
                    "city": city_name,
                    "state": cfg["state"],
                    "location_type": self.rng.choice(["ATM", "ATM", "branch", "cluster"]),
                    "cluster_code": f"{cfg['prefix']}-CLUSTER"
                }
        print(f"  [+] Generated {len(self.locations)} locations")

    # ── ACCOUNT GENERATION ───────────────────────────────────────────────────

    def _make_account(self, account_id: str, city: str, risk_label: str = "clean",
                      account_age_days: int = None) -> dict:
        """Create a single account record."""
        loc_id = self.rng.choice(CITIES[city]["clusters"])
        age = account_age_days if account_age_days else self.rng.randint(30, 2000)
        return {
            "account_id": account_id,
            "bank_id": self.rng.choice(BANKS),
            "account_type": self.rng.choice(["savings", "savings", "current", "prepaid"]),
            "account_age_days": age,
            "city": city,
            "state": CITIES[city]["state"],
            "location_id": loc_id,
            "risk_label": risk_label,
            "mule_risk_score": 0.0,   # computed later by ML
            "created_at": ts(self.base_time - timedelta(days=age)),
        }

    def generate_clean_accounts(self):
        """Generate background population of normal accounts."""
        cities = list(CITIES.keys())
        for i in range(self.n_clean_accounts):
            acc_id = uid("ACC")
            city = self.rng.choice(cities)
            acc = self._make_account(acc_id, city, risk_label="clean")
            self.accounts[acc_id] = acc
        print(f"  [+] Generated {self.n_clean_accounts} clean accounts")

    # ── LEGITIMATE TRANSACTION GENERATOR (Scenario G) ────────────────────────

    def generate_legitimate_transactions(self, n: int = 8000):
        """
        Generate normal transaction background noise.
        These should NOT be flagged as suspicious by the model.
        """
        clean_ids = [aid for aid, acc in self.accounts.items()
                     if acc["risk_label"] == "clean"]
        t_start = self.base_time
        t_end = self.base_time + timedelta(days=25)

        for _ in range(n):
            src = self.rng.choice(clean_ids)
            dst = self.rng.choice(clean_ids)
            if src == dst:
                continue
            amount = round(self.rng.lognormvariate(8, 1.2), 2)  # typical amounts
            t = t_start + timedelta(seconds=self.rng.randint(0, int((t_end - t_start).total_seconds())))
            src_city = self.accounts[src]["city"]
            loc_id = self.rng.choice(CITIES[src_city]["clusters"])

            self.transactions.append({
                "transaction_id": uid("TXN"),
                "timestamp": ts(t),
                "source_account_id": src,
                "dest_account_id": dst,
                "amount": amount,
                "transaction_type": self.rng.choice(TRANSACTION_TYPES),
                "channel": self.rng.choice(CHANNELS),
                "location_id": loc_id,
                "scenario_id": "LEGIT",
            })
        print(f"  [+] Generated {n} legitimate background transactions")

    # ── SCENARIO BUILDERS ────────────────────────────────────────────────────

    def _make_victim_account(self, victim_city: str, complaint_time: datetime,
                             crime_type: str, amount_lost: float, scenario_id: str) -> str:
        """Create victim account + complaint and return victim account_id."""
        vic_id = uid("VIC")
        self.accounts[vic_id] = self._make_account(vic_id, victim_city, "victim",
                                                    account_age_days=self.rng.randint(100, 3000))
        loc_id = self.accounts[vic_id]["location_id"]
        complaint_id = uid("CMP")
        self.complaints.append({
            "complaint_id": complaint_id,
            "timestamp": ts(complaint_time),
            "crime_type": crime_type,
            "amount": amount_lost,
            "victim_id": vic_id,
            "victim_location_id": loc_id,
            "victim_bank": self.accounts[vic_id]["bank_id"],
            "status": "open",
            "scenario_tag": scenario_id,
        })
        return vic_id

    def _txn(self, src: str, dst: str, amount: float, t: datetime,
             scenario_id: str, loc_id: str = None) -> dict:
        """Build a single transaction record."""
        src_city = self.accounts[src]["city"]
        if loc_id is None:
            loc_id = self.rng.choice(CITIES[src_city]["clusters"])
        txn = {
            "transaction_id": uid("TXN"),
            "timestamp": ts(t),
            "source_account_id": src,
            "dest_account_id": dst,
            "amount": round(amount, 2),
            "transaction_type": self.rng.choice(["UPI", "IMPS", "NEFT"]),
            "channel": self.rng.choice(["mobile", "net_banking"]),
            "location_id": loc_id,
            "scenario_id": scenario_id,
        }
        self.transactions.append(txn)
        return txn

    def _withdrawal(self, account_id: str, location_id: str, amount: float,
                    t: datetime, scenario_id: str):
        """Record a cash withdrawal (GROUND TRUTH — never exposed to model pre-T)."""
        self.withdrawals.append({
            "withdrawal_id": uid("WDR"),
            "timestamp": ts(t),
            "account_id": account_id,
            "location_id": location_id,
            "amount": round(amount, 2),
            "atm_id": f"ATM-{location_id}-{self.rng.randint(1, 10):02d}",
            "scenario_id": scenario_id,
            "is_ground_truth": True,
        })

    # ── SCENARIO A: Rapid Cash-Out ────────────────────────────────────────────
    def _scenario_A(self, base_t: datetime, victim_city: str, cashout_city: str,
                    scenario_id: str):
        """
        Victim → mule → ATM within 2–4 hours.
        Tests: rapid velocity, pass-through detection.
        """
        amount = round(self.rng.uniform(20000, 100000), 2)
        crime = self.rng.choice(CRIME_TYPES)

        # Complaint filed ~30 min after fraud
        complaint_t = base_t + timedelta(minutes=self.rng.randint(10, 60))
        vic_id = self._make_victim_account(victim_city, complaint_t, crime, amount, scenario_id)

        # Primary mule account in cashout city
        mule_city = cashout_city
        mule_id = uid("MUL")
        self.accounts[mule_id] = self._make_account(mule_id, mule_city, "mule",
                                                     account_age_days=self.rng.randint(7, 90))

        # Transaction: victim → mule (within 15 min of fraud)
        t1 = base_t + timedelta(minutes=self.rng.randint(2, 20))
        self._txn(vic_id, mule_id, amount * 0.95, t1, scenario_id)

        # Cash-out (1–3 hours later at target city)
        cashout_loc = self.rng.choice(CITIES[cashout_city]["clusters"])
        t_cashout = t1 + timedelta(hours=self.rng.uniform(1, 3))
        self._withdrawal(mule_id, cashout_loc, amount * 0.90, t_cashout, scenario_id)

        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": "A",
            "victim_city": victim_city, "cashout_city": cashout_city,
            "terminal_account_city": mule_city,
            "ground_truth_location": cashout_loc,
            "ground_truth_time": ts(t_cashout),
            "prediction_cutoff": ts(complaint_t),
        })

    # ── SCENARIO B: Multi-Victim Convergence ─────────────────────────────────
    def _scenario_B(self, base_t: datetime, victim_city: str, cashout_city: str,
                    scenario_id: str):
        """
        3–5 victims → one aggregator mule → secondary mule → ATM.
        Tests: fan-in detection, multi-victim linkage.
        """
        n_victims = self.rng.randint(3, 5)
        per_amount = round(self.rng.uniform(15000, 50000), 2)

        # Aggregator mule
        agg_id = uid("MUL")
        agg_city = victim_city
        self.accounts[agg_id] = self._make_account(agg_id, agg_city, "mule",
                                                    account_age_days=self.rng.randint(10, 60))

        last_complaint_t = base_t
        for i in range(n_victims):
            crime = self.rng.choice(CRIME_TYPES)
            fraud_t = base_t + timedelta(minutes=i * self.rng.randint(15, 45))
            complaint_t = fraud_t + timedelta(minutes=self.rng.randint(10, 60))
            if complaint_t > last_complaint_t:
                last_complaint_t = complaint_t
            vic_id = self._make_victim_account(victim_city, complaint_t, crime,
                                               per_amount, scenario_id)
            t1 = fraud_t + timedelta(minutes=self.rng.randint(2, 15))
            self._txn(vic_id, agg_id, per_amount * 0.97, t1, scenario_id)

        # Secondary mule in cashout city
        sec_id = uid("MUL")
        self.accounts[sec_id] = self._make_account(sec_id, cashout_city, "mule",
                                                    account_age_days=self.rng.randint(5, 45))

        total = per_amount * n_victims * 0.90
        t2 = last_complaint_t + timedelta(hours=self.rng.uniform(0.5, 2))
        self._txn(agg_id, sec_id, total * 0.93, t2, scenario_id)

        cashout_loc = self.rng.choice(CITIES[cashout_city]["clusters"])
        t_cashout = t2 + timedelta(hours=self.rng.uniform(0.5, 3))
        self._withdrawal(sec_id, cashout_loc, total * 0.88, t_cashout, scenario_id)

        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": "B",
            "victim_city": victim_city, "cashout_city": cashout_city,
            "terminal_account_city": cashout_city,
            "n_victims": n_victims,
            "ground_truth_location": cashout_loc,
            "ground_truth_time": ts(t_cashout),
            "prediction_cutoff": ts(last_complaint_t),
        })

    # ── SCENARIO C: Cross-City Cash-Out ──────────────────────────────────────
    def _scenario_C(self, base_t: datetime, scenario_id: str):
        """
        KEY SCENARIO: Fraud in Ahmedabad → cross-city movement → cash-out in Mumbai.
        Demonstrates that victim city ≠ withdrawal city.
        """
        victim_city = "Ahmedabad"
        cashout_city = "Mumbai"
        self._scenario_B_custom(base_t, victim_city, cashout_city, scenario_id,
                                 n_hops=3, scenario_type="C")

    def _scenario_B_custom(self, base_t: datetime, victim_city: str, cashout_city: str,
                            scenario_id: str, n_hops: int = 2, scenario_type: str = "C"):
        """
        Multi-hop chain: victim → hop1 → hop2 → ... → ATM in different city.
        """
        amount = round(self.rng.uniform(30000, 150000), 2)
        crime = self.rng.choice(CRIME_TYPES)

        complaint_t = base_t + timedelta(minutes=self.rng.randint(20, 90))
        vic_id = self._make_victim_account(victim_city, complaint_t, crime, amount, scenario_id)

        # Build hop chain
        current_id = vic_id
        current_amount = amount
        hop_cities = self._choose_hop_cities(victim_city, cashout_city, n_hops)
        last_t = base_t + timedelta(minutes=self.rng.randint(5, 25))

        hop_ids = []
        for i, hop_city in enumerate(hop_cities):
            hop_id = uid("MUL")
            age = self.rng.randint(7, 120) if i < n_hops - 1 else self.rng.randint(5, 30)
            self.accounts[hop_id] = self._make_account(hop_id, hop_city, "mule", age)
            hop_t = last_t + timedelta(minutes=self.rng.randint(10, 60))
            current_amount = current_amount * self.rng.uniform(0.88, 0.97)
            self._txn(current_id, hop_id, current_amount, hop_t, scenario_id)
            current_id = hop_id
            last_t = hop_t
            hop_ids.append(hop_id)

        cashout_loc = self.rng.choice(CITIES[cashout_city]["clusters"])
        t_cashout = last_t + timedelta(hours=self.rng.uniform(1, 5))
        self._withdrawal(current_id, cashout_loc, current_amount * 0.90, t_cashout, scenario_id)

        # Terminal account is the last hop account (in cashout_city)
        terminal_city = self.accounts[current_id]["city"]
        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": scenario_type,
            "victim_city": victim_city, "cashout_city": cashout_city,
            "terminal_account_city": terminal_city,
            "n_hops": n_hops, "hop_cities": str(hop_cities),
            "ground_truth_location": cashout_loc,
            "ground_truth_time": ts(t_cashout),
            "prediction_cutoff": ts(complaint_t),
        })

    def _choose_hop_cities(self, src: str, dst: str, n_hops: int) -> list[str]:
        """Choose intermediate cities between src and dst."""
        intermediates = [c for c in CITIES if c not in (src, dst)]
        if n_hops == 1:
            return [dst]
        mid = self.rng.sample(intermediates, min(n_hops - 1, len(intermediates)))
        return mid + [dst]

    # ── SCENARIO D: Cross-State Movement ─────────────────────────────────────
    def _scenario_D(self, base_t: datetime, scenario_id: str):
        """Gujarat fraud → Maharashtra cash-out."""
        gujarat_cities = ["Ahmedabad", "Surat", "Vadodara"]
        maha_cities = ["Mumbai", "Pune"]
        vic_city = self.rng.choice(gujarat_cities)
        cash_city = self.rng.choice(maha_cities)
        self._scenario_B_custom(base_t, vic_city, cash_city, scenario_id,
                                 n_hops=2, scenario_type="D")

    # ── SCENARIO E: Delayed Cash-Out ─────────────────────────────────────────
    def _scenario_E(self, base_t: datetime, victim_city: str, cashout_city: str,
                    scenario_id: str):
        """Money enters account, withdrawal occurs 6–18 hours later."""
        amount = round(self.rng.uniform(25000, 80000), 2)
        crime = self.rng.choice(CRIME_TYPES)

        complaint_t = base_t + timedelta(minutes=self.rng.randint(15, 45))
        vic_id = self._make_victim_account(victim_city, complaint_t, crime, amount, scenario_id)

        mule_id = uid("MUL")
        self.accounts[mule_id] = self._make_account(mule_id, cashout_city, "mule",
                                                     account_age_days=self.rng.randint(20, 180))

        t1 = base_t + timedelta(minutes=self.rng.randint(5, 30))
        self._txn(vic_id, mule_id, amount * 0.96, t1, scenario_id)

        # Long delay before cash-out
        delay_hours = self.rng.uniform(6, 18)
        cashout_loc = self.rng.choice(CITIES[cashout_city]["clusters"])
        t_cashout = t1 + timedelta(hours=delay_hours)
        self._withdrawal(mule_id, cashout_loc, amount * 0.90, t_cashout, scenario_id)

        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": "E",
            "victim_city": victim_city, "cashout_city": cashout_city,
            "terminal_account_city": cashout_city,
            "delay_hours": delay_hours,
            "ground_truth_location": cashout_loc,
            "ground_truth_time": ts(t_cashout),
            "prediction_cutoff": ts(complaint_t),
        })

    # ── SCENARIO F: No Cash-Out ───────────────────────────────────────────────
    def _scenario_F(self, base_t: datetime, victim_city: str, scenario_id: str):
        """
        Suspicious network — money moves but never results in ATM withdrawal.
        Critical: prevents model from flagging every suspicious account.
        """
        amount = round(self.rng.uniform(10000, 60000), 2)
        crime = self.rng.choice(CRIME_TYPES)

        complaint_t = base_t + timedelta(minutes=self.rng.randint(10, 60))
        vic_id = self._make_victim_account(victim_city, complaint_t, crime, amount, scenario_id)

        # 1–2 mules, money moves but stops
        mule_id = uid("MUL")
        self.accounts[mule_id] = self._make_account(mule_id, victim_city, "suspect",
                                                     account_age_days=self.rng.randint(30, 200))
        t1 = base_t + timedelta(minutes=self.rng.randint(5, 30))
        self._txn(vic_id, mule_id, amount * 0.95, t1, scenario_id)

        # Optional second hop — money freezes
        if self.rng.random() < 0.5:
            mule2_id = uid("MUL")
            freeze_city = self.rng.choice(list(CITIES.keys()))
            self.accounts[mule2_id] = self._make_account(mule2_id, freeze_city, "suspect",
                                                           account_age_days=self.rng.randint(10, 90))
            t2 = t1 + timedelta(hours=self.rng.uniform(1, 6))
            self._txn(mule_id, mule2_id, amount * 0.88, t2, scenario_id)

        # NO withdrawal record — this is the "no cash-out" scenario
        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": "F",
            "victim_city": victim_city, "cashout_city": None,
            "terminal_account_city": None,
            "ground_truth_location": None,
            "ground_truth_time": None,
            "prediction_cutoff": ts(complaint_t),
        })

    # ── SCENARIO H: Decoy Mule (City Disambiguation) ─────────────────────────
    def _scenario_H(self, base_t: datetime, victim_city: str, cashout_city: str,
                    scenario_id: str):
        """
        Decoy mule scenario: victim → mule1 (victim city, partial funds) AND
        victim → mule2 (cashout city, main funds → ATM).
        Tests whether model picks the mule with the higher outflow, not proximity.
        """
        amount = round(self.rng.uniform(30000, 100000), 2)
        crime = self.rng.choice(CRIME_TYPES)
        complaint_t = base_t + timedelta(minutes=self.rng.randint(15, 60))
        vic_id = self._make_victim_account(victim_city, complaint_t, crime, amount, scenario_id)

        # Decoy mule in victim city — gets a small cut
        decoy_id = uid("MUL")
        self.accounts[decoy_id] = self._make_account(decoy_id, victim_city, "mule",
                                                     account_age_days=self.rng.randint(10, 90))
        t1 = base_t + timedelta(minutes=self.rng.randint(5, 20))
        self._txn(vic_id, decoy_id, amount * 0.15, t1, scenario_id)  # small decoy transfer

        # Real mule in cashout city — gets the bulk
        real_id = uid("MUL")
        self.accounts[real_id] = self._make_account(real_id, cashout_city, "mule",
                                                    account_age_days=self.rng.randint(5, 30))
        t2 = base_t + timedelta(minutes=self.rng.randint(8, 25))
        self._txn(vic_id, real_id, amount * 0.80, t2, scenario_id)  # main transfer

        cashout_loc = self.rng.choice(CITIES[cashout_city]["clusters"])
        t_cashout = t2 + timedelta(hours=self.rng.uniform(0.5, 2))
        self._withdrawal(real_id, cashout_loc, amount * 0.75, t_cashout, scenario_id)

        self.scenarios_meta.append({
            "scenario_id": scenario_id, "type": "H",
            "victim_city": victim_city, "cashout_city": cashout_city,
            "terminal_account_city": cashout_city,
            "ground_truth_location": cashout_loc,
            "ground_truth_time": ts(t_cashout),
            "prediction_cutoff": ts(complaint_t),
        })

    # ── SCENARIO ORCHESTRATOR ─────────────────────────────────────────────────

    def generate_scenarios(self):
        """
        Generate a mix of all scenario types spread over 25 days.
        Scenarios are distributed chronologically to allow chronological train/test split.
        """
        cities = list(CITIES.keys())

        # Ensure good scenario mix
        # ~15% C (Ahmedabad→Mumbai cross-city multi-hop)
        # ~10% D (cross-state Gujarat→Maharashtra)
        # ~18% A (rapid single-hop)
        # ~18% B (multi-victim convergence)
        # ~10% E (delayed cash-out)
        # ~12% F (no cash-out — critical negatives)
        # ~10% H (decoy mule — city disambiguation)
        # ~7%  AHM_MUM (key demo)
        n = self.n_scenarios
        distribution = (
            ["C"] * max(1, int(n * 0.15)) +
            ["D"] * max(1, int(n * 0.10)) +
            ["A"] * max(1, int(n * 0.18)) +
            ["B"] * max(1, int(n * 0.18)) +
            ["E"] * max(1, int(n * 0.10)) +
            ["F"] * max(1, int(n * 0.12)) +
            ["H"] * max(1, int(n * 0.10)) +
            ["AHM_MUM"] * max(1, int(n * 0.07))
        )
        # Pad to n_scenarios
        while len(distribution) < n:
            distribution.append(self.rng.choice(["A", "B", "C", "D", "H"]))
        distribution = distribution[:n]
        self.rng.shuffle(distribution)

        days_span = 25  # spread over 25 days
        for i, stype in enumerate(distribution):
            # Chronological ordering — earlier scenarios get earlier timestamps
            day_offset = (i / n) * days_span
            hour_offset = self.rng.uniform(0, 20)
            base_t = self.base_time + timedelta(days=day_offset, hours=hour_offset)
            sid = uid("SCN")

            if stype == "A":
                vc = self.rng.choice(cities)
                cc = self.rng.choice([c for c in cities if c != vc])
                self._scenario_A(base_t, vc, cc, sid)
            elif stype == "B":
                vc = self.rng.choice(cities)
                cc = self.rng.choice([c for c in cities if c != vc])
                self._scenario_B(base_t, vc, cc, sid)
            elif stype == "C":
                self._scenario_C(base_t, sid)
            elif stype == "D":
                self._scenario_D(base_t, sid)
            elif stype == "E":
                vc = self.rng.choice(cities)
                cc = self.rng.choice([c for c in cities if c != vc])
                self._scenario_E(base_t, vc, cc, sid)
            elif stype == "F":
                vc = self.rng.choice(cities)
                self._scenario_F(base_t, vc, sid)
            elif stype == "H":
                vc = self.rng.choice(cities)
                cc = self.rng.choice([c for c in cities if c != vc])
                self._scenario_H(base_t, vc, cc, sid)
            elif stype == "AHM_MUM":
                # The critical demo scenario: Ahmedabad → Mumbai
                self._scenario_B_custom(base_t, "Ahmedabad", "Mumbai", sid,
                                         n_hops=self.rng.randint(2, 3), scenario_type="C")

        print(f"  [+] Generated {len(distribution)} scenarios "
              f"({sum(1 for s in self.scenarios_meta if s.get('ground_truth_location'))} with cash-out)")
        print(f"  [+] Total transactions: {len(self.transactions)}")
        print(f"  [+] Total complaints: {len(self.complaints)}")
        print(f"  [+] Total withdrawals (ground truth): {len(self.withdrawals)}")
        print(f"  [+] Total accounts: {len(self.accounts)}")

    # ── EXPORT ───────────────────────────────────────────────────────────────

    def save_csvs(self, out_dir: str):
        """Save all generated data as CSVs for inspection."""
        os.makedirs(out_dir, exist_ok=True)
        pd.DataFrame(list(self.locations.values())).to_csv(
            f"{out_dir}/locations.csv", index=False)
        pd.DataFrame(list(self.accounts.values())).to_csv(
            f"{out_dir}/accounts.csv", index=False)
        pd.DataFrame(self.complaints).to_csv(
            f"{out_dir}/complaints.csv", index=False)
        pd.DataFrame(self.transactions).to_csv(
            f"{out_dir}/transactions.csv", index=False)
        pd.DataFrame(self.withdrawals).to_csv(
            f"{out_dir}/withdrawals.csv", index=False)
        pd.DataFrame(self.scenarios_meta).to_csv(
            f"{out_dir}/scenarios_meta.csv", index=False)
        print(f"  [+] CSVs saved to {out_dir}/")

    def seed_database(self, db_session):
        """Write all generated data into the SQLite database."""
        from backend.database.models import (
            Location, Account, Complaint, Transaction, Withdrawal
        )
        # Clear existing synthetic data
        for Model in [Withdrawal, Complaint, Transaction, Account, Location]:
            db_session.query(Model).delete()
        db_session.commit()

        # Insert locations
        for loc in self.locations.values():
            db_session.add(Location(**loc))

        # Insert accounts
        for acc in self.accounts.values():
            db_session.add(Account(**acc))

        # Insert complaints
        for cmp in self.complaints:
            db_session.add(Complaint(**cmp))

        # Insert transactions (batch for speed)
        for txn in self.transactions:
            db_session.add(Transaction(**txn))

        # Insert withdrawals (GROUND TRUTH)
        for wdr in self.withdrawals:
            db_session.add(Withdrawal(**wdr))

        db_session.commit()
        print(f"  [+] Database seeded: "
              f"{len(self.locations)} locations, {len(self.accounts)} accounts, "
              f"{len(self.complaints)} complaints, {len(self.transactions)} txns, "
              f"{len(self.withdrawals)} withdrawals")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic fraud data")
    parser.add_argument("--accounts", type=int, default=2000,
                        help="Number of clean background accounts")
    parser.add_argument("--scenarios", type=int, default=200,
                        help="Number of fraud scenarios to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-db", action="store_true",
                        help="Skip database seeding, only save CSVs")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  SYNTHETIC DATA GENERATOR")
    print("  Cash-Out Forecasting Platform — SIH 2026")
    print("="*60)

    gen = SyntheticDataGenerator(
        seed=args.seed,
        n_clean_accounts=args.accounts,
        n_scenarios=args.scenarios
    )

    print("\n[1/5] Generating locations...")
    gen.generate_locations()

    print("\n[2/5] Generating clean background accounts...")
    gen.generate_clean_accounts()

    print("\n[3/5] Generating fraud scenarios (A–G)...")
    gen.generate_scenarios()

    print("\n[4/5] Generating legitimate background transactions...")
    gen.generate_legitimate_transactions(n=8000)

    print("\n[5/5] Saving data...")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    gen.save_csvs(out_dir)

    if not args.no_db:
        from backend.database.connection import init_db, SessionLocal
        print("\n  Initializing database...")
        init_db()
        db = SessionLocal()
        try:
            gen.seed_database(db)
        finally:
            db.close()

    print("\n" + "="*60)
    print("  DATA GENERATION COMPLETE")
    print(f"  Scenarios: {args.scenarios}")
    print(f"  Accounts:  {len(gen.accounts)}")
    print(f"  Transactions: {len(gen.transactions)}")
    print(f"  Complaints: {len(gen.complaints)}")
    print(f"  Withdrawals (ground truth): {len(gen.withdrawals)}")
    print("="*60 + "\n")

    return gen  # Return for use in other scripts


if __name__ == "__main__":
    main()

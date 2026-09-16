"""
Controlled Decoy Intelligence Engine — Phase 6 Advancement.

Simulates controlled synthetic financial decoys (honeypots) inside suspicious
transaction networks to gather proactive telemetry before cash-out occurs.

SAFETY NOTICE:
Purely synthetic simulation environment. No connection to real banking APIs,
real accounts, real money transfers, or real payment infrastructure.
"""

import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session

from backend.database.models import (
    Account, Transaction, Location, Decoy, DecoyInteraction,
    Complaint, Prediction, Alert, User
)
from backend.audit.audit_chain import create_audit_record


class DecoyIntelligenceEngine:
    """
    Modular engine for detecting suspicious dispersal patterns,
    deploying controlled synthetic decoys, simulating interactions,
    and feeding telemetry into the transaction graph and investigator workbench.
    """

    DEFAULT_MULE_THRESHOLD = 0.85
    DEFAULT_DISPERSAL_THRESHOLD = 0.75

    def __init__(self,
                 mule_threshold: float = DEFAULT_MULE_THRESHOLD,
                 dispersal_threshold: float = DEFAULT_DISPERSAL_THRESHOLD):
        self.mule_threshold = mule_threshold
        self.dispersal_threshold = dispersal_threshold

    @staticmethod
    def _utc_now_str() -> str:
        return datetime.now(timezone.utc).isoformat()

    def detect_dispersal_pattern(self,
                                 account_id: str,
                                 db: Session,
                                 cutoff_time: Optional[datetime] = None) -> Tuple[bool, float, Dict]:
        """
        Analyze an account to determine if it acts as a suspicious dispersal splitter.
        Returns: (is_triggered, dispersal_score, signal_details)
        """
        acc = db.query(Account).filter(Account.account_id == account_id).first()
        if not acc:
            return False, 0.0, {}

        mule_score = float(acc.mule_risk_score or 0.0)

        # Query outgoing and incoming transactions
        q_out = db.query(Transaction).filter(Transaction.source_account_id == account_id)
        q_in = db.query(Transaction).filter(Transaction.dest_account_id == account_id)

        if cutoff_time:
            c_str = cutoff_time.isoformat()
            q_out = q_out.filter(Transaction.timestamp <= c_str)
            q_in = q_in.filter(Transaction.timestamp <= c_str)

        outgoing = q_out.all()
        incoming = q_in.all()

        fan_out = len(outgoing)
        fan_in = len(incoming)

        total_in_amt = sum(t.amount or 0.0 for t in incoming)
        total_out_amt = sum(t.amount or 0.0 for t in outgoing)
        pass_through_ratio = (total_out_amt / total_in_amt) if total_in_amt > 0 else 0.0

        dest_accounts = set(t.dest_account_id for t in outgoing)
        unique_dests = len(dest_accounts)

        # Check cross-city movement
        dest_accs = db.query(Account).filter(Account.account_id.in_(dest_accounts)).all() if dest_accounts else []
        dest_cities = set(a.city for a in dest_accs if a.city)
        is_cross_city = len(dest_cities) > 0 and (acc.city not in dest_cities or len(dest_cities) > 1)

        # Compute Dispersal Score (composite explainable index)
        # 1. Fan-out weight (0.35)
        # 2. Pass-through ratio (0.25)
        # 3. Mule risk score (0.25)
        # 4. Cross-city vector (0.15)
        s_fanout = min(unique_dests / 3.0, 1.0)
        s_passthrough = min(pass_through_ratio, 1.0)
        s_mule = min(mule_score / 1.0, 1.0)
        s_crosscity = 1.0 if is_cross_city else 0.4

        dispersal_score = round(
            (0.35 * s_fanout) + (0.25 * s_passthrough) + (0.25 * s_mule) + (0.15 * s_crosscity),
            4
        )

        is_triggered = (
            (mule_score >= self.mule_threshold or dispersal_score >= self.dispersal_threshold) and
            (fan_out >= 2 or unique_dests >= 2 or mule_score >= 0.85)
        )

        signals = {
            "account_id": account_id,
            "mule_risk_score": mule_score,
            "dispersal_score": dispersal_score,
            "fan_in": fan_in,
            "fan_out": fan_out,
            "unique_destinations": unique_dests,
            "pass_through_ratio": round(pass_through_ratio, 3),
            "is_cross_city": is_cross_city,
            "origin_city": acc.city,
            "destination_cities": list(dest_cities),
            "triggered": is_triggered,
        }

        return is_triggered, dispersal_score, signals

    def arm_controlled_decoys(self,
                              case_id: str,
                              scenario_id: str,
                              trigger_account_id: str,
                              target_city: str,
                              activation_reason: str,
                              db: Session,
                              user_id: Optional[str] = None) -> List[Decoy]:
        """
        Create and arm synthetic decoy nodes for an active suspicious case.
        """
        # Define 3 standard synthetic decoy archetypes
        decoy_archetypes = [
            {
                "decoy_id": f"D-{case_id[-4:] if len(case_id) >= 4 else '001'}-1",
                "decoy_type": "CONTROLLED_ACCOUNT",
                "synthetic_account_id": f"SYN_ACC_DEC_{uuid.uuid4().hex[:6].upper()}",
                "city": target_city or "Mumbai",
            },
            {
                "decoy_id": f"D-{case_id[-4:] if len(case_id) >= 4 else '002'}-2",
                "decoy_type": "CONTROLLED_WALLET",
                "synthetic_account_id": f"SYN_WAL_DEC_{uuid.uuid4().hex[:6].upper()}",
                "city": target_city or "Mumbai",
            },
            {
                "decoy_id": f"D-{case_id[-4:] if len(case_id) >= 4 else '003'}-3",
                "decoy_type": "CONTROLLED_ATM_ENDPOINT",
                "synthetic_account_id": f"SYN_ATM_DEC_{uuid.uuid4().hex[:6].upper()}",
                "city": target_city or "Mumbai",
            },
        ]

        created_decoys = []
        now_str = self._utc_now_str()

        for arch in decoy_archetypes:
            existing = db.query(Decoy).filter(Decoy.decoy_id == arch["decoy_id"]).first()
            if not existing:
                decoy = Decoy(
                    decoy_id=arch["decoy_id"],
                    decoy_type=arch["decoy_type"],
                    synthetic_account_id=arch["synthetic_account_id"],
                    city=arch["city"],
                    status="ARMED",
                    activation_reason=activation_reason,
                    monitoring_status="ACTIVE",
                    risk_context=f"Triggered by Mule {trigger_account_id} (Dispersal Layer)",
                    interaction_count=0,
                    scenario_id=scenario_id,
                    case_id=case_id,
                    created_at=now_str,
                    is_synthetic=True,
                )
                db.add(decoy)
                created_decoys.append(decoy)
            else:
                existing.status = "ARMED"
                existing.activation_reason = activation_reason
                created_decoys.append(existing)

        db.commit()

        # Write to SHA-256 Tamper-evident Audit Ledger
        create_audit_record(db, "DECOY_ACTIVATED", {
            "case_id": case_id,
            "scenario_id": scenario_id,
            "trigger_account_id": trigger_account_id,
            "target_city": target_city,
            "decoys_armed": [d.decoy_id for d in created_decoys],
            "activation_reason": activation_reason,
        }, user_id=user_id)

        return created_decoys

    def simulate_interaction_event(self,
                                   decoy_id: str,
                                   source_account_id: str,
                                   synthetic_amount: float,
                                   originating_city: str,
                                   destination_city: str,
                                   interaction_type: str,
                                   hop_number: int,
                                   case_id: str,
                                   scenario_id: str,
                                   db: Session,
                                   user_id: Optional[str] = None,
                                   timestamp: Optional[datetime] = None) -> DecoyInteraction:
        """
        Record a simulated adversary interaction with a controlled decoy node.
        """
        decoy = db.query(Decoy).filter(Decoy.decoy_id == decoy_id).first()
        if not decoy:
            raise ValueError(f"Decoy {decoy_id} not found.")

        t_str = timestamp.isoformat() if timestamp else self._utc_now_str()
        inter_id = f"DEC_INT_{uuid.uuid4().hex[:8].upper()}"

        interaction = DecoyInteraction(
            interaction_id=inter_id,
            decoy_id=decoy_id,
            source_account_id=source_account_id,
            synthetic_amount=synthetic_amount,
            timestamp=t_str,
            originating_city=originating_city,
            destination_city=destination_city,
            hop_number=hop_number,
            interaction_type=interaction_type,
            activation_reason=decoy.activation_reason,
            scenario_id=scenario_id,
            case_id=case_id,
            is_synthetic=True,
        )

        db.add(interaction)

        # Update decoy state
        decoy.status = "INTERACTION_DETECTED"
        decoy.interaction_count = (decoy.interaction_count or 0) + 1
        db.commit()

        # Audit ledger record
        create_audit_record(db, "DECOY_INTERACTION_SIMULATED", {
            "interaction_id": inter_id,
            "decoy_id": decoy_id,
            "source_account_id": source_account_id,
            "synthetic_amount": synthetic_amount,
            "destination_city": destination_city,
            "interaction_type": interaction_type,
            "is_synthetic": True,
        }, user_id=user_id)

        return interaction

    def compute_decoy_score(self,
                            case_id: Optional[str],
                            scenario_id: Optional[str],
                            db: Session) -> Tuple[float, List[str]]:
        """
        Compute auxiliary decoy intelligence score and generate explainability bullets.
        """
        q = db.query(DecoyInteraction)
        if scenario_id:
            q = q.filter(DecoyInteraction.scenario_id == scenario_id)
        elif case_id:
            q = q.filter(DecoyInteraction.case_id == case_id)

        interactions = q.all()
        if not interactions:
            return 0.0, ["No controlled decoy interactions detected."]

        n_events = len(interactions)
        total_synthetic_amt = sum(i.synthetic_amount or 0.0 for i in interactions)
        target_cities = list(set(i.destination_city for i in interactions if i.destination_city))
        types = list(set(i.interaction_type for i in interactions if i.interaction_type))

        # Auxiliary score bounded between 0.5 and 0.98
        score = min(0.65 + (0.10 * n_events), 0.98)

        bullets = [
            f"Controlled Decoy Telemetry: {n_events} synthetic interaction(s) captured.",
            f"Suspicious dispersal routed toward: {', '.join(target_cities)} cluster.",
            f"Synthetic amount probed: ₹{total_synthetic_amt:,.2f} across multi-hop channels ({', '.join(types)}).",
            "High-priority honeypot confirmation: Active layer diversion pattern identified."
        ]

        return round(score, 3), bullets

    def get_case_decoy_summary(self, case_id: str, db: Session) -> Dict:
        """Return full structured summary for the investigator workbench."""
        decoys = db.query(Decoy).filter(
            (Decoy.case_id == case_id) | (Decoy.scenario_id == case_id)
        ).all()

        interactions = db.query(DecoyInteraction).filter(
            (DecoyInteraction.case_id == case_id) | (DecoyInteraction.scenario_id == case_id)
        ).order_by(DecoyInteraction.timestamp.desc()).all()

        score, bullets = self.compute_decoy_score(case_id, case_id, db)

        return {
            "case_id": case_id,
            "total_decoys": len(decoys),
            "active_decoys": [
                {
                    "decoy_id": d.decoy_id,
                    "type": d.decoy_type,
                    "city": d.city,
                    "status": d.status,
                    "interaction_count": d.interaction_count,
                    "synthetic_account_id": d.synthetic_account_id,
                    "activation_reason": d.activation_reason,
                    "risk_context": d.risk_context,
                }
                for d in decoys
            ],
            "total_interactions": len(interactions),
            "interactions": [
                {
                    "interaction_id": i.interaction_id,
                    "timestamp": i.timestamp,
                    "source": i.source_account_id,
                    "decoy": i.decoy_id,
                    "synthetic_amount": i.synthetic_amount,
                    "origin": i.originating_city,
                    "destination": i.destination_city,
                    "hop": i.hop_number,
                    "type": i.interaction_type,
                    "is_synthetic": True,
                }
                for i in interactions
            ],
            "decoy_interaction_score": score,
            "evidence_bullets": bullets,
            "is_simulation_only": True,
        }

"""
SQLAlchemy ORM models — defines all 11 database tables.

Design note: All monetary values stored as Float (₹).
Timestamps stored as ISO-8601 strings for SQLite compatibility.
Upgrade path: swap SQLite engine for PostgreSQL; all models remain unchanged.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database.connection import Base


class User(Base):
    """Investigator / admin user."""
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="investigator")   # "investigator" | "admin"
    is_active = Column(Boolean, default=True)
    created_at = Column(String)


class Location(Base):
    """Geographic location — city-level cluster or ATM-like node."""
    __tablename__ = "locations"

    location_id = Column(String, primary_key=True)   # e.g. "M17", "A04"
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    location_type = Column(String)   # "ATM", "branch", "cluster"
    cluster_code = Column(String)    # e.g. "M-WEST", "A-NORTH"


class Account(Base):
    """Bank account — may be victim, mule, or regular."""
    __tablename__ = "accounts"

    account_id = Column(String, primary_key=True)
    bank_id = Column(String)
    account_type = Column(String)    # "savings", "current", "prepaid"
    account_age_days = Column(Integer)
    city = Column(String)
    state = Column(String)
    location_id = Column(String, ForeignKey("locations.location_id"))
    risk_label = Column(String, default="unknown")   # "mule", "victim", "clean", "suspect"
    mule_risk_score = Column(Float, default=0.0)     # 0–1 score from ML
    is_frozen = Column(Boolean, default=False)       # 1930 / I4C Emergency Freeze
    frozen_at = Column(String, nullable=True)        # ISO timestamp of lien
    freeze_reason = Column(String, nullable=True)    # Legal basis e.g. "Section 102 CrPC / BNSS 107"
    frozen_amount = Column(Float, default=0.0)       # Amount secured
    created_at = Column(String)

    location = relationship("Location")
    sent_transactions = relationship("Transaction", foreign_keys="Transaction.source_account_id", back_populates="source_account")
    received_transactions = relationship("Transaction", foreign_keys="Transaction.dest_account_id", back_populates="dest_account")


class Complaint(Base):
    """Cybercrime complaint filed by a victim."""
    __tablename__ = "complaints"

    complaint_id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    crime_type = Column(String)      # "UPI fraud", "OTP fraud", "investment scam", etc.
    amount = Column(Float)           # ₹ lost
    victim_id = Column(String)       # account_id of victim
    victim_location_id = Column(String, ForeignKey("locations.location_id"))
    victim_bank = Column(String)
    status = Column(String, default="open")  # "open", "under investigation", "closed"
    scenario_tag = Column(String)    # which synthetic scenario this belongs to

    victim_location = relationship("Location")


class Transaction(Base):
    """Individual financial transaction between two accounts."""
    __tablename__ = "transactions"

    transaction_id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    source_account_id = Column(String, ForeignKey("accounts.account_id"))
    dest_account_id = Column(String, ForeignKey("accounts.account_id"))
    amount = Column(Float)
    transaction_type = Column(String)   # "UPI", "NEFT", "RTGS", "IMPS"
    channel = Column(String)            # "mobile", "net_banking", "atm"
    location_id = Column(String, ForeignKey("locations.location_id"), nullable=True)
    scenario_id = Column(String)        # links to synthetic scenario

    source_account = relationship("Account", foreign_keys=[source_account_id], back_populates="sent_transactions")
    dest_account = relationship("Account", foreign_keys=[dest_account_id], back_populates="received_transactions")


class Withdrawal(Base):
    """
    Cash withdrawal event at an ATM/location.
    Ground truth for model evaluation — never leaked to features before withdrawal_time.
    """
    __tablename__ = "withdrawals"

    withdrawal_id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)       # actual withdrawal time (future)
    account_id = Column(String, ForeignKey("accounts.account_id"))
    location_id = Column(String, ForeignKey("locations.location_id"))
    amount = Column(Float)
    atm_id = Column(String)
    scenario_id = Column(String)   # links back to scenario
    is_ground_truth = Column(Boolean, default=True)  # always True in synthetic data


class Prediction(Base):
    """ML-generated cash-out location forecast."""
    __tablename__ = "predictions"

    prediction_id = Column(String, primary_key=True)
    created_at = Column(String)
    prediction_time_cutoff = Column(String)   # T — only data before this was used
    scenario_id = Column(String)
    model_version = Column(String)
    top_k = Column(Integer, default=3)
    status = Column(String, default="active")   # "active", "confirmed", "rejected", "uncertain"


class PredictionEvidence(Base):
    """
    Per-location evidence for a prediction.
    One row per candidate location per prediction.
    """
    __tablename__ = "prediction_evidence"

    evidence_id = Column(String, primary_key=True)
    prediction_id = Column(String, ForeignKey("predictions.prediction_id"))
    rank = Column(Integer)                   # 1 = highest ranked
    location_id = Column(String, ForeignKey("locations.location_id"))
    score = Column(Float)                    # model score 0–1
    expected_window_start = Column(String)   # predicted time window
    expected_window_end = Column(String)
    evidence_json = Column(Text)             # JSON: list of evidence bullets + SHAP values
    transaction_path_json = Column(Text)     # JSON: account chain from victim to ATM

    prediction = relationship("Prediction")
    location = relationship("Location")


class Alert(Base):
    """Generated when prediction score crosses threshold."""
    __tablename__ = "alerts"

    alert_id = Column(String, primary_key=True)
    created_at = Column(String)
    prediction_id = Column(String, ForeignKey("predictions.prediction_id"))
    location_id = Column(String, ForeignKey("locations.location_id"))
    score = Column(Float)
    priority = Column(String)    # "HIGH", "MEDIUM", "LOW"
    expected_window_start = Column(String)
    expected_window_end = Column(String)
    status = Column(String, default="active")   # "active", "viewed", "actioned", "dismissed"
    summary = Column(Text)       # short human-readable summary

    location = relationship("Location")


class InvestigatorFeedback(Base):
    """Structured investigator review of a prediction."""
    __tablename__ = "investigator_feedback"

    feedback_id = Column(String, primary_key=True)
    prediction_id = Column(String, ForeignKey("predictions.prediction_id"))
    investigator_id = Column(String, ForeignKey("users.user_id"))
    action = Column(String)          # "confirm", "reject", "uncertain"
    actual_location_id = Column(String, nullable=True)
    actual_time = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    timestamp = Column(String)
    # Feedback is stored but NOT used for automatic retraining.
    # It requires human review → validated dataset → controlled retraining cycle.
    approved_for_training = Column(Boolean, default=False)


class AuditLog(Base):
    """
    Tamper-evident audit log — SHA-256 hash chain.
    Each record includes the hash of the previous record,
    forming a chain. Any alteration breaks the chain.
    Labelled as 'Prototype tamper-evident audit ledger'.
    Designed for future migration to Hyperledger Fabric.
    """
    __tablename__ = "audit_log"

    audit_id = Column(String, primary_key=True)
    sequence_number = Column(Integer, unique=True)
    timestamp = Column(String, nullable=False)
    event_type = Column(String)       # "prediction_generated", "alert_issued", "feedback_submitted", etc.
    user_id = Column(String, nullable=True)
    event_data = Column(Text)         # JSON payload of the event
    event_data_hash = Column(String)  # SHA-256 of event_data
    previous_hash = Column(String)    # hash of previous audit record (or "GENESIS")
    current_hash = Column(String)     # SHA-256 of (previous_hash + event_data_hash + timestamp)


class Decoy(Base):
    """
    Controlled Financial Decoy / Honeypot Node.
    Purely synthetic / simulated entity used for cybercrime intelligence research and early interception.
    """
    __tablename__ = "decoys"

    decoy_id = Column(String, primary_key=True)               # e.g. "D-001"
    decoy_type = Column(String, nullable=False)              # "CONTROLLED_ACCOUNT", "CONTROLLED_WALLET", "CONTROLLED_MERCHANT", "CONTROLLED_ATM_ENDPOINT"
    synthetic_account_id = Column(String, unique=True)       # e.g. "SYN_DEC_8801"
    city = Column(String, nullable=False)
    status = Column(String, default="INACTIVE")              # "INACTIVE", "ARMED", "INTERACTION_DETECTED"
    activation_reason = Column(String)                       # e.g. "High Mule Risk (0.94) & Dispersal Splitter"
    monitoring_status = Column(String, default="ACTIVE")     # "ACTIVE", "PAUSED", "COMPLETED"
    risk_context = Column(String)                            # e.g. "Ahmedabad -> Mumbai Layering"
    interaction_count = Column(Integer, default=0)
    scenario_id = Column(String, nullable=True)
    case_id = Column(String, nullable=True)
    created_at = Column(String)
    is_synthetic = Column(Boolean, default=True)

    interactions = relationship("DecoyInteraction", back_populates="decoy", cascade="all, delete-orphan")


class DecoyInteraction(Base):
    """
    Simulated telemetry event recording an interaction with a controlled decoy node.
    Completely isolated from real financial systems.
    """
    __tablename__ = "decoy_interactions"

    interaction_id = Column(String, primary_key=True)
    decoy_id = Column(String, ForeignKey("decoys.decoy_id"), nullable=False)
    source_account_id = Column(String, nullable=False)       # suspicious mule account
    synthetic_amount = Column(Float, default=0.0)
    timestamp = Column(String, nullable=False)
    originating_city = Column(String)
    destination_city = Column(String)
    hop_number = Column(Integer, default=1)
    interaction_type = Column(String)                        # "IMPS_PROBE", "DISPERSAL_ROUTING", "WALLET_ATTEMPT", "ATM_QUERY"
    activation_reason = Column(String)
    scenario_id = Column(String, nullable=True)
    case_id = Column(String, nullable=True)
    is_synthetic = Column(Boolean, default=True)

    decoy = relationship("Decoy", back_populates="interactions")


class PoliceStation(Base):
    """Local Law Enforcement Jurisdiction Police Station."""
    __tablename__ = "police_stations"

    station_id = Column(String, primary_key=True)       # e.g. "PS-MUM-BKC-01"
    name = Column(String, nullable=False)              # e.g. "BKC Cyber Police Station"
    city = Column(String, nullable=False)              # "Mumbai"
    state = Column(String, nullable=False)             # "Maharashtra"
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    nodal_officer = Column(String)                     # "Inspector R. K. Sharma"
    contact_phone = Column(String)                     # "+91-22-2650-4400"
    control_room_email = Column(String)
    jurisdiction_radius_km = Column(Float, default=7.5)


class InterceptionDispatch(Base):
    """Tactical interception advisory dispatched to local law enforcement."""
    __tablename__ = "interception_dispatches"

    dispatch_id = Column(String, primary_key=True)      # e.g. "DSP-2026-001"
    prediction_id = Column(String, ForeignKey("predictions.prediction_id"))
    location_id = Column(String, ForeignKey("locations.location_id"))
    station_id = Column(String, ForeignKey("police_stations.station_id"))
    dispatched_at = Column(String, nullable=False)
    status = Column(String, default="DISPATCHED")       # "DISPATCHED", "EN_ROUTE", "PATROL_ACTIVE", "INTERCEPTED", "STAND_DOWN"
    priority = Column(String, default="HIGH")           # "CRITICAL", "HIGH", "MEDIUM"
    expected_window = Column(String)
    officer_notes = Column(Text, nullable=True)
    verification_token = Column(String)                 # SHA-256 token for patrol team verification
    dispatched_by = Column(String, default="I4C_AUTOMATION")


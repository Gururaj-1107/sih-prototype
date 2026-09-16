"""
Unit tests for SHA-256 tamper-evident audit ledger.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base, AuditLog
from backend.audit.audit_chain import create_audit_record, verify_chain_integrity


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_audit_chain_sequential_linking(db_session):
    """Test that audit blocks link with valid SHA-256 previous_hash pointers."""
    rec1 = create_audit_record(db_session, "CASE_OPENED", {"case_id": "C-1001"}, "officer_1")
    rec2 = create_audit_record(db_session, "PREDICTION_RUN", {"score": 0.85}, "system")
    rec3 = create_audit_record(db_session, "ALERT_DISPATCHED", {"priority": "HIGH"}, "officer_2")

    assert rec1.sequence_number == 1
    assert rec2.sequence_number == 2
    assert rec3.sequence_number == 3

    assert rec2.previous_hash == rec1.current_hash
    assert rec3.previous_hash == rec2.current_hash

    res = verify_chain_integrity(db_session)
    assert res["is_valid"] is True
    assert res["n_records"] == 3


def test_audit_chain_tamper_detection(db_session):
    """Test that altering any record's payload invalidates the cryptographic chain."""
    create_audit_record(db_session, "EVENT_1", {"data": 100}, "officer_1")
    create_audit_record(db_session, "EVENT_2", {"data": 200}, "officer_2")
    create_audit_record(db_session, "EVENT_3", {"data": 300}, "officer_3")

    # Verify initial valid state
    assert verify_chain_integrity(db_session)["is_valid"] is True

    # Tamper with record 2's hash
    rec2 = db_session.query(AuditLog).filter(AuditLog.sequence_number == 2).first()
    rec2.current_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    db_session.commit()

    # Integrity verification must detect corruption
    res = verify_chain_integrity(db_session)
    assert res["is_valid"] is False
    assert res["first_broken_at"] in [2, 3]

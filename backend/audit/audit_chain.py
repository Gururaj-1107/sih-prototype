"""
Audit Chain Module — Hash-chain tamper-evident ledger.

Each audit record includes:
  - SHA-256 hash of its own data
  - SHA-256 hash of the previous record
  - A "current_hash" = SHA-256(previous_hash + event_data_hash + timestamp)

This creates a hash chain: altering any record breaks all subsequent hashes.

Labelled as: "Prototype tamper-evident audit ledger"
Designed for future migration to Hyperledger Fabric permissioned blockchain.

DO NOT call this "blockchain" — it is a hash chain, an honest prototype.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone


def _sha256(data: str) -> str:
    """Compute SHA-256 hash of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def create_audit_record(db_session, event_type: str, event_data: dict,
                         user_id: str = None) -> "AuditLog":
    """
    Create and persist a new audit log entry.
    Automatically links to the previous record to form the chain.
    """
    from backend.database.models import AuditLog

    # Get the last audit record (highest sequence number)
    last_record = (
        db_session.query(AuditLog)
        .order_by(AuditLog.sequence_number.desc())
        .first()
    )

    if last_record:
        prev_hash = last_record.current_hash
        seq_num = last_record.sequence_number + 1
    else:
        prev_hash = "GENESIS"   # First record in chain
        seq_num = 1

    # Compute hashes
    event_data_str = json.dumps(event_data, sort_keys=True, default=str)
    event_data_hash = _sha256(event_data_str)

    timestamp = datetime.now(timezone.utc).isoformat()

    # current_hash ties together: previous state + this event + timestamp
    current_hash = _sha256(prev_hash + event_data_hash + timestamp)

    record = AuditLog(
        audit_id=str(uuid.uuid4()),
        sequence_number=seq_num,
        timestamp=timestamp,
        event_type=event_type,
        user_id=user_id,
        event_data=event_data_str,
        event_data_hash=event_data_hash,
        previous_hash=prev_hash,
        current_hash=current_hash,
    )

    db_session.add(record)
    db_session.commit()
    return record


def verify_chain_integrity(db_session) -> dict:
    """
    Walk the entire audit chain and verify every hash.
    Returns a dict with: is_valid, n_records, first_broken_at (if any).

    A real production system would store the chain on an immutable ledger.
    For the prototype, we verify in-process against the SQLite database.
    """
    from backend.database.models import AuditLog

    records = (
        db_session.query(AuditLog)
        .order_by(AuditLog.sequence_number.asc())
        .all()
    )

    if not records:
        return {
            "is_valid": True,
            "n_records": 0,
            "message": "Audit chain is empty.",
            "first_broken_at": None,
        }

    prev_hash = "GENESIS"
    for record in records:
        # Recompute the expected current_hash
        expected_current = _sha256(
            record.previous_hash + record.event_data_hash + record.timestamp
        )

        # Check 1: previous_hash matches the actual previous record
        if record.previous_hash != prev_hash:
            return {
                "is_valid": False,
                "n_records": len(records),
                "message": f"Chain broken at sequence {record.sequence_number}: previous_hash mismatch.",
                "first_broken_at": record.sequence_number,
            }

        # Check 2: current_hash is correct
        if record.current_hash != expected_current:
            return {
                "is_valid": False,
                "n_records": len(records),
                "message": f"Chain broken at sequence {record.sequence_number}: current_hash mismatch (record may have been altered).",
                "first_broken_at": record.sequence_number,
            }

        prev_hash = record.current_hash

    return {
        "is_valid": True,
        "n_records": len(records),
        "message": f"Audit chain verified: {len(records)} records intact.",
        "first_broken_at": None,
    }

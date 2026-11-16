"""
Data Integrity Verification Module
===================================
Provides cryptographic data integrity checks for streaming records separate
from Homomorphic Encryption (HE).

HE provides confidentiality and computation over encrypted data, but does NOT
guarantee data authenticity or non-malleability in transit. This module implements
cryptographic message hashing (SHA-256) and optional HMAC to verify that records
were not tampered with, corrupted, or altered during Kafka transport.
"""

import hashlib
import hmac
import json
from typing import Any, Dict, Tuple


def canonical_serialize(data: Dict[str, Any]) -> bytes:
    """
    Serializes a dictionary into a deterministic, canonical UTF-8 JSON byte string.
    Keys are strictly sorted with uniform separators to guarantee reproducible hashes.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_record_hash(data: Dict[str, Any]) -> str:
    """
    Calculates the SHA-256 cryptographic digest of a streaming record.
    """
    serialized = canonical_serialize(data)
    return hashlib.sha256(serialized).hexdigest()


def compute_record_hmac(data: Dict[str, Any], secret_key: bytes) -> str:
    """
    Calculates a Keyed-Hash Message Authentication Code (HMAC-SHA256).
    Distinct from the HE Secret Key: This key is shared exclusively between
    the streaming Producer and Consumer for authenticity verification.
    """
    serialized = canonical_serialize(data)
    return hmac.new(secret_key, serialized, hashlib.sha256).hexdigest()


def verify_integrity(
    record_payload: Dict[str, Any],
    received_hash: str,
    secret_key: bytes = None
) -> Tuple[bool, str]:
    """
    Verifies that the transmitted record matches its cryptographic hash.

    Returns:
        (is_valid, status_string): (True, 'INTEGRITY OK') or (False, 'INTEGRITY FAILURE')
    """
    if secret_key:
        expected_hash = compute_record_hmac(record_payload, secret_key)
    else:
        expected_hash = compute_record_hash(record_payload)

    # Use constant-time comparison to prevent timing side-channel attacks
    if hmac.compare_digest(expected_hash, received_hash):
        return True, "INTEGRITY OK"
    else:
        return False, "INTEGRITY FAILURE"

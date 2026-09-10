"""
Homomorphic Encryption Module  –  TenSEAL / CKKS
=================================================
Wraps TenSEAL context creation, encryption, and decryption.

CKKS parameters chosen for the demo:
  poly_modulus_degree : 8192   → 128-bit security level
  coeff_mod_bit_sizes : [60, 40, 40, 60]  → 3 multiplication levels
  global_scale        : 2^40   → ~12 decimal digits of precision

The context is intentionally kept in a single module-level dict so that
main.py can interrogate the active parameters for the /context endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List

import tenseal as ts

# ------------------------------------------------------------------
# Context registry — exposed so callers can read active parameters.
# ------------------------------------------------------------------
_active_params: Dict[str, Any] = {}


def get_context_params() -> Dict[str, Any]:
    """Return a copy of the parameters used to build the current context."""
    return dict(_active_params)


# ------------------------------------------------------------------
# Context factory
# ------------------------------------------------------------------

def create_context(scheme: str = "CKKS") -> ts.Context:
    """
    Create and return a TenSEAL HE context.

    Parameters
    ----------
    scheme : str
        ``"CKKS"`` (floating-point, approximate) or ``"BFV"`` (integer, exact).

    Side-effects
    ------------
    Updates the module-level ``_active_params`` dict so that ``/context``
    can report the live parameters without re-building the context.
    """
    global _active_params

    if scheme == "CKKS":
        poly_mod = 8192
        coeff_bits = [60, 40, 40, 60]
        scale_bits = 40
        context = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=poly_mod,
            coeff_mod_bit_sizes=coeff_bits,
        )
        context.generate_galois_keys()
        context.global_scale = 2 ** scale_bits

        _active_params = {
            "scheme": "CKKS",
            "poly_modulus_degree": poly_mod,
            "coeff_mod_bit_sizes": coeff_bits,
            "global_scale_bits": scale_bits,
            "multiplication_depth": len(coeff_bits) - 2,  # usable levels
            "security_level_bits": 128,
            "galois_keys": True,
        }
    else:
        poly_mod = 4096
        plain_mod = 1032193
        context = ts.context(
            ts.SCHEME_TYPE.BFV,
            poly_modulus_degree=poly_mod,
            plain_modulus=plain_mod,
        )
        _active_params = {
            "scheme": "BFV",
            "poly_modulus_degree": poly_mod,
            "plain_modulus": plain_mod,
        }

    return context


# ------------------------------------------------------------------
# Encrypt / decrypt
# ------------------------------------------------------------------

def encrypt_data(context: ts.Context, data: List[float]) -> ts.CKKSVector:
    """
    Encrypt a list of floats as a CKKS vector.

    The returned CKKSVector supports ``+``, ``*``, and ``.decrypt()``.
    """
    return ts.ckks_vector(context, data)


def decrypt_data(enc: ts.CKKSVector) -> List[float]:
    """
    Decrypt a CKKS vector back to plaintext floats.

    Returns a Python list of float values.
    """
    return enc.decrypt()


def serialize_ciphertext(enc: ts.CKKSVector) -> bytes:
    """Serialize a CKKS vector to raw bytes for Kafka transport."""
    return enc.serialize()


def deserialize_ciphertext(context: ts.Context, raw: bytes) -> ts.CKKSVector:
    """Reconstruct a CKKS vector from raw bytes."""
    return ts.ckks_vector_from(context, raw)

"""
Computation Module  –  Homomorphic Operations
==============================================
All HE operations go through this module so that:
  1. Noise tracking is always applied consistently.
  2. The per-operation noise delta is returned to the caller for
     observability (logged, pushed via WebSocket, etc.).
  3. Errors from TenSEAL are surfaced as typed ComputeError exceptions
     rather than raw library exceptions.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from noise_manager import NoiseManager


class ComputeError(RuntimeError):
    """Raised when a homomorphic operation fails."""


# ------------------------------------------------------------------
# Primitive operations
# ------------------------------------------------------------------

def add(
    enc1: Any,
    enc2: Any,
    noise_manager: NoiseManager,
) -> Tuple[Any, int]:
    """
    Ciphertext–ciphertext addition.

    Additions grow noise only modestly in CKKS (no relinearisation needed).

    Returns
    -------
    (result_ciphertext, noise_delta)
    """
    try:
        result = enc1 + enc2
    except Exception as exc:
        raise ComputeError(f"HE add failed: {exc}") from exc

    delta = noise_manager.increase_noise("add")
    return result, delta


def multiply(
    enc1: Any,
    enc2: Any,
    noise_manager: NoiseManager,
) -> Tuple[Any, int]:
    """
    Ciphertext–ciphertext multiplication.

    Multiplications consume a rescaling level and grow noise significantly;
    they should be followed by bootstrapping if the budget is near the
    threshold.

    Returns
    -------
    (result_ciphertext, noise_delta)
    """
    try:
        result = enc1 * enc2
    except Exception as exc:
        raise ComputeError(f"HE multiply failed: {exc}") from exc

    delta = noise_manager.increase_noise("multiply")
    return result, delta


def scale_plaintext(
    enc: Any,
    scalar: float,
    noise_manager: NoiseManager,
) -> Tuple[Any, int]:
    """
    Multiply a ciphertext by a plaintext scalar (cheaper than ct*ct).

    Returns
    -------
    (result_ciphertext, noise_delta)
    """
    try:
        result = enc * scalar
    except Exception as exc:
        raise ComputeError(f"HE scalar multiply failed: {exc}") from exc

    # Plaintext multiply costs roughly the same as an add.
    delta = noise_manager.increase_noise("add")
    return result, delta


# ------------------------------------------------------------------
# Aggregate helper
# ------------------------------------------------------------------

def aggregate(
    enc_list: List[Any],
    noise_manager: NoiseManager,
) -> Tuple[Any, int]:
    """
    Sum a list of ciphertexts via repeated addition.

    Returns
    -------
    (accumulated_ciphertext, total_noise_delta)
    """
    if not enc_list:
        raise ComputeError("aggregate requires at least one ciphertext")

    total_delta = 0
    result = enc_list[0]
    for enc in enc_list[1:]:
        try:
            result = result + enc
        except Exception as exc:
            raise ComputeError(f"HE aggregate step failed: {exc}") from exc
        total_delta += noise_manager.increase_noise("aggregate_step")

    return result, total_delta

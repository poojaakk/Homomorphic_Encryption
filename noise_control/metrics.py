"""
Noise & Precision Metrics Module
=================================
Calculates scientifically defensible accuracy and precision loss metrics
from actual CKKS homomorphic evaluations without artificial noise injection.
"""

import math
from typing import Dict, List, Union
import numpy as np


def compute_absolute_error(
    reference: Union[List[float], np.ndarray],
    decrypted: Union[List[float], np.ndarray],
) -> float:
    """
    Computes Mean Absolute Error (MAE) between plaintext reference and decrypted ciphertext:
        MAE = (1/N) * sum(|ref_i - dec_i|)
    """
    ref_arr = np.asarray(reference, dtype=np.float64)
    dec_arr = np.asarray(decrypted, dtype=np.float64)
    return float(np.mean(np.abs(ref_arr - dec_arr)))


def compute_max_absolute_error(
    reference: Union[List[float], np.ndarray],
    decrypted: Union[List[float], np.ndarray],
) -> float:
    """Computes the maximum single-element absolute discrepancy."""
    ref_arr = np.asarray(reference, dtype=np.float64)
    dec_arr = np.asarray(decrypted, dtype=np.float64)
    return float(np.max(np.abs(ref_arr - dec_arr)))


def compute_relative_error(
    reference: Union[List[float], np.ndarray],
    decrypted: Union[List[float], np.ndarray],
    epsilon: float = 1e-9,
) -> float:
    """
    Computes Mean Relative Error:
        MRE = (1/N) * sum(|ref_i - dec_i| / (|ref_i| + epsilon))
    """
    ref_arr = np.asarray(reference, dtype=np.float64)
    dec_arr = np.asarray(decrypted, dtype=np.float64)
    rel = np.abs(ref_arr - dec_arr) / (np.abs(ref_arr) + epsilon)
    return float(np.mean(rel))


def compute_rmse(
    reference: Union[List[float], np.ndarray],
    decrypted: Union[List[float], np.ndarray],
) -> float:
    """Computes Root Mean Square Error (RMSE)."""
    ref_arr = np.asarray(reference, dtype=np.float64)
    dec_arr = np.asarray(decrypted, dtype=np.float64)
    return float(np.sqrt(np.mean((ref_arr - dec_arr) ** 2)))


def estimate_precision_bits(abs_error: float, epsilon: float = 1e-16) -> float:
    """
    Estimates the number of preserved fractional precision bits:
        bits = -log2(max(abs_error, epsilon))
    For example, an absolute error of 1e-6 preserves ~20 bits of precision.
    """
    effective_error = max(abs_error, epsilon)
    return float(-math.log2(effective_error))


def generate_quality_snapshot(
    reference: List[float],
    decrypted: List[float],
    enc_latency: float,
    comp_latency: float,
    dec_latency: float,
    comp_depth: int,
    is_success: bool = True,
) -> Dict[str, Union[float, int, bool]]:
    """
    Assembles a comprehensive experimental quality snapshot for a single stream record.
    """
    mae = compute_absolute_error(reference, decrypted)
    max_err = compute_max_absolute_error(reference, decrypted)
    rel_err = compute_relative_error(reference, decrypted)
    rmse = compute_rmse(reference, decrypted)
    bits = estimate_precision_bits(mae)
    total_latency = enc_latency + comp_latency + dec_latency

    return {
        "mae": mae,
        "max_error": max_err,
        "relative_error": rel_err,
        "rmse": rmse,
        "precision_bits": bits,
        "computation_depth": comp_depth,
        "decryption_success": is_success,
        "encryption_time_ms": enc_latency * 1000.0,
        "computation_time_ms": comp_latency * 1000.0,
        "decryption_time_ms": dec_latency * 1000.0,
        "total_latency_ms": total_latency * 1000.0,
    }

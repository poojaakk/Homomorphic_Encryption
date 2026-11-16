"""
Experiment C: Adaptive Homomorphic Encryption Pipeline
======================================================
Executes CKKS homomorphic evaluations equipped with the Adaptive Noise and
Depth Controller. Automatically detects precision degradation and executes
mitigations to guarantee accuracy and reliability.
"""

import time
from typing import Dict, List
import numpy as np

from encryption.he_engine import HEEngine
from noise_control.adaptive_controller import AdaptiveNoiseController
from noise_control.metrics import compute_absolute_error, compute_relative_error, compute_rmse


def run_adaptive_he_experiment(
    data_records: List[List[float]],
    engine: HEEngine,
    error_threshold: float = 1e-4,
    c2: float = 0.05,
    c1: float = 1.10,
    c0: float = 2.50,
) -> Dict:
    print(f"\n--- Running Experiment C: Adaptive HE (Threshold: {error_threshold:.2e}) ---")
    controller = AdaptiveNoiseController(error_threshold=error_threshold, max_multiplicative_depth=2)

    enc_latencies = []
    comp_latencies = []
    dec_latencies = []
    abs_errors = []
    rel_errors = []
    interventions = []
    successes = 0
    failures = 0

    for idx, row in enumerate(data_records):
        record_id = idx + 1
        # 1. Plaintext reference
        plain_out = engine.evaluate_polynomial_plaintext_reference(row, c2=c2, c1=c1, c0=c0)

        # 2. Encryption
        try:
            enc_vec, enc_t = engine.encrypt_vector(row)
            enc_latencies.append(enc_t * 1000.0)
        except Exception:
            failures += 1
            continue

        # 3. Encrypted Homomorphic Evaluation
        try:
            comp_cipher, comp_t, depth = engine.evaluate_polynomial(enc_vec, c2=c2, c1=c1, c0=c0)
            comp_latencies.append(comp_t * 1000.0)
        except Exception:
            failures += 1
            continue

        # 4. Decryption
        try:
            dec_out, dec_t = engine.decrypt_vector(comp_cipher)
            dec_latencies.append(dec_t * 1000.0)
            successes += 1

            abs_err = compute_absolute_error(plain_out, dec_out)
            rel_err = compute_relative_error(plain_out, dec_out)
            abs_errors.append(abs_err)
            rel_errors.append(rel_err)

            # 5. Adaptive Controller Step
            controller.record_observation(abs_err, depth_consumed=depth)
            should_act, reason = controller.should_intervene()
            if should_act:
                event = controller.trigger_mitigation(reason=reason, record_id=record_id)
                interventions.append(event)
        except Exception:
            failures += 1
            continue

    mean_abs_err = float(np.mean(abs_errors)) if abs_errors else 0.0
    max_abs_err = float(np.max(abs_errors)) if abs_errors else 0.0
    mean_rel_err = float(np.mean(rel_errors)) if rel_errors else 0.0
    mean_enc = float(np.mean(enc_latencies)) if enc_latencies else 0.0
    mean_comp = float(np.mean(comp_latencies)) if comp_latencies else 0.0
    mean_dec = float(np.mean(dec_latencies)) if dec_latencies else 0.0
    total_lat = mean_enc + mean_comp + mean_dec

    print(f"[+] Adaptive HE completed {successes}/{len(data_records)} decryptions.")
    print(f"    Mean Absolute Error: {mean_abs_err:.3e} | Total Interventions: {len(interventions)}")
    print(f"    Total Processing Latency: {total_lat:.2f} ms")

    return {
        "experiment": "C_Adaptive_HE",
        "num_records": len(data_records),
        "encryption_latency_ms": mean_enc,
        "computation_latency_ms": mean_comp,
        "decryption_latency_ms": mean_dec,
        "total_latency_ms": total_lat,
        "mean_absolute_error": mean_abs_err,
        "max_absolute_error": max_abs_err,
        "mean_relative_error": mean_rel_err,
        "rmse": float(np.sqrt(np.mean(np.array(abs_errors)**2))) if abs_errors else 0.0,
        "successful_decryptions": successes,
        "failed_results": failures,
        "adaptive_interventions": len(interventions),
        "intervention_details": interventions,
        "absolute_errors": abs_errors,
        "relative_errors": rel_errors,
    }

"""
Experiment A: Plaintext Baseline
================================
Runs the benchmark computation on raw unencrypted floating-point data.
Establishes the performance and precision upper bound (zero encryption overhead).
"""

import time
from typing import Dict, List
import numpy as np
import pandas as pd


def run_plaintext_experiment(
    data_records: List[List[float]],
    c2: float = 0.05,
    c1: float = 1.10,
    c0: float = 2.50,
) -> Dict:
    print("\n--- Running Experiment A: Plaintext Baseline ---")
    latencies = []
    results = []

    t_start = time.perf_counter()
    for row in data_records:
        arr = np.array(row, dtype=np.float64)
        t0 = time.perf_counter()
        out = c2 * (arr ** 2) + c1 * arr + c0
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)  # ms
        results.append(out.tolist())

    total_wall_time = time.perf_counter() - t_start
    avg_latency = float(np.mean(latencies))

    print(f"[+] Plaintext completed {len(data_records)} records in {total_wall_time:.4f}s.")
    print(f"    Mean computation latency: {avg_latency:.4f} ms/record")

    return {
        "experiment": "A_Plaintext_Baseline",
        "num_records": len(data_records),
        "encryption_latency_ms": 0.0,
        "computation_latency_ms": avg_latency,
        "decryption_latency_ms": 0.0,
        "total_latency_ms": avg_latency,
        "mean_absolute_error": 0.0,
        "max_absolute_error": 0.0,
        "mean_relative_error": 0.0,
        "rmse": 0.0,
        "successful_decryptions": len(data_records),
        "failed_results": 0,
        "adaptive_interventions": 0,
        "results": results,
    }

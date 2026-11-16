"""
Comparative Experiment Benchmark Runner
========================================
Runs Experiment A (Plaintext), Experiment B (Unmanaged HE), and Experiment C (Adaptive HE)
over identical streaming records, outputting side-by-side comparative evidence.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from encryption.he_engine import HEEngine
from encryption.key_manager import KeyManager
from experiments.plaintext_baseline import run_plaintext_experiment
from experiments.he_baseline import run_he_baseline_experiment
from experiments.adaptive_he import run_adaptive_he_experiment

DATASET_PATH = "data/sensor_stream.csv"
RESULTS_DIR = "results"


def run_all_experiments(num_records: int = 100):
    print("=" * 80)
    print("HOMOMORPHIC ENCRYPTION EXPERIMENTAL COMPARISON BENCHMARK")
    print("=" * 80)
    print(f"[*] Dataset: {DATASET_PATH} (Records to evaluate: {num_records})")

    if not os.path.exists(DATASET_PATH):
        print(f"[-] ERROR: Dataset '{DATASET_PATH}' not found.")
        sys.exit(1)

    df = pd.read_csv(DATASET_PATH)
    features = ["temperature", "dew_point", "pressure", "wind_speed", "pm25"]
    sample_rows = df[features].iloc[:num_records].values.tolist()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Initialize TenSEAL CKKS engine
    print("[*] Initializing Cryptographic Context (CKKS 8192)...")
    km = KeyManager(poly_modulus_degree=8192, global_scale=2**40)
    engine = HEEngine(key_manager=km)

    # 1. Experiment A
    res_a = run_plaintext_experiment(sample_rows)

    # 2. Experiment B
    res_b = run_he_baseline_experiment(sample_rows, engine=engine)

    # 3. Experiment C
    res_c = run_adaptive_he_experiment(sample_rows, engine=engine, error_threshold=1e-4)

    # Assemble Comparative Results Table
    comparison = [
        {
            "Metric": "Evaluated Records",
            "Experiment A (Plaintext)": str(res_a["num_records"]),
            "Experiment B (Unmanaged HE)": str(res_b["num_records"]),
            "Experiment C (Adaptive HE)": str(res_c["num_records"]),
        },
        {
            "Metric": "Encryption Latency (ms)",
            "Experiment A (Plaintext)": "0.00",
            "Experiment B (Unmanaged HE)": f"{res_b['encryption_latency_ms']:.2f}",
            "Experiment C (Adaptive HE)": f"{res_c['encryption_latency_ms']:.2f}",
        },
        {
            "Metric": "HE Computation Latency (ms)",
            "Experiment A (Plaintext)": f"{res_a['computation_latency_ms']:.4f}",
            "Experiment B (Unmanaged HE)": f"{res_b['computation_latency_ms']:.2f}",
            "Experiment C (Adaptive HE)": f"{res_c['computation_latency_ms']:.2f}",
        },
        {
            "Metric": "Decryption Latency (ms)",
            "Experiment A (Plaintext)": "0.00",
            "Experiment B (Unmanaged HE)": f"{res_b['decryption_latency_ms']:.2f}",
            "Experiment C (Adaptive HE)": f"{res_c['decryption_latency_ms']:.2f}",
        },
        {
            "Metric": "Total Processing Latency (ms)",
            "Experiment A (Plaintext)": f"{res_a['total_latency_ms']:.4f}",
            "Experiment B (Unmanaged HE)": f"{res_b['total_latency_ms']:.2f}",
            "Experiment C (Adaptive HE)": f"{res_c['total_latency_ms']:.2f}",
        },
        {
            "Metric": "Mean Absolute Error (MAE)",
            "Experiment A (Plaintext)": "0.00 (Exact)",
            "Experiment B (Unmanaged HE)": f"{res_b['mean_absolute_error']:.3e}",
            "Experiment C (Adaptive HE)": f"{res_c['mean_absolute_error']:.3e}",
        },
        {
            "Metric": "Max Absolute Error",
            "Experiment A (Plaintext)": "0.00",
            "Experiment B (Unmanaged HE)": f"{res_b['max_absolute_error']:.3e}",
            "Experiment C (Adaptive HE)": f"{res_c['max_absolute_error']:.3e}",
        },
        {
            "Metric": "Mean Relative Error",
            "Experiment A (Plaintext)": "0.00",
            "Experiment B (Unmanaged HE)": f"{res_b['mean_relative_error']:.3e}",
            "Experiment C (Adaptive HE)": f"{res_c['mean_relative_error']:.3e}",
        },
        {
            "Metric": "Root Mean Square Error (RMSE)",
            "Experiment A (Plaintext)": "0.00",
            "Experiment B (Unmanaged HE)": f"{res_b['rmse']:.3e}",
            "Experiment C (Adaptive HE)": f"{res_c['rmse']:.3e}",
        },
        {
            "Metric": "Successful Decryptions",
            "Experiment A (Plaintext)": f"{res_a['successful_decryptions']}/{res_a['num_records']}",
            "Experiment B (Unmanaged HE)": f"{res_b['successful_decryptions']}/{res_b['num_records']}",
            "Experiment C (Adaptive HE)": f"{res_c['successful_decryptions']}/{res_c['num_records']}",
        },
        {
            "Metric": "Adaptive Interventions",
            "Experiment A (Plaintext)": "0",
            "Experiment B (Unmanaged HE)": "0 (None)",
            "Experiment C (Adaptive HE)": str(res_c["adaptive_interventions"]),
        },
    ]

    comp_df = pd.DataFrame(comparison)
    csv_path = os.path.join(RESULTS_DIR, "experiment_comparison.csv")
    comp_df.to_csv(csv_path, index=False)

    print("\n" + "=" * 80)
    print("EXPERIMENTAL RESULTS COMPARISON TABLE")
    print("=" * 80)
    print(comp_df.to_string(index=False))
    print("=" * 80)
    print(f"[+] Saved comparison CSV to: {csv_path}")

    # Save complete JSON raw data for plotting
    summary_json = {
        "num_records": num_records,
        "experiment_a": {k: v for k, v in res_a.items() if k != "results"},
        "experiment_b": {k: v for k, v in res_b.items() if k != "absolute_errors" and k != "relative_errors"},
        "experiment_c": {k: v for k, v in res_c.items() if k != "absolute_errors" and k != "relative_errors"},
    }
    json_path = os.path.join(RESULTS_DIR, "experiment_summary.json")
    with open(json_path, "w") as f:
        json.dump(summary_json, f, indent=2)
    print(f"[+] Saved complete experimental metadata to: {json_path}")

    return comp_df


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    run_all_experiments(num_records=n)

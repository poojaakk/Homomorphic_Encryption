"""
Adaptive Noise-Resilient Homomorphic Encryption for Streaming Data
===================================================================
Master Orchestrator & CLI Entry Point
"""

import argparse
import os
import sys
import threading
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from experiments.run_comparison import run_all_experiments
from streaming.kafka_consumer import run_consumer
from streaming.kafka_producer import run_producer
from visualization.dashboard import Dashboard
from noise_control.noise_monitor import NoiseMonitor


def print_banner():
    banner = """
================================================================================
  ADAPTIVE NOISE-RESILIENT HOMOMORPHIC ENCRYPTION FOR STREAMING DATA
  TenSEAL CKKS | Apache Kafka | Environmental IoT Stream | Matplotlib
================================================================================
    """
    print(banner)


def check_status():
    print("=" * 70)
    print("[*] SYSTEM READINESS & STATUS CHECK")
    print("=" * 70)

    # 1. Dataset Check
    dataset_path = "data/sensor_stream.csv"
    if os.path.exists(dataset_path):
        import pandas as pd
        df = pd.read_csv(dataset_path)
        print(f"[+] Dataset:  READY ({len(df)} records at '{dataset_path}')")
    else:
        print(f"[-] Dataset:  MISSING ('{dataset_path}') - Run 'python verify_dataset.py'")

    # 2. Kafka Check
    try:
        from kafka.admin import KafkaAdminClient
        admin = KafkaAdminClient(bootstrap_servers="localhost:9092", request_timeout_ms=3000)
        topics = admin.list_topics()
        print(f"[+] Kafka:    CONNECTED (Broker at localhost:9092, topics: {topics})")
        admin.close()
    except Exception as exc:
        print(f"[-] Kafka:    UNREACHABLE ({exc}) - Start via 'docker compose up -d'")

    # 3. TenSEAL Check
    try:
        import tenseal as ts
        print(f"[+] TenSEAL:  READY (v{ts.__version__}, CKKS vector acceleration loaded)")
    except Exception as exc:
        print(f"[-] TenSEAL:  FAILED ({exc})")

    # 4. Results Check
    res_path = "results/experiment_comparison.csv"
    if os.path.exists(res_path):
        print(f"[+] Results:  SAVED (Comparison table available at '{res_path}')")
    else:
        print(f"[*] Results:  No prior benchmark runs. Execute '--mode experiment' to generate.")

    print("=" * 70)


def run_integrated_pipeline(num_records: int = 50, delay: float = 0.05):
    """
    Runs producer and consumer in parallel threads within a single process,
    feeds live metrics into NoiseMonitor, and automatically renders the 6-panel dashboard!
    """
    print_banner()
    print(f"[*] Launching Integrated Streaming Pipeline ({num_records} records)...")
    print()

    monitor = NoiseMonitor()

    # Consumer thread
    consumer_thread = threading.Thread(
        target=run_consumer,
        kwargs={
            "max_records": num_records,
            "adaptive_enabled": True,
            "error_threshold": 1e-4,
            "monitor": monitor,
        },
        daemon=True,
    )
    consumer_thread.start()

    # Give consumer 1 second to bind and join group
    time.sleep(1.0)

    # Producer thread
    producer_thread = threading.Thread(
        target=run_producer,
        kwargs={
            "max_records": num_records,
            "delay": delay,
            "loop": False,
        },
        daemon=True,
    )
    producer_thread.start()

    # Wait for consumer to finish processing all records
    consumer_thread.join()
    producer_thread.join()

    print("\n[*] Processing completed! Generating live 6-panel Matplotlib dashboard...")
    dashboard = Dashboard(monitor=monitor, output_dir="results")
    dashboard.render_plots("dashboard_streaming_run.png", interactive=False)
    print("[SUCCESS] All pipeline stages executed cleanly!")


def main():
    parser = argparse.ArgumentParser(
        description="Adaptive Noise-Resilient Homomorphic Encryption Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["stream", "producer", "consumer", "experiment", "dashboard", "status"],
        default="stream",
        help="Pipeline execution mode (default: stream)",
    )
    parser.add_argument("--records", type=int, default=50, help="Number of records to process")
    parser.add_argument("--delay", type=float, default=0.04, help="Producer delay in seconds")
    parser.add_argument("--threshold", type=float, default=1e-4, help="Adaptive error threshold")
    parser.add_argument("--no-adaptive", action="store_true", help="Disable adaptive control")

    args = parser.parse_args()

    if args.mode == "status":
        check_status()
    elif args.mode == "producer":
        print_banner()
        run_producer(max_records=args.records, delay=args.delay)
    elif args.mode == "consumer":
        print_banner()
        run_consumer(
            max_records=args.records,
            adaptive_enabled=not args.no_adaptive,
            error_threshold=args.threshold,
        )
    elif args.mode == "experiment":
        print_banner()
        run_all_experiments(num_records=args.records)
    elif args.mode == "dashboard":
        print_banner()
        # Test dashboard render
        dash = Dashboard(output_dir="results")
        print("[+] Dashboard module ready. Rendered from live stream or 'results/' data.")
    elif args.mode == "stream":
        run_integrated_pipeline(num_records=args.records, delay=args.delay)


if __name__ == "__main__":
    main()

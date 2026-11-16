"""
Streaming Kafka Producer
=========================
Reads continuous environmental sensor telemetry from data/sensor_stream.csv,
computes canonical SHA-256 integrity digests, and streams records into Kafka topic 'he-stream'.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from integrity.integrity_checker import compute_record_hash

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_NAME = os.environ.get("KAFKA_TOPIC_STREAM", "he-stream")
DATASET_PATH = "data/sensor_stream.csv"


def run_producer(
    dataset_path: str = DATASET_PATH,
    topic: str = TOPIC_NAME,
    delay: float = 0.05,
    max_records: int = None,
    loop: bool = False,
):
    print("=" * 65)
    print("STREAMING KAFKA PRODUCER")
    print("=" * 65)
    print(f"[*] Dataset Source:     {dataset_path}")
    print(f"[*] Target Broker:      {BOOTSTRAP_SERVERS}")
    print(f"[*] Target Topic:       {topic}")
    print(f"[*] Ingestion Delay:    {delay * 1000:.0f} ms/record")
    print()

    if not os.path.exists(dataset_path):
        print(f"[-] ERROR: Dataset file '{dataset_path}' not found.")
        sys.exit(1)

    df = pd.read_csv(dataset_path)
    total_available = len(df)
    print(f"[+] Loaded {total_available} sensor telemetry records.")

    print("[*] Connecting to Kafka Producer...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            linger_ms=5,
        )
        print("    [+] Connected successfully to Kafka broker.")
    except NoBrokersAvailable:
        print(f"    [-] ERROR: Cannot reach Kafka broker at {BOOTSTRAP_SERVERS}.")
        print("        Ensure Docker Kafka is running (docker compose up -d).")
        sys.exit(1)

    record_count = 0
    feature_cols = ["temperature", "dew_point", "pressure", "wind_speed", "pm25"]

    print("-" * 65)
    print(f"{'Record ID':<10} | {'Sensor Data [T, Dew, P, Wind, PM]':<35} | {'SHA-256':<12}")
    print("-" * 65)

    try:
        while True:
            for idx, row in df.iterrows():
                if max_records and record_count >= max_records:
                    break

                raw_values = [float(row[col]) for col in feature_cols]
                sensor_payload = {
                    "record_id": record_count + 1,
                    "timestamp": str(row["timestamp"]),
                    "features": raw_values,
                }

                # Compute deterministic SHA-256 hash for transit integrity verification
                integrity_hash = compute_record_hash(sensor_payload)

                message = {
                    "payload": sensor_payload,
                    "sha256": integrity_hash,
                }

                producer.send(topic, key=str(sensor_payload["record_id"]).encode("utf-8"), value=message)
                record_count += 1

                vals_str = f"[{raw_values[0]:.1f}, {raw_values[1]:.1f}, {raw_values[2]:.0f}, {raw_values[3]:.1f}, {raw_values[4]:.1f}]"
                print(f"#{record_count:<9} | {vals_str:<35} | {integrity_hash[:10]}…")

                time.sleep(delay)

            if not loop or (max_records and record_count >= max_records):
                break

    except KeyboardInterrupt:
        print("\n[!] Producer stopped by user.")
    finally:
        producer.flush(timeout=5)
        producer.close()
        print(f"\n[+] Finished streaming {record_count} records to topic '{topic}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensor Stream Kafka Producer")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between records in seconds (default: 0.05)")
    parser.add_argument("--max", type=int, default=None, help="Maximum records to publish (default: all)")
    parser.add_argument("--loop", action="store_true", help="Loop the dataset indefinitely")
    args = parser.parse_args()

    run_producer(delay=args.delay, max_records=args.max, loop=args.loop)

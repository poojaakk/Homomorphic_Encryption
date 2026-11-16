"""
Streaming Kafka Consumer & Homomorphic Encryption Pipeline
===========================================================
Subscribes to Kafka topic 'he-stream', verifies data integrity,
executes TenSEAL CKKS homomorphic evaluation, tracks natural approximation noise,
and applies adaptive control mitigations.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Optional
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from encryption.he_engine import HEEngine
from encryption.key_manager import KeyManager
from integrity.integrity_checker import verify_integrity
from noise_control.adaptive_controller import AdaptiveNoiseController
from noise_control.metrics import compute_absolute_error, compute_relative_error, compute_rmse
from noise_control.noise_monitor import NoiseMonitor

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_NAME = os.environ.get("KAFKA_TOPIC_STREAM", "he-stream")


def run_consumer(
    topic: str = TOPIC_NAME,
    max_records: Optional[int] = None,
    adaptive_enabled: bool = True,
    error_threshold: float = 1e-4,
    monitor: Optional[NoiseMonitor] = None,
):
    print("=" * 80)
    print("HOMOMORPHIC ENCRYPTION STREAMING CONSUMER & ADAPTIVE CONTROLLER")
    print("=" * 80)
    print(f"[*] Subscribing to Topic:     {topic}")
    print(f"[*] Kafka Broker:             {BOOTSTRAP_SERVERS}")
    print(f"[*] Adaptive Control Enabled: {adaptive_enabled} (Threshold: {error_threshold:.2e})")
    print()

    # 1. Initialize Cryptographic Engine & Adaptive Controller
    print("[*] Initializing TenSEAL CKKS Engine (poly_modulus=8192, scale=2^40)...")
    key_manager = KeyManager(poly_modulus_degree=8192, global_scale=2**40)
    engine = HEEngine(key_manager=key_manager)
    print("    [+] Generated Context, Secret Key, Public Key, and Relinearization Keys.")

    controller = AdaptiveNoiseController(error_threshold=error_threshold, max_multiplicative_depth=2)
    stream_monitor = monitor or NoiseMonitor()

    # 2. Connect to Kafka Consumer
    consumer_group = f"he_pipeline_group_{int(time.time())}"
    print(f"[*] Connecting Kafka Consumer (Group: {consumer_group})...")
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=BOOTSTRAP_SERVERS,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            group_id=consumer_group,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            consumer_timeout_ms=10000,
        )
        print("    [+] Consumer connected and listening for live stream events...")
    except NoBrokersAvailable:
        print(f"    [-] ERROR: Cannot reach Kafka broker at {BOOTSTRAP_SERVERS}.")
        sys.exit(1)

    print("-" * 80)
    print(
        f"{'Rec ID':<7} | {'Integrity':<12} | {'Enc(ms)':<8} | {'HE(ms)':<7} | {'Dec(ms)':<8} | "
        f"{'Plain Ref':<10} | {'HE Decrypted':<12} | {'Abs Error':<10} | {'Action':<10}"
    )
    print("-" * 80)

    processed_count = 0
    try:
        for msg in consumer:
            message_dict = msg.value
            if not isinstance(message_dict, dict) or "payload" not in message_dict:
                continue

            payload = message_dict["payload"]
            received_sha256 = message_dict.get("sha256", "")

            # -------------------------------------------------------------
            # STEP A: Data Integrity Verification (Separate from HE)
            # -------------------------------------------------------------
            is_valid, integrity_status = verify_integrity(payload, received_sha256)
            if not is_valid:
                print(f"[-] Record #{payload.get('record_id')}: {integrity_status} - Dropping corrupted message!")
                continue

            record_id = payload.get("record_id", processed_count + 1)
            raw_features = payload.get("features", [])

            # -------------------------------------------------------------
            # STEP B: Plaintext Ground-Truth Reference
            # -------------------------------------------------------------
            plain_ref = engine.evaluate_polynomial_plaintext_reference(
                raw_features, c2=0.05, c1=1.10, c0=2.50
            )

            # -------------------------------------------------------------
            # STEP C: Homomorphic Encryption (TenSEAL CKKS)
            # -------------------------------------------------------------
            enc_vector, enc_time = engine.encrypt_vector(raw_features)

            # -------------------------------------------------------------
            # STEP D: Homomorphic Computation on Ciphertext
            # -------------------------------------------------------------
            evaluated_cipher, comp_time, depth = engine.evaluate_polynomial(
                enc_vector, c2=0.05, c1=1.10, c0=2.50
            )

            # -------------------------------------------------------------
            # STEP E: Decryption
            # -------------------------------------------------------------
            decrypted_vals, dec_time = engine.decrypt_vector(evaluated_cipher)

            # -------------------------------------------------------------
            # STEP F: Natural CKKS Error & Precision Calculation
            # -------------------------------------------------------------
            abs_err = compute_absolute_error(plain_ref, decrypted_vals)
            rel_err = compute_relative_error(plain_ref, decrypted_vals)

            # -------------------------------------------------------------
            # STEP G: Adaptive Noise / Depth Management
            # -------------------------------------------------------------
            adaptive_action_str = "NONE"
            was_intervened = False
            if adaptive_enabled:
                controller.record_observation(abs_err, depth_consumed=depth)
                should_act, reason = controller.should_intervene()
                if should_act:
                    event = controller.trigger_mitigation(reason=reason, record_id=record_id)
                    adaptive_action_str = "REFRESH"
                    was_intervened = True

            # -------------------------------------------------------------
            # STEP H: Record Observation in Live Monitor
            # -------------------------------------------------------------
            stream_monitor.record_step(
                record_id=record_id,
                timestamp=payload.get("timestamp", ""),
                plaintext_ref=plain_ref[0],
                decrypted_val=decrypted_vals[0],
                abs_err=abs_err,
                rel_err=rel_err,
                enc_t_ms=enc_time * 1000.0,
                comp_t_ms=comp_time * 1000.0,
                dec_t_ms=dec_time * 1000.0,
                was_intervened=was_intervened,
            )

            processed_count += 1

            # Format real-time terminal output
            print(
                f"#{record_id:<6} | {integrity_status:<12} | "
                f"{enc_time * 1000.0:6.2f}ms | {comp_time * 1000.0:5.2f}ms | {dec_time * 1000.0:6.2f}ms | "
                f"{plain_ref[0]:10.4f} | {decrypted_vals[0]:12.4f} | {abs_err:10.2e} | {adaptive_action_str:<10}"
            )

            if max_records and processed_count >= max_records:
                break

    except KeyboardInterrupt:
        print("\n[!] Consumer interrupted by user.")
    finally:
        consumer.close()
        print("=" * 80)
        summary = stream_monitor.get_summary()
        if summary:
            print("[+] STREAM PROCESSING SUMMARY:")
            print(f"    - Total Records Processed:   {summary['total_processed']}")
            print(f"    - Mean Absolute Error (MAE): {summary['mean_abs_error']:.3e}")
            print(f"    - Max Absolute Error:        {summary['max_abs_error']:.3e}")
            print(f"    - Mean Relative Error:       {summary['mean_rel_error']:.3e}")
            print(f"    - Mean Encryption Latency:   {summary['mean_enc_latency_ms']:.2f} ms")
            print(f"    - Mean HE Compute Latency:   {summary['mean_comp_latency_ms']:.2f} ms")
            print(f"    - Mean Decryption Latency:   {summary['mean_dec_latency_ms']:.2f} ms")
            print(f"    - Total Interventions:       {summary['total_interventions']}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HE Streaming Consumer & Adaptive Controller")
    parser.add_argument("--max", type=int, default=None, help="Maximum records to process")
    parser.add_argument("--no-adaptive", action="store_true", help="Disable adaptive noise management")
    parser.add_argument("--threshold", type=float, default=1e-4, help="MAE threshold for adaptive intervention")
    args = parser.parse_args()

    run_consumer(
        max_records=args.max,
        adaptive_enabled=not args.no_adaptive,
        error_threshold=args.threshold,
    )

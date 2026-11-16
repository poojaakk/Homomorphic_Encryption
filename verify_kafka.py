"""
Phase 2: Kafka Verification & End-to-End Roundtrip Test
Verifies broker connectivity, topic management, and publish-subscribe flow.
"""
import json
import sys
import time
from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.admin import NewTopic
from kafka.errors import NoBrokersAvailable, TopicAlreadyExistsError

BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC_NAME = "he-stream"

def test_kafka_pipeline():
    print("=" * 65)
    print("PHASE 2: APACHE KAFKA INSTALLATION & BROKER VERIFICATION")
    print("=" * 65)
    print(f"[*] Target Broker: {BOOTSTRAP_SERVERS}")
    print(f"[*] Target Topic:  {TOPIC_NAME}")
    print()

    # Step 1: Broker Connectivity & Admin Client
    print("[1/4] Checking connection to Apache Kafka broker...")
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=BOOTSTRAP_SERVERS,
            client_id="phase2_admin_checker",
            request_timeout_ms=5000,
        )
        cluster_topics = admin_client.list_topics()
        print(f"    [+] Connected successfully! Found {len(cluster_topics)} topics: {cluster_topics}")
    except NoBrokersAvailable:
        print("    [-] ERROR: Could not connect to Kafka broker at localhost:9092.")
        print("        Ensure the Docker containers are running (docker compose up -d).")
        sys.exit(1)
    except Exception as exc:
        print(f"    [-] Connection error: {exc}")
        sys.exit(1)

    # Step 2: Ensure Target Topic Exists
    print(f"[2/4] Verifying topic '{TOPIC_NAME}'...")
    if TOPIC_NAME not in cluster_topics:
        try:
            new_topic = NewTopic(name=TOPIC_NAME, num_partitions=1, replication_factor=1)
            admin_client.create_topics([new_topic])
            print(f"    [+] Created topic '{TOPIC_NAME}' (1 partition, replication=1).")
        except TopicAlreadyExistsError:
            print(f"    [+] Topic '{TOPIC_NAME}' exists.")
    else:
        print(f"    [+] Topic '{TOPIC_NAME}' exists and is ready.")

    # Step 3: Publish a Test Message via Producer
    print("[3/4] Publishing test heartbeat message via KafkaProducer...")
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        linger_ms=0,
    )
    
    test_payload = {
        "event": "phase2_verification",
        "sender": "producer_test",
        "timestamp": time.time(),
        "status": "ready_for_homomorphic_encryption",
    }
    
    start_time = time.perf_counter()
    future = producer.send(TOPIC_NAME, value=test_payload)
    record_metadata = future.get(timeout=10)
    produce_elapsed_ms = (time.perf_counter() - start_time) * 1000
    producer.flush()
    print(f"    [+] Message produced to partition {record_metadata.partition} at offset {record_metadata.offset}")
    print(f"    [+] Produce latency: {produce_elapsed_ms:.2f} ms")

    # Step 4: Consume Message via Consumer
    print("[4/4] Verifying subscription & message delivery via KafkaConsumer...")
    consumer = KafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        auto_offset_reset="earliest",
        consumer_timeout_ms=5000,
        enable_auto_commit=True,
        group_id=f"phase2_test_group_{int(time.time())}",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    received_msg = None
    for msg in consumer:
        if isinstance(msg.value, dict) and msg.value.get("event") == "phase2_verification":
            received_msg = msg.value
            break
            
    consumer.close()
    producer.close()
    admin_client.close()

    print("=" * 65)
    if received_msg:
        print("[SUCCESS] Apache Kafka broker and topic 'he-stream' are fully operational!")
        print(f"          Received payload: {received_msg['event']} (status: {received_msg['status']})")
    else:
        print("[FAILURE] Message published but could not be consumed within timeout.")
        sys.exit(1)
    print("=" * 65)

if __name__ == "__main__":
    test_kafka_pipeline()

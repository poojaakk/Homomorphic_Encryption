import base64
import json
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


BOOTSTRAP_SERVERS = _env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_STREAM = _env("KAFKA_TOPIC_STREAM", "he-stream")

# How many seconds to wait between retries when Kafka is not yet ready.
_RETRY_DELAY = 3
_MAX_RETRIES = 10


def build_producer() -> KafkaProducer:
    """Connect to Kafka with retries to handle broker start-up lag."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                acks="all",
                linger_ms=5,
                key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                retries=3,
            )
            print(f"[kafka] Producer connected on attempt {attempt}")
            return producer
        except NoBrokersAvailable:
            print(f"[kafka] Broker not ready, retrying in {_RETRY_DELAY}s… (attempt {attempt}/{_MAX_RETRIES})")
            time.sleep(_RETRY_DELAY)
    raise NoBrokersAvailable("Kafka broker unavailable after retries")


def build_consumer(group_id: str) -> KafkaConsumer:
    """Connect consumer with retries."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            consumer = KafkaConsumer(
                TOPIC_STREAM,
                bootstrap_servers=BOOTSTRAP_SERVERS,
                group_id=group_id,
                auto_offset_reset="latest",
                enable_auto_commit=True,
                key_deserializer=lambda k: k.decode("utf-8") if k else None,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            print(f"[kafka] Consumer connected on attempt {attempt}")
            return consumer
        except NoBrokersAvailable:
            print(f"[kafka] Consumer broker not ready, retrying in {_RETRY_DELAY}s… (attempt {attempt}/{_MAX_RETRIES})")
            time.sleep(_RETRY_DELAY)
    raise NoBrokersAvailable("Kafka broker unavailable after retries (consumer)")


def serialize_ciphertext(raw_bytes: bytes) -> str:
    return base64.b64encode(raw_bytes).decode("ascii")


def deserialize_ciphertext(b64: str) -> bytes:
    return base64.b64decode(b64.encode("ascii"))


def new_message_key() -> str:
    return uuid.uuid4().hex


def produce_encrypted_value(
    producer: KafkaProducer,
    ciphertext_bytes: bytes,
    *,
    message_key: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    key = message_key or new_message_key()
    payload: Dict[str, Any] = {
        "message_key": key,
        "ciphertext_b64": serialize_ciphertext(ciphertext_bytes),
        "meta": meta or {},
    }
    producer.send(TOPIC_STREAM, key=key, value=payload)
    producer.flush(timeout=5)
    return key


class ConsumerThread:
    def __init__(self, on_message: Callable[[str, Dict[str, Any]], None], *, group_id: str):
        self._on_message = on_message
        self._group_id = group_id
        self._consumer: Optional[KafkaConsumer] = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._consumer:
                self._consumer.close(timeout=2)
        except Exception:
            pass

    def _run(self) -> None:
        # Build the consumer inside the thread so retries don't block startup.
        try:
            self._consumer = build_consumer(group_id=self._group_id)
        except NoBrokersAvailable:
            print("[kafka] ConsumerThread: could not connect, exiting thread")
            return

        for msg in self._consumer:
            if self._stop.is_set():
                break
            try:
                key = msg.key or ""
                value = msg.value or {}
                self._on_message(key, value)
            except Exception:
                continue

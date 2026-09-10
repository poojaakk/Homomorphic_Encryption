"""
Backend API  –  FastAPI
=======================
Endpoints
---------
POST /upload            – ingest CSV column → encrypt → Kafka → stream
GET  /encrypt           – encrypt a demo sample
GET  /compute/add       – add last two ciphertexts in the store
GET  /compute/multiply  – multiply last two ciphertexts in the store
GET  /noise             – current noise summary (adaptive threshold, rate, %)
GET  /bootstrap         – manually trigger a noise refresh
GET  /decrypt           – decrypt the last ciphertext in the store
GET  /logs              – in-memory log ring-buffer (optional ?category= filter)
GET  /status            – system health (context, Kafka, store size)
GET  /context           – active CKKS/BFV parameter set
WS   /ws                – push live events to all connected dashboards

WebSocket event types
---------------------
  stream      – new encrypted sample ingested from the upload pipeline
  kafka_ack   – Kafka consumer confirmed receipt of a message
  bootstrap   – a noise refresh was performed (auto or manual)
  noise       – periodic noise snapshot pushed every ~2 s
  error       – pipeline error (Kafka unreachable, etc.)
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import pandas as pd
import tenseal as ts
from fastapi import FastAPI, File, Form, Query, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from bootstrapping import bootstrap
from computation import ComputeError, add, multiply
from encryption import (
    create_context,
    decrypt_data,
    encrypt_data,
    get_context_params,
    serialize_ciphertext,
)
from kafka_service import (
    ConsumerThread,
    build_producer,
    deserialize_ciphertext as kafka_deserialize,
    produce_encrypted_value,
)
from logger import get_logs, log
from models import (
    BootstrapResponse,
    ComputeResponse,
    ContextResponse,
    DecryptResponse,
    EncryptResponse,
    LogsResponse,
    NoiseResponse,
    StatusResponse,
    UploadResponse,
)
from noise_manager import NoiseManager
from ws_hub import WebSocketHub

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "he-backend")

# ---------------------------------------------------------------------------
# Globals (initialised inside lifespan)
# ---------------------------------------------------------------------------
ingest_queue: "asyncio.Queue[List[float]]" = asyncio.Queue()
hub = WebSocketHub()
noise_manager = NoiseManager()
encrypted_store: List[Any] = []
current_context: Optional[ts.Context] = None
producer = None
consumer_thread: Optional[ConsumerThread] = None
main_loop: Optional[asyncio.AbstractEventLoop] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_context() -> None:
    global current_context
    current_context = create_context()
    log("HE context initialised (CKKS, poly_modulus=8192, depth=3)", "system")


def _deserialize_ckks_vector(ctx: ts.Context, raw: bytes) -> Any:
    return ts.ckks_vector_from(ctx, raw)


def _bootstrap_and_notify(label: str = "auto") -> Dict[str, Any]:
    """
    Run a bootstrap, log it, push a WS event, and return the payload dict.
    The WS push is fire-and-forget via asyncio (safe to call from sync code).
    """
    def _emit(payload: dict) -> None:
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(hub.publish(payload), main_loop)

    before, after = bootstrap(noise_manager, on_event=_emit, label=label)
    log(
        f"Bootstrap ({label}): noise {before} → {after} "
        f"| threshold now {noise_manager.get_threshold()} "
        f"| total bootstraps {noise_manager.bootstraps}",
        "noise",
    )
    return {"before": before, "after": after, "bootstraps": noise_manager.bootstraps}


# ---------------------------------------------------------------------------
# Producer loop  – reads from ingest_queue, encrypts, publishes to Kafka
# ---------------------------------------------------------------------------

async def _producer_loop() -> None:
    assert producer is not None
    assert current_context is not None

    while True:
        sample: List[float] = await ingest_queue.get()

        # ── Encrypt ──────────────────────────────────────────────────────────
        enc = encrypt_data(current_context, sample)
        encrypted_store.append(enc)
        noise_manager.increase_noise("encrypt")

        # ── Publish to Kafka ──────────────────────────────────────────────────
        message_key = uuid.uuid4().hex
        kafka_ok = True
        try:
            produce_encrypted_value(
                producer,
                serialize_ciphertext(enc),
                message_key=message_key,
                meta={"schema": "ckks_vector", "dims": len(sample)},
            )
        except Exception as exc:
            kafka_ok = False
            log(f"Kafka produce failed: {exc}", "kafka")
            await hub.publish(
                {
                    "type": "error",
                    "message": "Kafka produce failed – is docker-compose up?",
                }
            )

        # ── Noise tracking per stream message ─────────────────────────────────
        noise_manager.increase_noise("stream")

        # ── Adaptive bootstrap check ──────────────────────────────────────────
        bootstrap_info: Optional[Dict] = None
        if noise_manager.check_threshold():
            bootstrap_info = _bootstrap_and_notify(label="auto")

        # ── Push stream event to dashboard ────────────────────────────────────
        nm = noise_manager.summary()
        await hub.publish(
            {
                "type": "stream",
                "message_key": message_key,
                "data": sample,           # plaintext for charting; Kafka carries only ciphertext
                "kafka_ok": kafka_ok,
                "noise": nm["noise"],
                "threshold": nm["threshold"],
                "noise_rate": nm["noise_rate"],
                "pct_used": nm["pct_used"],
                "bootstraps": nm["bootstraps"],
                "refreshed": bootstrap_info is not None,
                "refresh_before": bootstrap_info["before"] if bootstrap_info else None,
                "refresh_after": bootstrap_info["after"] if bootstrap_info else None,
            }
        )


# ---------------------------------------------------------------------------
# Kafka consumer callback  (runs in a background thread)
# ---------------------------------------------------------------------------

def _consumer_on_message(kafka_key: str, payload: Dict[str, Any]) -> None:
    global main_loop
    if not main_loop or not current_context:
        return

    try:
        raw = kafka_deserialize(payload["ciphertext_b64"])
        _deserialize_ckks_vector(current_context, raw)   # validates the payload
        evt = {
            "type": "kafka_ack",
            "kafka_key": kafka_key,
            "message_key": payload.get("message_key", kafka_key),
        }
        asyncio.run_coroutine_threadsafe(hub.publish(evt), main_loop)
        log(f"Kafka ack: {payload.get('message_key', kafka_key)}", "kafka")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Periodic noise heartbeat  – pushes a 'noise' event every 2 s
# ---------------------------------------------------------------------------

async def _noise_heartbeat() -> None:
    while True:
        await asyncio.sleep(2)
        await hub.publish({"type": "noise", **noise_manager.summary()})


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global producer, consumer_thread, main_loop
    main_loop = asyncio.get_running_loop()

    _generate_context()

    producer = build_producer()
    consumer_thread = ConsumerThread(
        on_message=_consumer_on_message, group_id=KAFKA_CONSUMER_GROUP
    )
    consumer_thread.start()
    log("Kafka consumer thread started", "kafka")

    producer_task = asyncio.create_task(_producer_loop())
    heartbeat_task = asyncio.create_task(_noise_heartbeat())

    try:
        yield
    finally:
        producer_task.cancel()
        heartbeat_task.cancel()
        if consumer_thread:
            consumer_thread.stop()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Noise-Resilient HE Streaming API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:5174", "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), column: str = Form(...)):
    content = await file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))

    if column not in df.columns:
        log(f"Upload failed – column '{column}' not found", "error")
        return {"error": f"Column '{column}' not found", "columns": list(df.columns)}

    pushed = 0
    for v in df[column].tolist():
        try:
            await ingest_queue.put([float(v)])
            pushed += 1
        except (TypeError, ValueError):
            continue

    log(f"Uploaded {pushed} rows from column '{column}'", "api")
    return UploadResponse(status="uploaded", column_used=column, rows=pushed)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await asyncio.sleep(30)   # keep-alive; events pushed via hub.publish
    except Exception:
        await hub.disconnect(ws)


@app.get("/encrypt", response_model=EncryptResponse)
def encrypt():
    if current_context is None:
        return {"error": "Context not ready"}
    data = [10.5, 20.3, 30.7]
    enc = encrypt_data(current_context, data)
    encrypted_store.append(enc)
    noise_manager.increase_noise("encrypt")
    log(f"Manual encrypt: {data}", "api")
    return EncryptResponse(
        plaintext=data,
        dims=len(data),
        ciphertext_preview=str(enc.serialize()[:32].hex()) + "…",
    )


@app.get("/compute/add")
def compute_add():
    assert current_context is not None

    if len(encrypted_store) < 2:
        log("compute/add – store has < 2 ciphertexts, using demo values", "compute")
        plain_a = [10.5, 20.3, 30.7]
        plain_b = [1.0,  2.0,  3.0]
    else:
        # Decrypt the last two real store entries to get their plaintext values,
        # then re-encrypt both fresh at full scale — this prevents any
        # "scale out of bounds" error no matter how many times add is clicked.
        try:
            plain_a = decrypt_data(encrypted_store[-1])
            plain_b = decrypt_data(encrypted_store[-2])
        except Exception:
            plain_a = [10.5, 20.3, 30.7]
            plain_b = [1.0,  2.0,  3.0]

    # Pad/trim so both vectors are the same length
    length = min(len(plain_a), len(plain_b))
    plain_a, plain_b = plain_a[:length], plain_b[:length]

    a = encrypt_data(current_context, plain_a)
    b = encrypt_data(current_context, plain_b)

    try:
        res, delta = add(a, b, noise_manager)
    except ComputeError as exc:
        log(str(exc), "error")
        return {"error": str(exc)}

    encrypted_store.append(res)
    log(f"compute/add: noise delta={delta}, total={noise_manager.get_noise()}", "compute")

    boot_info = None
    if noise_manager.check_threshold():
        boot_info = _bootstrap_and_notify("auto")

    # Show the user what the expected plaintext result should be
    expected = [round(a + b, 6) for a, b in zip(plain_a, plain_b)]

    nm = noise_manager.summary()
    return {
        "status": "ok",
        "operation": "add",
        "operand_a (sample)": plain_a[:5],
        "operand_b (sample)": plain_b[:5],
        "expected_result (sample)": expected[:5],
        "vector_length": length,
        "noise_delta": delta,
        "noise": nm["noise"],
        "threshold": nm["threshold"],
        "bootstrap": boot_info,
    }


@app.get("/compute/multiply")
def compute_mul():
    assert current_context is not None

    if len(encrypted_store) < 2:
        log("compute/multiply – store has < 2 ciphertexts, using demo values", "compute")
        plain_a = [10.5, 20.3, 30.7]
        plain_b = [2.0,  2.0,  2.0]
    else:
        # Decrypt the last two real store entries, re-encrypt fresh at full
        # scale — prevents "scale out of bounds" on every repeated multiply.
        try:
            plain_a = decrypt_data(encrypted_store[-1])
            plain_b = decrypt_data(encrypted_store[-2])
        except Exception:
            plain_a = [10.5, 20.3, 30.7]
            plain_b = [2.0,  2.0,  2.0]

    # Pad/trim so both vectors are the same length
    length = min(len(plain_a), len(plain_b))
    plain_a, plain_b = plain_a[:length], plain_b[:length]

    a = encrypt_data(current_context, plain_a)
    b = encrypt_data(current_context, plain_b)

    try:
        res, delta = multiply(a, b, noise_manager)
    except ComputeError as exc:
        log(str(exc), "error")
        return {"error": str(exc)}

    encrypted_store.append(res)
    log(f"compute/multiply: noise delta={delta}, total={noise_manager.get_noise()}", "compute")

    boot_info = None
    if noise_manager.check_threshold():
        boot_info = _bootstrap_and_notify("auto")

    # Show the user what the expected plaintext result should be
    expected = [round(a * b, 6) for a, b in zip(plain_a, plain_b)]

    nm = noise_manager.summary()
    return {
        "status": "ok",
        "operation": "multiply",
        "operand_a (sample)": plain_a[:5],
        "operand_b (sample)": plain_b[:5],
        "expected_result (sample)": expected[:5],
        "vector_length": length,
        "noise_delta": delta,
        "noise": nm["noise"],
        "threshold": nm["threshold"],
        "bootstrap": boot_info,
    }


@app.get("/noise", response_model=NoiseResponse)
def noise():
    nm = noise_manager.summary()
    return NoiseResponse(**nm)


@app.get("/noise/history")
def noise_history():
    return {"history": noise_manager.get_history()}


@app.get("/bootstrap", response_model=BootstrapResponse)
def boot():
    info = _bootstrap_and_notify(label="manual")
    log("Manual bootstrap triggered via /bootstrap", "noise")
    return BootstrapResponse(
        before=info["before"],
        after=info["after"],
        bootstraps=info["bootstraps"],
        threshold=noise_manager.get_threshold(),
        label="manual",
    )


@app.get("/decrypt", response_model=DecryptResponse)
def decrypt():
    if not encrypted_store:
        log("decrypt failed – store is empty", "error")
        return {"error": "No ciphertexts in store"}
    try:
        result = decrypt_data(encrypted_store[-1])
        log(f"Decrypted last ciphertext: {result}", "api")
        return DecryptResponse(result=result, store_size=len(encrypted_store))
    except Exception as exc:
        log(f"Decrypt error: {exc}", "error")
        return {"error": str(exc)}


@app.get("/logs", response_model=LogsResponse)
def logs(category: Optional[str] = Query(None, description="Filter by category")):
    return get_logs(category=category)


@app.get("/status", response_model=StatusResponse)
def status():
    return StatusResponse(
        context_ready=current_context is not None,
        kafka_producer_ready=producer is not None,
        kafka_consumer_alive=consumer_thread is not None and consumer_thread._thread.is_alive(),
        store_size=len(encrypted_store),
        noise=noise_manager.get_noise(),
        bootstraps=noise_manager.bootstraps,
    )


@app.get("/context", response_model=ContextResponse)
def context_info():
    params = get_context_params()
    if not params:
        return {"error": "Context not initialised"}
    return ContextResponse(**params)

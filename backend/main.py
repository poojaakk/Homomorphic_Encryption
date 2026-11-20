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
POST /video/process     – upload video → frame extraction → HE smoothing
GET  /video/status      – current video pipeline state
WS   /ws                – push live events to all connected dashboards

WebSocket event types
---------------------
  stream          – new encrypted sample ingested (CSV pipeline)
  kafka_ack       – Kafka consumer confirmed receipt
  bootstrap       – CSV-mode ciphertext refresh
  noise           – periodic noise snapshot (every 2 s)
  video_frame     – per-frame noise snapshot during video processing
  video_bootstrap – bootstrap fired during video processing
  video_stream    – one video batch completed
  error           – pipeline error
"""

from __future__ import annotations

import asyncio
import io
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import pandas as pd
import tenseal as ts
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket
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
    FrameAnalysisResponse,
    FrameAnalysisStatusResponse,
    FrameHistogramResponse,
    FramePageResponse,
    LogsResponse,
    NoiseResponse,
    StatusResponse,
    UploadResponse,
    VideoProcessResponse,
    VideoStatusResponse,
)
from noise_manager import NoiseManager
from video_processor import process_video, save_upload_to_temp
from frame_analyzer import (
    analyze_video,
    get_frame_jpeg,
    pixel_histogram,
    FrameAnalysisResult,
)
from ws_hub import WebSocketHub

# CSV/static HE + Kafka stream (do not share this pool with the video pipeline)
_csv_he_lock = threading.Lock()
_csv_stream_ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="csv-stream")
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "he-backend")

# ---------------------------------------------------------------------------
# Globals (initialised inside lifespan)
# ---------------------------------------------------------------------------
ingest_queue: "asyncio.Queue[List[float]]" = asyncio.Queue()
hub = WebSocketHub()
# CSV-mode noise manager (mode="csv", threshold 50-80)
noise_manager = NoiseManager(mode="csv")
encrypted_store: List[Any] = []
csv_values: List[float] = []
csv_column: str = ""
csv_cursor: int = 0
current_context: Optional[ts.Context] = None
producer = None
consumer_thread: Optional[ConsumerThread] = None
main_loop: Optional[asyncio.AbstractEventLoop] = None

# ---------------------------------------------------------------------------
# Video processing state
# ---------------------------------------------------------------------------
_video_processing: bool = False
_video_last_result: Optional[Dict] = None
_video_last_error: Optional[str] = None
# Dedicated video-mode noise manager (mode="video", threshold 200-500).
# Kept separate so CSV and video noise budgets don't interfere with each other.
_video_noise_manager = NoiseManager(mode="video")

# ---------------------------------------------------------------------------
# Frame analysis state  (independent pipeline — no HE, pure OpenCV stats)
# ---------------------------------------------------------------------------
_fa_analyzing: bool = False
_fa_frames_done: int = 0
_fa_total_frames: int = 0
_fa_last_result: Optional[FrameAnalysisResult] = None
_fa_last_error: Optional[str] = None
_fa_tmp_path: Optional[str] = None      # kept alive so JPEG/histogram endpoints can re-open it


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_context() -> None:
    global current_context
    current_context = create_context()
    log("HE context initialised (CKKS, poly_modulus=8192, depth=3)", "system")


def _next_csv_values(n: int) -> List[tuple[int, float]]:
    """Take the next n numbers from the uploaded CSV column (wraps around)."""
    global csv_cursor
    if not csv_values:
        return []
    out: List[tuple[int, float]] = []
    for _ in range(n):
        idx = csv_cursor % len(csv_values)
        out.append((idx, csv_values[idx]))
        csv_cursor += 1
    return out


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

def _csv_stream_one(sample: List[float], prod, message_key: str):
    """Encrypt one CSV sample and optionally publish to Kafka. CSV path only."""
    with _csv_he_lock:
        enc = encrypt_data(current_context, sample)
        raw = serialize_ciphertext(enc)
    if prod is None:
        return enc, False
    produce_encrypted_value(
        prod,
        raw,
        message_key=message_key,
        meta={"schema": "ckks_vector", "dims": len(sample)},
    )
    return enc, True


async def _producer_loop() -> None:
    global producer
    assert current_context is not None
    loop = asyncio.get_running_loop()

    while True:
        sample: List[float] = await ingest_queue.get()
        message_key = uuid.uuid4().hex
        kafka_ok = True
        prod = producer
        t_sample = time.perf_counter()
        try:
            enc, kafka_ok = await loop.run_in_executor(
                _csv_stream_ex, _csv_stream_one, sample, prod, message_key
            )
        except Exception as exc:
            kafka_ok = False
            producer = None
            log(f"Kafka produce failed: {exc}", "kafka")
            await hub.publish(
                {
                    "type": "error",
                    "message": "Kafka produce failed – is docker-compose up?",
                }
            )
            continue

        encrypted_store.append(enc)
        noise_manager.increase_noise("encrypt")
        noise_manager.increase_noise("stream")

        bootstrap_info: Optional[Dict] = None
        if noise_manager.check_threshold():
            bootstrap_info = _bootstrap_and_notify(label="auto")

        nm = noise_manager.summary()
        sample_ms = (time.perf_counter() - t_sample) * 1000
        await hub.publish(
            {
                "type": "stream",
                "message_key": message_key,
                "data": sample,
                "kafka_ok": kafka_ok,
                "noise": nm["noise"],
                "threshold": nm["threshold"],
                "noise_rate": nm["noise_rate"],
                "pct_used": nm["pct_used"],
                "bootstraps": nm["bootstraps"],
                "refreshed": bootstrap_info is not None,
                "refresh_before": bootstrap_info["before"] if bootstrap_info else None,
                "refresh_after": bootstrap_info["after"] if bootstrap_info else None,
                "sample_ms": round(sample_ms, 2),
            }
        )
        await asyncio.sleep(0)


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

    # Never block API startup on Kafka — reconnect in the background.
    kafka_task = asyncio.create_task(_kafka_connect_loop())
    producer_task = asyncio.create_task(_producer_loop())
    heartbeat_task = asyncio.create_task(_noise_heartbeat())

    try:
        yield
    finally:
        kafka_task.cancel()
        producer_task.cancel()
        heartbeat_task.cancel()
        if consumer_thread:
            consumer_thread.stop()


async def _kafka_connect_loop() -> None:
    """Keep trying until the broker is up, then rebuild if it drops."""
    global producer, consumer_thread
    while True:
        if producer is None:
            try:
                producer = await asyncio.get_running_loop().run_in_executor(
                    None, build_producer
                )
                log("Kafka producer connected", "kafka")
            except Exception as exc:
                producer = None
                log(f"Kafka producer waiting: {exc}", "kafka")

        alive = (
            consumer_thread is not None
            and consumer_thread._thread.is_alive()
        )
        if producer is not None and not alive:
            consumer_thread = ConsumerThread(
                on_message=_consumer_on_message, group_id=KAFKA_CONSUMER_GROUP
            )
            consumer_thread.start()
            log("Kafka consumer thread started", "kafka")
            await asyncio.sleep(8.0)
            continue

        await asyncio.sleep(5.0)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# 500 MB multipart body limit — needed for large video uploads
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024

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

def _resolve_csv_column(df: pd.DataFrame, requested: str) -> Optional[str]:
    """Match a user-typed name against CSV headers (trim + case-insensitive)."""
    wanted = requested.strip().lower()
    if not wanted:
        return None
    stripped = [(str(c).strip(), c) for c in df.columns]
    for name, original in stripped:
        if name.lower() == wanted:
            return original
    return None


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), column: str = Form(...)):
    global csv_values, csv_column, csv_cursor
    content = await file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")), skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]

    available = list(df.columns)
    resolved = _resolve_csv_column(df, column)
    if resolved is None:
        log(f"Upload failed – column '{column}' not found. Available: {available}", "error")
        raise HTTPException(
            status_code=422,
            detail=(
                f"Column '{column}' not found. "
                f"Available columns: {', '.join(available)}"
            ),
        )

    values: List[float] = []
    pushed = 0
    for v in df[resolved].tolist():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if pd.isna(fv):
            continue
        values.append(fv)
        await ingest_queue.put([fv])
        pushed += 1

    if pushed == 0:
        raise HTTPException(
            status_code=422,
            detail=f"Column '{resolved}' has no numeric values (NaN rows are skipped).",
        )

    csv_values = values
    csv_column = resolved
    csv_cursor = 0

    log(f"Uploaded {pushed} rows from column '{resolved}'", "api")
    return UploadResponse(status="uploaded", column_used=resolved, rows=pushed)


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
    taken = _next_csv_values(1)
    if not taken:
        return {"error": "Upload a CSV and pick a numeric column first."}
    row_idx, value = taken[0]
    data = [value]
    with _csv_he_lock:
        enc = encrypt_data(current_context, data)
        preview = str(enc.serialize()[:32].hex()) + "…"
    encrypted_store.append(enc)
    noise_manager.increase_noise("encrypt")
    log(f"Encrypt CSV {csv_column}[{row_idx}] = {value}", "api")
    return EncryptResponse(
        plaintext=data,
        dims=len(data),
        ciphertext_preview=preview,
        source_column=csv_column,
        source_row=row_idx,
    )


@app.get("/compute/add")
def compute_add():
    assert current_context is not None

    if len(encrypted_store) < 2:
        if len(csv_values) < 2:
            log("compute/add – upload a CSV with at least 2 numeric rows", "compute")
            return {"error": "Upload a CSV with at least 2 numeric values first."}
        log("compute/add – store has < 2 ciphertexts, using first two CSV values", "compute")
        plain_a = [csv_values[0]]
        plain_b = [csv_values[1]]
    else:
        # Decrypt the last two real store entries to get their plaintext values,
        # then re-encrypt both fresh at full scale — this prevents any
        # "scale out of bounds" error no matter how many times add is clicked.
        try:
            with _csv_he_lock:
                plain_a = decrypt_data(encrypted_store[-1])
                plain_b = decrypt_data(encrypted_store[-2])
        except Exception:
            if len(csv_values) < 2:
                return {"error": "Could not read store; upload a CSV first."}
            plain_a = [csv_values[0]]
            plain_b = [csv_values[1]]

    # Pad/trim so both vectors are the same length
    length = min(len(plain_a), len(plain_b))
    plain_a, plain_b = plain_a[:length], plain_b[:length]

    with _csv_he_lock:
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
        if len(csv_values) < 2:
            log("compute/multiply – upload a CSV with at least 2 numeric rows", "compute")
            return {"error": "Upload a CSV with at least 2 numeric values first."}
        log("compute/multiply – store has < 2 ciphertexts, using first two CSV values", "compute")
        plain_a = [csv_values[0]]
        plain_b = [csv_values[1]]
    else:
        # Decrypt the last two real store entries, re-encrypt fresh at full
        # scale — prevents "scale out of bounds" on every repeated multiply.
        try:
            with _csv_he_lock:
                plain_a = decrypt_data(encrypted_store[-1])
                plain_b = decrypt_data(encrypted_store[-2])
        except Exception:
            if len(csv_values) < 2:
                return {"error": "Could not read store; upload a CSV first."}
            plain_a = [csv_values[0]]
            plain_b = [csv_values[1]]

    # Pad/trim so both vectors are the same length
    length = min(len(plain_a), len(plain_b))
    plain_a, plain_b = plain_a[:length], plain_b[:length]

    with _csv_he_lock:
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
        with _csv_he_lock:
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


# ---------------------------------------------------------------------------
# Video streaming endpoints
# ---------------------------------------------------------------------------

@app.get("/video/status", response_model=VideoStatusResponse)
def video_status():
    """Report the state of the video processing pipeline."""
    global _video_processing, _video_last_result, _video_last_error
    result = _video_last_result
    return VideoStatusResponse(
        ready=current_context is not None,
        processing=_video_processing,
        last_filename=result["info"]["filename"] if result else None,
        last_total_frames=result.get("frames_processed") if result else None,
        last_batches=None,
        last_bootstraps=result["total_bootstraps"] if result else None,
        error=_video_last_error,
    )


@app.post("/video/process", response_model=VideoProcessResponse)
async def video_process(
    file: UploadFile = File(...),
    threshold: int = Form(50, ge=10, le=500, description="Bootstrap threshold (10–500)"),
):
    """
    Stream every frame through CKKS encrypt → add last two → scale 0.5.
    Ciphertext noise from those ops is bootstrapped when it exceeds *threshold*.
    """
    global _video_processing, _video_last_result, _video_last_error, _video_noise_manager

    if current_context is None:
        raise HTTPException(status_code=503, detail="HE context not ready")
    if _video_processing:
        raise HTTPException(status_code=409, detail="A video is already being processed")

    filename = file.filename or "upload.mp4"
    ext = os.path.splitext(filename)[1].lower()
    supported = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
    if ext not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported video format '{ext}'. Supported: {', '.join(sorted(supported))}",
        )

    _video_processing = True
    _video_last_error = None
    _video_last_result = None

    # Fresh noise manager pinned to the user-supplied threshold
    _video_noise_manager = NoiseManager(mode="video", custom_threshold=threshold)
    log(f"Video pipeline starting: threshold={threshold}", "api")

    tmp_path: Optional[str] = None

    try:
        content = await file.read()
        if len(content) == 0:
            raise ValueError("Uploaded file is empty")
        if len(content) > _MAX_UPLOAD_BYTES:
            raise ValueError(
                f"File too large ({len(content) // (1024*1024)} MB). "
                f"Maximum allowed: {_MAX_UPLOAD_BYTES // (1024*1024)} MB."
            )

        loop = asyncio.get_running_loop()
        tmp_path = await loop.run_in_executor(
            None, save_upload_to_temp, content, filename
        )
        log(f"Video upload saved: {filename} ({len(content)//1024} KB)", "api")

        # Run the heavy synchronous pipeline in a thread executor so we
        # don't block the asyncio event loop (WebSocket heartbeats keep firing).
        result = await loop.run_in_executor(
            None,
            _run_video_pipeline,
            tmp_path,
            threshold,
        )

        _video_last_result = result

        log(
            f"Video stream HE: {filename} | "
            f"{result['frames_processed']} frames | "
            f"{result['total_bootstraps']} bootstraps | "
            f"peak CKKS noise {result['peak_noise']}",
            "api",
        )

        return VideoProcessResponse(**result)

    except (FileNotFoundError, ValueError) as exc:
        _video_last_error = str(exc)
        log(f"Video processing error: {exc}", "error")
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        _video_last_error = str(exc)
        log(f"Video processing unexpected error: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")
    finally:
        _video_processing = False
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _run_video_pipeline(tmp_path: str, threshold: int = 50) -> Dict:
    """Synchronous wrapper — runs in a thread executor."""
    def _emit(payload: dict) -> None:
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(hub.publish(payload), main_loop)

    vr = process_video(
        video_path=tmp_path,
        context=current_context,
        noise_mgr=_video_noise_manager,
        on_emit=_emit,
        threshold=threshold,
    )

    snapshots = [
        {
            "frame_idx":       s["frame_idx"],
            "noise":           s["noise"],
            "threshold":       s["threshold"],
            "pct_used":        s["pct_used"],
            "bootstrapped":    s["bootstrapped"],
            "bootstraps":      s["bootstraps"],
            "ops":             s.get("ops") or [],
            "noise_generated": s.get("noise_generated") or 0,
            "noise_reduced":   s.get("noise_reduced") or 0,
            "frame_a":         s.get("frame_a"),
            "frame_b":         s.get("frame_b"),
            "frame_ms":        s.get("frame_ms") or 0,
            "elapsed_ms":      s.get("elapsed_ms") or 0,
            "he_ops":          s.get("he_ops") or 0,
        }
        for s in vr.all_noise_snapshots
    ]

    return {
        "status":                 "ok",
        "info": {
            "filename":     vr.info.filename,
            "fps":          vr.info.fps,
            "total_frames": vr.info.total_frames,
            "duration_sec": vr.info.duration_sec,
            "width":        vr.info.width,
            "height":       vr.info.height,
        },
        "process_width":          vr.process_width,
        "process_height":         vr.process_height,
        "frames_processed":       vr.frames_processed,
        "truncated":              vr.truncated,
        "fps":                    vr.fps,
        "total_bootstraps":       vr.total_bootstraps,
        "computation":            vr.computation,
        "original_frames_jpeg":   vr.original_frames_jpeg,
        "result_frames_jpeg":     vr.result_frames_jpeg,
        "all_noise_snapshots":    snapshots,
        "peak_noise":             vr.peak_noise,
        "total_noise_generated":  vr.total_noise_generated,
        "total_noise_reduced":    vr.total_noise_reduced,
        "elapsed_ms":             vr.elapsed_ms,
        "avg_frame_ms":           vr.avg_frame_ms,
        "throughput_fps":         vr.throughput_fps,
    }


# ===========================================================================
# Frame Analysis endpoints  (pure OpenCV — independent of the HE pipeline)
# ===========================================================================

def _run_frame_analysis(tmp_path: str) -> None:
    """
    Synchronous worker — runs in a thread executor.
    Updates global state and publishes WebSocket progress events.
    """
    global _fa_analyzing, _fa_frames_done, _fa_total_frames
    global _fa_last_result, _fa_last_error

    def _on_progress(done: int, total: int) -> None:
        global _fa_frames_done, _fa_total_frames
        _fa_frames_done  = done
        _fa_total_frames = total
        if main_loop and main_loop.is_running():
            pct = round(done / total * 100, 1) if total > 0 else 0.0
            asyncio.run_coroutine_threadsafe(
                hub.publish({
                    "type":         "frame_extraction_progress",
                    "frames_done":  done,
                    "total_frames": total,
                    "pct_done":     pct,
                }),
                main_loop,
            )

    try:
        result = analyze_video(tmp_path, on_progress=_on_progress)
        _fa_last_result = result
        log(
            f"Frame analysis complete: {result.filename} | "
            f"{result.frames_analyzed} frames extracted",
            "api",
        )
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                hub.publish({
                    "type":            "frame_extraction_done",
                    "frames_analyzed": result.frames_analyzed,
                    "total_frames":    result.total_frames,
                    "filename":        result.filename,
                }),
                main_loop,
            )
    except Exception as exc:
        _fa_last_error = str(exc)
        log(f"Frame analysis error: {exc}", "error")
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                hub.publish({"type": "frame_extraction_error", "message": str(exc)}),
                main_loop,
            )
    finally:
        _fa_analyzing = False


@app.post("/frames/analyze", response_model=FrameAnalysisResponse)
async def frames_analyze(file: UploadFile = File(...)):
    """
    Upload a video → extract every frame → compute grayscale stats.
    Returns the complete stats list synchronously (runs in a thread so the
    event-loop stays responsive for WS heartbeats during processing).
    """
    global _fa_analyzing, _fa_frames_done, _fa_total_frames
    global _fa_last_result, _fa_last_error, _fa_tmp_path

    if _fa_analyzing:
        raise HTTPException(status_code=409, detail="Frame analysis already in progress.")

    filename = file.filename or "upload.mp4"
    ext = os.path.splitext(filename)[1].lower()
    supported = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
    if ext not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported format '{ext}'. Supported: {', '.join(sorted(supported))}",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File too large ({len(content) // (1024*1024)} MB). "
                f"Maximum: {_MAX_UPLOAD_BYTES // (1024*1024)} MB."
            ),
        )

    # Clean up previous temp file if any
    if _fa_tmp_path and os.path.exists(_fa_tmp_path):
        try:
            os.remove(_fa_tmp_path)
        except OSError:
            pass

    _fa_analyzing    = True
    _fa_frames_done  = 0
    _fa_total_frames = 0
    _fa_last_result  = None
    _fa_last_error   = None

    loop = asyncio.get_running_loop()
    tmp_path = await loop.run_in_executor(None, save_upload_to_temp, content, filename)
    _fa_tmp_path = tmp_path

    log(f"Frame analysis upload saved: {filename} ({len(content)//1024} KB)", "api")

    # Run the CPU-bound analysis in a thread executor
    await loop.run_in_executor(None, _run_frame_analysis, tmp_path)

    if _fa_last_error:
        raise HTTPException(status_code=500, detail=_fa_last_error)

    r = _fa_last_result
    return FrameAnalysisResponse(
        status="ok",
        info={
            "filename":        r.filename,
            "fps":             r.fps,
            "total_frames":    r.total_frames,
            "duration_sec":    r.duration_sec,
            "width":           r.width,
            "height":          r.height,
            "frames_analyzed": r.frames_analyzed,
        },
        stats=[
            {
                "frame_idx":     s.frame_idx,
                "timestamp_s":   s.timestamp_s,
                "width":         s.width,
                "height":        s.height,
                "avg_intensity": s.avg_intensity,
                "min_intensity": s.min_intensity,
                "max_intensity": s.max_intensity,
                "std_intensity": s.std_intensity,
                "frame_size_kb": s.frame_size_kb,
            }
            for s in r.stats
        ],
    )


@app.get("/frames/analyze/status", response_model=FrameAnalysisStatusResponse)
def frames_analyze_status():
    """Live progress: poll this during processing."""
    pct = (
        round(_fa_frames_done / _fa_total_frames * 100, 1)
        if _fa_total_frames > 0 else 0.0
    )
    return FrameAnalysisStatusResponse(
        analyzing    = _fa_analyzing,
        frames_done  = _fa_frames_done,
        total_frames = _fa_total_frames,
        pct_done     = pct,
        filename     = _fa_last_result.filename if _fa_last_result else None,
        error        = _fa_last_error,
    )


@app.get("/frames/page", response_model=FramePageResponse)
def frames_page(
    frame_idx: int = Query(0, ge=0, description="Zero-based frame index"),
    width:     int = Query(320, ge=64, le=1920),
    height:    int = Query(180, ge=36, le=1080),
):
    """
    Return the JPEG thumbnail + stat for a single frame.
    The original video temp file is re-opened for each request so only one
    frame is decoded at a time.
    """
    if _fa_last_result is None:
        raise HTTPException(status_code=404, detail="No frame analysis result available.")
    if not _fa_tmp_path or not os.path.exists(_fa_tmp_path):
        raise HTTPException(
            status_code=404,
            detail="Source video has been cleaned up. Re-upload to view frames.",
        )

    r = _fa_last_result
    if frame_idx >= r.frames_analyzed:
        raise HTTPException(
            status_code=422,
            detail=f"frame_idx {frame_idx} out of range (0–{r.frames_analyzed - 1}).",
        )

    try:
        jpeg = get_frame_jpeg(_fa_tmp_path, frame_idx, width, height)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    stat = r.stats[frame_idx]
    return FramePageResponse(
        frame_idx    = frame_idx,
        total_frames = r.frames_analyzed,
        jpeg_b64     = jpeg,
        stat         = {
            "frame_idx":     stat.frame_idx,
            "timestamp_s":   stat.timestamp_s,
            "width":         stat.width,
            "height":        stat.height,
            "avg_intensity": stat.avg_intensity,
            "min_intensity": stat.min_intensity,
            "max_intensity": stat.max_intensity,
            "std_intensity": stat.std_intensity,
            "frame_size_kb": stat.frame_size_kb,
        },
    )


@app.get("/frames/histogram", response_model=FrameHistogramResponse)
def frames_histogram(
    frame_idx: int = Query(0, ge=0),
    bins:      int = Query(32, ge=8, le=256),
):
    """Return grayscale intensity histogram for a single frame (recharts-ready)."""
    if _fa_last_result is None:
        raise HTTPException(status_code=404, detail="No frame analysis result available.")
    if not _fa_tmp_path or not os.path.exists(_fa_tmp_path):
        raise HTTPException(status_code=404, detail="Source video cleaned up. Re-upload.")

    r = _fa_last_result
    if frame_idx >= r.frames_analyzed:
        raise HTTPException(
            status_code=422,
            detail=f"frame_idx {frame_idx} out of range (0–{r.frames_analyzed - 1}).",
        )
    try:
        buckets = pixel_histogram(_fa_tmp_path, frame_idx, bins=bins)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return FrameHistogramResponse(frame_idx=frame_idx, buckets=buckets)

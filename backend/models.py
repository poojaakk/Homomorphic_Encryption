"""
Pydantic Request / Response Models
====================================
Centralises all API schemas so FastAPI generates accurate OpenAPI docs
and validation errors are descriptive.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Request bodies
# ------------------------------------------------------------------

class EncryptRequest(BaseModel):
    values: List[float] = Field(..., min_length=1, description="Plaintext floats to encrypt")


class ComputeRequest(BaseModel):
    operation: str = Field(..., pattern="^(add|multiply)$", description="'add' or 'multiply'")
    index_a: int = Field(-1, description="Index into encrypted_store; -1 = last")
    index_b: int = Field(-2, description="Index into encrypted_store; -2 = second-to-last")


# ------------------------------------------------------------------
# Response bodies
# ------------------------------------------------------------------

class NoiseResponse(BaseModel):
    noise: int
    threshold: int
    bootstraps: int
    noise_rate: float
    pct_used: float


class BootstrapResponse(BaseModel):
    before: int
    after: int
    bootstraps: int
    threshold: int
    label: str = "manual"


class EncryptResponse(BaseModel):
    plaintext: List[float]
    dims: int
    ciphertext_preview: str


class ComputeResponse(BaseModel):
    status: str
    operation: str
    noise_delta: int
    noise: int
    threshold: int
    bootstrap: Optional[Dict[str, Any]] = None


class DecryptResponse(BaseModel):
    result: List[float]
    store_size: int


class UploadResponse(BaseModel):
    status: str
    column_used: str
    rows: int


class StatusResponse(BaseModel):
    context_ready: bool
    kafka_producer_ready: bool
    kafka_consumer_alive: bool
    store_size: int
    noise: int
    bootstraps: int


class ContextResponse(BaseModel):
    scheme: str
    poly_modulus_degree: int
    coeff_mod_bit_sizes: Optional[List[int]] = None
    global_scale_bits: Optional[int] = None
    multiplication_depth: Optional[int] = None
    security_level_bits: Optional[int] = None
    galois_keys: Optional[bool] = None


class LogEntry(BaseModel):
    time: str
    category: str
    message: str


class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total: int


# ------------------------------------------------------------------
# Video streaming models
# ------------------------------------------------------------------

class VideoInfoModel(BaseModel):
    filename: str
    fps: float
    total_frames: int
    duration_sec: float
    width: int
    height: int


class VideoBatchResult(BaseModel):
    batch_index: int
    frame_indices: List[int]
    original: List[float]
    noisy: List[float]
    he_smoothed: List[float]
    plaintext_smoothed: List[float]
    mae: float
    mse: float
    noise_units_used: int
    bootstraps_in_batch: int = 0


class VideoNoiseSnapshot(BaseModel):
    """Per-frame noise budget snapshot for the video noise chart."""
    frame_idx:    int
    noise:        int
    threshold:    int
    pct_used:     float
    bootstrapped: bool
    bootstraps:   int


class VideoProcessResponse(BaseModel):
    """Full result returned by POST /video/process."""
    status: str
    info: VideoInfoModel
    total_frames_extracted: int
    total_batches: int
    total_bootstraps: int
    noise_std: float
    # Flattened series for charting  (one entry per frame)
    all_frame_indices: List[int]
    all_original: List[float]
    all_noisy: List[float]
    all_he_smoothed: List[float]
    all_plaintext_smoothed: List[float]
    # Per-frame noise budget history for the noise chart
    all_noise_snapshots: List[VideoNoiseSnapshot]
    # Batch-level detail
    batches: List[VideoBatchResult]
    # Aggregate validation metrics
    overall_mae_he_vs_plain: float
    overall_mse_he_vs_plain: float
    overall_mae_noisy_vs_orig: float
    overall_mse_noisy_vs_orig: float


class VideoStatusResponse(BaseModel):
    """Returned by GET /video/status."""
    ready: bool
    processing: bool
    last_filename: Optional[str] = None
    last_total_frames: Optional[int] = None
    last_batches: Optional[int] = None
    last_bootstraps: Optional[int] = None
    error: Optional[str] = None

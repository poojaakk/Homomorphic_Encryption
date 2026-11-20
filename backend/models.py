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
    source_column: Optional[str] = None
    source_row: Optional[int] = None


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


class VideoNoiseSnapshot(BaseModel):
    """Per-frame CKKS budget snapshot (crypto noise, not video grain)."""
    frame_idx:    int
    noise:        int
    threshold:    int
    pct_used:     float
    bootstrapped: bool
    bootstraps:   int
    ops: List[str] = []
    noise_generated: int = 0
    noise_reduced: int = 0
    frame_a: Optional[int] = None
    frame_b: Optional[int] = None


class VideoProcessResponse(BaseModel):
    """Streaming HE result: all frames + CKKS computation-noise history."""
    status: str
    info: VideoInfoModel
    process_width: int
    process_height: int
    frames_processed: int
    truncated: bool           # True when source had more frames than MAX_FRAMES
    fps: float
    total_bootstraps: int
    peak_noise: int
    total_noise_generated: int = 0
    total_noise_reduced: int = 0
    computation: str
    original_frames_jpeg: List[str]
    result_frames_jpeg: List[str]
    all_noise_snapshots: List[VideoNoiseSnapshot]


class VideoStatusResponse(BaseModel):
    """Returned by GET /video/status."""
    ready: bool
    processing: bool
    last_filename: Optional[str] = None
    last_total_frames: Optional[int] = None
    last_batches: Optional[int] = None
    last_bootstraps: Optional[int] = None
    error: Optional[str] = None


# ------------------------------------------------------------------
# Frame extraction / analysis models
# ------------------------------------------------------------------

class FrameStatModel(BaseModel):
    """Grayscale statistics for one extracted frame."""
    frame_idx:      int
    timestamp_s:    float
    width:          int
    height:         int
    avg_intensity:  float
    min_intensity:  int
    max_intensity:  int
    std_intensity:  float
    frame_size_kb:  float


class FrameAnalysisInfo(BaseModel):
    """Video-level metadata returned alongside frame stats."""
    filename:       str
    fps:            float
    total_frames:   int
    duration_sec:   float
    width:          int
    height:         int
    frames_analyzed: int


class FrameAnalysisResponse(BaseModel):
    """Full response for POST /frames/analyze."""
    status:         str
    info:           FrameAnalysisInfo
    stats:          List[FrameStatModel]


class FrameAnalysisStatusResponse(BaseModel):
    """Returned by GET /frames/analyze/status (live progress)."""
    analyzing:      bool
    frames_done:    int
    total_frames:   int
    pct_done:       float
    filename:       Optional[str] = None
    error:          Optional[str] = None


class FramePageResponse(BaseModel):
    """One page of frame JPEGs returned by GET /frames/page."""
    frame_idx:   int
    total_frames: int
    jpeg_b64:    str          # base64 JPEG of the requested frame
    stat:        Optional[FrameStatModel] = None


class HistogramBucket(BaseModel):
    intensity: int
    count:     int


class FrameHistogramResponse(BaseModel):
    frame_idx: int
    buckets:   List[HistogramBucket]

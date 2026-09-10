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

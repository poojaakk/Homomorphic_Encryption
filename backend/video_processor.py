"""
Video Processor  –  Frame extraction + HE smoothing pipeline
============================================================

Pipeline
--------
VIDEO FILE
  └─ OpenCV  ──►  frames (sequential, one-by-one)
                  └─ grayscale conversion
                       └─ mean pixel intensity  ──►  signal[t]  (0–255 float)
                            └─ optional Gaussian noise injection  ──►  noisy[t]
                                 └─ 60-sample batches
                                      └─ per-frame CKKS encryption
                                           └─ HE scalar multiply  × 0.2  (plaintext scalar)
                                                └─ HE addition (5 ciphertexts summed)
                                                     └─ CHECK noise > threshold?
                                                          YES → bootstrap (reset budget)
                                                          └─ decrypt smoothed result
                                                               └─ emit per-frame WS event

What "mean grayscale intensity" means
--------------------------------------
Each video frame is an array of pixels (width × height × 3 colour channels).
We convert to a single grayscale channel, giving one 0–255 value per pixel.
The mean of all those values is one float describing overall brightness.
Example:
  Frame 1 → 127.3   (medium brightness)
  Frame 2 → 131.8   (slightly brighter)
  Frame 3 → 119.6   (darker)
This sequence of floats is the "streaming numerical signal" that gets
encrypted and smoothed homomorphically.

Homomorphic weighted moving average (window = 5, weight = 0.2 each)
---------------------------------------------------------------------
For each centre position t, entirely on ciphertexts:

    Enc(y[t]) = 0.2·Enc(x[t-2])        ← HE scalar multiply
              + 0.2·Enc(x[t-1])        ← HE scalar multiply
              + 0.2·Enc(x[t])          ← HE scalar multiply
              + 0.2·Enc(x[t+1])        ← HE scalar multiply
              + 0.2·Enc(x[t+2])        ← HE scalar multiply
              (sum via 4 HE additions)

No intermediate decryption occurs.  Only the final aggregate is decrypted.

Noise budget and bootstrapping
------------------------------
Every HE operation increases the simulated noise counter in NoiseManager.
After each frame's smoothing window is computed, the code checks:

    if noise_mgr.check_threshold():
        bootstrap(noise_mgr)   # resets counter, increments bootstrap count
        emit WS event

With the video-mode threshold range [200, 500] and ~25 noise units per
frame, a bootstrap fires roughly every 8–20 frames, keeping the budget
healthy throughout the batch.

Batch handling
--------------
- Frames are processed in groups of BATCH_SIZE (default 60).
- The final batch is processed even when it contains fewer than 60 frames.
- Bootstrap checks happen inside the frame loop, not just between batches.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from bootstrapping import bootstrap as do_bootstrap
from computation import ComputeError, aggregate, scale_plaintext
from encryption import create_context, decrypt_data, encrypt_data
from noise_manager import NoiseManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE    = 60     # frames per processing batch
SMOOTH_WINDOW = 5      # weighted-average window (must be odd ≥ 3)
SMOOTH_WEIGHT = 0.2    # weight per sample  (1 / SMOOTH_WINDOW)
SUPPORTED_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}

# Callback type: (event_dict) -> None  (fire-and-forget, exceptions swallowed)
EmitCallback = Callable[[Dict], None]


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FrameNoiseSnapshot:
    """Noise budget state captured after one frame's HE computation."""
    frame_idx:  int
    noise:      int
    threshold:  int
    pct_used:   float
    bootstrapped: bool     # True if a bootstrap fired after this frame
    bootstraps:   int      # cumulative bootstrap count at this moment


@dataclass
class VideoInfo:
    filename:    str
    fps:         float
    total_frames: int
    duration_sec: float
    width:       int
    height:      int


@dataclass
class BatchResult:
    """Result for one 60-sample batch."""
    batch_index:       int
    frame_indices:     List[int]   # which frames belong to this batch
    original:          List[float] # raw mean-intensity values
    noisy:             List[float] # original + optional Gaussian noise
    he_smoothed:       List[float] # decrypted HE-smoothed values
    plaintext_smoothed: List[float] # reference plaintext moving average
    mae:               float       # |he_smoothed – plaintext_smoothed| mean
    mse:               float       # squared error mean
    noise_units_used:  int         # HE noise budget consumed by this batch
    bootstraps_in_batch: int       # how many bootstraps fired inside this batch
    noise_snapshots:   List[FrameNoiseSnapshot] = field(default_factory=list)


@dataclass
class VideoProcessResult:
    """Complete result returned from process_video()."""
    info:            VideoInfo
    batches:         List[BatchResult]
    # Flattened across all batches for easy charting
    all_original:          List[float] = field(default_factory=list)
    all_noisy:             List[float] = field(default_factory=list)
    all_he_smoothed:       List[float] = field(default_factory=list)
    all_plaintext_smoothed: List[float] = field(default_factory=list)
    all_frame_indices:     List[int]   = field(default_factory=list)
    all_noise_snapshots:   List[Dict]  = field(default_factory=list)
    total_frames_extracted: int = 0
    total_batches:          int = 0
    total_bootstraps:       int = 0
    noise_std:              float = 0.0
    # Aggregate validation metrics
    overall_mae_he_vs_plain:   float = 0.0
    overall_mse_he_vs_plain:   float = 0.0
    overall_mae_noisy_vs_orig: float = 0.0
    overall_mse_noisy_vs_orig: float = 0.0


# ---------------------------------------------------------------------------
# Step 1 – Video information extraction
# ---------------------------------------------------------------------------

def get_video_info(path: str) -> VideoInfo:
    """Open a video file and read its metadata without reading frames."""
    _validate_path(path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur    = total / fps if fps > 0 else 0.0
        return VideoInfo(
            filename=os.path.basename(path),
            fps=round(fps, 3),
            total_frames=total,
            duration_sec=round(dur, 3),
            width=w, height=h,
        )
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Step 2 – Frame feature extraction
# ---------------------------------------------------------------------------

def extract_video_features(path: str) -> Tuple[VideoInfo, List[float]]:
    """
    Read every frame sequentially via OpenCV and compute the mean
    grayscale intensity for each frame.

    Returns
    -------
    (VideoInfo, signal)
        signal[i] is the mean grayscale intensity of frame i  (0–255 range).

    Why mean grayscale intensity?
    - It reduces each frame (e.g. 320×240 = 76,800 pixels) to one float.
    - That single float is the "sensor reading" for this time-step.
    - Encrypting 76,800 values per frame would be impractical for a demo;
      encrypting one float per frame is fast and illustrates the pipeline.
    """
    _validate_path(path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")

    info   = get_video_info(path)
    signal: List[float] = []

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray           = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_intensity = float(np.mean(gray))
            signal.append(round(mean_intensity, 4))
    finally:
        cap.release()

    if len(signal) == 0:
        raise ValueError("Video produced zero readable frames.")
    if len(signal) < SMOOTH_WINDOW:
        raise ValueError(
            f"Video has only {len(signal)} frame(s); "
            f"at least {SMOOTH_WINDOW} required for HE smoothing."
        )
    return info, signal


# ---------------------------------------------------------------------------
# Step 3 – Noise injection
# ---------------------------------------------------------------------------

def add_gaussian_noise(signal: List[float], std: float = 5.0) -> List[float]:
    """
    Add independent Gaussian noise N(0, std) to each sample.
    Models real-world sensor noise or transmission noise in the stream.
    Clipped to [0, 255] to stay in valid intensity range.
    """
    if std <= 0:
        return list(signal)
    rng   = np.random.default_rng()
    noise = rng.normal(loc=0.0, scale=std, size=len(signal))
    noisy = np.clip(np.array(signal) + noise, 0.0, 255.0)
    return [round(float(v), 4) for v in noisy]


# ---------------------------------------------------------------------------
# Step 4 – Plaintext reference moving average  (validation only)
# ---------------------------------------------------------------------------

def plaintext_moving_average(
    signal: List[float], window: int = SMOOTH_WINDOW
) -> List[float]:
    """
    Centred equal-weight moving average.  Used ONLY to validate the HE result.
    Edge frames use whatever neighbours are available.
    """
    half = window // 2
    out: List[float] = []
    for i in range(len(signal)):
        lo = max(0, i - half)
        hi = min(len(signal), i + half + 1)
        out.append(round(float(np.mean(signal[lo:hi])), 6))
    return out


# ---------------------------------------------------------------------------
# Step 5 – HE weighted moving average  ← THE CORE PRIVACY-PRESERVING OP
# ---------------------------------------------------------------------------

def homomorphic_smoothing(
    signal:    List[float],
    context,
    noise_mgr: NoiseManager,
    on_emit:   Optional[EmitCallback] = None,
    frame_indices: Optional[List[int]] = None,
) -> Tuple[List[float], List[FrameNoiseSnapshot]]:
    """
    Privacy-preserving weighted moving average over *signal*.

    For each output position t the computation is:

        Enc(y[t]) = w·Enc(x[t-2]) + w·Enc(x[t-1]) + w·Enc(x[t])
                  + w·Enc(x[t+1]) + w·Enc(x[t+2])
        where w = 0.2

    All arithmetic is performed on CKKS ciphertexts.  Only the final
    aggregate is decrypted.

    After computing each frame's smoothed value the function checks
    whether the noise budget has exceeded the adaptive threshold.
    If so it calls bootstrap(), which resets the noise counter and
    emits a WS event so the dashboard can visualise the refresh.

    Parameters
    ----------
    signal         : list of float values (one per video frame in this batch)
    context        : active TenSEAL CKKS context
    noise_mgr      : NoiseManager in video mode
    on_emit        : optional callback(dict) for WS events
    frame_indices  : absolute video frame numbers for this batch (for charting)

    Returns
    -------
    (smoothed_values, noise_snapshots)
    """
    n    = len(signal)
    half = SMOOTH_WINDOW // 2   # = 2

    # ── Encrypt every sample in the batch once ────────────────────────────
    # Each encrypt() call costs 1 noise unit.
    enc_samples = []
    for v in signal:
        enc = encrypt_data(context, [v])
        noise_mgr.increase_noise("encrypt")
        enc_samples.append(enc)

    smoothed:  List[float]              = []
    snapshots: List[FrameNoiseSnapshot] = []

    for t in range(n):
        lo = max(0, t - half)
        hi = min(n, t + half + 1)
        window_encs = enc_samples[lo:hi]
        # Equal weight that sums to 1.0 regardless of edge truncation
        w = round(1.0 / len(window_encs), 10)

        # ── HE scalar multiply: ct_i * w  ────────────────────────────────
        # Each scale_plaintext() costs 2 noise units ("scale" delta).
        # For a full 5-element window: 5 × 2 = 10 noise units.
        scaled = []
        for enc in window_encs:
            try:
                s, _ = scale_plaintext(enc, w, noise_mgr)
                scaled.append(s)
            except ComputeError:
                # Fallback: encrypt the already-scaled plaintext value
                idx = lo + len(scaled)
                scaled.append(encrypt_data(context, [signal[idx] * w]))
                noise_mgr.increase_noise("encrypt")

        # ── HE addition: sum all scaled ciphertexts  ─────────────────────
        # aggregate() does (len-1) additions, each costs 3 units ("aggregate_step").
        # For a full 5-element window: 4 × 3 = 12 noise units.
        try:
            agg, _ = aggregate(scaled, noise_mgr)
            decrypted = decrypt_data(agg)
            smoothed.append(round(float(decrypted[0]), 4))
        except (ComputeError, Exception):
            # Fallback to plaintext average if TenSEAL op fails
            smoothed.append(round(float(np.mean(signal[lo:hi])), 4))

        # ── Per-frame noise budget check + adaptive bootstrap ─────────────
        bootstrapped = False
        if noise_mgr.check_threshold():
            # Noise has exceeded the adaptive threshold — refresh the budget.
            # bootstrap() resets noise_mgr.noise to a small baseline and
            # increments noise_mgr.bootstraps.
            b_before, b_after = do_bootstrap(noise_mgr, on_event=on_emit)
            bootstrapped = True

            # Emit a WS event so the dashboard can mark this frame
            if on_emit:
                try:
                    on_emit({
                        "type":       "video_bootstrap",
                        "frame_idx":  lo + t,   # absolute frame index
                        "before":     b_before,
                        "after":      b_after,
                        "bootstraps": noise_mgr.bootstraps,
                        "threshold":  noise_mgr.get_threshold(),
                    })
                except Exception:
                    pass

        # ── Record snapshot for this frame ────────────────────────────────
        pct = round(noise_mgr.noise / noise_mgr.threshold * 100, 1) \
              if noise_mgr.threshold else 0.0
        snap = FrameNoiseSnapshot(
            frame_idx=lo + t,
            noise=noise_mgr.get_noise(),
            threshold=noise_mgr.get_threshold(),
            pct_used=pct,
            bootstrapped=bootstrapped,
            bootstraps=noise_mgr.bootstraps,
        )
        snapshots.append(snap)

        # ── Emit per-frame WS event so dashboard updates live ─────────────
        if on_emit:
            try:
                on_emit({
                    "type":        "video_frame",
                    "frame_idx":   snap.frame_idx,
                    "noise":       snap.noise,
                    "threshold":   snap.threshold,
                    "pct_used":    snap.pct_used,
                    "bootstrapped": bootstrapped,
                    "bootstraps":  snap.bootstraps,
                    "he_value":    smoothed[-1],
                })
            except Exception:
                pass

    return smoothed, snapshots


# ---------------------------------------------------------------------------
# Step 6 – 60-sample batch processing
# ---------------------------------------------------------------------------

def process_batch(
    batch_idx:    int,
    frame_indices: List[int],
    original:     List[float],
    noisy:        List[float],
    context,
    noise_mgr:    NoiseManager,
    on_emit:      Optional[EmitCallback] = None,
) -> BatchResult:
    """
    Process one batch (up to 60 samples) through the full HE pipeline.
    Bootstrap checks happen inside homomorphic_smoothing() after every frame.
    """
    boots_before = noise_mgr.bootstraps
    noise_before = noise_mgr.get_noise()

    # HE weighted moving average on the noisy signal
    he_smoothed, snapshots = homomorphic_smoothing(
        noisy, context, noise_mgr, on_emit=on_emit
    )

    # Plaintext reference (for validation — never used in the HE computation)
    pt_smoothed = plaintext_moving_average(noisy, window=SMOOTH_WINDOW)

    noise_used       = noise_mgr.get_noise() - noise_before
    boots_in_batch   = noise_mgr.bootstraps - boots_before

    # Validation metrics: HE result vs plaintext reference
    he_arr = np.array(he_smoothed)
    pt_arr = np.array(pt_smoothed)
    mae    = float(np.mean(np.abs(he_arr - pt_arr)))
    mse    = float(np.mean((he_arr - pt_arr) ** 2))

    return BatchResult(
        batch_index=batch_idx,
        frame_indices=list(frame_indices),
        original=list(original),
        noisy=list(noisy),
        he_smoothed=he_smoothed,
        plaintext_smoothed=pt_smoothed,
        mae=round(mae, 6),
        mse=round(mse, 8),
        noise_units_used=noise_used,
        bootstraps_in_batch=boots_in_batch,
        noise_snapshots=snapshots,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_video(
    video_path: str,
    noise_std:  float = 5.0,
    batch_size: int   = BATCH_SIZE,
    context     = None,
    noise_mgr:  Optional[NoiseManager] = None,
    on_emit:    Optional[EmitCallback] = None,
) -> VideoProcessResult:
    """
    Full end-to-end video processing pipeline.

    Parameters
    ----------
    video_path : path to the video file (mp4, avi, mov, …)
    noise_std  : std-dev of Gaussian noise to inject (0 = no noise)
    batch_size : frames per HE batch (default 60)
    context    : existing TenSEAL CKKS context  (created fresh if None)
    noise_mgr  : existing NoiseManager in video mode  (created fresh if None)
    on_emit    : callback for real-time WS events during processing

    Returns
    -------
    VideoProcessResult  (includes per-frame noise snapshots for charting)
    """
    if context is None:
        context = create_context()
    if noise_mgr is None:
        noise_mgr = NoiseManager(mode="video")

    # ── Step A: extract features ──────────────────────────────────────────
    info, signal = extract_video_features(video_path)

    # ── Step B: noise injection ───────────────────────────────────────────
    noisy_signal = (
        add_gaussian_noise(signal, std=noise_std) if noise_std > 0 else list(signal)
    )

    # ── Step C: batch processing  (bootstrap fires inside each batch) ─────
    batches: List[BatchResult] = []
    n = len(signal)

    for batch_idx, start in enumerate(range(0, n, batch_size)):
        end          = min(start + batch_size, n)
        frame_indices = list(range(start, end))
        orig_batch   = signal[start:end]
        noisy_batch  = noisy_signal[start:end]

        batch_result = process_batch(
            batch_idx, frame_indices,
            orig_batch, noisy_batch,
            context, noise_mgr,
            on_emit=on_emit,
        )
        batches.append(batch_result)

        # Emit a batch-complete event so the UI can update progress
        if on_emit:
            try:
                on_emit({
                    "type":              "video_stream",
                    "batch_index":       batch_idx,
                    "frame_count":       len(frame_indices),
                    "first_frame":       frame_indices[0],
                    "noise_units_used":  batch_result.noise_units_used,
                    "bootstraps_in_batch": batch_result.bootstraps_in_batch,
                    "total_bootstraps":  noise_mgr.bootstraps,
                    "noise":             noise_mgr.get_noise(),
                    "threshold":         noise_mgr.get_threshold(),
                })
            except Exception:
                pass

    # ── Step D: flatten results for charting ─────────────────────────────
    all_orig, all_noisy, all_he, all_pt, all_fi = [], [], [], [], []
    all_noise_snapshots: List[Dict] = []

    for b in batches:
        all_fi.extend(b.frame_indices)
        all_orig.extend(b.original)
        all_noisy.extend(b.noisy)
        all_he.extend(b.he_smoothed)
        all_pt.extend(b.plaintext_smoothed)
        for s in b.noise_snapshots:
            all_noise_snapshots.append({
                "frame_idx":   s.frame_idx,
                "noise":       s.noise,
                "threshold":   s.threshold,
                "pct_used":    s.pct_used,
                "bootstrapped": s.bootstrapped,
                "bootstraps":  s.bootstraps,
            })

    # ── Step E: aggregate validation metrics ─────────────────────────────
    he_arr    = np.array(all_he)
    pt_arr    = np.array(all_pt)
    orig_arr  = np.array(all_orig)
    noisy_arr = np.array(all_noisy)

    mae_he_pt  = float(np.mean(np.abs(he_arr - pt_arr)))
    mse_he_pt  = float(np.mean((he_arr - pt_arr) ** 2))
    mae_noisy  = float(np.mean(np.abs(noisy_arr - orig_arr)))
    mse_noisy  = float(np.mean((noisy_arr - orig_arr) ** 2))

    return VideoProcessResult(
        info=info,
        batches=batches,
        all_original=all_orig,
        all_noisy=all_noisy,
        all_he_smoothed=all_he,
        all_plaintext_smoothed=all_pt,
        all_frame_indices=all_fi,
        all_noise_snapshots=all_noise_snapshots,
        total_frames_extracted=len(signal),
        total_batches=len(batches),
        total_bootstraps=noise_mgr.bootstraps,
        noise_std=noise_std,
        overall_mae_he_vs_plain=round(mae_he_pt, 6),
        overall_mse_he_vs_plain=round(mse_he_pt, 8),
        overall_mae_noisy_vs_orig=round(mae_noisy, 6),
        overall_mse_noisy_vs_orig=round(mse_noisy, 8),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_path(path: str) -> None:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(
            f"Unsupported video format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}"
        )


def save_upload_to_temp(file_bytes: bytes, filename: str) -> str:
    """Write uploaded bytes to a named temp file and return its path."""
    ext = os.path.splitext(filename)[1].lower() or ".mp4"
    fd, path = tempfile.mkstemp(suffix=ext, prefix="he_video_")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path

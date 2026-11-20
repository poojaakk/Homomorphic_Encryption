"""
Frame Analyzer
==============
Extracts every frame from a video file, computes per-frame grayscale
statistics, and stores them in a compact in-memory list.

Design goals
------------
- Never hold more than ONE decoded full-resolution frame in RAM at a time.
  After computing stats the frame is immediately discarded.
- Keep a 192×108 (or smaller) JPEG thumbnail for the viewer; these are
  generated on demand via get_frame_jpeg() so the HTTP response can page
  through frames without loading everything at once.
- All stats (avg, min, max, std, timestamp) are stored as plain Python
  floats/ints — roughly 60 bytes per frame → 2000 frames ≈ 120 KB.

Public API
----------
  analyze_video(path, on_progress) -> FrameAnalysisResult
  get_frame_jpeg(path, frame_idx, width, height) -> str   # base64 JPEG
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np

THUMB_W = 320          # thumbnail width stored for the viewer
THUMB_H = 180          # thumbnail height
JPEG_Q  = 65           # JPEG quality for thumbnails
VIEWER_JPEG_Q = 75     # higher quality for the per-frame viewer endpoint

ProgressCallback = Callable[[int, int], None]   # (frames_done, total)


@dataclass
class FrameStat:
    """Grayscale statistics for one extracted frame."""
    frame_idx:   int
    timestamp_s: float          # presentation timestamp in seconds
    width:       int            # source frame width
    height:      int            # source frame height
    avg_intensity:  float       # mean grayscale value (0–255)
    min_intensity:  int         # minimum pixel value
    max_intensity:  int         # maximum pixel value
    std_intensity:  float       # standard deviation of pixel values
    frame_size_kb:  float       # uncompressed grayscale frame size in KB


@dataclass
class FrameAnalysisResult:
    filename:       str
    fps:            float
    total_frames:   int
    duration_sec:   float
    width:          int
    height:         int
    frames_analyzed: int
    stats: List[FrameStat] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def analyze_video(
    path: str,
    on_progress: Optional[ProgressCallback] = None,
) -> FrameAnalysisResult:
    """
    Iterate through every frame of *path*, compute grayscale stats, and
    return a FrameAnalysisResult.  At most one decoded frame is in RAM at
    any time.

    *on_progress* is called after every frame with (frames_done, total).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Video not found: {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")

    try:
        fps         = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total       = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        src_w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration    = total / fps if fps > 0 else 0.0
        filename    = os.path.basename(path)

        stats: List[FrameStat] = []
        idx = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Grayscale for stats — shape (H, W) uint8
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            avg = float(np.mean(gray))
            mn  = int(gray.min())
            mx  = int(gray.max())
            std = float(np.std(gray))
            ts  = idx / fps if fps > 0 else 0.0
            # Uncompressed grayscale frame size
            size_kb = (src_w * src_h) / 1024.0

            stats.append(FrameStat(
                frame_idx    = idx,
                timestamp_s  = round(ts, 4),
                width        = src_w,
                height       = src_h,
                avg_intensity   = round(avg, 3),
                min_intensity   = mn,
                max_intensity   = mx,
                std_intensity   = round(std, 3),
                frame_size_kb   = round(size_kb, 2),
            ))

            # Immediately release the frame from RAM
            del gray, frame

            idx += 1
            if on_progress:
                on_progress(idx, total if total > 0 else idx)

    finally:
        cap.release()

    if not stats:
        raise ValueError("Video produced zero readable frames.")

    return FrameAnalysisResult(
        filename        = filename,
        fps             = round(fps, 3),
        total_frames    = total,
        duration_sec    = round(duration, 3),
        width           = src_w,
        height          = src_h,
        frames_analyzed = len(stats),
        stats           = stats,
    )


def get_frame_jpeg(
    path: str,
    frame_idx: int,
    width: int  = THUMB_W,
    height: int = THUMB_H,
) -> str:
    """
    Seek to *frame_idx* in *path*, decode it, resize to *width*×*height*,
    and return a base64-encoded JPEG string.  Only one frame is decoded.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Video not found: {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Cannot read frame {frame_idx}")
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        ok2, buf = cv2.imencode(
            ".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), VIEWER_JPEG_Q]
        )
        if not ok2:
            raise ValueError("JPEG encode failed")
        return base64.b64encode(buf.tobytes()).decode("ascii")
    finally:
        cap.release()


def pixel_histogram(
    path: str,
    frame_idx: int,
    bins: int = 32,
) -> List[Dict]:
    """
    Return grayscale histogram data for *frame_idx* as a list of dicts
    ``{"intensity": int, "count": int}`` suitable for recharts.
    *bins* controls how many buckets are used (default 32 → groups of 8).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Video not found: {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Cannot read frame {frame_idx}")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist, edges = np.histogram(gray.ravel(), bins=bins, range=(0, 256))
        result = []
        for i, count in enumerate(hist):
            result.append({
                "intensity": int(round(edges[i])),
                "count": int(count),
            })
        return result
    finally:
        cap.release()

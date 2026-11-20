"""
Video Processor streaming HE computations + CKKS noise
==========================================================

Noise here is ciphertext noise created by HE operations as frames stream
(encrypt, add last two, scale) — the same budget as CSV mode.  It is
reduced by bootstrapping when the adaptive threshold is crossed.

No Gaussian (or any other) noise is added to the video.  Pixel grain is
not the thing being reduced.

Per sampled frame t (up to MAX_FRAMES from the full video):
  Enc(x[t])
  if t > 0:  y[t] = 0.5 · (Enc(x[t-1]) + Enc(x[t]))   # CSV add + scale
  else:      y[t] = Enc(x[t])
  if noise ≥ threshold: bootstrap (reset CKKS budget)
  decrypt y[t] for playback

The graph that matters is CKKS noise vs frame (sawtooth = bootstrap).

Large-video support
-------------------
  MAX_FRAMES = 2000  — if the video has more frames, we sample them
  uniformly so processing always works through exactly this many frames.
  VideoProcessResult.truncated is True when sampling occurred.
  Frames are streamed one at a time from disk (no full in-memory list)
  to keep RAM use proportional to GRID size, not to source resolution.
"""

from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np

from bootstrapping import bootstrap as do_bootstrap
from computation import ComputeError, add, scale_plaintext
from encryption import decrypt_data, encrypt_data
from noise_manager import NoiseManager

GRID = 32
DISPLAY_SIZE = 192
JPEG_QUALITY = 55
MAX_FRAMES = 2000          # hard cap — sample uniformly above this
SUPPORTED_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}

EmitCallback = Callable[[Dict], None]


@dataclass
class VideoInfo:
    filename: str
    fps: float
    total_frames: int
    duration_sec: float
    width: int
    height: int


@dataclass
class VideoProcessResult:
    info: VideoInfo
    frames_processed: int
    process_width: int
    process_height: int
    fps: float
    truncated: bool
    total_bootstraps: int
    original_frames_jpeg: List[str] = field(default_factory=list)
    result_frames_jpeg: List[str] = field(default_factory=list)
    all_noise_snapshots: List[Dict] = field(default_factory=list)
    peak_noise: int = 0
    total_noise_generated: int = 0
    total_noise_reduced: int = 0
    computation: str = (
        "Per frame t: encrypt luma of frame t; if t>0 add Enc(t-1)+Enc(t) and scale by 0.5. "
        "Threshold 50: bootstrap resets CKKS noise."
    )


def get_video_info(path: str) -> VideoInfo:
    _validate_path(path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur = total / fps if fps > 0 else 0.0
        return VideoInfo(
            filename=os.path.basename(path),
            fps=round(fps, 3),
            total_frames=total,
            duration_sec=round(dur, 3),
            width=w,
            height=h,
        )
    finally:
        cap.release()


def _sample_indices(total: int, max_frames: int) -> List[int]:
    """
    Return a sorted list of frame indices to process.
    If total <= max_frames, every frame is included.
    Otherwise, spread max_frames indices uniformly across [0, total).
    """
    if total <= max_frames:
        return list(range(total))
    # Uniform spacing — include the first and last frame
    step = (total - 1) / (max_frames - 1)
    return sorted(set(round(i * step) for i in range(max_frames)))


def _stream_sampled_frames(
    path: str, indices: List[int]
) -> Generator[Tuple[int, np.ndarray], None, None]:
    """
    Yield (original_frame_index, bgr_frame) for each index in *indices*.
    Frames are read one at a time; only the current frame is held in RAM.
    Uses cv2.CAP_PROP_POS_FRAMES to seek efficiently.
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        idx_set = set(indices)
        idx_iter = iter(sorted(indices))
        next_target = next(idx_iter, None)
        current_pos = 0

        while next_target is not None:
            # Seek if we need to jump forward more than 1 frame
            if next_target != current_pos:
                cap.set(cv2.CAP_PROP_POS_FRAMES, next_target)
                current_pos = next_target

            ok, frame = cap.read()
            if not ok:
                break
            yield next_target, frame
            current_pos = next_target + 1
            next_target = next(idx_iter, None)
    finally:
        cap.release()


def _luma_vec(frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    small = cv2.resize(frame, (GRID, GRID), interpolation=cv2.INTER_AREA)
    ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    return y.astype(np.float64).ravel(), cr, cb


def _jpeg_b64(frame_bgr: np.ndarray) -> str:
    display = cv2.resize(
        frame_bgr, (DISPLAY_SIZE, DISPLAY_SIZE), interpolation=cv2.INTER_LINEAR
    )
    ok, buf = cv2.imencode(".jpg", display, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        raise ValueError("Failed to encode frame as JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _vec_to_bgr(vec: np.ndarray, cr: np.ndarray, cb: np.ndarray) -> np.ndarray:
    y = np.clip(np.round(vec[: GRID * GRID]), 0, 255).astype(np.uint8).reshape(GRID, GRID)
    return cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2BGR)


def _snapshot(
    idx: int,
    noise_mgr: NoiseManager,
    bootstrapped: bool,
    *,
    ops: List[str],
    noise_generated: int,
    noise_reduced: int,
    frame_a: Optional[int],
    frame_b: Optional[int],
) -> Dict:
    pct = (
        round(noise_mgr.noise / noise_mgr.threshold * 100, 1)
        if noise_mgr.threshold
        else 0.0
    )
    return {
        "frame_idx": idx,
        "noise": noise_mgr.get_noise(),
        "threshold": noise_mgr.get_threshold(),
        "pct_used": pct,
        "bootstrapped": bootstrapped,
        "bootstraps": noise_mgr.bootstraps,
        "ops": ops,
        "noise_generated": noise_generated,
        "noise_reduced": noise_reduced,
        "frame_a": frame_a,
        "frame_b": frame_b,
    }


def process_video(
    video_path: str,
    noise_std: float = 0.0,
    batch_size: int = 0,
    context=None,
    noise_mgr: Optional[NoiseManager] = None,
    on_emit: Optional[EmitCallback] = None,
    max_frames: int = MAX_FRAMES,
    threshold: Optional[int] = None,
) -> VideoProcessResult:
    del noise_std, batch_size
    if context is None:
        from encryption import create_context
        context = create_context()
    if noise_mgr is None:
        noise_mgr = NoiseManager(mode="video", custom_threshold=threshold)

    info = get_video_info(video_path)
    total_source_frames = info.total_frames

    # Determine which frames to process (uniform sample if above cap)
    indices = _sample_indices(total_source_frames, max_frames)
    truncated = len(indices) < total_source_frames

    actual_threshold = noise_mgr.get_threshold()

    # Update computation description to reflect sampling and threshold
    sample_note = (
        f" Sampled {len(indices)} of {total_source_frames} source frames uniformly."
        if truncated else ""
    )
    computation = (
        "Per frame t: encrypt luma of frame t; if t>0 add Enc(t-1)+Enc(t) and scale by 0.5. "
        f"Threshold {actual_threshold}: bootstrap resets CKKS noise.{sample_note}"
    )

    snapshots: List[Dict] = []
    orig_jpegs: List[str] = []
    result_jpegs: List[str] = []
    prev_enc = None
    peak = 0
    total_generated = 0
    total_reduced = 0

    # Stream frames one at a time — no full-resolution list in RAM
    for seq_idx, (src_frame_idx, frame) in enumerate(
        _stream_sampled_frames(video_path, indices)
    ):
        y_vec, cr, cb = _luma_vec(frame)
        orig_jpegs.append(
            _jpeg_b64(cv2.resize(frame, (GRID, GRID), interpolation=cv2.INTER_AREA))
        )

        noise_before = noise_mgr.get_noise()
        ops: List[str] = []
        frame_a: Optional[int] = seq_idx          # sequential index (0-based in processed set)
        frame_b: Optional[int] = None

        enc = encrypt_data(context, y_vec.tolist())
        noise_mgr.increase_noise("encrypt")
        noise_mgr.increase_noise("stream")
        ops.append(f"encrypt luma of frame {seq_idx} (source #{src_frame_idx})")

        try:
            if prev_enc is None:
                out_enc = enc
                ops.append("no add (first frame / after bootstrap)")
            else:
                frame_b = seq_idx - 1
                summed, _ = add(enc, prev_enc, noise_mgr)
                out_enc, _ = scale_plaintext(summed, 0.5, noise_mgr)
                ops.append(f"add Enc(frame {seq_idx}) + Enc(frame {seq_idx - 1})")
                ops.append("scale result × 0.5")
            raw = np.array(decrypt_data(out_enc), dtype=np.float64)
        except ComputeError:
            raw = y_vec
            ops.append("HE op failed — used plaintext luma")

        generated = noise_mgr.get_noise() - noise_before
        total_generated += max(0, generated)

        prev_enc = enc
        result_jpegs.append(_jpeg_b64(_vec_to_bgr(raw, cr, cb)))

        bootstrapped = False
        boot_before = boot_after = None
        reduced = 0
        if noise_mgr.check_threshold():
            boot_before, boot_after = do_bootstrap(noise_mgr, on_event=on_emit)
            bootstrapped = True
            reduced = max(0, (boot_before or 0) - (boot_after or 0))
            total_reduced += reduced
            ops.append(f"bootstrap (noise {boot_before} → {boot_after})")
            prev_enc = None

        peak = max(peak, noise_before + max(0, generated))
        snap = _snapshot(
            seq_idx,
            noise_mgr,
            bootstrapped,
            ops=ops,
            noise_generated=max(0, generated),
            noise_reduced=reduced,
            frame_a=frame_a,
            frame_b=frame_b,
        )
        snapshots.append(snap)

        if on_emit:
            try:
                on_emit({"type": "video_frame", **snap})
                if bootstrapped:
                    on_emit({
                        "type": "video_bootstrap",
                        "frame_idx": seq_idx,
                        "bootstraps": noise_mgr.bootstraps,
                        "threshold": noise_mgr.get_threshold(),
                        "before": boot_before,
                        "after": boot_after,
                    })
            except Exception:
                pass

    frames_processed = len(snapshots)

    if on_emit:
        try:
            on_emit({
                "type": "video_stream",
                "batch_index": 0,
                "frame_count": frames_processed,
                "bootstraps_in_batch": noise_mgr.bootstraps,
                "noise_units_used": peak,
            })
        except Exception:
            pass

    return VideoProcessResult(
        info=info,
        frames_processed=frames_processed,
        process_width=GRID,
        process_height=GRID,
        fps=info.fps or 25.0,
        truncated=truncated,
        total_bootstraps=noise_mgr.bootstraps,
        original_frames_jpeg=orig_jpegs,
        result_frames_jpeg=result_jpegs,
        all_noise_snapshots=snapshots,
        peak_noise=peak,
        total_noise_generated=total_generated,
        total_noise_reduced=total_reduced,
        computation=computation,
    )


def save_upload_to_temp(file_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower() or ".mp4"
    fd, path = tempfile.mkstemp(suffix=ext, prefix="he_video_")
    os.close(fd)
    with open(path, "wb") as fh:
        fh.write(file_bytes)
    return path


def _validate_path(path: str) -> None:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(
            f"Unsupported video format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}"
        )

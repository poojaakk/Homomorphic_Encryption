"""
Adaptive Noise Manager
======================
Tracks ciphertext noise budget across homomorphic operations and adapts
the bootstrap threshold dynamically based on the observed noise growth rate.

Noise model (simulated, not from TenSEAL internals):
  - Each HE operation adds a random delta drawn from a per-op range.
  - The adaptive threshold shrinks when the rate of noise growth is high,
    triggering bootstrapping sooner to keep the budget safe.
  - History is kept in a bounded ring-buffer so the UI can chart it.

Two operating modes
-------------------
  "csv"   : low-volume static dataset. Threshold range 50–80 is appropriate.

  "video" : per-frame CKKS ops (encrypt + optional add/scale + stream).
            Bootstrap threshold is pinned at 50.
"""

from __future__ import annotations

import random
import time
from collections import deque
from typing import Deque, Dict, List, Literal, Optional, Tuple

# How many historical data-points we keep for rate calculation and UI charting.
_HISTORY_CAPACITY = 2000  # enough for a full 2000-frame video run

# Inclusive random ranges per operation. These are simulated budget units,
# not a real CKKS noise formula — previously they were fixed constants, which
# made every video frame grow by exactly +7 (encrypt 1 + stream 2 + add 2 + scale/add 2).
NOISE_RANGES: Dict[str, Tuple[int, int]] = {
    "encrypt":        (1, 4),
    "add":            (1, 5),
    "multiply":       (8, 16),
    "stream":         (1, 4),
    "aggregate_step": (2, 6),
    "scale":          (1, 5),
}
_DEFAULT_RANGE: Tuple[int, int] = (1, 4)

# ── Adaptive parameters per mode ──────────────────────────────────────────
#
#  CSV mode  – small operations, threshold in [50, 80]
_CSV_BASE_THRESHOLD  = 50
_CSV_MIN_THRESHOLD   = 20
_CSV_MAX_THRESHOLD   = 80
#
#  Video mode – bootstrap when CKKS noise exceeds 50.
_VIDEO_BASE_THRESHOLD = 50
_VIDEO_MIN_THRESHOLD  = 50
_VIDEO_MAX_THRESHOLD  = 50

# Shared adaptive knobs
_RATE_WINDOW_SEC = 10.0   # seconds over which growth rate is calculated
_RATE_HIGH_MARK  = 50.0   # noise-units/sec — "high growth" for video
_RATE_LOW_MARK   = 5.0    # noise-units/sec — "low growth" for video
_THRESHOLD_STEP  = 25     # how much we nudge the threshold each adaptation


class NoiseManager:
    """
    Maintains the noise budget and adapts the bootstrap threshold.

    Parameters
    ----------
    mode : "csv" | "video"
        Controls which threshold range is used.  Defaults to "csv" so the
        existing static pipeline is completely unchanged.

    Attributes
    ----------
    noise       : current noise budget counter
    threshold   : current adaptive bootstrap threshold
    bootstraps  : number of bootstraps performed so far
    history     : bounded list of ``{t, noise, threshold, bootstraps}`` snapshots
    """

    def __init__(self, mode: Literal["csv", "video"] = "csv", custom_threshold: Optional[int] = None) -> None:
        self.mode      = mode
        self.noise: int = 0
        self.bootstraps: int = 0

        # Set initial threshold from mode, then override if caller supplied one
        if mode == "video":
            self.threshold: int = _VIDEO_BASE_THRESHOLD
            self._min_threshold  = _VIDEO_MIN_THRESHOLD
            self._max_threshold  = _VIDEO_MAX_THRESHOLD
        else:
            self.threshold = _CSV_BASE_THRESHOLD
            self._min_threshold = _CSV_MIN_THRESHOLD
            self._max_threshold = _CSV_MAX_THRESHOLD

        # Pin to user-supplied threshold — both min and max locked to same value
        # so the adaptive logic cannot drift away from the user's choice.
        if custom_threshold is not None:
            t = max(1, int(custom_threshold))
            self.threshold      = t
            self._min_threshold = t
            self._max_threshold = t

        # Ring-buffer of (timestamp_float, noise_int) for rate calculation.
        self._rate_buf: Deque[tuple[float, int]] = deque(maxlen=100)

        # Full history snapshot list for UI charting (bounded).
        self._history: Deque[Dict] = deque(maxlen=_HISTORY_CAPACITY)
        self._record_snapshot()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def increase_noise(self, operation: str = "stream") -> int:
        """
        Increase noise by the delta for *operation*.
        Returns the delta that was applied.
        """
        lo, hi = NOISE_RANGES.get(operation, _DEFAULT_RANGE)
        delta = random.randint(lo, hi)
        self.noise += delta
        now = time.monotonic()
        self._rate_buf.append((now, self.noise))
        self._adapt_threshold()
        self._record_snapshot()
        return delta

    def get_noise(self) -> int:
        return self.noise

    def get_threshold(self) -> int:
        return self.threshold

    def check_threshold(self) -> bool:
        """Return True when the current noise exceeds the adaptive threshold."""
        return self.noise > self.threshold

    def reset_noise(self) -> None:
        """Simulate a bootstrapping refresh: reset budget, keep small baseline."""
        self.noise = max(10, self.threshold // 10)  # small residual after refresh
        self.bootstraps += 1
        self._record_snapshot()

    def get_history(self) -> List[Dict]:
        return list(self._history)

    def noise_rate(self) -> float:
        """
        Estimated noise-units / second over the last ``_RATE_WINDOW_SEC``
        seconds.  Returns 0.0 if there is not enough data.
        """
        now = time.monotonic()
        cutoff = now - _RATE_WINDOW_SEC
        window = [(t, n) for t, n in self._rate_buf if t >= cutoff]
        if len(window) < 2:
            return 0.0
        elapsed = window[-1][0] - window[0][0]
        if elapsed <= 0:
            return 0.0
        noise_gained = window[-1][1] - window[0][1]
        return max(0.0, noise_gained / elapsed)

    def summary(self) -> Dict:
        """Return a JSON-serialisable snapshot for API responses."""
        return {
            "noise":      self.noise,
            "threshold":  self.threshold,
            "bootstraps": self.bootstraps,
            "noise_rate": round(self.noise_rate(), 3),
            "pct_used":   round(self.noise / self.threshold * 100, 1)
                          if self.threshold else 0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adapt_threshold(self) -> None:
        """
        Nudge the adaptive threshold based on the current noise growth rate.
        High rate → lower threshold (bootstrap sooner).
        Low rate  → raise threshold (allow more headroom).
        """
        rate = self.noise_rate()
        if rate >= _RATE_HIGH_MARK:
            self.threshold = max(
                self._min_threshold, self.threshold - _THRESHOLD_STEP
            )
        elif rate <= _RATE_LOW_MARK and self.threshold < self._max_threshold:
            self.threshold = min(
                self._max_threshold, self.threshold + _THRESHOLD_STEP
            )

    def _record_snapshot(self) -> None:
        self._history.append(
            {
                "t":          len(self._history),
                "noise":      self.noise,
                "threshold":  self.threshold,
                "bootstraps": self.bootstraps,
            }
        )

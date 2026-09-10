"""
Adaptive Noise Manager
======================
Tracks ciphertext noise budget across homomorphic operations and adapts
the bootstrap threshold dynamically based on the observed noise growth rate.

Noise model (simulated, not from TenSEAL internals):
  - Each HE operation adds a configurable delta to the budget counter.
  - The adaptive threshold shrinks when the rate of noise growth is high,
    triggering bootstrapping sooner to keep the budget safe.
  - History is kept in a bounded ring-buffer so the UI can chart it.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional

# How many historical data-points we keep for rate calculation and UI charting.
_HISTORY_CAPACITY = 200

# Noise deltas per operation type (CKKS approximate values).
NOISE_DELTAS: Dict[str, int] = {
    "encrypt": 1,
    "add": 2,
    "multiply": 12,
    "stream": 2,
    "aggregate_step": 3,
}

# Adaptive parameters.
_BASE_THRESHOLD = 50       # noise units before a refresh is needed
_MIN_THRESHOLD = 20        # floor — never let the threshold go below this
_MAX_THRESHOLD = 80        # ceiling — never let it go above this
_RATE_WINDOW_SEC = 10.0    # seconds over which growth rate is calculated
_RATE_HIGH_MARK = 5.0      # noise-units/sec — considered "high growth"
_RATE_LOW_MARK = 1.0       # noise-units/sec — considered "low growth"
_THRESHOLD_STEP = 5        # how much we nudge the threshold each adaptation


class NoiseManager:
    """
    Maintains the noise budget and adapts the bootstrap threshold.

    Attributes
    ----------
    noise       : current noise budget counter
    threshold   : current adaptive bootstrap threshold
    bootstraps  : number of bootstraps performed so far
    history     : bounded list of ``{t, noise, threshold}`` snapshots
    """

    def __init__(self) -> None:
        self.noise: int = 0
        self.threshold: int = _BASE_THRESHOLD
        self.bootstraps: int = 0

        # Ring-buffer of (timestamp_float, noise_int) for rate calculation.
        self._rate_buf: Deque[tuple[float, int]] = deque(maxlen=50)

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
        delta = NOISE_DELTAS.get(operation, 2)
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
        self.noise = 10
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
            "noise": self.noise,
            "threshold": self.threshold,
            "bootstraps": self.bootstraps,
            "noise_rate": round(self.noise_rate(), 3),
            "pct_used": round(self.noise / self.threshold * 100, 1) if self.threshold else 0,
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
            self.threshold = max(_MIN_THRESHOLD, self.threshold - _THRESHOLD_STEP)
        elif rate <= _RATE_LOW_MARK and self.threshold < _MAX_THRESHOLD:
            self.threshold = min(_MAX_THRESHOLD, self.threshold + _THRESHOLD_STEP)

    def _record_snapshot(self) -> None:
        self._history.append(
            {
                "t": len(self._history),
                "noise": self.noise,
                "threshold": self.threshold,
                "bootstraps": self.bootstraps,
            }
        )

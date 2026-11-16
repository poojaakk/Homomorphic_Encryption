"""
Noise & Precision Monitor
==========================
Thread-safe in-memory metrics buffer for streaming records, error analysis,
and live visualization feeds.
"""

from collections import deque
from typing import Dict, List, Optional
import numpy as np


class NoiseMonitor:
    def __init__(self, buffer_size: int = 500):
        self.buffer_size = buffer_size

        self.records = deque(maxlen=buffer_size)
        self.timestamps = deque(maxlen=buffer_size)
        self.plaintext_results = deque(maxlen=buffer_size)
        self.decrypted_results = deque(maxlen=buffer_size)
        self.absolute_errors = deque(maxlen=buffer_size)
        self.relative_errors = deque(maxlen=buffer_size)
        self.encryption_times = deque(maxlen=buffer_size)
        self.computation_times = deque(maxlen=buffer_size)
        self.decryption_times = deque(maxlen=buffer_size)
        self.total_latencies = deque(maxlen=buffer_size)
        self.intervention_markers: List[int] = []

    def record_step(
        self,
        record_id: int,
        timestamp: str,
        plaintext_ref: float,
        decrypted_val: float,
        abs_err: float,
        rel_err: float,
        enc_t_ms: float,
        comp_t_ms: float,
        dec_t_ms: float,
        was_intervened: bool = False,
    ) -> None:
        """Records a single streaming evaluation step into rolling series."""
        self.records.append(record_id)
        self.timestamps.append(timestamp)
        self.plaintext_results.append(plaintext_ref)
        self.decrypted_results.append(decrypted_val)
        self.absolute_errors.append(abs_err)
        self.relative_errors.append(rel_err)
        self.encryption_times.append(enc_t_ms)
        self.computation_times.append(comp_t_ms)
        self.decryption_times.append(dec_t_ms)
        self.total_latencies.append(enc_t_ms + comp_t_ms + dec_t_ms)

        if was_intervened:
            self.intervention_markers.append(record_id)

    def get_summary(self) -> Dict[str, float]:
        """Calculates global statistical summaries across the recorded history."""
        if not self.absolute_errors:
            return {}

        return {
            "total_processed": len(self.records),
            "mean_abs_error": float(np.mean(self.absolute_errors)),
            "max_abs_error": float(np.max(self.absolute_errors)),
            "mean_rel_error": float(np.mean(self.relative_errors)),
            "mean_enc_latency_ms": float(np.mean(self.encryption_times)),
            "mean_comp_latency_ms": float(np.mean(self.computation_times)),
            "mean_dec_latency_ms": float(np.mean(self.decryption_times)),
            "mean_total_latency_ms": float(np.mean(self.total_latencies)),
            "total_interventions": len(self.intervention_markers),
        }

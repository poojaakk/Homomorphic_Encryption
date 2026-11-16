"""
Adaptive Noise & Precision Controller
======================================
Dynamically monitors CKKS approximation error and depth headroom, triggering
mitigation strategies when numerical precision degrades beyond acceptable bounds.

ACADEMIC NOTE ON BOOTSTRAPPING VS RE-ENCRYPTION:
------------------------------------------------
In cryptographic literature, true "Bootstrapping" evaluates the decryption circuit
homomorphically on an encrypted secret key to reset ciphertext noise WITHOUT exposing
plaintext. TenSEAL / Microsoft SEAL does not support CKKS bootstrapping natively.
Therefore, our mitigation mechanism is an "Architectural Ciphertext Refresh"
(authorized edge checkpoint re-encryption) and "Adaptive Depth Management".
We explicitly distinguish this from true bootstrapping.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np


class AdaptiveNoiseController:
    def __init__(
        self,
        error_threshold: float = 1e-4,
        max_multiplicative_depth: int = 2,
        window_size: int = 10,
    ):
        """
        Parameters:
            error_threshold: Maximum tolerated Mean Absolute Error (MAE). If rolling
                             error exceeds this threshold, mitigation is triggered.
            max_multiplicative_depth: Multiplicative depth supported by the CKKS parameter set
                                     (e.g., coeff_mod_bit_sizes=[60, 40, 40, 60] supports depth 2).
            window_size: Rolling window size for smoothing error fluctuations.
        """
        self.error_threshold = error_threshold
        self.max_multiplicative_depth = max_multiplicative_depth
        self.window_size = window_size

        self.error_history: List[float] = []
        self.intervention_history: List[Dict] = []
        self.total_interventions = 0
        self.current_depth = 0

    def record_observation(self, mae: float, depth_consumed: int = 1) -> None:
        """Records an observed measurement error and updates accumulated depth."""
        self.error_history.append(mae)
        self.current_depth += depth_consumed

    def get_rolling_error(self) -> float:
        """Returns the mean error over the most recent window."""
        if not self.error_history:
            return 0.0
        recent = self.error_history[-self.window_size:]
        return float(np.mean(recent))

    def evaluate_headroom(self) -> Dict[str, float]:
        """
        Estimates remaining computational headroom before precision exhaustion.
        """
        rolling_err = self.get_rolling_error()
        remaining_depth = max(0, self.max_multiplicative_depth - self.current_depth)
        headroom_ratio = max(0.0, 1.0 - (rolling_err / self.error_threshold))
        
        return {
            "rolling_mae": rolling_err,
            "threshold": self.error_threshold,
            "headroom_ratio": headroom_ratio,
            "remaining_depth": remaining_depth,
            "current_depth": self.current_depth,
        }

    def should_intervene(self) -> Tuple[bool, Optional[str]]:
        """
        Determines whether an adaptive intervention is required based on:
        1. Numerical precision degradation: rolling MAE > error_threshold
        2. Multiplicative depth exhaustion: current_depth >= max_multiplicative_depth
        """
        rolling_err = self.get_rolling_error()

        if rolling_err >= self.error_threshold:
            return True, f"Precision degraded (rolling MAE {rolling_err:.2e} >= threshold {self.error_threshold:.2e})"

        if self.current_depth >= self.max_multiplicative_depth:
            return True, f"Multiplicative depth exhausted ({self.current_depth}/{self.max_multiplicative_depth})"

        return False, None

    def trigger_mitigation(
        self,
        reason: str,
        record_id: int,
    ) -> Dict:
        """
        Executes an adaptive mitigation action:
        - Resets active computational depth counter.
        - Logs the event with record ID, timestamp, and triggering reason.
        """
        self.total_interventions += 1
        self.current_depth = 0  # Fresh depth restored

        event = {
            "intervention_id": self.total_interventions,
            "record_id": record_id,
            "action": "CIPHERTEXT_REFRESH_AND_DEPTH_RESET",
            "reason": reason,
            "rolling_error_at_intervention": self.get_rolling_error(),
        }
        self.intervention_history.append(event)
        return event

"""
Homomorphic Encryption Engine
==============================
Executes TenSEAL CKKS encryption, encrypted evaluation, and decryption.
All computations take place on encrypted ciphertexts; plaintext references
are evaluated separately strictly for accuracy comparison.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import tenseal as ts

from encryption.key_manager import KeyManager


class HEEngine:
    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager()
        # Initialize context and evaluation keys
        self.context = self.key_manager.private_context
        self.public_context = self.key_manager.public_context

    def encrypt_vector(self, data_vector: List[float]) -> Tuple[ts.CKKSVector, float]:
        """
        Encrypts a numerical float vector into a CKKS ciphertext vector.
        Returns: (ciphertext_vector, encryption_time_seconds)
        """
        t0 = time.perf_counter()
        ciphertext = ts.ckks_vector(self.context, data_vector)
        enc_time = time.perf_counter() - t0
        return ciphertext, enc_time

    def decrypt_vector(self, ciphertext: ts.CKKSVector) -> Tuple[List[float], float]:
        """
        Decrypts a CKKS ciphertext vector into plaintext float list using Secret Key.
        Returns: (decrypted_floats, decryption_time_seconds)
        """
        t0 = time.perf_counter()
        decrypted = ciphertext.decrypt()
        dec_time = time.perf_counter() - t0
        return decrypted, dec_time

    def evaluate_polynomial(
        self,
        ciphertext: ts.CKKSVector,
        c2: float = 0.05,
        c1: float = 1.10,
        c0: float = 2.50,
    ) -> Tuple[ts.CKKSVector, float, int]:
        """
        Performs non-linear polynomial evaluation on ciphertext:
            P(x) = c2 * x^2 + c1 * x + c0

        This operation generates authentic multiplicative depth (depth=1 multiplication)
        which triggers relinearization and consumes modulus bits in the RNS chain.

        Returns:
            (evaluated_ciphertext, computation_time_seconds, multiplicative_depth)
        """
        t0 = time.perf_counter()
        # Ciphertext * Ciphertext (degree 2) -> automatically relinearized by TenSEAL
        c_squared = ciphertext * ciphertext
        # Scale and add linear term and scalar constant
        result = c_squared * c2 + ciphertext * c1 + c0
        comp_time = time.perf_counter() - t0
        return result, comp_time, 1

    def evaluate_polynomial_plaintext_reference(
        self,
        plaintext_vector: List[float],
        c2: float = 0.05,
        c1: float = 1.10,
        c0: float = 2.50,
    ) -> List[float]:
        """
        Evaluates the exact identical polynomial on raw plaintext floats.
        Used as the mathematical ground-truth reference to measure CKKS approximation error.
        """
        arr = np.array(plaintext_vector, dtype=np.float64)
        result = c2 * (arr ** 2) + c1 * arr + c0
        return result.tolist()

    def evaluate_moving_average_step(
        self,
        current_ciphertext: ts.CKKSVector,
        prev_ema_ciphertext: Optional[ts.CKKSVector],
        alpha: float = 0.30,
    ) -> Tuple[ts.CKKSVector, float]:
        """
        Performs encrypted Exponential Moving Average (EMA) step:
            EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}
        """
        t0 = time.perf_counter()
        if prev_ema_ciphertext is None:
            comp_time = time.perf_counter() - t0
            return current_ciphertext.copy(), comp_time

        part_new = current_ciphertext * alpha
        part_prev = prev_ema_ciphertext * (1.0 - alpha)
        ema = part_new + part_prev
        comp_time = time.perf_counter() - t0
        return ema, comp_time

    def serialize_ciphertext(self, ciphertext: ts.CKKSVector) -> bytes:
        """Serializes ciphertext into binary format for transmission or storage."""
        return ciphertext.serialize()

    def deserialize_ciphertext(self, raw_bytes: bytes) -> ts.CKKSVector:
        """Deserializes raw bytes back into an active CKKSVector linked to current context."""
        return ts.ckks_vector_from(self.context, raw_bytes)

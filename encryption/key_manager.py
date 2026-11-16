"""
Cryptographic Key Management Module
====================================
Manages TenSEAL CKKS encryption context, key material lifecycle, and serialization.

UNDERSTANDING HE KEYS VS INTEGRITY:
-----------------------------------
1. Secret Key (SK):
   - Private key polynomial s(x) kept exclusively by the decryptor/client.
   - Required ONLY for decrypting ciphertexts.
   - In TenSEAL, this is generated automatically when the Context is initialized.

2. Public / Encryption Key (PK):
   - Public key pair (a, b) derived from s(x) with small gaussian noise.
   - Used to encrypt plaintext vectors into ciphertexts.

3. Relinearization Keys (Relin Keys):
   - Evaluation key material required after homomorphic ciphertext-ciphertext multiplication.
   - Multiplying two degree-1 ciphertexts (c0, c1) yields a degree-2 ciphertext (c0, c1, c2).
   - Relinearization transforms the degree-2 ciphertext back to degree-1 (c0, c1)
     so further multiplications can be performed without quadratic ciphertext expansion.

4. Galois Keys (Evaluation / Rotation Keys):
   - Required for homomorphic vector rotations (e.g. cyclically shifting slots).
   - Generated when vector rotations or slot aggregations are needed.

5. Data Integrity:
   - HE keys DO NOT provide message authenticity or transit integrity.
   - A separate SHA-256 / HMAC integrity layer (see integrity/integrity_checker.py)
     is used to detect tampering during streaming transport.
"""

import os
from typing import Optional, Tuple
import tenseal as ts


class KeyManager:
    def __init__(
        self,
        poly_modulus_degree: int = 8192,
        coeff_mod_bit_sizes: Optional[list] = None,
        global_scale: float = 2**40,
    ):
        """
        Initializes the CKKS Parameter Context.
        
        Parameters:
            poly_modulus_degree: Power-of-two degree N of polynomial quotient ring R_q = Z_q[X]/(X^N + 1).
                                 8192 provides 128-bit post-quantum classical security level.
            coeff_mod_bit_sizes: Chain of prime moduli in the RNS (Residue Number System) representation.
                                 Default [60, 40, 40, 60] provides multiplicative depth of 2.
            global_scale: Default scale factor Delta for fixed-point message encoding (2^40).
        """
        self.poly_modulus_degree = poly_modulus_degree
        self.coeff_mod_bit_sizes = coeff_mod_bit_sizes or [60, 40, 40, 60]
        self.global_scale = global_scale

        self._private_context: Optional[ts.Context] = None
        self._public_context: Optional[ts.Context] = None

    def initialize_context(self, generate_galois: bool = True) -> ts.Context:
        """
        Creates the TenSEAL CKKS context and generates necessary evaluation keys.
        """
        # 1. Context Creation & Secret Key generation
        context = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=self.poly_modulus_degree,
            coeff_mod_bit_sizes=self.coeff_mod_bit_sizes,
        )
        context.global_scale = self.global_scale

        # 2. Evaluation Keys generation
        # Relinearization keys are MANDATORY for ciphertext multiplication
        context.generate_relin_keys()

        # Galois keys for homomorphic vector rotations
        if generate_galois:
            context.generate_galois_keys()

        self._private_context = context

        # 3. Create public context (drops the secret key) for untrusted evaluators
        # Copy context and make it public
        public_ctx = context.copy()
        public_ctx.make_context_public()
        self._public_context = public_ctx

        return self._private_context

    @property
    def private_context(self) -> ts.Context:
        """Returns the full context containing the Secret Key (used strictly by Decryptor)."""
        if self._private_context is None:
            self.initialize_context()
        return self._private_context

    @property
    def public_context(self) -> ts.Context:
        """Returns the public evaluation context without Secret Key (safe for Evaluator)."""
        if self._public_context is None:
            self.initialize_context()
        return self._public_context

    def get_security_summary(self) -> dict:
        """Provides cryptographic parameter summary for academic reporting and viva verification."""
        ctx = self.private_context
        return {
            "scheme": "CKKS (Cheon-Kim-Kim-Song)",
            "poly_modulus_degree": self.poly_modulus_degree,
            "coeff_mod_bit_sizes": self.coeff_mod_bit_sizes,
            "scale": f"2^{int(self.global_scale.bit_length() - 1)}",
            "has_secret_key": ctx.has_secret_key(),
            "has_public_key": ctx.has_public_key(),
            "has_relin_keys": ctx.has_relin_keys(),
            "has_galois_keys": ctx.has_galois_keys(),
            "estimated_security": "128-bit (HomomorphicEncryption.org standard)",
        }

"""
Bootstrapping Module
====================
Simulates ciphertext noise refresh (bootstrapping).

In a production CKKS pipeline, bootstrapping would serialize the ciphertext,
re-encrypt it from scratch at a fresh noise level, and return a new ciphertext
object.  Here we simulate that by resetting the noise budget tracker and
optionally re-serializing the in-memory ciphertext (no-op semantically but
demonstrates the pipeline touchpoint).

The module also accepts optional callback hooks so the caller (main.py) can
emit WebSocket events without creating a circular import.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

# Type alias for the optional WS-publish callback.
PublishCallback = Callable[[dict], Any]


def bootstrap(
    noise_manager,
    *,
    ciphertext=None,
    on_event: Optional[PublishCallback] = None,
    label: str = "auto",
) -> tuple[int, int]:
    """
    Perform a simulated bootstrapping refresh.

    Parameters
    ----------
    noise_manager : NoiseManager
        The live noise tracker; its ``reset_noise()`` is called.
    ciphertext : CKKSVector | None
        If provided, the ciphertext is serialized and immediately
        deserialized — a stand-in for the real refresh pipeline step.
    on_event : callable | None
        Optional coroutine-safe callback for emitting a 'bootstrap' WS event.
        Signature: ``on_event(dict) -> None``.  Called synchronously here;
        callers that use asyncio should schedule it appropriately.
    label : str
        Annotation tag — 'auto' for threshold-triggered, 'manual' for
        user-requested bootstraps.

    Returns
    -------
    (before, after) : tuple[int, int]
        Noise budget before and after the refresh.
    """
    before = noise_manager.get_noise()
    noise_manager.reset_noise()
    after = noise_manager.get_noise()

    # Simulate the serialize → deserialize pipeline touchpoint.
    refreshed_ct = None
    if ciphertext is not None:
        try:
            raw = ciphertext.serialize()
            # In a full pipeline: ctx.ckks_vector_from(raw) would recreate it.
            refreshed_ct = raw  # kept as bytes; caller replaces their ref if needed
        except Exception:
            refreshed_ct = None  # graceful — don't crash the stream

    event_payload = {
        "type": "bootstrap",
        "label": label,
        "before": before,
        "after": after,
        "bootstraps": noise_manager.bootstraps,
        "threshold": noise_manager.get_threshold(),
        "ts": time.time(),
    }

    if on_event is not None:
        try:
            on_event(event_payload)
        except Exception:
            pass  # never let a hook crash the bootstrap itself

    return before, after

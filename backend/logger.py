"""
Logger
======
In-memory, categorised log store with a bounded ring buffer.

Categories:  api | compute | noise | kafka | error | system
"""

from __future__ import annotations

import datetime
from collections import deque
from typing import Deque, Dict, List, Literal, Optional

LogCategory = Literal["api", "compute", "noise", "kafka", "error", "system"]

_MAX_LOGS = 500  # ring-buffer capacity

_store: Deque[Dict] = deque(maxlen=_MAX_LOGS)


def log(
    message: str,
    category: LogCategory = "system",
) -> None:
    """
    Append a log entry.

    Parameters
    ----------
    message  : Human-readable description of the event.
    category : One of ``api | compute | noise | kafka | error | system``.
    """
    _store.append(
        {
            "time": datetime.datetime.now().isoformat(timespec="milliseconds"),
            "category": category,
            "message": message,
        }
    )


def get_logs(
    category: Optional[str] = None,
    limit: int = 200,
) -> Dict:
    """
    Return log entries, optionally filtered by category.

    Parameters
    ----------
    category : If provided, only entries with this category are returned.
    limit    : Maximum number of entries (most-recent first).
    """
    entries = list(_store)
    if category:
        entries = [e for e in entries if e["category"] == category]
    entries = entries[-limit:][::-1]  # most-recent first
    return {"logs": entries, "total": len(entries)}

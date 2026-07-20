from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

CATEGORIES = [
    "Sub-Query Generation",
    "Total DB Retrieval Time",
    "Total DB Retrieval Validation Time",
    "Total Merge Time for Retrieved Chunks",
    "Total Validation Time for Merged Chunks",
    "Compression",
    "Draft Generation",
    "CAQ",
    "Final Generation",
]


class TimingTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, list[float]] = {cat: [] for cat in CATEGORIES}
        self._json_path: Optional[Path] = None

    def set_json_path(self, path: Path) -> None:
        with self._lock:
            self._json_path = path
            self._flush_unlocked()

    def record(self, category: str, duration: float) -> None:
        with self._lock:
            if category in self._data:
                self._data[category].append(round(duration, 4))
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if self._json_path is None:
            return
        try:
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            self._json_path.write_text(
                json.dumps(self._data, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


timing_tracker = TimingTracker()


from .operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Timing")

"""Singleton timing tracker that records per-phase durations to a JSON file.

Initialized by logger_config.setup_logging(); all other modules call
record() or record_llm() without needing the file path.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

CATEGORIES = (
    "Sub-Query Generation",
    "Total DB Retrieval Time",
    "Total DB Retrieval Validation Time",
    "Total Merge Time for Retrieved Chunks",
    "Total Validation Time for Merged Chunks",
    "Compression",
    "Draft Generation",
    "CAQ",
    "Final Generation",
)

# Map llm_invoke caller_tag → timing category.
# Tags not listed here are silently ignored by record_llm().
_LLM_TAG_TO_CATEGORY: dict[str, str] = {
    "AGENT-RETRIEVE": "Sub-Query Generation",
    "AGENT-DRAFT":    "Draft Generation",
    "AGENT-FINAL":    "Final Generation",
    "CAQ-JUDGE":      "CAQ",
    "CAQ-JUDGE-TD":   "CAQ",
}

_data: dict[str, list[float]] = {c: [] for c in CATEGORIES}
_json_path: Path | None = None
_lock = threading.Lock()


def initialize(json_path: Path) -> None:
    """Set the output file and reset all lists. Called once by setup_logging()."""
    global _data, _json_path
    with _lock:
        _json_path = json_path
        _data = {c: [] for c in CATEGORIES}
        _write()


def record(category: str, duration: float) -> None:
    """Append a duration (seconds) to the given category list and flush to disk."""
    with _lock:
        if category in _data:
            _data[category].append(round(duration, 4))
            _write()


def record_llm(caller_tag: str, duration: float) -> None:
    """Resolve caller_tag to a category and record; no-op for unmapped tags."""
    category = _LLM_TAG_TO_CATEGORY.get(caller_tag)
    if category:
        record(category, duration)


def _write() -> None:
    if _json_path is None:
        return
    try:
        _json_path.write_text(json.dumps(_data, indent=2), encoding="utf-8")
    except OSError:
        pass

"""Per-request overrides for the ENABLE_* workflow toggles in config.py.

Callers (API layer) resolve a request's switch overrides once into a plain
dict via `resolve_switches()` and store it on GraphState["switches"]. Node
code reads effective values via `get_switches(state)` instead of importing
the ENABLE_* constants directly, so a request without overrides transparently
falls back to the config.py defaults.
"""
from app_workflow.config import (
    ENABLE_SUB_QUERY_GENERATION,
    ENABLE_QUERY_VARIANTS_OUTPUT_FIX,
    ENABLE_RETRIEVAL_DEDUP_MERGE,
    ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX,
    ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION,
    ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX,
    ENABLE_RETRIEVAL_VALIDATION,
    ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX,
    ENABLE_NAC_COMPRESSION,
    ENABLE_DC_COMPRESSION,
    ENABLE_LBC_COMPRESSION,
    ENABLE_COMPRESSION_VALIDATION,
    ENABLE_COMPRESSION_OUTPUT_FIX,
    ENABLE_ANSWER_DRAFT_CREATION,
    ENABLE_ANSWER_QUALITY_CHECK,
    ENABLE_ANSWER_QUALITY_OUTPUT_FIX,
    ENABLE_AUTO_DISTILLATION,
    ENABLE_QA_PAIR_GENERATION,
    ENABLE_QA_PAIR_OUTPUT_FIX,
    ENABLE_GLOBAL_LLM_OUTPUT_FIX,
)

DEFAULT_SWITCHES: dict[str, bool] = {
    "ENABLE_SUB_QUERY_GENERATION": ENABLE_SUB_QUERY_GENERATION,
    "ENABLE_QUERY_VARIANTS_OUTPUT_FIX": ENABLE_QUERY_VARIANTS_OUTPUT_FIX,
    "ENABLE_RETRIEVAL_DEDUP_MERGE": ENABLE_RETRIEVAL_DEDUP_MERGE,
    "ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX": ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX,
    "ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION": ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION,
    "ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX": ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX,
    "ENABLE_RETRIEVAL_VALIDATION": ENABLE_RETRIEVAL_VALIDATION,
    "ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX": ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX,
    "ENABLE_NAC_COMPRESSION": ENABLE_NAC_COMPRESSION,
    "ENABLE_DC_COMPRESSION": ENABLE_DC_COMPRESSION,
    "ENABLE_LBC_COMPRESSION": ENABLE_LBC_COMPRESSION,
    "ENABLE_COMPRESSION_VALIDATION": ENABLE_COMPRESSION_VALIDATION,
    "ENABLE_COMPRESSION_OUTPUT_FIX": ENABLE_COMPRESSION_OUTPUT_FIX,
    "ENABLE_ANSWER_DRAFT_CREATION": ENABLE_ANSWER_DRAFT_CREATION,
    "ENABLE_ANSWER_QUALITY_CHECK": ENABLE_ANSWER_QUALITY_CHECK,
    "ENABLE_ANSWER_QUALITY_OUTPUT_FIX": ENABLE_ANSWER_QUALITY_OUTPUT_FIX,
    "ENABLE_AUTO_DISTILLATION": ENABLE_AUTO_DISTILLATION,
    "ENABLE_QA_PAIR_GENERATION": ENABLE_QA_PAIR_GENERATION,
    "ENABLE_QA_PAIR_OUTPUT_FIX": ENABLE_QA_PAIR_OUTPUT_FIX,
    "ENABLE_GLOBAL_LLM_OUTPUT_FIX": ENABLE_GLOBAL_LLM_OUTPUT_FIX,
}

SWITCH_NAMES = frozenset(DEFAULT_SWITCHES)


def resolve_switches(overrides: dict | None) -> dict[str, bool]:
    """Merge request-provided overrides onto the config.py defaults.

    Unknown keys and non-bool values are ignored so a malformed request
    field can't silently corrupt the run.
    """
    merged = dict(DEFAULT_SWITCHES)
    if overrides:
        for key, value in overrides.items():
            if key in SWITCH_NAMES and isinstance(value, bool):
                merged[key] = value
    return merged


def get_switches(state) -> dict[str, bool]:
    """Read the effective switch set for this run from GraphState.

    Falls back to config.py defaults when the state has no "switches" key
    (e.g. the CLI entrypoint in main.py, which doesn't set one).
    """
    return state.get("switches") or DEFAULT_SWITCHES

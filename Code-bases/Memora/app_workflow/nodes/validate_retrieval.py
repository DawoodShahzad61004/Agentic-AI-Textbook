import logging
import time
from state import GraphState
from app_workflow.services.llm_setup import judge_llm
from app_workflow.services.switches import get_switches
from app_workflow.services.validators import validate_retrieval
from app_workflow.services.timing_tracker import timing_tracker

logger = logging.getLogger(__name__)


def _validate_track(track_name: str, chunks: list[dict], query: str, switches: dict, config=None) -> list[dict]:
    if not chunks:
        logger.debug("[VALIDATE_%s] no chunks — skipping", track_name.upper())
        return []

    if not switches["ENABLE_RETRIEVAL_VALIDATION"]:
        logger.debug(
            "[VALIDATE_%s] disabled — passing through %d chunk(s)",
            track_name.upper(), len(chunks),
        )
        return list(chunks)

    result = validate_retrieval(query, chunks, judge_llm, config=config, switches=switches)
    verdict = result["verdict"]

    irrelevant_idx: set[int] = set()
    if verdict != "UNKNOWN":
        for pc in result.get("per_chunk", []):
            if pc.get("relevant") is False and isinstance(pc.get("index"), int):
                irrelevant_idx.add(pc["index"])

    kept = [c for i, c in enumerate(chunks) if i not in irrelevant_idx]
    logger.debug(
        "[VALIDATE_%s] verdict=%s | kept %d/%d | query=%r",
        track_name.upper(), verdict, len(kept), len(chunks), query[:60],
    )
    return kept


def validate_document_retrieval(state: GraphState, config=None) -> dict:
    """Validate chunks from the documents collection.

    Runs in parallel with validate_learned_qa_retrieval after post_retrieval_filter
    completes. Reads post_filtered_document_chunks (set by post_retrieval_filter_node)
    so that redundant-variant chunks are excluded before validation.
    """
    _t0 = time.perf_counter()
    query = state.get("query") or state.get("user_input") or ""
    chunks = state.get("post_filtered_document_chunks") or state.get("retrieved_document_chunks") or []
    kept = _validate_track("documents", chunks, query, get_switches(state), config=config)
    timing_tracker.record("Total DB Retrieval Validation Time", time.perf_counter() - _t0)
    return {"validated_document_chunks": kept}


def validate_learned_qa_retrieval(state: GraphState, config=None) -> dict:
    """Validate chunks from the learned_qa collection.

    Runs in parallel with validate_document_retrieval after post_retrieval_filter
    completes. Reads post_filtered_learned_qa_chunks (set by post_retrieval_filter_node)
    so that redundant-variant chunks are excluded before validation.
    """
    _t0 = time.perf_counter()
    query = state.get("query") or state.get("user_input") or ""
    chunks = state.get("post_filtered_learned_qa_chunks") or state.get("retrieved_learned_qa_chunks") or []
    kept = _validate_track("learned_qa", chunks, query, get_switches(state), config=config)
    timing_tracker.record("Total DB Retrieval Validation Time", time.perf_counter() - _t0)
    return {"validated_learned_qa_chunks": kept}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Retrieval Validation Node", exclude={"validate_document_retrieval", "validate_learned_qa_retrieval"})

import logging
import time
from state import GraphState
from app_workflow.services.timing_tracker import timing_tracker

logger = logging.getLogger(__name__)


def post_retrieval_filter_node(state: GraphState) -> dict:
    """Discard variant contributions whose combined chunk content is identical to a
    previously kept variant, then write the cleaned lists to post_filtered_* fields
    for downstream validation.

    Uses (content, source) pairs as chunk identity since the flat retrieved lists
    don't carry vector-store IDs. Chunk data (similarity_score, chunk_seq) is
    preserved by filtering the accumulated retrieved_* lists rather than
    reconstructing from variants_with_chunks.
    """
    _t0 = time.perf_counter()

    variants = state.get("variants_with_chunks") or []
    all_doc_chunks = state.get("retrieved_document_chunks") or []
    all_qa_chunks = state.get("retrieved_learned_qa_chunks") or []

    seen_sets: set[frozenset] = set()
    kept_keys: set[tuple] = set()   # (content, source) pairs that belong to kept variants
    redundant: list[str] = []

    for vr in variants:
        doc_chunks = vr.get("document_chunks") or []
        qa_chunks = vr.get("learned_qa_chunks") or []
        combined = frozenset(
            (c.get("content", ""), c.get("source", ""))
            for c in (doc_chunks + qa_chunks)
        )
        if not combined:
            # variant retrieved nothing — skip, don't add to redundant
            continue
        if combined in seen_sets:
            redundant.append(vr.get("query", ""))
            logger.info("[POST_FILTER] redundant variant: %r", vr.get("query", "")[:60])
        else:
            seen_sets.add(combined)
            kept_keys.update(combined)

    if not redundant:
        # Fast path: nothing to filter
        filtered_doc = list(all_doc_chunks)
        filtered_qa = list(all_qa_chunks)
    else:
        filtered_doc = [
            c for c in all_doc_chunks
            if (c.get("content", ""), c.get("source", "")) in kept_keys
        ]
        filtered_qa = [
            c for c in all_qa_chunks
            if (c.get("content", ""), c.get("source", "")) in kept_keys
        ]

    logger.info(
        "[POST_FILTER] redundant_variants=%d  doc=%d→%d  qa=%d→%d",
        len(redundant),
        len(all_doc_chunks), len(filtered_doc),
        len(all_qa_chunks), len(filtered_qa),
    )
    timing_tracker.record("Post-Retrieval Filter", time.perf_counter() - _t0)
    return {
        "post_filtered_document_chunks": filtered_doc,
        "post_filtered_learned_qa_chunks": filtered_qa,
    }

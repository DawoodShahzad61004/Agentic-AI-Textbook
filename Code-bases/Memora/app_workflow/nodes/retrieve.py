import logging
import time
from state import GraphState
from app_workflow.services.services import retriever
from app_workflow.config import RETRIEVAL_TOP_K, RETRIEVAL_TOP_L, DOCUMENTS_MIN_SIMILARITY, LEARNED_QA_MIN_SIMILARITY
from app_workflow.services.timing_tracker import timing_tracker

logger = logging.getLogger(__name__)


def _flatten_chunks(chunks: list[dict]) -> list[dict]:
    flat = []
    for d in chunks:
        meta = d.get("metadata") or {}
        item: dict = {
            "content": d.get("content", ""),
            "source": meta.get("source", "?"),
            "similarity_score": d.get("similarity_score", 0.0),
        }
        if isinstance(meta.get("chunk_seq"), int):
            item["chunk_seq"] = meta["chunk_seq"]
        flat.append(item)
    return flat


def retrieve(state: GraphState) -> dict:
    """Query both collections with a single embedding for the current variant.

    Called in parallel for each query variant via LangGraph Send.  The two
    resulting lists are accumulated into the main state via Annotated reducers
    (operator.add), so all variant results are gathered before validation runs.
    """
    _t0 = time.perf_counter()
    query = state["query"]

    results = retriever.retrieve_separate(
        query,
        top_k=RETRIEVAL_TOP_K,
        top_l=RETRIEVAL_TOP_L,
        doc_score_threshold=DOCUMENTS_MIN_SIMILARITY,
        learned_score_threshold=LEARNED_QA_MIN_SIMILARITY,
    )

    doc_chunks = _flatten_chunks(results["documents"])
    qa_chunks = _flatten_chunks(results["learned_qa"])

    logger.debug(
        "[RETRIEVE] query=%r  docs=%d  learned_qa=%d",
        query[:60], len(doc_chunks), len(qa_chunks),
    )

    # Track per-variant retrieval results for cmd_bad (user_thumbdowns.json)
    # and for saving zero-result phrasings to failed_variants.json.
    variant_entry = {
        "query": query,
        "document_chunks": [{"content": c["content"], "source": c["source"]} for c in doc_chunks],
        "learned_qa_chunks": [{"content": c["content"], "source": c["source"]} for c in qa_chunks],
    }
    newly_failed = [query] if not doc_chunks and not qa_chunks else []

    timing_tracker.record("Total DB Retrieval Time", time.perf_counter() - _t0)
    return {
        "retrieved_document_chunks": doc_chunks,
        "retrieved_learned_qa_chunks": qa_chunks,
        "variants_with_chunks": [variant_entry],
        "newly_failed_variants": newly_failed,
    }


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Retrieval Node", exclude={"retrieve"})

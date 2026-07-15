import logging
from state import GraphState

logger = logging.getLogger(__name__)


def combine_tracks(state: GraphState) -> dict:
    """Join compressed learned_qa and document tracks into the final context list.

    Fan-in point after both per-track compression pipelines complete.
    Learned-QA chunks appear first (higher priority), then document chunks,
    mirroring the precedence ordering in agent_query.py's
    format_precedence_context_for_llm().
    """
    learned_qa = state.get("compressed_learned_qa_chunks") or []
    documents = state.get("compressed_document_chunks") or []
    combined = [*learned_qa, *documents]
    logger.info(
        "[COMBINE_TRACKS] learned_qa=%d  documents=%d  combined=%d chunk(s)",
        len(learned_qa), len(documents), len(combined),
    )
    return {"compressed_docs": combined}

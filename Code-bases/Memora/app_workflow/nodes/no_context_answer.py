import logging
from state import GraphState
from app_workflow.services.prompts import NO_CONTEXT_ANSWER
from app_workflow.services import services
from app_workflow.services.services import feedback_store

logger = logging.getLogger(__name__)


def no_context_answer(state: GraphState) -> dict:
    answer = NO_CONTEXT_ANSWER
    logger.debug("No Context Available:\n%s", answer)
    logger.info("Assistant: %s", answer)

    user_input = state["user_input"]

    # Log the no-context interaction to interactions.jsonl as INSUFFICIENT.
    feedback_store.log(
        query=user_input,
        answer=answer,
        sources=[],
        quality="INSUFFICIENT",
        document_retrieved_chunks=[],
        learned_qa_retrieved_chunks=[],
    )

    # Persist zero-result query phrasings to failed_variants.json.
    newly_failed = list(state.get("newly_failed_variants") or [])
    feedback_store.save_failed_variants(user_input, newly_failed)
    if newly_failed:
        logger.info(
            "[NO_CONTEXT] saved %d newly-failed variant(s) to failed_variants.json",
            len(newly_failed),
        )

    # Update session-level cache so cmd_bad can enrich the thumbdown entry.
    services.last_variants_with_chunks = list(state.get("variants_with_chunks") or [])

    return {"answer": answer}

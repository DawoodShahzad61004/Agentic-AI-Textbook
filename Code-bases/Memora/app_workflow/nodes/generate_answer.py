import logging
import time
from state import GraphState
from app_workflow.services.llm_setup import llm
from app_workflow.services.llm_caller import llm_invoke
from app_workflow.services import services
from app_workflow.services.services import feedback_store
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.prompts import _GENERATE_ANSWER_PROMPT, _GENERATE_ANSWER_FROM_DRAFT_PROMPT
from nodes.check_answer_quality import QUALITY_PASS_VERDICT

logger = logging.getLogger(__name__)


def _build_context(compressed_docs: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {doc['content']}" for i, doc in enumerate(compressed_docs)
    )


def generate_answer(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    compressed_docs = state["compressed_docs"]
    user_input = state["user_input"]

    context = _build_context(compressed_docs)
    draft = state.get("draft")

    if draft:
        prompt = _GENERATE_ANSWER_FROM_DRAFT_PROMPT.format(
            query=user_input,
            context=context,
            draft=draft,
        )
        caller_tag = "GENERATE-ANSWER-FROM-DRAFT"
    else:
        prompt = _GENERATE_ANSWER_PROMPT.format(
            query=user_input,
            context=context
        )
        caller_tag = "GENERATE-ANSWER"

    logger.debug("[GENERATE_ANSWER] PROMPT:\n%s", prompt)
    result = llm_invoke(llm, [{"role": "user", "content": prompt}], caller_tag=caller_tag, config=config)
    if result.ok:
        answer = (result.content or "").strip()
    elif draft:
        # Final-synthesis call failed — fall back to the draft as-is rather than
        # returning nothing.
        logger.warning(
            "[GENERATE_ANSWER] final synthesis LLM call failed (%s) — falling back to draft",
            result.error_kind,
        )
        answer = draft
    else:
        logger.error(
            "[GENERATE_ANSWER] LLM call failed (%s): %s",
            result.error_kind, result.error_message,
        )
        answer = ""

    logger.debug("[GENERATE_ANSWER] RESPONSE:\n%s", answer)
    logger.info("Assistant: %s", answer)

    # Derive quality from the judge verdict so non-GROUNDED answers are logged correctly.
    verdict = (state.get("quality_verdict") or "").strip().upper()
    quality = "OK" if (not verdict or verdict == QUALITY_PASS_VERDICT) else verdict

    sources = [{"source": d.get("source", "?")} for d in compressed_docs]
    feedback_store.log(
        query=user_input,
        answer=answer,
        sources=sources,
        quality=quality,
        document_retrieved_chunks=state.get("compressed_document_chunks") or [],
        learned_qa_retrieved_chunks=state.get("compressed_learned_qa_chunks") or [],
        request_id=state.get("request_id", ""),
        variants=list(state.get("variants_with_chunks") or []),
    )

    # Persist zero-result query phrasings so future runs block them upfront.
    newly_failed = list(state.get("newly_failed_variants") or [])
    feedback_store.save_failed_variants(user_input, newly_failed)
    if newly_failed:
        logger.info(
            "[GENERATE_ANSWER] saved %d newly-failed variant(s) to failed_variants.json",
            len(newly_failed),
        )

    # Update session-level cache so cmd_bad can enrich the thumbdown entry.
    services.last_variants_with_chunks = list(state.get("variants_with_chunks") or [])

    timing_tracker.record("Final Generation", time.perf_counter() - _t0)
    return {"answer": answer}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Answer Generation Node", exclude={"generate_answer"})

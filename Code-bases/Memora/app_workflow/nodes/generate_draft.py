import logging
import time
from state import GraphState
from app_workflow.services.llm_setup import llm
from app_workflow.services.llm_caller import llm_invoke
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.prompts import _GENERATE_DRAFT_PROMPT

logger = logging.getLogger(__name__)


def _build_context(compressed_docs: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {doc['content']}" for i, doc in enumerate(compressed_docs)
    )


def generate_draft(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    compressed_docs = state["compressed_docs"]
    user_input = state["user_input"]
    context = _build_context(compressed_docs)

    draft_prompt = _GENERATE_DRAFT_PROMPT.format(query=user_input, context=context)
    logger.debug("[GENERATE_DRAFT] prompt:\n%s", draft_prompt)
    result = llm_invoke(llm, [{"role": "user", "content": draft_prompt}], caller_tag="GENERATE-DRAFT", config=config)
    draft = (result.content or "").strip()
    logger.debug("[GENERATE_DRAFT] draft:\n%s", draft)

    timing_tracker.record("Draft Generation", time.perf_counter() - _t0)
    return {"draft": draft}

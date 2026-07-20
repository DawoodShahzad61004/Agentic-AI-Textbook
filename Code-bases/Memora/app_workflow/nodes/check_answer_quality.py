import logging
import time
from state import GraphState
from app_workflow.services.switches import get_switches
from app_workflow.services.llm_setup import judge_llm
from app_workflow.services.llm_caller import llm_invoke
from app_workflow.services.prompts import GROUNDING_PROMPT
from app_workflow.services.fix_llm_output import fix_llm_output, _parse_to_python
from app_workflow.services.timing_tracker import timing_tracker

logger = logging.getLogger(__name__)

# Verdict that means the draft passed every rule — everything else is a failure
# of some kind (fabrication, overclaiming, off-topic, or unparseable judge output).
QUALITY_PASS_VERDICT = "GROUNDED"
_VALID_VERDICTS = {QUALITY_PASS_VERDICT, "PARTIALLY_FABRICATED", "OVERCLAIMED", "OFF_TOPIC", "UNKNOWN"}


def _build_context(compressed_docs: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {doc['content']}" for i, doc in enumerate(compressed_docs)
    )


def check_answer_quality(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    sw = get_switches(state)
    compressed_docs = state["compressed_docs"]
    user_input = state["user_input"]
    context = _build_context(compressed_docs)
    draft = state["draft"]

    quality_prompt = GROUNDING_PROMPT.format(
        query=user_input,
        context=context,
        answer=draft,
    )
    quality_result = llm_invoke(
        judge_llm,
        [{"role": "system", "content": quality_prompt}],
        caller_tag="ANSWER-QUALITY",
        config=config,
    )

    if not quality_result.ok:
        logger.warning(
            "[CHECK_ANSWER_QUALITY] judge LLM call failed (%s): %s",
            quality_result.error_kind, quality_result.error_message[:200],
        )
        timing_tracker.record("CAQ", time.perf_counter() - _t0)
        return {"quality_verdict": "UNKNOWN"}

    raw = quality_result.content or ""

    if sw["ENABLE_ANSWER_QUALITY_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
        llm_result, _ok = fix_llm_output("grounding_judge", raw, llm=judge_llm, config=config)
        if not _ok or not isinstance(llm_result, dict) or "verdict" not in llm_result:
            logger.warning("[CHECK_ANSWER_QUALITY] failed to fix malformed judge output.")
            logger.debug("[CHECK_ANSWER_QUALITY] raw: %s", raw[:400])
            timing_tracker.record("CAQ", time.perf_counter() - _t0)
            return {"quality_verdict": "UNKNOWN"}
        logger.info("[CHECK_ANSWER_QUALITY] successfully fixed malformed judge output.")
    else:
        llm_result = _parse_to_python(raw)

    if not isinstance(llm_result, dict):
        logger.warning("[CHECK_ANSWER_QUALITY] judge response was not valid JSON.")
        logger.debug("[CHECK_ANSWER_QUALITY] raw: %s", raw[:400])
        timing_tracker.record("CAQ", time.perf_counter() - _t0)
        return {"quality_verdict": "UNKNOWN"}

    verdict = str(llm_result.get("verdict") or "UNKNOWN").upper().strip()
    if verdict not in _VALID_VERDICTS:
        verdict = "UNKNOWN"

    logger.info(
        "[CHECK_ANSWER_QUALITY] verdict=%s unsupported_claims=%d reason=%s",
        verdict,
        len(llm_result.get("unsupported_claims") or []),
        str(llm_result.get("overall_reason") or "")[:200],
    )

    timing_tracker.record("CAQ", time.perf_counter() - _t0)
    return {"quality_verdict": verdict}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Answer Quality Node", exclude={"check_answer_quality"})

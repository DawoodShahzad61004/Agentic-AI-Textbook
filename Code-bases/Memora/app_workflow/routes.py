import logging
from langgraph.graph import END
from langgraph.types import Send
from state import GraphState
from app_workflow.config import LLM_RESPONSE_RETRY_LIMIT
from app_workflow.services.switches import get_switches
from app_workflow.services.services import self_learner
from app_workflow.nodes.check_answer_quality import QUALITY_PASS_VERDICT

logger = logging.getLogger(__name__)


def fan_out_retrievals(state: GraphState):
    """Fan out one retrieve Send per query variant.

    Each Send runs retrieve() in parallel with query=variant.  retrieve() calls
    retrieve_separate() which queries both collections with a single embedding,
    writing to retrieved_document_chunks and retrieved_learned_qa_chunks via the
    Annotated(operator.add) reducers so all variant results accumulate.
    """
    return [
        Send("retrieve", {**state, "query": variant})
        for variant in state["query_variants"]
    ]


def route_user_input(state: GraphState) -> str:
    cmd = state.get("command", "")
    if cmd == "stats":
        return "cmd_stats"
    if cmd == "learn":
        return "cmd_learn"
    if cmd == "bad":
        return "cmd_bad"
    if cmd == "exit":
        return "cmd_exit"
    return "generate_query_variants"


# ── Document compression track routes ────────────────────────────────────────

def route_nac_documents_to_validator(state: GraphState) -> str:
    return "validate_NAC_documents" if get_switches(state)["ENABLE_COMPRESSION_VALIDATION"] else "DC_documents"


def route_dc_documents_to_validator(state: GraphState) -> str:
    return "validate_DC_documents" if get_switches(state)["ENABLE_COMPRESSION_VALIDATION"] else "LBC_documents"


# ── Learned-QA compression track routes ──────────────────────────────────────

def route_dc_learned_qa_to_validator(state: GraphState) -> str:
    return "validate_DC_learned_qa" if get_switches(state)["ENABLE_COMPRESSION_VALIDATION"] else "LBC_learned_qa"


# ── Post-combine route ────────────────────────────────────────────────────────

def route_after_combine(state: GraphState) -> str:
    """Route after combine_tracks: empty result triggers retry or no_context_answer."""
    if not state.get("compressed_docs"):
        if state.get("retry_count", 0) >= LLM_RESPONSE_RETRY_LIMIT:
            logger.warning(
                "[ROUTE] max retries reached with no relevant documents — routing to no_context_answer"
            )
            return "no_context_answer"
        logger.warning(
            "[ROUTE] no relevant documents after compression — retrying (attempt %d)",
            state.get("retry_count", 0),
        )
        return "retry"
    return "generate_draft" if get_switches(state)["ENABLE_ANSWER_DRAFT_CREATION"] else "generate_answer"


# ── Post-draft routes ─────────────────────────────────────────────────────────

def route_after_generate_draft(state: GraphState) -> str:
    return "check_answer_quality" if get_switches(state)["ENABLE_ANSWER_QUALITY_CHECK"] else "generate_answer"


def route_after_quality_check(state: GraphState) -> str:
    verdict = state.get("quality_verdict", QUALITY_PASS_VERDICT)
    if verdict == QUALITY_PASS_VERDICT:
        return "generate_answer"
    budget_ok = (
        get_switches(state)["ENABLE_SUB_QUERY_GENERATION"]
        and state.get("retry_count", 0) < LLM_RESPONSE_RETRY_LIMIT
    )
    if budget_ok:
        logger.warning(
            "[ROUTE] quality verdict=%s with budget remaining (retry_count=%d) — retrying retrieval",
            verdict, state.get("retry_count", 0),
        )
        return "retry"
    logger.warning(
        "[ROUTE] quality verdict=%s but no budget left — using best-effort draft", verdict
    )
    return "generate_answer"


# ── Post-generate-answer route ────────────────────────────────────────────────

def route_after_generate_answer(state: GraphState) -> str:
    if get_switches(state)["ENABLE_AUTO_DISTILLATION"] and self_learner.should_learn():
        return "auto_distillation"
    return END


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Workflow Routing")

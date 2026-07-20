import logging
import time
from state import GraphState
from app_workflow.services.llm_setup import llm_tool
from app_workflow.services.llm_caller import llm_invoke
from app_workflow.services.services import embedding_manager
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.prompts import _ROLE_AND_RULES, _PROCESS_INSTRUCTIONS
from app_workflow.services.fix_llm_output import fix_llm_output, _parse_to_python
from app_workflow.services.switches import get_switches
from config import (
    PRE_RETRIEVAL_SIM_THRESHOLD,
    BRANCH_BUDGET_SHORT_WORD_COUNT,
    BRANCH_BUDGET_MEDIUM_WORD_COUNT,
    BRANCH_BUDGET_CONJUNCTION_KEYWORDS,
    BRANCH_BUDGET_FOR_SHORT_QUESTIONS,
    BRANCH_BUDGET_FOR_MEDIUM_QUESTIONS,
    BRANCH_BUDGET_FOR_CONJUNCTION_QUESTIONS,
)

logger = logging.getLogger(__name__)


def adaptive_branch_budget(user_query: str) -> int:
    """Return how many variants are worth generating based on query complexity."""
    word_count = len(user_query.split())
    has_conjunction = any(
        w in user_query.lower()
        for w in BRANCH_BUDGET_CONJUNCTION_KEYWORDS
    )
    if word_count <= BRANCH_BUDGET_SHORT_WORD_COUNT and not has_conjunction:
        budget = BRANCH_BUDGET_FOR_SHORT_QUESTIONS
    elif word_count <= BRANCH_BUDGET_MEDIUM_WORD_COUNT or not has_conjunction:
        budget = BRANCH_BUDGET_FOR_MEDIUM_QUESTIONS
    else:
        budget = BRANCH_BUDGET_FOR_CONJUNCTION_QUESTIONS
    logger.debug(
        "[QUERY_VARIANTS] budget=%d (words=%d, has_conjunction=%s)",
        budget, word_count, has_conjunction,
    )
    return budget


def pre_retrieval_filter(
    user_query: str,
    raw_variants: list[str],
    inter_variant_threshold: float = PRE_RETRIEVAL_SIM_THRESHOLD,
    max_variants: int | None = None,
) -> tuple[list[str], list[str]]:
    """
    Phase 1: Pairwise inter-variant dedup — drop variants too similar to an
             already-kept variant (greedy, first occurrence wins).
    Phase 2: Rank survivors by cosine similarity to user_query (descending)
             and cap to max_variants.

    Returns (kept, redundant).
    """
    if not raw_variants:
        return [], []

    # Phase 1: inter-variant pairwise deduplication
    variant_embs: list[tuple[str, list]] = [
        (v, embedding_manager.generate_embedding(v.strip().lower()))
        for v in raw_variants
    ]
    kept_embs: list[tuple[str, list]] = []
    redundant: list[str] = []

    for variant, var_emb in variant_embs:
        is_redundant = any(
            embedding_manager.cosine_similarity(var_emb, kept_emb) >= inter_variant_threshold
            for _, kept_emb in kept_embs
        )
        if is_redundant:
            redundant.append(variant)
            logger.debug("[QUERY_VARIANTS] pre_filter inter-dup dropped: %r", variant[:60])
        else:
            kept_embs.append((variant, var_emb))

    # Phase 2: rank by similarity to user_query; cap to budget
    user_emb = embedding_manager.generate_embedding(user_query.strip().lower())
    sims: dict[str, float] = {
        v: embedding_manager.cosine_similarity(user_emb, ve) for v, ve in kept_embs
    }
    sorted_kept = sorted(sims, key=sims.__getitem__, reverse=True)

    if max_variants is not None and len(sorted_kept) > max_variants:
        capped = sorted_kept[max_variants:]
        redundant.extend(capped)
        sorted_kept = sorted_kept[:max_variants]
        logger.debug("[QUERY_VARIANTS] pre_filter budget cap: dropped %d", len(capped))

    logger.info(
        "[QUERY_VARIANTS] pre_retrieval_filter: kept=%d, redundant=%d",
        len(sorted_kept), len(redundant),
    )
    return sorted_kept, redundant


def _build_system_prompt(
    blocked_variants: list[str],
    prior_thumbdowns: list[dict] | None = None,
    max_variants: int = 3,
) -> str:
    """Mirror of agent_query._build_system_prompt — same ordering and blocks."""
    parts = [_ROLE_AND_RULES]

    parts.append(
        f"RETRIEVAL BUDGET — Generate exactly {max_variants} query variant(s)"
        " for this query. Do NOT exceed this limit."
    )

    if blocked_variants:
        lines = "\n".join(f'  - "{v}"' for v in blocked_variants)
        parts.append(
            "BLOCKED QUERY VARIANTS — These exact phrasings retrieved 0 useful chunks"
            " the last time this question was asked. Do NOT reuse them under any"
            " circumstances. Generate different, semantically distinct reformulations:"
            f"\n{lines}"
        )

    if prior_thumbdowns:
        # ── Passive block: what went wrong (near _ROLE_AND_RULES) ────────────
        td_history_block = (
            "USER-FLAGGED PRIOR FAILURE — This same question (or a near-identical one)"
            " was asked before and the user explicitly marked the answer as bad. Below is"
            " what went wrong last time, including the exact query reformulations that were"
            " tried and the chunks they retrieved.\n"
            "  1. AVOID re-using the same query reformulations — they led to a bad answer.\n"
            "  2. AVOID grounding your answer in the same chunks unless you can clearly"
            " interpret them differently.\n"
            "  3. Try genuinely different angles, vocabulary, and sub-topics.\n"
        )
        for i, td in enumerate(prior_thumbdowns, start=1):
            td_history_block += f"\n--- Prior failure #{i} ---\n"
            td_history_block += f"Original query : {td.get('original_query', '')}\n"
            ufb = td.get("user_feedback", "")
            if ufb:
                td_history_block += f"User feedback  : {ufb}\n"
            bad_ans = td.get("bad_answer", "")
            if bad_ans:
                snippet = bad_ans[:300] + ("..." if len(bad_ans) > 300 else "")
                td_history_block += f"Bad answer was : {snippet}\n"
            variants = td.get("variants", []) or []
            if variants:
                td_history_block += "Reformulations that were tried (DO NOT REUSE):\n"
                for v in variants:
                    td_history_block += f'  - "{v.get("query", "")}"\n'
                    document_chunks = v.get("document_chunks", v.get("chunks", [])) or []
                    learned_qa_chunks = v.get("learned_qa_chunks", []) or []
                    for track_name, chunks in (
                        ("learned_qa", learned_qa_chunks),
                        ("documents", document_chunks),
                    ):
                        for c in chunks[:2]:
                            content = (c.get("content") or "").replace("\n", " ")
                            preview = content[:200] + ("..." if len(content) > 200 else "")
                            td_history_block += (
                                f"      retrieved {track_name} "
                                f"[{c.get('source', '?')}]: {preview}\n"
                            )
        parts.append(td_history_block)

    # PROCESS goes after the history context — same position as in agent_query.py
    parts.append(_PROCESS_INSTRUCTIONS)

    if prior_thumbdowns:
        # ── Active block: what to seek — appended LAST so recency bias helps ──
        feedback_lines = []
        for td in prior_thumbdowns:
            ufb = (td.get("user_feedback") or "").strip()
            if ufb:
                feedback_lines.append(f'  - "{ufb}"')
        if feedback_lines:
            fb_str = "\n".join(feedback_lines)
            active_block = (
                "PRIORITY — USER FEEDBACK MUST BE ADDRESSED\n"
                "The user previously flagged an answer to this exact question as bad and"
                " told you specifically what was missing or wrong:\n"
                f"{fb_str}\n\n"
                "You MUST generate at least one retrieve_documents query that directly"
                " targets the topics or facts described in this feedback. Do not treat"
                " this as a passive hint — it is your primary retrieval objective."
            )
            parts.append(active_block)

    return "\n\n".join(parts)


def generate_query_variants(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    user_query = state["user_input"]
    sw = get_switches(state)

    if not sw["ENABLE_SUB_QUERY_GENERATION"]:
        logger.debug("[QUERY_VARIANTS] sub-query generation disabled — using original query")
        timing_tracker.record("Sub-Query Generation", time.perf_counter() - _t0)
        return {"query_variants": [user_query], "retry_count": state["retry_count"] + 1}

    max_variants = adaptive_branch_budget(user_query)

    blocked_variants: list[str] = list(state.get("blocked_variants") or [])  # type: ignore[arg-type]
    prior_thumbdowns: list[dict] = list(state.get("prior_thumbdowns") or [])  # type: ignore[arg-type]

    system_prompt = _build_system_prompt(
        blocked_variants,
        prior_thumbdowns if prior_thumbdowns else None,
        max_variants,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    logger.debug("[QUERY_VARIANTS] Invoking LLM for direct query-variant generation")
    result = llm_invoke(
        llm_tool,
        messages,
        caller_tag="QUERY-VARIANTS",
        config=config,
    )

    raw_variants: list[str] = []

    if result.ok:
        raw = result.content
        if sw["ENABLE_QUERY_VARIANTS_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
            parsed, parsed_ok = fix_llm_output("query_variants", raw, llm=llm_tool, config=config)
        else:
            parsed = _parse_to_python(raw)
            parsed_ok = isinstance(parsed, list)

        if parsed_ok and isinstance(parsed, list):
            seen: set[str] = set()
            for item in parsed:
                q = (item.get("query") or "").strip() if isinstance(item, dict) else ""
                if q and q.lower() not in seen:
                    raw_variants.append(q)
                    seen.add(q.lower())
            logger.debug("[QUERY_VARIANTS] LLM returned %d variant(s)", len(raw_variants))
        else:
            logger.warning(
                "[QUERY_VARIANTS] failed to parse variant list from LLM response: %r",
                raw[:200],
            )
    else:
        logger.warning(
            "[QUERY_VARIANTS] LLM call failed (%s) — falling back to user query",
            result.error_kind,
        )

    if not raw_variants:
        logger.warning("[QUERY_VARIANTS] No query variants produced — falling back to user query")
        raw_variants = [user_query]

    # Strip variants that are known to have failed for this query
    blocked_set = {v.strip().lower() for v in blocked_variants}
    non_failed = [v for v in raw_variants if v.strip().lower() not in blocked_set]
    if not non_failed:
        non_failed = raw_variants  # all blocked — keep originals as fallback

    # Pre-retrieval filter: inter-variant dedup (≥0.95 sim) then rank+cap to budget
    query_variants, _ = pre_retrieval_filter(user_query, non_failed, max_variants=max_variants)
    if not query_variants:
        query_variants = non_failed[:max_variants] or [user_query]

    logger.debug(
        "[QUERY_VARIANTS] %d query variant(s) after filter: %s",
        len(query_variants), query_variants,
    )

    timing_tracker.record("Sub-Query Generation", time.perf_counter() - _t0)
    # Each variant is dispatched to a parallel `retrieve` node via fan_out_retrievals
    # (routes.py Send mechanism) — that is where each variant's query runs in parallel.
    return {"query_variants": query_variants, "retry_count": state["retry_count"] + 1}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Query Variants", exclude={"generate_query_variants"})

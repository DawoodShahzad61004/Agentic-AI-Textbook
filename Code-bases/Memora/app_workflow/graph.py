from langgraph.graph import StateGraph, START, END
from state import GraphState
from nodes import (
    user_input_node,
    cmd_stats,
    cmd_learn,
    cmd_bad,
    cmd_exit,
    generate_query_variants,
    retrieve,
    post_retrieval_filter_node,
    validate_document_retrieval,
    validate_learned_qa_retrieval,
    dedup_merge_documents,
    dedup_merge_learned_qa,
    validate_dedup_merge_documents,
    validate_dedup_merge_learned_qa,
    execute_nac_documents,
    validate_nac_documents,
    execute_dc_documents,
    validate_dc_documents,
    execute_lbc_documents,
    validate_lbc_documents,
    execute_dc_learned_qa,
    validate_dc_learned_qa,
    execute_lbc_learned_qa,
    validate_lbc_learned_qa,
    combine_tracks,
    generate_draft,
    check_answer_quality,
    generate_answer,
    auto_distillation,
    no_context_answer,
)
from routes import (
    route_user_input,
    fan_out_retrievals,
    route_after_combine,
    route_nac_documents_to_validator,
    route_dc_documents_to_validator,
    route_dc_learned_qa_to_validator,
    route_after_generate_draft,
    route_after_quality_check,
    route_after_generate_answer,
)


def build_graph():
    graph = StateGraph(GraphState)

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.add_node("user_input", user_input_node)

    # ── Command nodes (each terminates at END) ────────────────────────────────
    graph.add_node("cmd_stats", cmd_stats)
    graph.add_node("cmd_learn", cmd_learn)
    graph.add_node("cmd_bad", cmd_bad)
    graph.add_node("cmd_exit", cmd_exit)

    # ── Query variant generation ──────────────────────────────────────────────
    graph.add_node("generate_query_variants", generate_query_variants)

    # ── Parallel retrieval ────────────────────────────────────────────────────
    graph.add_node("retrieve", retrieve)

    # ── Post-retrieval filter (fan-in barrier after all retrieve branches) ────
    graph.add_node("post_retrieval_filter", post_retrieval_filter_node)

    # ── Per-track retrieval validation (parallel) ─────────────────────────────
    graph.add_node("validate_document_retrieval", validate_document_retrieval)
    graph.add_node("validate_learned_qa_retrieval", validate_learned_qa_retrieval)

    # ── Per-track dedup-merge (parallel) ──────────────────────────────────────
    graph.add_node("dedup_merge_documents", dedup_merge_documents)
    graph.add_node("dedup_merge_learned_qa", dedup_merge_learned_qa)

    # ── Per-track dedup-merge validation (parallel, always-present pass-throughs)
    graph.add_node("validate_dedup_merge_documents", validate_dedup_merge_documents)
    graph.add_node("validate_dedup_merge_learned_qa", validate_dedup_merge_learned_qa)

    # ── Document compression track (parallel with learned_qa track) ───────────
    # NAC → DC → LBC, each with an optional validation step.
    # validate_LBC_documents is always present (pass-through when validation is
    # disabled) to give combine_tracks a fixed set of two predecessors.
    graph.add_node("NAC_documents", execute_nac_documents)
    graph.add_node("validate_NAC_documents", validate_nac_documents)
    graph.add_node("DC_documents", execute_dc_documents)
    graph.add_node("validate_DC_documents", validate_dc_documents)
    graph.add_node("LBC_documents", execute_lbc_documents)
    graph.add_node("validate_LBC_documents", validate_lbc_documents)

    # ── Learned-QA compression track (parallel with documents track) ──────────
    # DC → LBC (no NAC), each with an optional validation step.
    # validate_LBC_learned_qa is always present for the same fan-in reason.
    graph.add_node("DC_learned_qa", execute_dc_learned_qa)
    graph.add_node("validate_DC_learned_qa", validate_dc_learned_qa)
    graph.add_node("LBC_learned_qa", execute_lbc_learned_qa)
    graph.add_node("validate_LBC_learned_qa", validate_lbc_learned_qa)

    # ── Track join (fan-in barrier after both compression pipelines complete) ──
    # combine_tracks waits for BOTH validate_LBC_* nodes to finish. The two
    # tracks have unequal depth (documents: NAC→DC→LBC, learned_qa: DC→LBC),
    # so they land in different supersteps — a plain multi-predecessor node
    # would fire once per predecessor instead of once total. defer=True makes
    # this a true barrier: LangGraph holds the node until every other pending
    # task (i.e. both tracks) has finished, then runs it exactly once.
    graph.add_node("combine_tracks", combine_tracks, defer=True)
    graph.add_node("no_context_answer", no_context_answer)

    # ── Answer generation pipeline ────────────────────────────────────────────
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("check_answer_quality", check_answer_quality)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("auto_distillation", auto_distillation)

    # ══════════════════════════════════════════════════════════════════════════
    # Edges
    # ══════════════════════════════════════════════════════════════════════════

    graph.add_edge(START, "user_input")
    graph.add_conditional_edges(
        "user_input",
        route_user_input,
        {
            "cmd_stats": "cmd_stats",
            "cmd_learn": "cmd_learn",
            "cmd_bad": "cmd_bad",
            "cmd_exit": "cmd_exit",
            "generate_query_variants": "generate_query_variants",
        },
    )

    graph.add_edge("cmd_stats", END)
    graph.add_edge("cmd_learn", END)
    graph.add_edge("cmd_bad", END)
    # cmd_exit raises SystemExit, no outgoing edge needed.

    # ── Fan-out: one Send per variant → retrieve (all parallel) ──────────────
    graph.add_conditional_edges(
        "generate_query_variants",
        fan_out_retrievals,
        ["retrieve"],
    )

    # ── After retrieve barrier: post_retrieval_filter runs once, then fan-out ──
    graph.add_edge("retrieve", "post_retrieval_filter")
    graph.add_edge("post_retrieval_filter", "validate_document_retrieval")
    graph.add_edge("post_retrieval_filter", "validate_learned_qa_retrieval")

    # ── Each validation feeds its own dedup-merge (parallel pair) ─────────────
    graph.add_edge("validate_document_retrieval", "dedup_merge_documents")
    graph.add_edge("validate_learned_qa_retrieval", "dedup_merge_learned_qa")

    # ── Each dedup-merge feeds its own validator (parallel pair) ──────────────
    graph.add_edge("dedup_merge_documents", "validate_dedup_merge_documents")
    graph.add_edge("dedup_merge_learned_qa", "validate_dedup_merge_learned_qa")

    # ── Document compression track ────────────────────────────────────────────
    graph.add_edge("validate_dedup_merge_documents", "NAC_documents")
    graph.add_conditional_edges(
        "NAC_documents",
        route_nac_documents_to_validator,
        {"validate_NAC_documents": "validate_NAC_documents", "DC_documents": "DC_documents"},
    )
    graph.add_edge("validate_NAC_documents", "DC_documents")
    graph.add_conditional_edges(
        "DC_documents",
        route_dc_documents_to_validator,
        {"validate_DC_documents": "validate_DC_documents", "LBC_documents": "LBC_documents"},
    )
    graph.add_edge("validate_DC_documents", "LBC_documents")
    graph.add_edge("LBC_documents", "validate_LBC_documents")
    graph.add_edge("validate_LBC_documents", "combine_tracks")

    # ── Learned-QA compression track ─────────────────────────────────────────
    graph.add_edge("validate_dedup_merge_learned_qa", "DC_learned_qa")
    graph.add_conditional_edges(
        "DC_learned_qa",
        route_dc_learned_qa_to_validator,
        {"validate_DC_learned_qa": "validate_DC_learned_qa", "LBC_learned_qa": "LBC_learned_qa"},
    )
    graph.add_edge("validate_DC_learned_qa", "LBC_learned_qa")
    graph.add_edge("LBC_learned_qa", "validate_LBC_learned_qa")
    graph.add_edge("validate_LBC_learned_qa", "combine_tracks")

    # ── After combine: route to draft/answer pipeline, retry, or no_context_answer
    graph.add_conditional_edges(
        "combine_tracks",
        route_after_combine,
        {
            "generate_draft": "generate_draft",
            "generate_answer": "generate_answer",
            "retry": "generate_query_variants",
            "no_context_answer": "no_context_answer",
        },
    )
    graph.add_edge("no_context_answer", END)

    # ── Draft → quality check → generate_answer ───────────────────────────────
    graph.add_conditional_edges(
        "generate_draft",
        route_after_generate_draft,
        {"check_answer_quality": "check_answer_quality", "generate_answer": "generate_answer"},
    )
    graph.add_conditional_edges(
        "check_answer_quality",
        route_after_quality_check,
        {"generate_answer": "generate_answer", "retry": "generate_query_variants"},
    )

    # ── Final answer → optional distillation → END ────────────────────────────
    graph.add_conditional_edges(
        "generate_answer",
        route_after_generate_answer,
        {"auto_distillation": "auto_distillation", END: END},
    )
    graph.add_edge("auto_distillation", END)

    return graph.compile()

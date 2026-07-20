import operator
from typing import TypedDict, Annotated, NotRequired


class GraphState(TypedDict):
    user_input: str
    query: str
    query_variants: list[str]
    answer: str
    retry_count: int
    # Per-request tracing identifier (set by the API layer before graph invocation)
    request_id: NotRequired[str]
    # Command routing
    command: NotRequired[str]
    user_feedback: NotRequired[str]
    # Per-request ENABLE_* switch overrides (see services/switches.py). Absent
    # or empty means "use config.py defaults" for every switch.
    switches: NotRequired[dict[str, bool]]
    # Feedback-driven retrieval context (populated by user_input_node)
    blocked_variants: NotRequired[list[str]]
    prior_thumbdowns: NotRequired[list[dict]]

    # ── Per-track raw retrieval ───────────────────────────────────────────────
    retrieved_document_chunks: Annotated[list[dict], operator.add]
    retrieved_learned_qa_chunks: Annotated[list[dict], operator.add]

    # ── Per-track validated ───────────────────────────────────────────────────
    validated_document_chunks: list[dict]
    validated_learned_qa_chunks: list[dict]

    # ── Per-track dedup-merged ────────────────────────────────────────────────
    dedup_merged_document_chunks: list[dict]
    dedup_merged_learned_qa_chunks: list[dict]
    dedup_merge_document_pairs: NotRequired[list[dict]]  
    dedup_merge_learned_qa_pairs: NotRequired[list[dict]]
    
    # ── Document compression track (NAC → DC → LBC, parallel with learned_qa) ─
    nac_output_document_chunks: list[dict]
    dc_output_document_chunks: list[dict]
    compressed_document_chunks: list[dict]
    nac_merge_pairs_documents: NotRequired[list[dict]]
    dc_groups_per_window_documents: NotRequired[list[dict]]
    lbc_validation_pairs_documents: NotRequired[list[dict]]

    # ── Learned-QA compression track (DC → LBC, parallel with documents) ──────
    dc_output_learned_qa_chunks: list[dict]
    compressed_learned_qa_chunks: list[dict]
    dc_groups_per_window_learned_qa: NotRequired[list[dict]]
    lbc_validation_pairs_learned_qa: NotRequired[list[dict]]

    # ── Final combined output (built by combine_tracks after both tracks finish)
    compressed_docs: list[dict]

    # ── Answer generation pipeline ────────────────────────────────────────────
    draft: NotRequired[str]          
    quality_verdict: NotRequired[str]

    # ── Feedback persistence (accumulated across all parallel retrieve branches)
    variants_with_chunks: Annotated[list[dict], operator.add]
    newly_failed_variants: Annotated[list[str], operator.add]

    # ── Post-retrieval filter output (set by post_retrieval_filter_node) ─────
    post_filtered_document_chunks: NotRequired[list[dict]]
    post_filtered_learned_qa_chunks: NotRequired[list[dict]]

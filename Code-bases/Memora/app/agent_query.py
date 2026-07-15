import json, os, re, argparse, uuid
import logging
import time
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from llm_caller import llm_invoke, LLMErrorKind, LLMRateLimitAbortError
from validators import validate_retrieval, validate_merge

from embedding_manager import EmbeddingManager
from vector_store import VectorStore
from retriever import RAGRetriever
from tools import make_tools, make_check_answer_quality
from context_compression import format_precedence_context_for_llm, merge_similar_chunks
from feedback_store import FeedbackStore, MIN_FEEDBACK_LEN
from learned_qa_store import get_or_create_learned_qa_collection
from self_learner import SelfLearner
from logger_config import setup_logging
import timing_tracker as _timing

logger = logging.getLogger(__name__)

from db import failed_variants_col
from config import (
    VECTOR_STORE_PATH,
    COLLECTION_NAME,
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_ITERATION,
    MAX_TOTAL_RETRIEVALS,
    LEARN_EVERY_N,
    PAD_TOKENS,
    MERGE_SIMILARITY_THRESHOLD,
    LLM_RESPONSE_RETRY_LIMIT,
    ENABLE_SUB_QUERY_GENERATION,
    ENABLE_RETRIEVAL_DEDUP_MERGE,
    ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION,
    ENABLE_RETRIEVAL_VALIDATION,
    ENABLE_ANSWER_DRAFT_CREATION,
    ENABLE_ANSWER_QUALITY_CHECK,
    ENABLE_AUTO_DISTILLATION,
)

from prompts import (
    _ROLE_AND_RULES,
    _PROCESS_INSTRUCTIONS,
    NO_CONTEXT_ANSWER,
    _THIN,
    _THICK,
)

def _normalize_query(q: str) -> str:
    return q.lower().strip()

def _project_chunks_for_output(chunks: list[dict]) -> list[dict]:
    """Return serializable final-pipeline chunks without internal embeddings."""
    return [
        {
            "content": chunk.get("content", ""),
            "source": chunk.get(
                "source",
                (chunk.get("metadata") or {}).get("source", "?"),
            ),
        }
        for chunk in chunks
        if chunk.get("content")
    ]

def _accumulated_retrieval_fields(agent_state: dict) -> dict:
    return {
        "document_chunks": _project_chunks_for_output(
            agent_state.get("accumulated_document_chunks", []) or []
        ),
        "learned_qa_chunks": _project_chunks_for_output(
            agent_state.get("accumulated_learned_qa_chunks", []) or []
        ),
    }

def _build_system_prompt(
    blocked_variants: list[str],
    prior_thumbdowns: list[dict] | None = None,
) -> str:
    parts = [_ROLE_AND_RULES]

    if blocked_variants:
        lines = "\n".join(f'  - "{v}"' for v in blocked_variants)
        parts.append(
            f"BLOCKED QUERY VARIANTS — These exact phrasings retrieved 0 useful chunks"
            f" the last time this question was asked. Do NOT reuse them under any"
            f" circumstances. Generate different, semantically distinct reformulations:\n{lines}"
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

    # PROCESS goes after the history context and before the active priority block
    parts.append(_PROCESS_INSTRUCTIONS)

    if prior_thumbdowns:
        # ── Active block: what to seek — appended LAST, closest to user message
        # so recency bias works in our favour.
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

def _serialize_messages(messages: list) -> str:
    lines = []
    for i, m in enumerate(messages):
        if isinstance(m, dict):
            role    = m.get("role", "?")
            content = str(m.get("content", ""))
            tid     = m.get("tool_call_id", "")
            header  = f"  [{i}] role={role}" + (f"  tool_call_id={tid}" if tid else "")
            lines.append(header)
            lines.append(f"      content: {content[:600]}{'...' if len(content) > 600 else ''}")
        else:
            # LangChain AIMessage
            content    = str(getattr(m, "content", ""))
            tool_calls = getattr(m, "tool_calls", []) or []
            lines.append(f"  [{i}] role=assistant")
            lines.append(f"      content: {content[:600]}{'...' if len(content) > 600 else ''}")
            for tc in tool_calls:
                lines.append(f"      tool_call → {tc['name']}  args={json.dumps(tc['args'])}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# run_agent  — retrieval/draft state machine with terminal final synthesis
#
#   Phase 1 — RETRIEVE : LLM calls retrieve_documents (and optionally
#                        compress_context to signal it's done).
#                        Transitions to COMPRESS when:
#                          (a) LLM emits text with no tool calls, or
#                          (b) retrieval cap is hit, or
#                          (c) LLM called compress_context itself.
#
#   Phase 2 — COMPRESS : if both accumulated tracks are empty → return canned
#                        NO_CONTEXT_ANSWER immediately, no more LLM calls.
#                        Otherwise, force compress_context if not already
#                        done, then transition to ANSWER.
#
#   Phase 3 — ANSWER   : when draft creation is enabled, call LLM with NO tool
#                        schemas to produce a draft answer. Otherwise, generate
#                        the final answer directly from compressed context.
#
#   Phase 4 — JUDGE    : when draft creation and quality checking are enabled,
#                        call check_answer_quality as a plain function.
#                        OK → use the approved draft to generate the final answer.
#                        INSUFFICIENT + budget remains → reset to RETRIEVE
#                        with a message asking for better query variants.
#
#   FINAL SYNTHESIS    : call LLM with NO tool schemas. Use the draft when one
#                        was created; otherwise answer directly from context.
# ─────────────────────────────────────────────────────────────────────────────

def run_agent(
    query: str,
    llm,
    merge_llm,
    judge_llm,
    tool_schemas: list,
    callables: dict,
    check_answer_quality,          # plain callable, NOT an LLM tool
    retriever: RAGRetriever,
    agent_state: dict,
    blocked_variants: list[str] | None = None,
    prior_thumbdowns: list[dict] | None = None,
    request_id: str = "",
) -> tuple[dict, list[str]]:

    newly_failed: list[str] = []
    messages: list = [
        {
            "role": "system",
            "content": _build_system_prompt(blocked_variants or [], prior_thumbdowns or []),
        },
        {"role": "user", "content": query},
    ]
    iterations = 0
    retrieved_sources = []
    variants_with_chunks: list[dict] = []
    total_retrievals = 0
    final_quality = "INSUFFICIENT"
    total_prompt_tokens = 0
    total_completion_tokens = 0
    all_tried_queries: set[str] = set()
    draft_answer = ""

    # ── Reset agent_state for this query ─────────────────────────────────────
    agent_state.clear()
    agent_state["request_id"] = request_id
    agent_state["query"] = query
    agent_state["accumulated_document_chunks"] = []
    agent_state["accumulated_learned_qa_chunks"] = []
    agent_state["messages"] = messages
    agent_state["embedding_manager"] = retriever.embedding_manager
    agent_state["compress_done"] = False

    # ── Phase tracker ─────────────────────────────────────────────────────────
    # RETRIEVE → COMPRESS → ANSWER → JUDGE → (back to RETRIEVE if INSUFFICIENT)
    phase = "RETRIEVE"

    # ── Retrieval tool schemas (used in RETRIEVE phase) ───────────────────────
    retrieve_tool_schemas = [s for s in tool_schemas
                             if s["function"]["name"] in ("retrieve_documents", "compress_context")]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _new_synthetic_id(prefix: str) -> str:
        return f"call_sys_{prefix}_{uuid.uuid4().hex[:12]}"

    def _has_accumulated_chunks() -> bool:
        return bool(
            agent_state["accumulated_learned_qa_chunks"]
            or agent_state["accumulated_document_chunks"]
        )

    def _format_accumulated_context() -> str:
        return format_precedence_context_for_llm(
            agent_state["accumulated_learned_qa_chunks"],
            agent_state["accumulated_document_chunks"],
        )

    def _final_retrieval_fields() -> dict:
        return _accumulated_retrieval_fields(agent_state)

    def _inject_synthetic_tool_call(tool_name: str, tool_args: dict, reason: str) -> str:
        synth_id = _new_synthetic_id(tool_name)
        logger.debug(f"\n{_THIN}")
        logger.debug(f"  [ENFORCE] system injecting synthetic call to {tool_name}() — reason: {reason}")
        logger.debug(_THIN)
        messages.append({
            "role": "assistant",
            "content": f"[system-injected tool call] Running {tool_name}() because: {reason}",
            "tool_calls": [{"id": synth_id, "name": tool_name, "args": dict(tool_args)}],
        })
        agent_state["messages"] = messages
        if tool_name not in callables:
            result_str = f"[ENFORCE] unknown tool '{tool_name}'"
        else:
            try:
                result_str = callables[tool_name](**tool_args)
            except TypeError as e:
                result_str = f"[ENFORCE] {tool_name} dispatch error: {e}"
        messages.append({
            "role": "tool",
            "tool_call_id": synth_id,
            "content": result_str,
        })
        return result_str

    def _generate_final_answer(
        *,
        draft: str = "",
        quality: str = "OK",
    ) -> tuple[dict, list[str]]:
        """Generate the user-facing final answer, optionally using a draft."""
        nonlocal total_prompt_tokens, total_completion_tokens

        logger.debug(f"\n{_THICK}")
        if draft:
            logger.info(f"  [PHASE: FINAL]  Invoking LLM with NO tool schemas using the draft.")
        else:
            logger.info(f"  [PHASE: FINAL]  Invoking LLM with NO tool schemas directly from context.")
        logger.debug(_THICK)

        if draft:
            final_prompt = (
                "Using ONLY the compressed context and the latest answer draft above, "
                "write the final answer now. Use the draft as working material, but "
                "improve its clarity and organization where useful. Do not add claims "
                "that are not supported by the compressed context. If learned QA and "
                "document context conflict, prefer learned QA.\n"
                "Plain prose paragraphs only. No tool calls. No headings or bullet lists.\n"
                "Cite sources inline as [Source: filename]. Max 400 words."
            )
        else:
            final_prompt = (
                "Using ONLY the compressed context provided in the conversation above "
                "(the compress_context tool result), write the final answer now. "
                "If learned QA and document context conflict, prefer learned QA.\n"
                "Plain prose paragraphs only. No tool calls. No headings or bullet lists.\n"
                "Cite sources inline as [Source: filename]. Max 400 words."
            )

        final_messages = [*messages, {"role": "user", "content": final_prompt}]
        final_result = None
        for attempt in range(1, LLM_RESPONSE_RETRY_LIMIT + 1):
            final_result = llm_invoke(
                llm, final_messages, tools=None, caller_tag="AGENT-FINAL"
            )
            if final_result.ok:
                break
            if final_result.error_kind in (
                LLMErrorKind.SERVER_ERROR, LLMErrorKind.CONNECTION,
                LLMErrorKind.TIMEOUT,
            ) and attempt < LLM_RESPONSE_RETRY_LIMIT:
                logger.warning(f"  [FINAL] transient error — retrying "
                      f"({attempt}/{LLM_RESPONSE_RETRY_LIMIT})")
                continue

            return {
                "answer": f"Final answer LLM call failed: {final_result.error_message}",
                "sources": retrieved_sources,
                "iterations": iterations,
                "quality": "INSUFFICIENT",
                **_final_retrieval_fields(),
                "variants": variants_with_chunks,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
            }, newly_failed

        usage = (getattr(final_result.response, "response_metadata", {}) or {}).get(
            "token_usage", {}
        )
        total_prompt_tokens += usage.get("prompt_tokens", 0)
        total_completion_tokens += usage.get("completion_tokens", 0)
        final_answer = final_result.content or ""

        return {
            "answer": final_answer,
            "sources": retrieved_sources,
            "iterations": iterations,
            "quality": quality,
            **_final_retrieval_fields(),
            "variants": variants_with_chunks,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
        }, newly_failed

    def _handle_retrieve_documents_call(tool_call: dict) -> str:
        """Execute one two-track retrieve_documents call and maintain state."""
        nonlocal total_retrievals
        args = tool_call["args"]
        accumulated_documents = agent_state["accumulated_document_chunks"]
        accumulated_learned_qa = agent_state["accumulated_learned_qa_chunks"]

        if total_retrievals >= MAX_TOTAL_RETRIEVALS:
            result = "Retrieval limit reached. Use what you have to answer."
            logger.warning(f"  [SKIPPED] retrieval cap ({MAX_TOTAL_RETRIEVALS}) reached")
            return result

        q_normalized = args["query"].strip().lower()
        if q_normalized in all_tried_queries:
            logger.warning(f"  [DEDUP] Skipping already-tried query: \"{args['query']}\"")
            return "You already tried this exact query. Try a genuinely different angle."
        all_tried_queries.add(q_normalized)

        result = callables["retrieve_documents"](query=args["query"])
        total_retrievals += 1

        document_chunks = retriever.get_last_document_chunks()
        learned_qa_chunks = retriever.get_last_learned_qa_chunks()

        def _variant_chunks(chunks: list[dict]) -> list[dict]:
            return [
                {
                    "content": c.get("content", ""),
                    "source": (c.get("metadata") or {}).get("source", "?"),
                }
                for c in chunks
            ]

        variants_with_chunks.append({
            "query": args["query"],
            "document_chunks": _variant_chunks(document_chunks),
            "learned_qa_chunks": _variant_chunks(learned_qa_chunks),
        })

        if not document_chunks and not learned_qa_chunks:
            newly_failed.append(args["query"])
            logger.warning(f"  [FAILED VARIANT] recorded: \"{args['query']}\"")
            retrieved_sources.append({"query": args["query"], "preview": result[:200]})
            agent_state["accumulated_document_chunks"] = accumulated_documents
            agent_state["accumulated_learned_qa_chunks"] = accumulated_learned_qa
            logger.debug(f"\n  [AGENT STATE] total_retrievals={total_retrievals}/{MAX_TOTAL_RETRIEVALS} | "
                  f"documents={len(accumulated_documents)} | "
                  f"learned_qa={len(accumulated_learned_qa)}")
            return result

        validation_summaries: list[str] = []

        def _validate_track(track_name: str, chunks: list[dict]) -> list[dict]:
            if not chunks:
                return []
            if not ENABLE_RETRIEVAL_VALIDATION:
                logger.debug(
                    f"  [VALIDATE-RETRIEVAL:{track_name}] disabled - "
                    f"using all {len(chunks)} chunk(s) as-is."
                )
                return chunks

            retrieval_check = validate_retrieval(
                query=query,
                chunks=chunks,
                judge_llm=judge_llm,
            )
            irrelevant_idx: set[int] = {
                pc.get("index")
                for pc in retrieval_check.get("per_chunk", [])
                if pc.get("relevant") is False and isinstance(pc.get("index"), int)
            }
            if retrieval_check["verdict"] == "UNKNOWN":
                irrelevant_idx = set()
            kept_chunks = [
                c for i, c in enumerate(chunks) if i not in irrelevant_idx
            ]
            logger.debug(
                f"  [VALIDATE-RETRIEVAL:{track_name}] "
                f"kept {len(kept_chunks)}/{len(chunks)} chunk(s)."
            )
            if retrieval_check["verdict"] in ("FAIL", "PARTIAL"):
                validation_summaries.append(
                    f"{track_name}={retrieval_check['verdict']} "
                    f"({retrieval_check['relevant_count']}/"
                    f"{retrieval_check['total_count']} relevant): "
                    f"{retrieval_check['overall_reason']}"
                )
            return kept_chunks

        learned_qa_chunks = _validate_track("learned_qa", learned_qa_chunks)
        document_chunks = _validate_track("documents", document_chunks)

        if validation_summaries:
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"] + "_judge",
                "content": (
                    "[RETRIEVAL JUDGE] The retrieval tracks were validated separately. "
                    "Irrelevant chunks were removed. "
                    + " | ".join(validation_summaries)
                ),
            })

        def _format_track(title: str, chunks: list[dict]) -> str:
            if not chunks:
                return f"[{title}]\nNo relevant chunks found."
            return f"[{title}]\n" + "\n\n".join(
                f"[Source: {c['metadata'].get('source', '?')}, "
                f"score: {c['similarity_score']:.3f}]\n{c['content']}"
                for c in chunks
            )

        result = "\n\n".join([
            _format_track("LEARNED QA RESULTS - HIGH PRIORITY", learned_qa_chunks),
            _format_track("DOCUMENT RESULTS - SECONDARY", document_chunks),
        ])
        if not learned_qa_chunks and not document_chunks:
            result = "No relevant documents found for this query."
            newly_failed.append(args["query"])
            retrieved_sources.append({"query": args["query"], "preview": result})
            return result

        def _accumulate_track(
            track_name: str,
            accumulated_chunks: list[dict],
            new_chunks: list[dict],
        ) -> list[dict]:
            for c in new_chunks:
                content = c.get("content", "")
                if not content:
                    continue
                accumulated_chunks.append({
                    "content": content,
                    "source": (c.get("metadata") or {}).get("source", "?"),
                    **({"embedding": retriever.embedding_manager.generate_embedding(content)}
                       if ENABLE_RETRIEVAL_DEDUP_MERGE else {}),
                    **({"chunk_seq": c["metadata"]["chunk_seq"]}
                       if isinstance((c.get("metadata") or {}).get("chunk_seq"), int)
                       else {}),
                })

            if not ENABLE_RETRIEVAL_DEDUP_MERGE:
                return accumulated_chunks

            claimed: set[int] = set()
            merge_groups: list[list[int]] = []
            for i in range(len(accumulated_chunks)):
                if i in claimed:
                    continue
                group = [i]
                for j in range(i + 1, len(accumulated_chunks)):
                    if j in claimed:
                        continue
                    sim = retriever.embedding_manager.cosine_similarity(
                        accumulated_chunks[i]["embedding"],
                        accumulated_chunks[j]["embedding"],
                    )
                    if sim >= MERGE_SIMILARITY_THRESHOLD:
                        group.append(j)
                        claimed.add(j)
                if len(group) > 1:
                    claimed.add(i)
                    merge_groups.append(group)

            indices_to_drop: set[int] = set()
            for group in merge_groups:
                keeper_idx = group[0]
                source_chunks = [accumulated_chunks[i] for i in group]
                feedback = ""
                attempts = (
                    LLM_RESPONSE_RETRY_LIMIT
                    if ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION
                    else 1
                )
                for attempt in range(1, attempts + 1):
                    _t_merge = time.perf_counter()
                    merged = merge_similar_chunks(
                        source_chunks,
                        merge_llm,
                        retriever.embedding_manager,
                        feedback=feedback,
                    )
                    _timing.record("Total Merge Time for Retrieved Chunks", time.perf_counter() - _t_merge)
                    if ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION:
                        _t_val = time.perf_counter()
                        merge_check = validate_merge(
                            source_chunks=source_chunks,
                            merged_chunk=merged,
                            judge_llm=judge_llm,
                        )
                        _timing.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t_val)
                        if merge_check["verdict"] != "FAITHFUL":
                            issues = [
                                *[
                                    f"- FABRICATED (must be removed): {claim}"
                                    for claim in merge_check.get("fabricated_claims", [])
                                ],
                                *[
                                    f"- DROPPED (must be re-included): {claim}"
                                    for claim in merge_check.get("dropped_claims", [])
                                ],
                            ]
                            feedback = "\n".join(issues) or merge_check.get(
                                "overall_reason", "Merge was unfaithful."
                            )
                            logger.debug(
                                f"  [MERGE:{track_name}] invalid attempt "
                                f"{attempt}/{attempts}"
                            )
                            continue
                    if not isinstance(merged.get("chunk_seq"), int) and isinstance(
                        accumulated_chunks[keeper_idx].get("chunk_seq"), int
                    ):
                        merged["chunk_seq"] = accumulated_chunks[keeper_idx]["chunk_seq"]
                    accumulated_chunks[keeper_idx] = merged
                    indices_to_drop.update(group[1:])
                    break

            return [
                c for i, c in enumerate(accumulated_chunks)
                if i not in indices_to_drop
            ]

        accumulated_learned_qa = _accumulate_track(
            "learned_qa", accumulated_learned_qa, learned_qa_chunks
        )
        accumulated_documents = _accumulate_track(
            "documents", accumulated_documents, document_chunks
        )
        agent_state["accumulated_learned_qa_chunks"] = accumulated_learned_qa
        agent_state["accumulated_document_chunks"] = accumulated_documents
        retrieved_sources.append({"query": args["query"], "preview": result[:200]})
        logger.debug(
            f"\n  [AGENT STATE] total_retrievals={total_retrievals}/{MAX_TOTAL_RETRIEVALS} | "
            f"documents={len(accumulated_documents)} | "
            f"learned_qa={len(accumulated_learned_qa)}"
        )

        # When this run is being retried because of a user thumbdown, every
        # variant that the LLM tries — even ones that return chunks — should be
        # recorded as a failed variant.  The user has already told us that the
        # previous reformulations led to a bad answer, so we treat the entire
        # prior search space as tainted regardless of whether chunks came back.
        if prior_thumbdowns and args["query"] not in newly_failed:
            newly_failed.append(args["query"])
            logger.warning(f"  [FAILED VARIANT] recorded (thumbdown run): \"{args['query']}\"")

        return result

    # ── Main state-machine loop ───────────────────────────────────────────────

    while iterations < MAX_ITERATIONS:
        iterations += 1

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 1 — RETRIEVE
        # ══════════════════════════════════════════════════════════════════════
        if phase == "RETRIEVE":
            if not ENABLE_SUB_QUERY_GENERATION:
                logger.debug(f"\n{_THICK}")
                logger.warning(f"  [PHASE: RETRIEVE]  sub-query generation disabled — "
                      f"retrieving with original query only.")
                logger.debug(_THICK)
                synth_id = _new_synthetic_id("retrieve_documents")
                messages.append({
                    "role": "assistant",
                    "content": "[sub-query generation disabled] retrieving with original query.",
                    "tool_calls": [{"id": synth_id, "name": "retrieve_documents",
                                    "args": {"query": query}}],
                })
                synthetic_tc = {
                    "id": synth_id,
                    "name": "retrieve_documents",
                    "args": {"query": query},
                }
                result = _handle_retrieve_documents_call(synthetic_tc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": synth_id,
                    "content": result,
                })
                phase = "COMPRESS"
                continue

            logger.debug(f"\n{_THICK}")
            logger.info(f"  [PHASE: RETRIEVE]  Iteration {iterations}/{MAX_ITERATIONS}")
            logger.debug(_THICK)
            logger.debug(_serialize_messages(messages))
            logger.debug(f"  Tool schemas: {[s['function']['name'] for s in retrieve_tool_schemas]}")
            logger.debug(_THICK)

            agent_result = llm_invoke(
                llm, messages, tools=retrieve_tool_schemas, caller_tag="AGENT-RETRIEVE"
            )

            if not agent_result.ok:
                if agent_result.error_kind == LLMErrorKind.TOOL_USE_FAILED:
                    recovered = agent_result.recovered_text
                    return {
                        "answer": recovered or "Unable to generate a clean answer.",
                        "sources": retrieved_sources,
                        "iterations": iterations,
                        "quality": final_quality,
                        **_final_retrieval_fields(),
                        "variants": variants_with_chunks,
                        "total_prompt_tokens": total_prompt_tokens,
                        "total_completion_tokens": total_completion_tokens,
                    }, newly_failed
                if agent_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR, LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(f"  [AGENT] transient error ({agent_result.error_kind.name}) — retrying")
                    continue
                return {
                    "answer": (
                        f"LLM call failed ({agent_result.error_kind.name}): "
                        f"{agent_result.error_message}"
                    ),
                    "sources": retrieved_sources, "iterations": iterations,
                    "quality": "INSUFFICIENT", **_final_retrieval_fields(),
                    "variants": variants_with_chunks,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                }, newly_failed

            response = agent_result.response
            usage = (getattr(response, "response_metadata", {}) or {}).get("token_usage", {})
            iter_prompt     = usage.get("prompt_tokens", 0)
            iter_completion = usage.get("completion_tokens", 0)
            total_prompt_tokens     += iter_prompt
            total_completion_tokens += iter_completion

            resp_content    = str(getattr(response, "content", ""))
            resp_tool_calls = getattr(response, "tool_calls", []) or []
            logger.debug(f"\n{_THICK}")
            logger.debug(f"  LLM RESPONSE  [Iteration {iterations}]")
            logger.debug(_THICK)
            logger.debug(f"  Tokens: {iter_prompt} prompt + {iter_completion} completion")
            logger.debug(f"  content ({len(resp_content)} chars): {resp_content[:400]}"
                  f"{'...' if len(resp_content) > 400 else ''}")
            if resp_tool_calls:
                logger.debug(f"\n  tool_calls ({len(resp_tool_calls)}):")
                for tc in resp_tool_calls:
                    logger.debug(f"    → {tc['name']}  args={json.dumps(tc['args'])}")
            else:
                logger.debug(f"\n  tool_calls: none")
            logger.debug(_THICK)

            # ── LLM emitted no tool calls → treat as "done retrieving" ───────
            if not resp_tool_calls:
                logger.debug(f"\n  [PHASE] LLM emitted text without tool calls in RETRIEVE phase "
                      f"— transitioning to COMPRESS.")
                # Don't append a bare text response to messages here; we just
                # move to COMPRESS phase (which handles the empty-chunks bail-out
                # and/or forces compress_context).
                phase = "COMPRESS"
                continue

            # ── Deduplicate within this batch ─────────────────────────────────
            seen_queries: set[str] = set()
            deduped = []
            for tc in resp_tool_calls[:MAX_TOOL_CALLS_PER_ITERATION]:
                if tc["name"] == "retrieve_documents":
                    q = tc["args"].get("query", "").strip().lower()
                    if q in seen_queries:
                        logger.warning(f"  [DEDUP] Blocked duplicate query in batch: \"{tc['args'].get('query')}\"")
                        continue
                    seen_queries.add(q)
                deduped.append(tc)

            messages.append(response)

            compress_called_this_iter = False
            for tool_call in deduped:
                name = tool_call["name"]
                args = tool_call["args"]
                logger.debug(f"\n{_THIN}")
                logger.debug(f"  AGENT ACTION — calling tool: {name}")
                logger.debug(_THIN)
                logger.debug(f"  args: {json.dumps(args, indent=4)}")
                logger.debug(_THIN)

                if name == "retrieve_documents":
                    result = _handle_retrieve_documents_call(tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })

                elif name == "compress_context":
                    # LLM called compress_context itself — honour it and move on.
                    agent_state["messages"] = messages
                    result = callables["compress_context"]()
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })
                    compress_called_this_iter = True
                    logger.info(f"  [PHASE] LLM called compress_context — transitioning to ANSWER.")

                else:
                    # Unknown tool — silently skip with an error message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": f"Unknown tool '{name}'.",
                    })

            # ── Check whether we should leave RETRIEVE phase ──────────────────
            if compress_called_this_iter:
                # LLM already called compress.
                # If there are still no chunks at all, bail immediately — no
                # further LLM calls (no ANSWER, no JUDGE).
                if not _has_accumulated_chunks():
                    logger.warning(f"\n  [PHASE] compress_context called on 0 chunks — "
                          f"returning canned no-context answer immediately.")
                    return {
                        "answer": NO_CONTEXT_ANSWER,
                        "sources": retrieved_sources,
                        "iterations": iterations,
                        "quality": "INSUFFICIENT",
                        "document_chunks": [],
                        "learned_qa_chunks": [],
                        "variants": variants_with_chunks,
                        "total_prompt_tokens": total_prompt_tokens,
                        "total_completion_tokens": total_completion_tokens,
                    }, newly_failed
                # Chunks exist — skip COMPRESS phase, go straight to ANSWER.
                phase = "ANSWER"
            # else: stay in RETRIEVE, let LLM do more retrieval or call compress itself

            continue  # next iteration

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 2 — COMPRESS
        # ══════════════════════════════════════════════════════════════════════
        if phase == "COMPRESS":
            document_count = len(agent_state["accumulated_document_chunks"])
            learned_qa_count = len(agent_state["accumulated_learned_qa_chunks"])
            logger.debug(f"\n{_THICK}")
            logger.debug(
                f"  [PHASE: COMPRESS] documents={document_count} | "
                f"learned_qa={learned_qa_count}"
            )
            logger.debug(_THICK)

            # ── Bail out immediately if no chunks at all ───────────────────────
            if not _has_accumulated_chunks():
                logger.warning(f"  [COMPRESS] No chunks — returning canned no-context answer. "
                      f"No further LLM calls.")
                return {
                    "answer": NO_CONTEXT_ANSWER,
                    "sources": retrieved_sources,
                    "iterations": iterations,
                    "quality": "INSUFFICIENT",
                    "document_chunks": [],
                    "learned_qa_chunks": [],
                    "variants": variants_with_chunks,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                }, newly_failed

            # ── Force compress_context if the LLM never called it ─────────────
            if not agent_state["compress_done"]:
                logger.debug(f"  [COMPRESS] LLM did not call compress_context — enforcing now.")
                agent_state["messages"] = messages
                _inject_synthetic_tool_call(
                    "compress_context", {},
                    "Retrieval phase ended without compress_context being called.",
                )

            phase = "ANSWER"
            continue  # next iteration

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 3 — ANSWER
        # ══════════════════════════════════════════════════════════════════════
        if phase == "ANSWER":
            full_context = _format_accumulated_context()
            document_count = len(agent_state["accumulated_document_chunks"])
            learned_qa_count = len(agent_state["accumulated_learned_qa_chunks"])

            if not ENABLE_ANSWER_DRAFT_CREATION:
                logger.warning(f"  [DRAFT] creation disabled — generating final answer directly.")
                return _generate_final_answer(quality="OK")

            logger.debug(f"\n{_THICK}")
            logger.info(f"  [PHASE: DRAFT]  Invoking LLM with NO tool schemas to produce answer draft.")
            logger.debug(
                f"  context: {len(full_context)} chars | "
                f"documents={document_count} | learned_qa={learned_qa_count}"
            )
            logger.debug(_THICK)

            # Ask the LLM to draft an answer from the compressed context.
            # No tool schemas — the LLM should produce plain text only.
            draft_prompt = (
                "Using ONLY the compressed context provided in the conversation above "
                "(the compress_context tool result), write an answer draft now. "
                "This draft will be used to generate the final answer. If learned QA "
                "and document context conflict, prefer learned QA.\n"
                "Plain prose paragraphs only. No tool calls. No headings or bullet lists.\n"
                "Cite sources inline as [Source: filename]. Max 400 words."
            )
            messages.append({"role": "user", "content": draft_prompt})

            draft_result = llm_invoke(
                llm, messages, tools=None, caller_tag="AGENT-DRAFT"
            )

            if not draft_result.ok:
                if draft_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR, LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(f"  [DRAFT] transient error — retrying")
                    messages.pop()  # remove the draft_prompt we just appended
                    continue
                return {
                    "answer": f"Draft LLM call failed: {draft_result.error_message}",
                    "sources": retrieved_sources, "iterations": iterations,
                    "quality": "INSUFFICIENT", **_final_retrieval_fields(),
                    "variants": variants_with_chunks,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                }, newly_failed

            usage = (getattr(draft_result.response, "response_metadata", {}) or {}).get("token_usage", {})
            total_prompt_tokens     += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)

            draft_answer = draft_result.content or ""
            logger.debug(f"\n{_THICK}")
            logger.debug(f"  DRAFT ANSWER  ({len(draft_answer)} chars)")
            logger.debug(_THICK)
            logger.debug(draft_answer[:800] + ("..." if len(draft_answer) > 800 else ""))
            logger.debug(_THICK)

            # Append the draft as an assistant message so the transcript stays coherent
            messages.append({"role": "assistant", "content": draft_answer})

            if not ENABLE_ANSWER_QUALITY_CHECK:
                logger.warning(f"  [DRAFT] quality check disabled — generating final answer from draft.")
                return _generate_final_answer(draft=draft_answer, quality="OK")

            phase = "JUDGE"
            continue  # next iteration

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 4 — JUDGE
        # ══════════════════════════════════════════════════════════════════════
        if phase == "JUDGE":
            full_context = _format_accumulated_context()

            logger.debug(f"\n{_THICK}")
            logger.info(f"  [PHASE: JUDGE]  Running check_answer_quality as plain function.")
            logger.debug(_THICK)

            verdict = check_answer_quality(
                answer=draft_answer,
                context=full_context,
                query=query,
                prior_thumbdowns=prior_thumbdowns,
            )
            final_quality = "OK" if verdict.strip().upper().startswith("OK") else "INSUFFICIENT"
            logger.debug(f"  [JUDGE] verdict: {verdict[:200]}")
            logger.debug(f"  [JUDGE] final_quality = {final_quality}")

            # ── OK → generate the final answer from the approved draft ────────
            if final_quality == "OK":
                return _generate_final_answer(draft=draft_answer, quality="OK")

            # ── INSUFFICIENT → loop back to RETRIEVE if budget allows ─────────
            budget_ok = (
                ENABLE_SUB_QUERY_GENERATION  # no new variants possible without sub-query generation
                and total_retrievals < MAX_TOTAL_RETRIEVALS
                and iterations < MAX_ITERATIONS - 1  # leave room for one more round-trip
            )
            if not budget_ok:
                logger.warning(f"  [JUDGE] INSUFFICIENT but no budget left — "
                      f"generating best-effort final answer from draft.")
                return _generate_final_answer(
                    draft=draft_answer,
                    quality="INSUFFICIENT",
                )

            logger.warning(f"\n  [JUDGE] INSUFFICIENT with budget remaining "
                  f"(retrievals={total_retrievals}/{MAX_TOTAL_RETRIEVALS}, "
                  f"iter={iterations}/{MAX_ITERATIONS}) — looping back to RETRIEVE.")

            # Tell the LLM why the previous answer failed and ask for new queries.
            reason = verdict.removeprefix("INSUFFICIENT — ").removeprefix("INSUFFICIENT: ").strip()
            retry_msg = (
                f"Your previous answer was judged INSUFFICIENT by the quality checker.\n"
                f"Reason: {reason}\n\n"
                f"Please call retrieve_documents again with 1-2 NEW, SEMANTICALLY DIFFERENT "
                f"query variants that approach the topic from a fresh angle. "
                f"Do NOT repeat any query you have already tried. "
                f"After retrieving, call compress_context again, and the system will "
                f"prompt you for a new draft."
            )
            messages.append({"role": "user", "content": retry_msg})

            # Reset compression flag so the new retrieval round gets a fresh compress pass
            agent_state["compress_done"] = False
            phase = "RETRIEVE"
            continue  # next iteration

    # ── Exhausted iterations ──────────────────────────────────────────────────
    if draft_answer:
        logger.warning(f"  [AGENT] Max iterations reached — generating final answer from best draft.")
        return _generate_final_answer(draft=draft_answer, quality=final_quality)

    return {
        "answer": "Max iterations reached without a confident answer.",
        "sources": retrieved_sources,
        "iterations": iterations,
        "quality": final_quality,
        **_final_retrieval_fields(),
        "variants": variants_with_chunks,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
    }, newly_failed


def main():
    setup_logging(app_name="agent_query")
    embedding_manager = EmbeddingManager()
    vector_store = VectorStore(collection_name=COLLECTION_NAME, persist_directory=VECTOR_STORE_PATH)

    if vector_store.collection.count() == 0:
        print("Vector store is empty. Run ingest.py first.")
        return

    chroma_client = chromadb.PersistentClient(path=VECTOR_STORE_PATH)
    learned_collection = get_or_create_learned_qa_collection(chroma_client)

    retriever = RAGRetriever(vector_store, embedding_manager, learned_collection=learned_collection)

    from llm_setup import llm, merge_llm, judge_llm

    # Shared state container wired into both make_tools and run_agent.
    agent_state: dict = {}

    tool_schemas, callables = make_tools(
        retriever,
        judge_llm=judge_llm,
        merge_llm=merge_llm,
        agent_state=agent_state,
    )

    # check_answer_quality is an orchestrator-side plain function (not an LLM tool).
    check_answer_quality = make_check_answer_quality(judge_llm)

    feedback_store = FeedbackStore()
    self_learner = SelfLearner(
        embedding_manager=embedding_manager,
        llm=llm,
        feedback_store=feedback_store,
        vector_store_path=VECTOR_STORE_PATH,
        learn_every_n=LEARN_EVERY_N,
    )

    print("\n=== Agentic RAG — Self-Learning Query Interface ===")
    if ENABLE_AUTO_DISTILLATION:
        print(f"Self-learning triggers every {LEARN_EVERY_N} successful interactions.\n")
    else:
        print("Automatic self-learning is disabled.\n")
    print("Commands: 'bad' to flag last answer | 'stats' for learning stats | 'learn' to force distillation | 'quit' to exit\n")

    last_result = None

    while True:
        raw = input("Your question: ").strip()
        if not raw or raw.lower() in {"quit", "exit"}:
            break

        # ── Special commands ─────────────────────────────────────────────────
        if raw.lower() == "bad":
            if last_result is None:
                if feedback_store.mark_last_bad():
                    print("Last answer flagged as bad (no in-session variants available to enrich).\n")
                else:
                    print("Nothing to flag yet.\n")
                continue

            print(
                "\nWhy was this answer bad? (optional — press Enter to skip)."
                f"\nIf you provide at least {MIN_FEEDBACK_LEN} characters, this query, all its"
                "\nLLM-generated reformulations, and the chunks they retrieved will be saved"
                "\nso the agent avoids repeating the same failure next time."
            )
            try:
                feedback = input("Your feedback: ").strip()
            except (EOFError, KeyboardInterrupt):
                feedback = ""
                print()

            ok = feedback_store.mark_last_bad(
                feedback=feedback,
                variants=last_result.get("variants", []),
            )
            if not ok:
                print("Nothing to flag yet.\n")
                continue

            if feedback and len(feedback) >= MIN_FEEDBACK_LEN:
                print(
                    f"Last answer flagged as bad and persisted to user_thumbdowns.json"
                    f" ({len(last_result.get('variants', []))} variant(s) captured).\n"
                )
            elif feedback:
                print(
                    f"Last answer flagged as bad. Feedback was too short"
                    f" (<{MIN_FEEDBACK_LEN} chars) — not persisted to user_thumbdowns.json.\n"
                )
            else:
                print("Last answer flagged as bad. No feedback provided — not persisted to user_thumbdowns.json.\n")
            continue

        if raw.lower() == "stats":
            all_i = feedback_store.count()
            good_i = feedback_store.count_good()
            learned = learned_collection.count()
            print(f"\n  Total interactions logged : {all_i}")
            print(f"  Successful (OK quality)   : {good_i}")
            print(f"  Learned QA pairs in store : {learned}")
            if ENABLE_AUTO_DISTILLATION:
                print(f"  Next distillation at      : {LEARN_EVERY_N - (good_i % LEARN_EVERY_N)} more good interaction(s)\n")
            else:
                print("  Automatic distillation    : disabled\n")
            continue

        if raw.lower() == "learn":
            print("Forcing distillation now…")
            added = self_learner.run_distillation()
            print(f"Added {added} QA pairs to learned_qa.\n")
            continue

        # ── Log the raw user query ───────────────────────────────────────────
        logger.info("User query received")
        logger.debug(f"Input: {raw!r}; length={len(raw)} chars")

        # ── Run the agent ────────────────────────────────────────────────────
        norm = _normalize_query(raw)
        fv_col = failed_variants_col()
        fv_doc = fv_col.find_one({"normalized_query": norm})
        blocked: list[str] = list(fv_doc["variants"]) if fv_doc else []
        if blocked:
            logger.debug("[BLOCKED VARIANTS] %d known-failing variant(s) loaded from DB.", len(blocked))
        db_blocked_count = len(blocked)

        prior_thumbdowns = feedback_store.find_thumbdowns_for_query(raw)
        if prior_thumbdowns:
            logger.debug(
                "  [USER THUMBDOWN HISTORY] %d prior bad-answer record(s)"
                " found for this query — injecting context into system prompt.",
                len(prior_thumbdowns),
            )
            # Seed blocked variants from ALL thumbdown variant queries, not just
            # the zero-chunk ones.  Every reformulation in a thumbdown run led to
            # a bad answer — the user has told us so — so block them all up-front.
            existing_blocked: set[str] = set(blocked)
            for td in prior_thumbdowns:
                for v in (td.get("variants") or []):
                    vq = (v.get("query") or "").strip()
                    if vq and vq not in existing_blocked:
                        blocked.append(vq)
                        existing_blocked.add(vq)
            if len(blocked) > db_blocked_count:
                logger.debug(
                    "  [BLOCKED VARIANTS] expanded to %d variant(s) after merging thumbdown history.",
                    len(blocked),
                )

        try:
            result, newly_failed = run_agent(
                raw, llm, merge_llm, judge_llm, tool_schemas, callables,
                check_answer_quality, retriever,
                agent_state, blocked, prior_thumbdowns,
            )
        except LLMRateLimitAbortError as e:
            print(
                f"\nRate limit hit — a backoff of {e.delay:.0f}s is required. "
                f"Please wait at least {e.delay:.0f} seconds before sending your next query.\n"
            )
            continue
        last_result = result

        # ── Persist any newly discovered failed variants ─────────────────────
        if newly_failed:
            fv_doc = fv_col.find_one({"normalized_query": norm})
            existing = set(fv_doc["variants"]) if fv_doc else set()
            fresh = [v for v in newly_failed if v not in existing]
            if fresh:
                fv_col.update_one(
                    {"normalized_query": norm},
                    {"$addToSet": {"variants": {"$each": fresh}}},
                    upsert=True,
                )
                logger.warning(
                    "[FAILED VARIANTS] saved %d new failing variant(s) to MongoDB for norm=%r",
                    len(fresh), norm,
                )

        # ── Final answer summary ─────────────────────────────────────────────
        print(f"\n{_THICK}")
        print(f"  FINAL ANSWER")
        print(_THICK)
        print(result["answer"])
        print(_THICK)
        print(f"  Iterations used : {result['iterations']} / {MAX_ITERATIONS}")
        print(f"  Quality signal  : {result['quality']}")
        tp = result.get("total_prompt_tokens", 0)
        tc = result.get("total_completion_tokens", 0)
        print(f"  Tokens (total)  : {tp} prompt + {tc} completion = {tp + tc} total")
        print(f"  Sources searched:")
        for s in result["sources"]:
            print(f"    • \"{s['query']}\"")
            print(f"      preview: {s['preview'][:100]}...")
        print(_THICK)

        # ── Log interaction ──────────────────────────────────────────────────
        feedback_store.log(
            query=raw,
            answer=result["answer"],
            sources=result["sources"],
            quality=result["quality"],
            document_retrieved_chunks=result.get("document_chunks", []),
            learned_qa_retrieved_chunks=result.get("learned_qa_chunks", []),
        )

        # ── Self-learning trigger ────────────────────────────────────────────
        if ENABLE_AUTO_DISTILLATION and result["quality"] == "OK" and self_learner.should_learn():
            logger.info(f"[Self-Learning] {feedback_store.count_good()} good interactions reached — running distillation")
            added = self_learner.run_distillation()
            logger.info(f"[Self-Learning] {added} new QA pair(s) added to knowledge base")


if __name__ == "__main__":
    main()

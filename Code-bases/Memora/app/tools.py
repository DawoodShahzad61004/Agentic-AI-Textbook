# tools.py
import logging

logger = logging.getLogger(__name__)
from retriever import RAGRetriever
from llm_caller import llm_invoke
from context_compression import (
    compress_context_pipeline,
    format_precedence_context_for_llm,
)

from config import (
    COMPRESS_MIN_TOKENS,
    MIN_ANSWER_LENGTH,
    MIN_SIMILARITY,
    RETRIEVAL_TOP_K,
    RETRIEVAL_TOP_L,
)
from prompts import GROUNDING_PROMPT, GROUNDING_PROMPT_WITH_THUMBDOWN, COMPRESSED_PLACEHOLDER
from prompts import _THIN as _SEP

# ~0.7–1.0 → strong topical match
# ~0.4–0.7 → related, same domain
# ~0.2–0.4 → loosely related / shared vocabulary only
# ~0.0–0.2 → effectively unrelated
# below 0 → rare; usually a sign of weird input (very short text, code vs prose mismatch, etc.)


def _approx_token_count(chunks: list[dict]) -> int:
    total_chars = 0
    for c in chunks:
        content = c.get("content", "") or ""
        total_chars += len(content)
    return total_chars // 4

def make_tools(
    retriever: RAGRetriever,
    judge_llm=None,
    merge_llm=None,
    agent_state: dict | None = None,
):
    state = agent_state if agent_state is not None else {}

    # ─────────────────────────────────────────────────────────────────────
    # Tool 1 — retrieve_documents
    # ─────────────────────────────────────────────────────────────────────
    def retrieve_documents(query: str) -> str:
        retrieved = retriever.retrieve_separate(
            query,
            top_k=RETRIEVAL_TOP_K,
            top_l=RETRIEVAL_TOP_L,
            score_threshold=MIN_SIMILARITY,
        )
        documents = retrieved["documents"]
        learned_qa = retrieved["learned_qa"]
        if not documents and not learned_qa:
            result = "No relevant documents found for this query."
            logger.debug(f"\n{_SEP}")
            logger.debug(f"  TOOL RESULT — retrieve_documents")
            logger.debug(_SEP)
            logger.debug(f"  {result}")
            logger.debug(_SEP)
            return result

        def _format_track(title: str, chunks: list[dict]) -> str:
            if not chunks:
                return f"[{title}]\nNo relevant chunks found."
            content = "\n\n".join(
                f"[Source: {d['metadata'].get('source', '?')}, "
                f"score: {d['similarity_score']:.3f}]\n{d['content']}"
                for d in chunks
            )
            return f"[{title}]\n{content}"

        result = "\n\n".join([
            _format_track("LEARNED QA RESULTS - HIGH PRIORITY", learned_qa),
            _format_track("DOCUMENT RESULTS - SECONDARY", documents),
        ])
        logger.debug(f"\n{_SEP}")
        logger.debug(f"  RETRIEVED (unfiltered) — retrieve_documents(\"{query}\")")
        logger.debug(
            f"  documents={len(documents)} | learned_qa={len(learned_qa)} | "
            f"{len(result)} chars total - pending separate relevance checks"
        )
        logger.debug(_SEP)
        logger.debug(result)
        logger.debug(_SEP)
        return result

    # ─────────────────────────────────────────────────────────────────────
    # Tool 2 — compress_context
    # ─────────────────────────────────────────────────────────────────────
    def compress_context() -> str:
        document_chunks = state.get("accumulated_document_chunks", []) or []
        learned_qa_chunks = state.get("accumulated_learned_qa_chunks", []) or []
        query = state.get("query", "") or ""
        embedding_manager = state.get("embedding_manager")
        messages = state.get("messages")

        logger.debug(f"\n{_SEP}")
        logger.debug(f"  TOOL CALL — compress_context")
        logger.debug(_SEP)
        logger.debug(f"  document chunks   : {len(document_chunks)}")
        logger.debug(f"  learned QA chunks : {len(learned_qa_chunks)}")
        logger.debug(f"  query             : \"{query[:120]}\"")
        if not document_chunks and not learned_qa_chunks:
            logger.warning(f"  [COMPRESS] no accumulated chunks — nothing to compress")
            logger.debug(_SEP)
            state["compress_done"] = True
            return (
                "No retrieved chunks were available to compress. "
                "Call retrieve_documents first."
            )

        # ── 1. Token-budget gate ──────────────────────────────────────────
        # Skip the NAC→DC→LBC pipeline if the accumulated chunks are below
        # the minimum compression budget. The rest of the bookkeeping (state
        # flag, message scrubbing, formatted-context return) still runs so
        # downstream callers see the same contract regardless.
        def _compress_track(track_name: str, chunks: list[dict]) -> list[dict]:
            if not chunks:
                logger.warning(f"  [COMPRESS:{track_name}] no chunks - skipping")
                return []
            approx_tokens = _approx_token_count(chunks)
            logger.debug(
                f"  [COMPRESS:{track_name}] approx tokens: {approx_tokens} "
                f"(threshold: {COMPRESS_MIN_TOKENS})"
            )
            if approx_tokens < COMPRESS_MIN_TOKENS:
                logger.debug(
                    f"  [COMPRESS:{track_name}] skipping NAC -> DC -> LBC pipeline - "
                    f"{approx_tokens} approx tokens < {COMPRESS_MIN_TOKENS} threshold"
                )
                return chunks
            chosen_llm = merge_llm if merge_llm is not None else judge_llm
            return compress_context_pipeline(
                chunks=chunks,
                query=query,
                llm=chosen_llm,
                embedding_manager=embedding_manager,
                judge_llm=judge_llm,
            )

        compressed_learned_qa = _compress_track("learned_qa", learned_qa_chunks)
        compressed_documents = _compress_track("documents", document_chunks)

        # ── 2. Install (possibly identical) chunks back into agent state ──
        state["accumulated_learned_qa_chunks"] = compressed_learned_qa
        state["accumulated_document_chunks"] = compressed_documents
        state["compress_done"] = True

        # ── 3. Scrub original (raw-chunk) tool-result messages from chat ──
        #     We replace the .content of any prior `retrieve_documents` tool
        #     result with a short placeholder. We never delete messages
        #     wholesale because that would break the assistant↔tool_call_id
        #     pairing the chat API enforces.
        scrubbed = 0
        if isinstance(messages, list):
            # Build a map: tool_call_id -> tool_name from prior assistant turns.
            tool_call_id_to_name: dict[str, str] = {}
            for m in messages:
                tool_calls = None
                if isinstance(m, dict):
                    tool_calls = m.get("tool_calls")
                else:
                    tool_calls = getattr(m, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        tc_id = tc.get("id") if isinstance(tc, dict) else None
                        tc_name = tc.get("name") if isinstance(tc, dict) else None
                        if tc_id and tc_name:
                            tool_call_id_to_name[tc_id] = tc_name
            for m in messages:
                if not isinstance(m, dict):
                    continue
                if m.get("role") != "tool":
                    continue
                tcid = m.get("tool_call_id", "")
                # Strip the "_judge" suffix used by the retrieval-judge sidecar.
                base_id = tcid[:-len("_judge")] if tcid.endswith("_judge") else tcid
                origin = tool_call_id_to_name.get(base_id)
                if origin == "retrieve_documents":
                    if m.get("content") != COMPRESSED_PLACEHOLDER:
                        m["content"] = COMPRESSED_PLACEHOLDER
                        scrubbed += 1
        logger.debug(f"  [COMPRESS] scrubbed {scrubbed} prior retrieve_documents tool-result "
              f"message(s) from chat history (replaced with placeholder)")

        # ── 4. Return the compressed context as this tool's result ─────────
        full_context = format_precedence_context_for_llm(
            compressed_learned_qa,
            compressed_documents,
        )
        total_chunks = len(compressed_learned_qa) + len(compressed_documents)
        header = (
            f"[COMPRESSED CONTEXT — {total_chunks} chunk(s), "
            f"learned_qa={len(compressed_learned_qa)}, "
            f"documents={len(compressed_documents)}, "
            f"{len(full_context)} chars]\n"
            f"Use both sections, but prefer learned QA if it conflicts with documents. "
            f"This is the only retrieval context you should rely on. Earlier raw "
            f"retrieve_documents results have been replaced with a placeholder.\n\n"
        )
        result_str = header + full_context
        logger.debug(f"  [COMPRESS] returning {len(result_str)} chars "
              f"({total_chunks} chunks) as compress_context tool result")
        logger.debug(_SEP)
        return result_str

    tool_schemas = [
        {
            "type": "function",
            "function": {
                "name": "retrieve_documents",
                "description": (
                    "Search documents and learned QA separately for chunks relevant "
                    "to a query. Learned QA is high priority if it conflicts with "
                    "documents. "
                    "Call this 2–3 times first with semantically different queries. "
                    "Stop retrieving once you have enough material, then call "
                    "compress_context to consolidate what you have."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compress_context",
                "description": (
                    "Consolidate the document and learned-QA tracks independently "
                    "(NAC → DC → LBC), then return both with learned-QA precedence. "
                    "Call this EXACTLY ONCE, "
                    "AFTER your retrieve_documents calls are done. Takes no "
                    "arguments. The system uses the chunks it has accumulated for "
                    "you. Returns the compressed context as the tool result; raw "
                    "retrieve_documents results are scrubbed from the chat once "
                    "this runs. After this returns, the system will handle the "
                    "remaining answer stages for you — do NOT emit a final "
                    "answer yourself in the same turn."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    ]

    callables = {
        "retrieve_documents": retrieve_documents,
        "compress_context": compress_context,
    }

    return tool_schemas, callables


# ─────────────────────────────────────────────────────────────────────────
# check_answer_quality — orchestrator-side function (NOT an LLM tool)
# ─────────────────────────────────────────────────────────────────────────

def _extract_thumbdown_feedback(prior_thumbdowns: list[dict] | None) -> str:
    if not prior_thumbdowns:
        return ""
    lines = []
    for i, td in enumerate(prior_thumbdowns, start=1):
        fb = (td.get("user_feedback") or "").strip()
        if fb:
            lines.append(f"[Feedback #{i}] {fb}")
    return "\n".join(lines)


def make_check_answer_quality(judge_llm):
    def check_answer_quality(
        answer: str,
        context: str,
        query: str,
        prior_thumbdowns: list[dict] | None = None,
    ) -> str:
        if not context or len(context.strip()) < 50:
            return "INSUFFICIENT — no supporting context was retrieved."

        if len(answer.strip()) < MIN_ANSWER_LENGTH:
            return (
                f"INSUFFICIENT — answer is too brief ({len(answer.strip())} chars, "
                f"minimum {MIN_ANSWER_LENGTH}). Expand using the retrieved chunks."
            )

        if judge_llm is None:
            return "OK"

        # Build a combined feedback string from all prior thumbdowns for this query.
        thumbdown_feedback = _extract_thumbdown_feedback(prior_thumbdowns)

        if thumbdown_feedback:
            grounding_prompt = GROUNDING_PROMPT_WITH_THUMBDOWN.format(
                answer=answer,
                context=context[:3000],
                query=query or "(not provided)",
                thumbdown_feedback=thumbdown_feedback,
            )
            caller_tag = "CAQ-JUDGE-TD"
        else:
            grounding_prompt = GROUNDING_PROMPT.format(
                answer=answer, context=context[:3000], query=query or "(not provided)"
            )
            caller_tag = "CAQ-JUDGE"

        result = llm_invoke(
            judge_llm,
            [{"role": "user", "content": grounding_prompt}],
            caller_tag=caller_tag,
        )

        if not result.ok:
            logger.warning(f"  [{caller_tag}] LLM call failed ({result.error_kind}), defaulting to OK")
            return "OK"

        verdict = result.content.strip()
        logger.debug(f"  [{caller_tag}] verdict: {verdict[:120]}")

        if verdict.upper().startswith("OK"):
            return "OK"
        else:
            reason = verdict if verdict else (
                "answer does not adequately address the query using the retrieved chunks"
            )
            return f"INSUFFICIENT — {reason.removeprefix('INSUFFICIENT — ').removeprefix('INSUFFICIENT: ')}"

    return check_answer_quality

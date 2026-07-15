import logging
import re
import time

from state import GraphState
from app_workflow.services.llm_setup import llm, judge_llm
from app_workflow.services.validators import validate_redundancy
from app_workflow.services.fix_llm_output import fix_llm_output, _parse_to_python
from app_workflow.services.llm_caller import llm_invoke, LLMErrorKind
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.config import (
    LLM_RESPONSE_RETRY_LIMIT,
    DC_WINDOW_SIZE,
    ENABLE_DC_COMPRESSION,
    ENABLE_COMPRESSION_OUTPUT_FIX,
    ENABLE_GLOBAL_LLM_OUTPUT_FIX,
)
from app_workflow.services.prompts import _DC_SCAN_PROMPT, _THIN

logger = logging.getLogger(__name__)


def _run_dc(chunks: list[dict], config=None) -> tuple[list[dict], list[dict]]:
    """Core DC logic. Returns (result_chunks, dc_groups_per_window)."""
    window_size = DC_WINDOW_SIZE

    if len(chunks) < 2:
        return list(chunks), []

    result: list[dict] = [dict(c) for c in chunks]
    total_sentences_removed = 0
    dc_groups_per_window: list[dict] = []
    _source_tag_re = re.compile(r"\[Source:[^\]]*\]", re.IGNORECASE)

    for window_start in range(0, len(result), window_size):
        window_end = min(window_start + window_size, len(result))
        window = result[window_start:window_end]

        if len(window) < 2:
            continue

        blocks = []
        for local_i, chunk in enumerate(window):
            src = chunk.get("source", "?")
            content = _source_tag_re.sub("", (chunk.get("content") or "")).strip()
            blocks.append(f"--- chunk {local_i} (source: {src}) ---\n{content}")
        chunks_block = "\n\n".join(blocks)

        prompt = _DC_SCAN_PROMPT.format(chunks_block=chunks_block)
        logger.debug(
            f"\n  [DC] scanning window [{window_start}:{window_end}] ({len(window)} chunk(s))"
        )

        raw = ""
        for attempt in range(LLM_RESPONSE_RETRY_LIMIT):
            dc_result = llm_invoke(
                llm, [{"role": "system", "content": prompt}], caller_tag="DC", config=config
            )
            if not dc_result.ok:
                if dc_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(
                        f"  [DC] transient error on attempt {attempt + 1} "
                        f"({dc_result.error_kind.name}) — retrying…"
                    )
                    continue
                logger.error(
                    f"  [DC] non-retryable error ({dc_result.error_kind.name}): "
                    f"{dc_result.error_message[:200]} — skipping window"
                )
                break
            raw = dc_result.content
            if raw:
                break
            logger.debug(f"  [DC] empty LLM response on attempt {attempt + 1}, retrying…")

        if not raw:
            logger.warning(
                f"  [DC] no usable response after {LLM_RESPONSE_RETRY_LIMIT} attempt(s) "
                f"— skipping window"
            )
            continue

        if ENABLE_COMPRESSION_OUTPUT_FIX and ENABLE_GLOBAL_LLM_OUTPUT_FIX:
            flagged, _ok = fix_llm_output("dc_scan", raw, llm=llm, config=config)
        else:
            flagged = _parse_to_python(raw)
            _ok = flagged is not None
        if not _ok or not isinstance(flagged, list):
            logger.warning("[DC] failed to parse scan response")
            logger.debug("[DC] raw scan response: %s", raw[:300])
            continue

        if not flagged:
            logger.debug(f"  [DC] window [{window_start}:{window_end}] — no redundancy found")
            continue

        logger.debug(f"  [DC] {len(flagged)} redundancy group(s) identified in this window:")
        for g in flagged:
            for m in g.get("members", []):
                logger.debug(
                    f"    chunk_index={m.get('chunk_index')}  "
                    f"sentence=\"{str(m.get('sentence', ''))[:120]}\""
                )

        valid_groups: list[list[dict]] = []
        for group in flagged:
            members = group.get("members")
            if not isinstance(members, list) or len(members) < 2:
                continue
            clean_members = []
            for m in members:
                local_idx = m.get("chunk_index")
                sentence = (m.get("sentence") or "").strip()
                if not isinstance(local_idx, int) or not sentence:
                    continue
                if local_idx < 0 or local_idx >= len(window):
                    continue
                clean_members.append({"chunk_index": local_idx, "sentence": sentence})
            if len(clean_members) < 2:
                continue
            unique_chunk_indices = {m["chunk_index"] for m in clean_members}
            if len(unique_chunk_indices) < 2:
                logger.debug(
                    f"  [DC] group dropped — all {len(clean_members)} member(s) "
                    f"are from chunk_index={next(iter(unique_chunk_indices))} "
                    f"(intra-chunk repetition, not cross-chunk redundancy)"
                )
                continue
            valid_groups.append(clean_members)

        if not valid_groups:
            logger.warning("  [DC] no structurally valid groups after normalization — skipping window")
            continue

        dc_groups_per_window.append({"window_chunks": list(window), "groups": valid_groups})

        confirmed_groups = [{"members": members} for members in valid_groups]

        flags_by_local: dict[int, list[str]] = {}
        for entry in confirmed_groups:
            members = entry["members"]
            keeper_idx = min(m["chunk_index"] for m in members)
            for m in members:
                if m["chunk_index"] != keeper_idx:
                    flags_by_local.setdefault(m["chunk_index"], []).append(m["sentence"])

        for local_idx, sentences_to_remove in flags_by_local.items():
            global_idx = window_start + local_idx
            original_chunk = result[global_idx]
            original_content = (original_chunk.get("content") or "").strip()

            cleaned_content = original_content
            for sentence in sentences_to_remove:
                if sentence in cleaned_content:
                    cleaned_content = cleaned_content.replace(sentence, "").strip()
                else:
                    norm_sentence = " ".join(sentence.split())
                    norm_content = " ".join(cleaned_content.split())
                    if norm_sentence in norm_content:
                        cleaned_content = norm_content.replace(norm_sentence, "").strip()

            if cleaned_content == original_content:
                logger.warning(f"  [DC] chunk {global_idx}: no change after removal attempt — skipping")
                continue
            if len(cleaned_content.strip()) < 50:
                logger.warning(
                    f"  [DC] chunk {global_idx}: cleaned content too short — skipping "
                    f"(would remove too much)"
                )
                continue

            removed_count = len(sentences_to_remove)
            logger.debug(
                f"\n  [DC] chunk {global_idx}: removing {removed_count} confirmed-redundant sentence(s)"
            )
            logger.debug(
                f"    before ({len(original_content)} chars): {original_content[:150]}…"
            )
            logger.debug(
                f"    after  ({len(cleaned_content)} chars): {cleaned_content[:150]}…"
            )
            result[global_idx] = {**original_chunk, "content": cleaned_content}
            total_sentences_removed += removed_count
            logger.debug(f"  [DC] chunk {global_idx}: INSTALLED cleaned version ✓")

    logger.debug(
        f"\n  [DC] done — {total_sentences_removed} redundant passage(s) removed "
        f"across {len(result)} chunk(s)"
    )
    logger.debug(_THIN)
    return result, dc_groups_per_window


def _validate_dc_groups(tag: str, windows: list[dict], config=None) -> None:
    if not windows:
        logger.info("[%s] no redundancy groups to validate", tag)
        return
    for i, entry in enumerate(windows):
        check = validate_redundancy(entry["window_chunks"], entry["groups"], judge_llm, config=config)
        logger.info(
            "[%s] window %d: confirmed=%d  rejected=%d",
            tag, i, len(check["confirmed_groups"]), len(check["rejected_groups"]),
        )


# ── Document track ────────────────────────────────────────────────────────────

def execute_dc_documents(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    chunks = state.get("nac_output_document_chunks") or []
    logger.info("[COMPRESS] running DC_documents on %d chunk(s)", len(chunks))
    if not ENABLE_DC_COMPRESSION:
        logger.debug("[DC] disabled — passing through %d chunk(s)", len(chunks))
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"dc_output_document_chunks": chunks, "dc_groups_per_window_documents": []}
    result, groups = _run_dc(chunks, config=config)
    logger.info("[COMPRESS] DC_documents complete — %d chunk(s) remain", len(result))
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {"dc_output_document_chunks": result, "dc_groups_per_window_documents": groups}


def validate_dc_documents(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    _validate_dc_groups("validate_DC_documents", state.get("dc_groups_per_window_documents") or [], config=config)
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {}


# ── Learned-QA track ──────────────────────────────────────────────────────────

def execute_dc_learned_qa(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    chunks = state.get("dedup_merged_learned_qa_chunks") or []
    logger.info("[COMPRESS] running DC_learned_qa on %d chunk(s)", len(chunks))
    if not ENABLE_DC_COMPRESSION:
        logger.debug("[DC] disabled — passing through %d chunk(s)", len(chunks))
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"dc_output_learned_qa_chunks": chunks, "dc_groups_per_window_learned_qa": []}
    result, groups = _run_dc(chunks, config=config)
    logger.info("[COMPRESS] DC_learned_qa complete — %d chunk(s) remain", len(result))
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {"dc_output_learned_qa_chunks": result, "dc_groups_per_window_learned_qa": groups}


def validate_dc_learned_qa(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    _validate_dc_groups("validate_DC_learned_qa", state.get("dc_groups_per_window_learned_qa") or [], config=config)
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {}

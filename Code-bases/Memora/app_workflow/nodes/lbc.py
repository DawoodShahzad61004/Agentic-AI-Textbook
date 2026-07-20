import logging
import time

from state import GraphState
from app_workflow.services.llm_setup import llm, judge_llm
from app_workflow.services.validators import validate_lbc as _validate_lbc_chunk
from app_workflow.services.fix_llm_output import fix_llm_output, _parse_to_python
from app_workflow.services.llm_caller import llm_invoke, LLMErrorKind
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.switches import get_switches
from app_workflow.config import LLM_RESPONSE_RETRY_LIMIT, LBC_MIN_RETENTION_RATIO
from app_workflow.services.prompts import _LBC_COMPRESS_PROMPT, _LBC_DEFAULT_INSTRUCTIONS, _THIN

logger = logging.getLogger(__name__)


def _run_lbc(chunks: list[dict], query: str, switches: dict, config=None) -> tuple[list[dict], list[dict]]:
    """Core LBC logic. Returns (result_chunks, lbc_validation_pairs)."""
    instructions = _LBC_DEFAULT_INSTRUCTIONS
    min_retention_ratio = LBC_MIN_RETENTION_RATIO

    if not chunks:
        return [], []

    result: list[dict] = []
    lbc_validation_pairs: list[dict] = []
    total_chars_before = sum(len(c.get("content", "")) for c in chunks)
    total_chars_after = 0
    skipped = accepted = irrelevant_dropped = 0

    for idx, chunk in enumerate(chunks):
        original_content = (chunk.get("content") or "").strip()
        source = chunk.get("source", "?")

        if not original_content:
            result.append(chunk)
            skipped += 1
            continue

        prompt = _LBC_COMPRESS_PROMPT.format(
            query=query,
            instructions=instructions,
            source=source,
            content=original_content,
        )
        logger.debug(
            f"\n  [LBC] chunk {idx} — source: '{source[:60]}'  ({len(original_content)} chars)"
        )

        raw = ""
        parsed_lbc: dict | None = None
        for attempt in range(1, LLM_RESPONSE_RETRY_LIMIT + 1):
            lbc_result = llm_invoke(
                llm, [{"role": "system", "content": prompt}], caller_tag="LBC", config=config
            )
            if not lbc_result.ok:
                if lbc_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(
                        f"  [LBC] chunk {idx}: transient error on attempt {attempt} "
                        f"({lbc_result.error_kind.name}) — retrying…"
                    )
                    raw = ""
                    continue
                logger.error(
                    f"  [LBC] chunk {idx}: non-retryable error on attempt {attempt} "
                    f"({lbc_result.error_kind.name}): "
                    f"{lbc_result.error_message[:200]} — keeping original"
                )
                raw = ""
                break
            raw = lbc_result.content

            if not raw:
                logger.warning(f"  [LBC] chunk {idx}: empty response on attempt {attempt}, retrying…")
                continue

            if switches["ENABLE_COMPRESSION_OUTPUT_FIX"] and switches["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
                candidate, _ok = fix_llm_output("lbc_compress", raw, llm=llm, config=config)
            else:
                candidate = _parse_to_python(raw)
                _ok = candidate is not None
            if _ok and isinstance(candidate, dict) and "compressed" in candidate:
                parsed_lbc = candidate
                break
            logger.warning(
                f"  [LBC] chunk {idx}: failed to parse JSON on attempt {attempt}, retrying…"
            )

        if parsed_lbc is None:
            logger.warning(
                f"  [LBC] chunk {idx}: parse failed after {LLM_RESPONSE_RETRY_LIMIT} "
                f"attempt(s) — keeping original"
            )
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        compressed_text = (parsed_lbc.get("compressed") or "").strip()
        dropped_count = parsed_lbc.get("dropped_count", 0)
        lbc_reason = (parsed_lbc.get("reason") or "").strip()
        logger.debug(
            f"  [LBC] chunk {idx}: LLM produced {len(compressed_text)} chars "
            f"(dropped_count={dropped_count})  reason: {lbc_reason[:120]}"
        )

        if compressed_text == "__IRRELEVANT__":
            logger.debug(f"  [LBC] chunk {idx}: marked __IRRELEVANT__ by LLM — dropping chunk")
            irrelevant_dropped += 1
            continue

        retention = len(compressed_text) / max(len(original_content), 1)
        if retention < min_retention_ratio:
            logger.debug(
                f"  [LBC] chunk {idx}: retention ratio {retention:.2f} < "
                f"{min_retention_ratio} — keeping original (over-compression guard)"
            )
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        if len(compressed_text) > len(original_content):
            logger.debug(
                f"  [LBC] chunk {idx}: 'compressed' output expanded "
                f"({len(original_content)} → {len(compressed_text)} chars) "
                f"— keeping original (over-expansion guard)"
            )
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        if compressed_text == original_content:
            logger.debug(f"  [LBC] chunk {idx}: no change — keeping as-is")
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        compressed_chunk_dict = {**chunk, "content": compressed_text}
        lbc_validation_pairs.append({"original": chunk, "compressed": compressed_chunk_dict})
        result.append(compressed_chunk_dict)
        total_chars_after += len(compressed_text)
        accepted += 1
        logger.info(
            "  [LBC] chunk %d: compressed (%d → %d chars, −%d chars)",
            idx, len(original_content), len(compressed_text),
            len(original_content) - len(compressed_text),
        )

    saved_chars = total_chars_before - total_chars_after
    pct = (saved_chars / max(total_chars_before, 1)) * 100
    logger.debug(
        f"\n  [LBC] done — {len(chunks)} → {len(result)} chunk(s) "
        f"({irrelevant_dropped} dropped as irrelevant, "
        f"{accepted} compressed, {skipped} kept as-is)"
    )
    logger.debug(
        f"  [LBC] chars: {total_chars_before:,} → {total_chars_after:,} "
        f"(-{saved_chars:,} = {pct:.1f}% reduction)"
    )
    logger.debug(_THIN)
    return result, lbc_validation_pairs


def _validate_lbc_pairs(tag: str, pairs: list[dict], query: str, switches: dict, config=None) -> None:
    """Pass-through when ENABLE_COMPRESSION_VALIDATION is False."""
    if not switches["ENABLE_COMPRESSION_VALIDATION"]:
        return
    if not pairs:
        logger.info("[%s] no compressed chunks to validate", tag)
        return
    for i, pair in enumerate(pairs):
        check = _validate_lbc_chunk(query, pair["original"], pair["compressed"], judge_llm, config=config, switches=switches)
        logger.info(
            "[%s] chunk %d: verdict=%s  fabricated=%d  lost_relevant=%d",
            tag, i, check["verdict"],
            len(check["fabricated_claims"]),
            len(check["lost_relevant_facts"]),
        )


# ── Document track ────────────────────────────────────────────────────────────

def execute_lbc_documents(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    sw = get_switches(state)
    chunks = state.get("dc_output_document_chunks") or []
    query = state["query"]
    logger.info("[COMPRESS] running LBC_documents on %d chunk(s)", len(chunks))
    if not sw["ENABLE_LBC_COMPRESSION"]:
        logger.debug("[LBC] disabled — passing through %d chunk(s)", len(chunks))
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"compressed_document_chunks": chunks, "lbc_validation_pairs_documents": []}
    result, pairs = _run_lbc(chunks, query, sw, config=config)
    logger.info("[COMPRESS] LBC_documents complete — %d chunk(s) remain", len(result))
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {"compressed_document_chunks": result, "lbc_validation_pairs_documents": pairs}


def validate_lbc_documents(state: GraphState, config=None) -> dict:
    """Always-present pass-through; validates when ENABLE_COMPRESSION_VALIDATION is True."""
    _t0 = time.perf_counter()
    _validate_lbc_pairs(
        "validate_LBC_documents",
        state.get("lbc_validation_pairs_documents") or [],
        state.get("query", ""),
        get_switches(state),
        config=config,
    )
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {}


# ── Learned-QA track ──────────────────────────────────────────────────────────

def execute_lbc_learned_qa(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    sw = get_switches(state)
    chunks = state.get("dc_output_learned_qa_chunks") or []
    query = state["query"]
    logger.info("[COMPRESS] running LBC_learned_qa on %d chunk(s)", len(chunks))
    if not sw["ENABLE_LBC_COMPRESSION"]:
        logger.debug("[LBC] disabled — passing through %d chunk(s)", len(chunks))
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"compressed_learned_qa_chunks": chunks, "lbc_validation_pairs_learned_qa": []}
    result, pairs = _run_lbc(chunks, query, sw, config=config)
    logger.info("[COMPRESS] LBC_learned_qa complete — %d chunk(s) remain", len(result))
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {"compressed_learned_qa_chunks": result, "lbc_validation_pairs_learned_qa": pairs}


def validate_lbc_learned_qa(state: GraphState, config=None) -> dict:
    """Always-present pass-through; validates when ENABLE_COMPRESSION_VALIDATION is True."""
    _t0 = time.perf_counter()
    _validate_lbc_pairs(
        "validate_LBC_learned_qa",
        state.get("lbc_validation_pairs_learned_qa") or [],
        state.get("query", ""),
        get_switches(state),
        config=config,
    )
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "LBC Compression", exclude={"execute_lbc_documents", "validate_lbc_documents", "execute_lbc_learned_qa", "validate_lbc_learned_qa"})

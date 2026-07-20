from __future__ import annotations
import logging
from typing import Any, Literal, TypedDict

from .llm_caller import llm_invoke, LLMErrorKind
from .fix_llm_output import fix_llm_output, _parse_to_python
from .switches import DEFAULT_SWITCHES

logger = logging.getLogger(__name__)

from .prompts import (
    _RETRIEVAL_JUDGE_PROMPT,
    _MERGE_JUDGE_PROMPT,
    _REDUNDANCY_JUDGE_PROMPT,
    _LBC_JUDGE_PROMPT,
    _THIN,
    _THICK,
)


def _log_validation_warning(message: str, raw: str = "") -> None:
    logger.warning(message)
    if raw:
        logger.debug("Raw validator response:\n%s", raw[:400])


RetrievalVerdict   = Literal["PASS", "PARTIAL", "FAIL", "UNKNOWN"]
MergeVerdict       = Literal["FAITHFUL", "UNFAITHFUL", "UNKNOWN"]
RedundancyVerdict  = Literal["CONFIRMED", "REJECTED"]


class RetrievalCheckResult(TypedDict):
    verdict: RetrievalVerdict
    relevant_count: int
    total_count: int
    per_chunk: list[dict]      # [{"index": int, "relevant": bool, "reason": str}, ...]
    overall_reason: str
    raw: str                   # raw LLM response, for logging/debugging

class MergeCheckResult(TypedDict):
    verdict: MergeVerdict
    fabricated_claims: list[str]   # facts in merged chunk NOT in sources
    dropped_claims: list[str]      # facts in sources NOT carried over
    overall_reason: str
    raw: str

class RedundancyGroupResult(TypedDict):
    """Verdict for one redundancy group proposed by the DC scanner LLM."""
    group_index: int                      # position in the input groups list
    verdict: RedundancyVerdict            # CONFIRMED or REJECTED
    reason: str                           # one sentence explaining the decision
    members: list[dict]                   # echo of the original members for easy lookup

class RedundancyCheckResult(TypedDict):
    confirmed_groups: list[RedundancyGroupResult]   # safe to remove non-keeper copies
    rejected_groups:  list[RedundancyGroupResult]   # must NOT remove — not truly redundant
    raw: str                                         # raw LLM response for debugging

class LBCCheckResult(TypedDict):
    verdict: Literal["SAFE", "OVER_COMPRESSED", "FABRICATED", "UNKNOWN"]
    fabricated_claims: list[str]   # sentences in compressed output not in original
    lost_relevant_facts: list[str] # query-relevant facts dropped from original
    overall_reason: str
    raw: str

def validate_retrieval(
    query: str,
    chunks: list[dict],
    judge_llm,
    max_chunk_chars: int = 1000,
    config=None,
    switches: dict | None = None,
) -> RetrievalCheckResult:
    sw = switches or DEFAULT_SWITCHES
    if not chunks:
        return RetrievalCheckResult(
            verdict="FAIL",
            relevant_count=0,
            total_count=0,
            per_chunk=[],
            overall_reason="No chunks were retrieved.",
            raw="",
        )

    blocks = []
    for i, c in enumerate(chunks):
        content = (c.get("content") or "").strip()
        if len(content) > max_chunk_chars:
            content = content[:max_chunk_chars] + " …[truncated]"
        src = (c.get("metadata") or {}).get("source", "?") if "metadata" in c else c.get("source", "?")
        blocks.append(f"--- chunk {i} (source: {src}) ---\n{content}")
    chunks_block = "\n\n".join(blocks)

    prompt = _RETRIEVAL_JUDGE_PROMPT.format(query=query, chunks_block=chunks_block)

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [VALIDATE-RETRIEVAL] judging {len(chunks)} chunk(s) for query: \"{query[:80]}\"")
    logger.debug(_THIN)

    raw = ""
    _retrieval_llm_result = llm_invoke(
        judge_llm, [{"role": "system", "content": prompt}],
        caller_tag="VALIDATE-RETRIEVAL",
        config=config,
    )
    if not _retrieval_llm_result.ok:
        logger.debug(
            f"  [VALIDATE-RETRIEVAL] LLM call failed "
            f"({_retrieval_llm_result.error_kind.name}): "
            f"{_retrieval_llm_result.error_message[:200]}"
        )
        return RetrievalCheckResult(
            verdict="UNKNOWN",
            relevant_count=0,
            total_count=len(chunks),
            per_chunk=[],
            overall_reason=(
                f"Judge LLM error ({_retrieval_llm_result.error_kind.name}): "
                f"{_retrieval_llm_result.error_message}"
            ),
            raw="",
        )
    raw = _retrieval_llm_result.content

    if sw["ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
        llm_result, _ok = fix_llm_output("retrieval_judge", raw, llm=judge_llm, config=config)
        if not _ok or not isinstance(llm_result, dict) or "verdict" not in llm_result:
            logger.warning("  [VALIDATE-RETRIEVAL] failed to fix malformed LLM output.")
            _log_validation_warning("[VALIDATE-RETRIEVAL] failed to parse JSON", raw)
            return RetrievalCheckResult(
                verdict="UNKNOWN",
                relevant_count=0,
                total_count=len(chunks),
                per_chunk=[],
                overall_reason="Judge response was not valid JSON.",
                raw=raw,
            )
        else:
            logger.info("  [VALIDATE-RETRIEVAL] successfully fixed malformed LLM output.")
    else:
        llm_result = _parse_to_python(raw)

    if not isinstance(llm_result, dict):
        _log_validation_warning("[VALIDATE-RETRIEVAL] failed to parse JSON", raw)
        return RetrievalCheckResult(
            verdict="UNKNOWN",
            relevant_count=0,
            total_count=len(chunks),
            per_chunk=[],
            overall_reason="Judge response was not valid JSON.",
            raw=raw,
        )

    verdict = llm_result.get("verdict", "UNKNOWN")
    if verdict not in ("PASS", "PARTIAL", "FAIL"):
        verdict = "UNKNOWN"

    per_chunk = llm_result.get("per_chunk", []) or []
    if not isinstance(per_chunk, list):
        per_chunk = []
    per_chunk = [pc for pc in per_chunk if isinstance(pc, dict)]
    relevant_count = sum(1 for pc in per_chunk if pc.get("relevant") is True)

    result = RetrievalCheckResult(
        verdict=verdict,
        relevant_count=relevant_count,
        total_count=len(chunks),
        per_chunk=per_chunk,
        overall_reason=llm_result.get("overall_reason", ""),
        raw=raw,
    )

    logger.debug(f"  [VALIDATE-RETRIEVAL] verdict={verdict}  "
          f"relevant={relevant_count}/{len(chunks)}")
    logger.debug(f"  [VALIDATE-RETRIEVAL] reason: {result['overall_reason'][:200]}")
    for pc in per_chunk:
        flag = "✓" if pc.get("relevant") else "✗"
        logger.debug(f"    {flag} chunk {pc.get('index', '?')}: {pc.get('reason', '')[:120]}")
    logger.debug(_THIN)

    return result
def validate_merge(
    source_chunks: list[dict],
    merged_chunk: dict,
    judge_llm,
    max_chunk_chars: int = 1200,
    config=None,
    switches: dict | None = None,
) -> MergeCheckResult:
    sw = switches or DEFAULT_SWITCHES
    if not source_chunks:
        return MergeCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            dropped_claims=[],
            overall_reason="No source chunks provided.",
            raw="",
        )

    merged_content = (merged_chunk.get("content") or "").strip()
    if not merged_content:
        return MergeCheckResult(
            verdict="UNFAITHFUL",
            fabricated_claims=[],
            dropped_claims=["(merged output is empty)"],
            overall_reason="Merged chunk has no content.",
            raw="",
        )

    # Build source block
    src_blocks = []
    for i, c in enumerate(source_chunks):
        content = (c.get("content") or "").strip()
        if len(content) > max_chunk_chars:
            content = content[:max_chunk_chars] + " …[truncated]"
        src = c.get("source", "?")
        src_blocks.append(f"--- source {i} ({src}) ---\n{content}")
    sources_block = "\n\n".join(src_blocks)

    if len(merged_content) > max_chunk_chars * 2:
        merged_block_text = merged_content[: max_chunk_chars * 2] + " …[truncated]"
    else:
        merged_block_text = merged_content

    prompt = _MERGE_JUDGE_PROMPT.format(
        sources_block=sources_block,
        merged_block=merged_block_text,
    )

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [VALIDATE-MERGE] judging merge of {len(source_chunks)} source chunk(s)")
    logger.debug(_THIN)

    raw = ""
    _merge_llm_result = llm_invoke(
        judge_llm, [{"role": "system", "content": prompt}],
        caller_tag="VALIDATE-MERGE",
        config=config,
    )
    if not _merge_llm_result.ok:
        logger.debug(
            f"  [VALIDATE-MERGE] LLM call failed "
            f"({_merge_llm_result.error_kind.name}): "
            f"{_merge_llm_result.error_message[:200]}"
        )
        return MergeCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            dropped_claims=[],
            overall_reason=(
                f"Judge LLM error ({_merge_llm_result.error_kind.name}): "
                f"{_merge_llm_result.error_message}"
            ),
            raw="",
        )
    raw = _merge_llm_result.content
    parsed_raw = _parse_to_python(raw)
    if isinstance(parsed_raw, dict) and (
        not isinstance(parsed_raw.get("fabricated_claims"), list)
        or not isinstance(parsed_raw.get("dropped_claims"), list)
    ):
        _log_validation_warning("[VALIDATE-MERGE] missing or invalid claim lists", raw)
        return MergeCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            dropped_claims=[],
            overall_reason=(
                "Judge response must contain fabricated_claims and dropped_claims lists."
            ),
            raw=raw,
        )

    if sw["ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
        llm_result, _ok = fix_llm_output("merge_judge", raw, llm=judge_llm, config=config)
        if not _ok or not isinstance(llm_result, dict):
            _log_validation_warning("[VALIDATE-MERGE] failed to parse JSON", raw)
            return MergeCheckResult(
                verdict="UNKNOWN",
                fabricated_claims=[],
                dropped_claims=[],
                overall_reason="Judge response was not valid JSON.",
                raw=raw,
            )
        else:            
            logger.info("  [VALIDATE-MERGE] successfully fixed malformed LLM output.")
    else:
        llm_result = parsed_raw

    if not isinstance(llm_result, dict):
        _log_validation_warning("[VALIDATE-MERGE] failed to parse JSON", raw)
        return MergeCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            dropped_claims=[],
            overall_reason="Judge response was not valid JSON.",
            raw=raw,
        )

    fabricated = llm_result.get("fabricated_claims")
    dropped = llm_result.get("dropped_claims")
    if not isinstance(fabricated, list) or not isinstance(dropped, list):
        _log_validation_warning("[VALIDATE-MERGE] missing or invalid claim lists", raw)
        return MergeCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            dropped_claims=[],
            overall_reason=(
                "Judge response must contain fabricated_claims and dropped_claims lists."
            ),
            raw=raw,
        )

    # Derive verdict from the lists: any fabrication or any meaningful drop ⇒ UNFAITHFUL.
    verdict: MergeVerdict = "UNFAITHFUL" if (fabricated or dropped) else "FAITHFUL"

    result = MergeCheckResult(
        verdict=verdict,
        fabricated_claims=[str(x) for x in fabricated],
        dropped_claims=[str(x) for x in dropped],
        overall_reason=llm_result.get("overall_reason", ""),
        raw=raw,
    )

    logger.debug(f"  [VALIDATE-MERGE] verdict={verdict}  "
          f"fabricated={len(fabricated)}  dropped={len(dropped)}")
    logger.debug(f"  [VALIDATE-MERGE] reason: {result['overall_reason'][:200]}")
    for f in fabricated:
        logger.debug(f"    fabricated: {str(f)[:160]}")
    for d in dropped:
        logger.debug(f"    dropped:    {str(d)[:160]}")
    logger.debug(_THIN)

    return result


def validate_redundancy(
    window_chunks: list[dict],
    groups: list[list[dict]],
    judge_llm,
    max_chunk_chars: int = 1000,
    config=None,
    switches: dict | None = None,
) -> RedundancyCheckResult:
    sw = switches or DEFAULT_SWITCHES
    if not groups:
        return RedundancyCheckResult(
            confirmed_groups=[],
            rejected_groups=[],
            raw="",
        )

    # ── Build chunks block ────────────────────────────────────────────────────
    chunk_blocks = []
    for local_i, chunk in enumerate(window_chunks):
        content = (chunk.get("content") or "").strip()
        if len(content) > max_chunk_chars:
            content = content[:max_chunk_chars] + " …[truncated]"
        src = chunk.get("source", "?")
        chunk_blocks.append(f"--- chunk {local_i} (source: {src}) ---\n{content}")
    chunks_block = "\n\n".join(chunk_blocks)

    # ── Build groups block ────────────────────────────────────────────────────
    group_blocks = []
    for g_idx, members in enumerate(groups):
        lines = [f"Group {g_idx}:"]
        for m in members:
            lines.append(
                f"  chunk_index={m['chunk_index']}  "
                f"sentence=\"{m['sentence']}\""
            )
        group_blocks.append("\n".join(lines))
    groups_block = "\n\n".join(group_blocks)

    prompt = _REDUNDANCY_JUDGE_PROMPT.format(
        chunks_block=chunks_block,
        groups_block=groups_block,
    )

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [VALIDATE-REDUNDANCY] judging {len(groups)} group(s) across "
          f"{len(window_chunks)} chunk(s)")
    logger.debug(_THIN)

    raw = ""
    _redundancy_llm_result = llm_invoke(
        judge_llm, [{"role": "system", "content": prompt}],
        caller_tag="VALIDATE-REDUNDANCY",
        config=config,
    )
    if not _redundancy_llm_result.ok:
        logger.debug(
            f"  [VALIDATE-REDUNDANCY] LLM call failed "
            f"({_redundancy_llm_result.error_kind.name}): "
            f"{_redundancy_llm_result.error_message[:200]} "
            f"— treating all groups as REJECTED (safe default)"
        )
        rejected = [
            RedundancyGroupResult(
                group_index=i,
                verdict="REJECTED",
                reason=(
                    f"Judge LLM error ({_redundancy_llm_result.error_kind.name}): "
                    f"{_redundancy_llm_result.error_message}"
                ),
                members=groups[i],
            )
            for i in range(len(groups))
        ]
        return RedundancyCheckResult(confirmed_groups=[], rejected_groups=rejected, raw="")
    raw = _redundancy_llm_result.content

    # ── Parse response ────────────────────────────────────────────────────────
    if sw["ENABLE_COMPRESSION_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
        llm_result, _ok = fix_llm_output("redundancy_judge", raw, llm=judge_llm, config=config)
        if not _ok or not isinstance(llm_result, list):
            logger.warning(f"  [VALIDATE-REDUNDANCY] failed to parse JSON — treating all groups as REJECTED")
            logger.debug(f"  raw: {raw[:400]}")
            rejected = [
                RedundancyGroupResult(
                    group_index=i,
                    verdict="REJECTED",
                    reason="Judge response was not valid JSON.",
                    members=groups[i],
                )
                for i in range(len(groups))
            ]
            return RedundancyCheckResult(confirmed_groups=[], rejected_groups=rejected, raw=raw)
        else:
            logger.info("  [VALIDATE-REDUNDANCY] successfully fixed malformed LLM output.")
    else:
        llm_result = _parse_to_python(raw)

    if not isinstance(llm_result, list):
        rejected = [
            RedundancyGroupResult(
                group_index=i,
                verdict="REJECTED",
                reason="Judge response was not valid JSON.",
                members=groups[i],
            )
            for i in range(len(groups))
        ]
        return RedundancyCheckResult(confirmed_groups=[], rejected_groups=rejected, raw=raw)

    # ── Map group_index → verdict from parsed response ───────────────────────
    verdict_map: dict[int, tuple[str, str]] = {}   # group_index → (verdict, reason)
    for item in llm_result:
        if not isinstance(item, dict):
            continue
        g_idx   = item.get("group_index")
        verdict = str(item.get("verdict") or "").upper().strip()
        reason  = str(item.get("reason") or "").strip()
        if not isinstance(g_idx, int) or verdict not in ("CONFIRMED", "REJECTED"):
            continue
        if g_idx < 0 or g_idx >= len(groups):
            # Out-of-range index — the LLM hallucinated a group that doesn't exist
            logger.warning(f"  [VALIDATE-REDUNDANCY] ignoring out-of-range group_index={g_idx} "
                  f"(only {len(groups)} group(s) were submitted)")
            continue
        if g_idx not in verdict_map:          # first verdict wins
            verdict_map[g_idx] = (verdict, reason)

    # Any group the LLM didn't mention defaults to REJECTED (safe)
    confirmed: list[RedundancyGroupResult] = []
    rejected:  list[RedundancyGroupResult] = []

    for i, members in enumerate(groups):
        v, r = verdict_map.get(i, ("REJECTED", "No verdict returned by judge — defaulting to REJECTED"))
        entry = RedundancyGroupResult(
            group_index=i,
            verdict=v,           # type: ignore[arg-type]
            reason=r,
            members=members,
        )
        if v == "CONFIRMED":
            confirmed.append(entry)
        else:
            rejected.append(entry)

    # ── Logging ───────────────────────────────────────────────────────────────
    logger.debug(f"  [VALIDATE-REDUNDANCY] confirmed={len(confirmed)}  rejected={len(rejected)}")
    for entry in confirmed:
        logger.debug(f"    ✓ group {entry['group_index']} CONFIRMED: {entry['reason'][:120]}")
        for m in entry["members"]:
            logger.debug(f"        chunk {m['chunk_index']}: \"{m['sentence'][:100]}\"")
    for entry in rejected:
        logger.debug(f"    ✗ group {entry['group_index']} REJECTED:  {entry['reason'][:120]}")
        for m in entry["members"]:
            logger.debug(f"        chunk {m['chunk_index']}: \"{m['sentence'][:100]}\"")
    logger.debug(_THIN)

    return RedundancyCheckResult(confirmed_groups=confirmed, rejected_groups=rejected, raw=raw)

def validate_lbc(
    query: str,
    source_chunk: dict,
    compressed_chunk: dict,
    judge_llm,
    max_chunk_chars: int = 1500,
    config=None,
    switches: dict | None = None,
) -> LBCCheckResult:
    sw = switches or DEFAULT_SWITCHES

    original_content    = (source_chunk.get("content") or "").strip()
    compressed_content  = (compressed_chunk.get("content") or "").strip()
    source              = source_chunk.get("source", "?")

    if not original_content:
        return LBCCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            lost_relevant_facts=[],
            overall_reason="Original chunk is empty — nothing to validate.",
            raw="",
        )
    if not compressed_content:
        return LBCCheckResult(
            verdict="OVER_COMPRESSED",
            fabricated_claims=[],
            lost_relevant_facts=["(entire chunk content was removed)"],
            overall_reason="Compressed chunk is empty — all content was stripped.",
            raw="",
        )

    # Truncate for prompt safety
    if len(original_content) > max_chunk_chars:
        original_content = original_content[:max_chunk_chars] + " …[truncated]"
    if len(compressed_content) > max_chunk_chars:
        compressed_content = compressed_content[:max_chunk_chars] + " …[truncated]"

    prompt = _LBC_JUDGE_PROMPT.format(
        query=query,
        source=source,
        original_content=original_content,
        compressed_content=compressed_content,
    )

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [VALIDATE-LBC] judging compressed chunk from source: '{source[:60]}'")
    logger.debug(f"  [VALIDATE-LBC] query: \"{query[:80]}\"")
    logger.debug(_THIN)

    raw = ""
    _lbc_llm_result = llm_invoke(
        judge_llm, [{"role": "system", "content": prompt}],
        caller_tag="VALIDATE-LBC",
        config=config,
    )
    if not _lbc_llm_result.ok:
        logger.debug(
            f"  [VALIDATE-LBC] LLM call failed "
            f"({_lbc_llm_result.error_kind.name}): "
            f"{_lbc_llm_result.error_message[:200]}"
        )
        return LBCCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            lost_relevant_facts=[],
            overall_reason=(
                f"Judge LLM error ({_lbc_llm_result.error_kind.name}): "
                f"{_lbc_llm_result.error_message}"
            ),
            raw="",
        )
    raw = _lbc_llm_result.content

    if sw["ENABLE_COMPRESSION_OUTPUT_FIX"] and sw["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
        llm_result, _ok = fix_llm_output("lbc_judge", raw, llm=judge_llm, config=config)
        if not _ok or not isinstance(llm_result, dict) or "verdict" not in llm_result:
            _log_validation_warning("[VALIDATE-LBC] failed to parse JSON", raw)
            return LBCCheckResult(
                verdict="UNKNOWN",
                fabricated_claims=[],
                lost_relevant_facts=[],
                overall_reason="Judge response was not valid JSON.",
                raw=raw,
            )
        else:
            logger.info("  [VALIDATE-LBC] successfully fixed malformed LLM output.")
    else:
        llm_result = _parse_to_python(raw)

    if not isinstance(llm_result, dict):
        _log_validation_warning("[VALIDATE-LBC] failed to parse JSON", raw)
        return LBCCheckResult(
            verdict="UNKNOWN",
            fabricated_claims=[],
            lost_relevant_facts=[],
            overall_reason="Judge response was not valid JSON.",
            raw=raw,
        )

    verdict = llm_result.get("verdict", "UNKNOWN")
    if verdict not in ("SAFE", "OVER_COMPRESSED", "FABRICATED", "UNKNOWN"):
        verdict = "UNKNOWN"

    fabricated        = llm_result.get("fabricated_claims", []) or []
    lost_relevant     = llm_result.get("lost_relevant_facts", []) or []
    if not isinstance(fabricated, list):    fabricated = []
    if not isinstance(lost_relevant, list): lost_relevant = []

    result = LBCCheckResult(
        verdict=verdict,
        fabricated_claims=[str(x) for x in fabricated],
        lost_relevant_facts=[str(x) for x in lost_relevant],
        overall_reason=llm_result.get("overall_reason", ""),
        raw=raw,
    )

    logger.debug(f"  [VALIDATE-LBC] verdict={verdict}  "
          f"fabricated={len(fabricated)}  lost_relevant={len(lost_relevant)}")
    logger.debug(f"  [VALIDATE-LBC] reason: {result['overall_reason'][:200]}")
    for f in fabricated:
        logger.debug(f"    fabricated:    {str(f)[:160]}")
    for l in lost_relevant:
        logger.debug(f"    lost_relevant: {str(l)[:160]}")
    logger.debug(_THIN)

    return result


from .operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Validation")

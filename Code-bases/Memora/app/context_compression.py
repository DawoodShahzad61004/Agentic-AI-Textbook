import json
import logging
import re
import time
from llm_caller import llm_invoke, LLMErrorKind
from validators import validate_merge, validate_redundancy, validate_lbc
from fix_llm_output import fix_llm_output, _parse_to_python
import timing_tracker as _timing

logger = logging.getLogger(__name__)

from config import (
    LLM_RESPONSE_RETRY_LIMIT,
    DC_WINDOW_SIZE,
    LBC_MIN_RETENTION_RATIO,
    ENABLE_COMPRESSION_VALIDATION,
    ENABLE_NAC_COMPRESSION,
    ENABLE_DC_COMPRESSION,
    ENABLE_LBC_COMPRESSION,
    ENABLE_COMPRESSION_OUTPUT_FIX,
    ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX,
    ENABLE_GLOBAL_LLM_OUTPUT_FIX,
)

from prompts import (
    _CHUNK_MERGE_PROMPT, 
    _DC_SCAN_PROMPT, 
    _LBC_COMPRESS_PROMPT, 
    _LBC_DEFAULT_INSTRUCTIONS,
    _THIN,
)

def _normalize_source(path: str) -> str:
    return path.replace("\\", "/")


def _denormalize_source(normalized: str, original_sources: list[str]) -> str:
    for orig in original_sources:
        if _normalize_source(orig) == normalized:
            return orig
    return normalized


def _merge_similar_chunks(
    similar_chunks: list[dict],
    llm,
    embedding_manager,
    feedback: str = "",
    *,
    output_fix_enabled: bool,
) -> dict:
    original_sources = [c["source"] for c in similar_chunks]
    normalized_chunks = [
        {**c, "source": _normalize_source(c["source"])} for c in similar_chunks
    ]

    formatted_input = "\n\n".join(
        f"[Source: {json.dumps(nc['source'])}]\n{json.dumps(nc['content'])}"
        for nc in normalized_chunks
    )
    prompt = f"{_CHUNK_MERGE_PROMPT}\n\nINPUT CHUNKS:\n{formatted_input}"

    if feedback:
        prompt += (
            "\n\nPREVIOUS ATTEMPT WAS REJECTED BY A FAITHFULNESS JUDGE."
            " Fix these issues in your next attempt:\n"
            f"{feedback}\n"
            "Stay strictly within the source chunks above. Do not introduce any"
            " claim that is not stated in them, and do not omit any factual claim"
            " that they make."
        )

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [CHUNK MERGE] consolidating {len(similar_chunks)} chunks "
          f"from sources: {original_sources}")
    if feedback:
        logger.debug(f"  [CHUNK MERGE] retry with judge feedback ({len(feedback)} chars)")
    logger.debug(_THIN)

    try:
        raw = ""
        for attempt in range(LLM_RESPONSE_RETRY_LIMIT):
            merge_result = llm_invoke(
                llm, [{"role": "system", "content": prompt}], caller_tag="MERGE"
            )
            if not merge_result.ok:
                if merge_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(f"  [CHUNK MERGE] transient error on attempt {attempt + 1} "
                          f"({merge_result.error_kind.name}) — retrying…")
                    continue
                logger.error(f"  [CHUNK MERGE] non-retryable error "
                     f"({merge_result.error_kind.name}): "
                     f"{merge_result.error_message[:200]} — aborting merge")
                return similar_chunks[0]
            raw = merge_result.content
            logger.debug(f"  [CHUNK MERGE] LLM response on attempt {attempt + 1}:\n{raw}")
            if raw:
                break
            logger.warning(f"  [CHUNK MERGE] empty response on attempt {attempt + 1}, retrying...")

        if not raw:
            raise json.JSONDecodeError("empty response after retry", "", 0)

        # Fix unescaped quotes inside [Source: "path"] tags before JSON parsing
        pre = re.sub(r'\[Source:\s*"([^"]+)"\]', r'[Source: \1]', raw)
        if output_fix_enabled and ENABLE_GLOBAL_LLM_OUTPUT_FIX:
            parsed, _ok = fix_llm_output("merge", pre, llm=llm)
        else:
            parsed = _parse_to_python(pre)
            _ok = parsed is not None
        if not _ok or not isinstance(parsed, dict) or "content" not in parsed:
            raise KeyError("fix_llm_output could not parse merge response")
        merged_content = parsed["content"]

        normalized_merged_sources = parsed.get(
            "sources",
            [nc["source"] for nc in normalized_chunks],
        )
        merged_sources = [
            _denormalize_source(s, original_sources)
            for s in normalized_merged_sources
        ]

        logger.info(f"  [CHUNK MERGE] success — {len(merged_content)} chars, "
              f"{len(merged_sources)} source(s)")
        logger.debug(_THIN)

        merged: dict = {
            "content": merged_content,
            "source": ", ".join(merged_sources),
            "embedding": embedding_manager.generate_embedding(merged_content),
        }

        seqs = [c.get("chunk_seq") for c in similar_chunks if isinstance(c.get("chunk_seq"), int)]
        srcs = [c.get("source", "") for c in similar_chunks]
        if seqs and len(set(srcs)) == 1:
            merged["chunk_seq"] = min(seqs)

        return merged

    except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
        logger.warning(f"  [CHUNK MERGE] FAILED ({type(e).__name__}: {e}) — keeping first chunk only")
        logger.debug(_THIN)
        return similar_chunks[0]


# ─────────────────────────────────────────────────────────────────────────────
# NAC — Neighbor-Aware Compression
# ─────────────────────────────────────────────────────────────────────────────
def compress_neighbor_chunks(
    accumulated_chunks: list[dict],
    llm,
    embedding_manager,
    judge_llm,
) -> list[dict]:
    if not accumulated_chunks:
        return accumulated_chunks

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [NAC] Neighbor-Aware Compression — scanning {len(accumulated_chunks)} chunk(s)")
    logger.debug(_THIN)

    eligible = [(i, c) for i, c in enumerate(accumulated_chunks)
                if isinstance(c.get("chunk_seq"), int)]
    ineligible = [(i, c) for i, c in enumerate(accumulated_chunks)
                  if not isinstance(c.get("chunk_seq"), int)]

    if not eligible:
        logger.warning(f"  [NAC] No chunks carry chunk_seq — skipping compression.")
        logger.debug(_THIN)
        return accumulated_chunks

    eligible.sort(key=lambda x: (x[1]["source"], x[1]["chunk_seq"]))
    runs: list[list[tuple[int, dict]]] = []
    current_run: list[tuple[int, dict]] = [eligible[0]]

    for orig_idx, chunk in eligible[1:]:
        prev_chunk = current_run[-1][1]
        same_source = chunk["source"] == prev_chunk["source"]
        consecutive_seq = chunk["chunk_seq"] == prev_chunk["chunk_seq"] + 1
        if same_source and consecutive_seq:
            current_run.append((orig_idx, chunk))
        else:
            runs.append(current_run)
            current_run = [(orig_idx, chunk)]
    runs.append(current_run)

    neighbor_runs = [r for r in runs if len(r) > 1]
    solo_runs = [r for r in runs if len(r) == 1]

    logger.debug(f"  [NAC] {len(neighbor_runs)} neighbor run(s) found | "
          f"{len(solo_runs)} singleton(s) pass through unchanged")
    for run in neighbor_runs:
        seqs = [c["chunk_seq"] for _, c in run]
        logger.debug(f"    run: source={run[0][1]['source']}  "
              f"seq={seqs[0]}→{seqs[-1]}  ({len(run)} chunks)")

    result_chunks: list[dict] = []

    for run in runs:
        if len(run) == 1:
            result_chunks.append(run[0][1])
            continue

        source_chunks_for_merge = [c for _, c in run]
        feedback = ""
        merged = None

        for attempt in range(1, LLM_RESPONSE_RETRY_LIMIT + 1):
            logger.debug(f"\n  [NAC MERGE attempt {attempt}/{LLM_RESPONSE_RETRY_LIMIT}] "
                  f"{len(run)} chunks from '{run[0][1]['source']}'  "
                  f"seq {run[0][1]['chunk_seq']}→{run[-1][1]['chunk_seq']}")

            _t_nac = time.perf_counter()
            candidate = _merge_similar_chunks(
                source_chunks_for_merge,
                llm,
                embedding_manager,
                feedback=feedback,
                output_fix_enabled=ENABLE_COMPRESSION_OUTPUT_FIX,
            )
            _timing.record("Compression", time.perf_counter() - _t_nac)

            if ENABLE_COMPRESSION_VALIDATION:
                _t_nac_val = time.perf_counter()
                check = validate_merge(
                    source_chunks=source_chunks_for_merge,
                    merged_chunk=candidate,
                    judge_llm=judge_llm,
                )
                _timing.record("Compression", time.perf_counter() - _t_nac_val)

                if check["verdict"] == "FAITHFUL":
                    candidate["chunk_seq_start"] = run[0][1]["chunk_seq"]
                    candidate["chunk_seq_end"] = run[-1][1]["chunk_seq"]
                    candidate.pop("chunk_seq", None)
                    merged = candidate
                    logger.info(f"  [NAC MERGE] success on attempt {attempt} "
                          f"(verdict={check['verdict']})")
                    break

                issues = []
                for claim in check.get("fabricated_claims", []):
                    issues.append(f"- FABRICATED: \"{str(claim)[:200]}\"")
                for claim in check.get("dropped_claims", []):
                    issues.append(f"- DROPPED: \"{str(claim)[:200]}\"")
                feedback = "\n".join(issues) or check.get("overall_reason", "Unfaithful merge.")
                logger.warning(f"  [NAC MERGE] attempt {attempt} rejected — retrying with feedback")
            else:
                candidate["chunk_seq_start"] = run[0][1]["chunk_seq"]
                candidate["chunk_seq_end"] = run[-1][1]["chunk_seq"]
                candidate.pop("chunk_seq", None)
                merged = candidate
                logger.warning(f"  [NAC MERGE] validation disabled — accepting on attempt {attempt}")
                break

        if merged is None:
            logger.warning(f"  [NAC MERGE] abandoned after {LLM_RESPONSE_RETRY_LIMIT} attempt(s) — "
                  f"keeping {len(run)} originals")
            result_chunks.extend(source_chunks_for_merge)
        else:
            result_chunks.append(merged)

    result_chunks.extend(c for _, c in ineligible)

    saved = len(accumulated_chunks) - len(result_chunks)
    logger.debug(f"\n  [NAC] compression done: {len(accumulated_chunks)} → {len(result_chunks)} "
          f"chunk(s) ({saved} eliminated)")
    logger.debug(_THIN)

    return result_chunks

# ─────────────────────────────────────────────────────────────────────────────
# DC — Deduplication Compression
# ─────────────────────────────────────────────────────────────────────────────
def deduplicate_compression(
    chunks: list[dict],
    llm,
    judge_llm,
    window_size: int = DC_WINDOW_SIZE,
) -> list[dict]:
    if len(chunks) < 2:
        return chunks

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [DC] Deduplication Compression — {len(chunks)} chunk(s), window={window_size}")
    logger.debug(_THIN)

    result: list[dict] = [dict(c) for c in chunks]
    total_sentences_removed = 0

    for window_start in range(0, len(result), window_size):
        window_end = min(window_start + window_size, len(result))
        window = result[window_start:window_end]

        if len(window) < 2:
            continue

        _source_tag_re = re.compile(r"\[Source:[^\]]*\]", re.IGNORECASE)
        blocks = []
        for local_i, chunk in enumerate(window):
            src = chunk.get("source", "?")
            content = _source_tag_re.sub("", (chunk.get("content") or "")).strip()
            blocks.append(f"--- chunk {local_i} (source: {src}) ---\n{content}")
        chunks_block = "\n\n".join(blocks)

        prompt = _DC_SCAN_PROMPT.format(chunks_block=chunks_block)

        logger.debug(f"\n  [DC] scanning window [{window_start}:{window_end}] "
              f"({len(window)} chunk(s))")

        raw = ""
        _t_dc_scan = time.perf_counter()
        for attempt in range(LLM_RESPONSE_RETRY_LIMIT):
            dc_result = llm_invoke(
                llm, [{"role": "system", "content": prompt}], caller_tag="DC"
            )
            if not dc_result.ok:
                if dc_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(f"  [DC] transient error on attempt {attempt + 1} "
                          f"({dc_result.error_kind.name}) — retrying…")
                    continue
                logger.error(f"  [DC] non-retryable error ({dc_result.error_kind.name}): "
                     f"{dc_result.error_message[:200]} — skipping window")
                break
            raw = dc_result.content
            if raw:
                break
            logger.debug(f"  [DC] empty LLM response on attempt {attempt + 1}, retrying…")
        _timing.record("Compression", time.perf_counter() - _t_dc_scan)

        if not raw:
            logger.warning(f"  [DC] no usable response after {LLM_RESPONSE_RETRY_LIMIT} attempt(s) "
                  f"— skipping window")
            continue

        if ENABLE_COMPRESSION_OUTPUT_FIX and ENABLE_GLOBAL_LLM_OUTPUT_FIX:
            flagged, _ok = fix_llm_output("dc_scan", raw, llm=llm)
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
                logger.debug(f"    chunk_index={m.get('chunk_index')}  "
                      f"sentence=\"{str(m.get('sentence', ''))[:120]}\"")

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
                logger.debug(f"  [DC] group dropped — all {len(clean_members)} member(s) "
                      f"are from chunk_index={next(iter(unique_chunk_indices))} "
                      f"(intra-chunk repetition, not cross-chunk redundancy)")
                continue
            valid_groups.append(clean_members)

        if not valid_groups:
            logger.warning(f"  [DC] no structurally valid groups after normalization — skipping window")
            continue

        if ENABLE_COMPRESSION_VALIDATION:
            _t_dc_val = time.perf_counter()
            redundancy_check = validate_redundancy(
                window_chunks=window,
                groups=valid_groups,
                judge_llm=judge_llm,
            )
            _timing.record("Compression", time.perf_counter() - _t_dc_val)

            if not redundancy_check["confirmed_groups"]:
                logger.warning(f"  [DC] no groups confirmed as genuinely redundant — skipping window")
                continue

            confirmed_groups = redundancy_check["confirmed_groups"]
        else:
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
                logger.warning(f"  [DC] chunk {global_idx}: cleaned content too short — skipping "
                      f"(would remove too much)")
                continue

            removed_count = len(sentences_to_remove)
            logger.debug(f"\n  [DC] chunk {global_idx}: removing {removed_count} confirmed-redundant "
                  f"sentence(s)")
            logger.debug(f"    before ({len(original_content)} chars): "
                  f"{original_content[:150]}…")
            logger.debug(f"    after  ({len(cleaned_content)} chars): "
                  f"{cleaned_content[:150]}…")

            result[global_idx] = {**original_chunk, "content": cleaned_content}
            total_sentences_removed += removed_count
            logger.debug(f"  [DC] chunk {global_idx}: INSTALLED cleaned version ✓")

    logger.debug(f"\n  [DC] done — {total_sentences_removed} redundant passage(s) removed "
          f"across {len(result)} chunk(s)")
    logger.debug(_THIN)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# LBC — LLM-Based Compression
# ─────────────────────────────────────────────────────────────────────────────
def llm_based_compression(
    chunks: list[dict],
    query: str,
    llm,
    judge_llm,
    instructions: str = _LBC_DEFAULT_INSTRUCTIONS,
    min_retention_ratio: float = LBC_MIN_RETENTION_RATIO,
) -> list[dict]:
    if not chunks:
        return chunks

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [LBC] LLM-Based Compression — {len(chunks)} chunk(s)")
    logger.debug(f"  [LBC] query: \"{query[:100]}\"")
    logger.debug(_THIN)

    result: list[dict] = []
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

        logger.debug(f"\n  [LBC] chunk {idx} — source: '{source[:60]}'  "
              f"({len(original_content)} chars)")

        raw = ""
        parsed_lbc: dict | None = None
        _t_lbc_scan = time.perf_counter()
        for attempt in range(1, LLM_RESPONSE_RETRY_LIMIT + 1):
            lbc_result = llm_invoke(
                llm, [{"role": "system", "content": prompt}], caller_tag="LBC"
            )
            if not lbc_result.ok:
                if lbc_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(f"  [LBC] chunk {idx}: transient error on attempt {attempt} "
                          f"({lbc_result.error_kind.name}) — retrying…")
                    raw = ""
                    continue
                logger.error(f"  [LBC] chunk {idx}: non-retryable error on attempt {attempt} "
                     f"({lbc_result.error_kind.name}): "
                     f"{lbc_result.error_message[:200]} — keeping original")
                raw = ""
                break
            raw = lbc_result.content

            if not raw:
                logger.warning(f"  [LBC] chunk {idx}: empty response on attempt {attempt}, retrying…")
                continue

            if ENABLE_COMPRESSION_OUTPUT_FIX and ENABLE_GLOBAL_LLM_OUTPUT_FIX:
                candidate, _ok = fix_llm_output("lbc_compress", raw, llm=llm)
            else:
                candidate = _parse_to_python(raw)
                _ok = candidate is not None
            if _ok and isinstance(candidate, dict) and "compressed" in candidate:
                parsed_lbc = candidate
                break
            logger.warning(f"  [LBC] chunk {idx}: failed to parse JSON on attempt {attempt}, retrying…")
        _timing.record("Compression", time.perf_counter() - _t_lbc_scan)

        if parsed_lbc is None:
            logger.warning(f"  [LBC] chunk {idx}: parse failed after {LLM_RESPONSE_RETRY_LIMIT} "
                    f"attempt(s) — keeping original")
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        compressed_text = (parsed_lbc.get("compressed") or "").strip()
        dropped_count = parsed_lbc.get("dropped_count", 0)
        lbc_reason = (parsed_lbc.get("reason") or "").strip()

        logger.debug(f"  [LBC] chunk {idx}: LLM produced {len(compressed_text)} chars "
              f"(dropped_count={dropped_count})  reason: {lbc_reason[:120]}")

        if compressed_text == "__IRRELEVANT__":
            logger.debug(f"  [LBC] chunk {idx}: marked __IRRELEVANT__ by LLM — dropping chunk")
            irrelevant_dropped += 1
            continue

        retention = len(compressed_text) / max(len(original_content), 1)
        if retention < min_retention_ratio:
            logger.debug(f"  [LBC] chunk {idx}: retention ratio {retention:.2f} < "
                  f"{min_retention_ratio} — keeping original (over-compression guard)")
            result.append(chunk)
            total_chars_after += len(original_content)
            skipped += 1
            continue

        if len(compressed_text) > len(original_content):
            logger.debug(f"  [LBC] chunk {idx}: 'compressed' output expanded "
                  f"({len(original_content)} → {len(compressed_text)} chars, "
                  f"+{len(compressed_text) - len(original_content)}) "
                  f"— keeping original (over-expansion guard)")
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
        if ENABLE_COMPRESSION_VALIDATION:
            _t_lbc_val = time.perf_counter()
            lbc_check = validate_lbc(
                query=query,
                source_chunk=chunk,
                compressed_chunk=compressed_chunk_dict,
                judge_llm=judge_llm,
            )
            _timing.record("Compression", time.perf_counter() - _t_lbc_val)

            if lbc_check["verdict"] == "SAFE":
                logger.debug(f"  [LBC] chunk {idx}: SAFE — installing "
                      f"({len(original_content)} → {len(compressed_text)} chars, "
                      f"−{len(original_content) - len(compressed_text)} chars)")
                result.append(compressed_chunk_dict)
                total_chars_after += len(compressed_text)
                accepted += 1

            elif lbc_check["verdict"] == "OVER_COMPRESSED":
                logger.debug(f"  [LBC] chunk {idx}: OVER_COMPRESSED — "
                      f"{len(lbc_check['lost_relevant_facts'])} relevant fact(s) lost "
                      f"— keeping original")
                for lrf in lbc_check["lost_relevant_facts"]:
                    logger.debug(f"    lost: {str(lrf)[:160]}")
                result.append(chunk)
                total_chars_after += len(original_content)
                skipped += 1

            elif lbc_check["verdict"] == "FABRICATED":
                logger.debug(f"  [LBC] chunk {idx}: FABRICATED — "
                      f"{len(lbc_check['fabricated_claims'])} invented claim(s) "
                      f"— keeping original")
                for fc in lbc_check["fabricated_claims"]:
                    logger.debug(f"    fabricated: {str(fc)[:160]}")
                result.append(chunk)
                total_chars_after += len(original_content)
                skipped += 1

            else:  # UNKNOWN
                logger.debug(f"  [LBC] chunk {idx}: judge UNKNOWN — keeping original (safe default)")
                result.append(chunk)
                total_chars_after += len(original_content)
                skipped += 1
        else:
            logger.warning(f"  [LBC] chunk {idx}: validation disabled — installing "
                  f"({len(original_content)} → {len(compressed_text)} chars, "
                  f"−{len(original_content) - len(compressed_text)} chars)")
            result.append(compressed_chunk_dict)
            total_chars_after += len(compressed_text)
            accepted += 1

    saved_chars = total_chars_before - total_chars_after
    pct = (saved_chars / max(total_chars_before, 1)) * 100

    logger.debug(f"\n  [LBC] done — {len(chunks)} → {len(result)} chunk(s) "
          f"({irrelevant_dropped} dropped as irrelevant, "
          f"{accepted} compressed, {skipped} kept as-is)")
    logger.debug(f"  [LBC] chars: {total_chars_before:,} → {total_chars_after:,} "
          f"(-{saved_chars:,} = {pct:.1f}% reduction)")
    logger.debug(_THIN)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline + formatting
# ─────────────────────────────────────────────────────────────────────────────
def format_context_for_llm(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    return "\n\n".join(
        f"[Source: {c['source']}]\n{c['content']}" for c in chunks
    )

def format_precedence_context_for_llm(
    learned_qa_chunks: list[dict],
    document_chunks: list[dict],
) -> str:
    """Format both independent tracks only at the answer-context boundary."""
    sections = [
        (
            "[CONFLICT RESOLUTION RULE]\n"
            "Use both context sections. If learned QA and document context conflict, "
            "prefer the learned QA response."
        )
    ]
    if learned_qa_chunks:
        sections.append(
            "[LEARNED QA CONTEXT - HIGH PRIORITY]\n"
            + format_context_for_llm(learned_qa_chunks)
        )
    if document_chunks:
        sections.append(
            "[DOCUMENT CONTEXT - SECONDARY]\n"
            + format_context_for_llm(document_chunks)
        )
    return "\n\n".join(sections) if learned_qa_chunks or document_chunks else ""

def compress_context_pipeline(
    chunks: list[dict],
    query: str,
    llm,
    embedding_manager,
    judge_llm,
) -> list[dict]:
    if not chunks:
        logger.warning(f"  [COMPRESS] no chunks to compress — skipping pipeline")
        return chunks

    if (not ENABLE_NAC_COMPRESSION and not ENABLE_DC_COMPRESSION and not ENABLE_LBC_COMPRESSION):
        logger.warning(f"  [COMPRESS] all compression stages disabled — skipping pipeline")
        return chunks
    logger.info(f"\n  [COMPRESS] running NAC → DC → LBC pipeline on {len(chunks)} chunk(s)")
    if ENABLE_NAC_COMPRESSION:
        chunks = compress_neighbor_chunks(chunks, llm, embedding_manager, judge_llm)
    if ENABLE_DC_COMPRESSION:
        chunks = deduplicate_compression(chunks, llm, judge_llm)
    if ENABLE_LBC_COMPRESSION:
        chunks = llm_based_compression(chunks, query, llm, judge_llm)
    logger.info(f"  [COMPRESS] pipeline complete — {len(chunks)} chunk(s) remain")
    return chunks

# Public chunk-merger used by the intra-retrieve cosine-similarity dedup step
# in agent_query.py.
def merge_similar_chunks(
    similar_chunks: list[dict],
    llm,
    embedding_manager,
    feedback: str = "",
) -> dict:
    return _merge_similar_chunks(
        similar_chunks,
        llm,
        embedding_manager,
        feedback=feedback,
        output_fix_enabled=ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX,
    )

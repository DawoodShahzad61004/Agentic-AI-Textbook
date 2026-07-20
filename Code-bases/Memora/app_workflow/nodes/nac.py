import json
import logging
import re
import time

from state import GraphState
from app_workflow.services.llm_setup import llm, judge_llm
from app_workflow.services.services import embedding_manager
from app_workflow.services.validators import validate_merge
from app_workflow.services.fix_llm_output import fix_llm_output, _parse_to_python
from app_workflow.services.llm_caller import llm_invoke, LLMErrorKind
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.switches import get_switches
from app_workflow.config import LLM_RESPONSE_RETRY_LIMIT
from app_workflow.services.prompts import _CHUNK_MERGE_PROMPT, _THIN

logger = logging.getLogger(__name__)


def _normalize_source(path: str) -> str:
    return path.replace("\\", "/")


def _denormalize_source(normalized: str, original_sources: list[str]) -> str:
    for orig in original_sources:
        if _normalize_source(orig) == normalized:
            return orig
    return normalized


def _merge_similar_chunks(
    similar_chunks: list[dict],
    _llm,
    _embedding_manager,
    feedback: str = "",
    *,
    output_fix_enabled: bool,
    switches: dict,
    config=None,
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
    logger.debug(
        f"  [CHUNK MERGE] consolidating {len(similar_chunks)} chunks "
        f"from sources: {original_sources}"
    )
    if feedback:
        logger.debug(f"  [CHUNK MERGE] retry with judge feedback ({len(feedback)} chars)")
    logger.debug(_THIN)

    try:
        raw = ""
        for attempt in range(LLM_RESPONSE_RETRY_LIMIT):
            merge_result = llm_invoke(
                _llm, [{"role": "system", "content": prompt}], caller_tag="NAC-MERGE", config=config
            )
            if not merge_result.ok:
                if merge_result.error_kind in (
                    LLMErrorKind.SERVER_ERROR,
                    LLMErrorKind.CONNECTION,
                    LLMErrorKind.TIMEOUT,
                ):
                    logger.warning(
                        f"  [CHUNK MERGE] transient error on attempt {attempt + 1} "
                        f"({merge_result.error_kind.name}) — retrying…"
                    )
                    continue
                logger.error(
                    f"  [CHUNK MERGE] non-retryable error "
                    f"({merge_result.error_kind.name}): "
                    f"{merge_result.error_message[:200]} — aborting merge"
                )
                return similar_chunks[0]
            raw = merge_result.content
            logger.debug(f"  [CHUNK MERGE] LLM response on attempt {attempt + 1}:\n{raw}")
            if raw:
                break
            logger.warning(f"  [CHUNK MERGE] empty response on attempt {attempt + 1}, retrying...")

        if not raw:
            raise json.JSONDecodeError("empty response after retry", "", 0)

        pre = re.sub(r'\[Source:\s*"([^"]+)"\]', r'[Source: \1]', raw)
        if output_fix_enabled and switches["ENABLE_GLOBAL_LLM_OUTPUT_FIX"]:
            parsed, _ok = fix_llm_output("merge", pre, llm=_llm, config=config)
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

        logger.info(
            f"  [CHUNK MERGE] success — {len(merged_content)} chars, "
            f"{len(merged_sources)} source(s)"
        )
        logger.debug(_THIN)

        merged: dict = {
            "content": merged_content,
            "source": ", ".join(merged_sources),
            "embedding": _embedding_manager.generate_embedding(merged_content),
        }

        seqs = [c.get("chunk_seq") for c in similar_chunks if isinstance(c.get("chunk_seq"), int)]
        sources = [c.get("source", "") for c in similar_chunks]
        if seqs and len(set(sources)) == 1:
            merged["chunk_seq"] = min(seqs)

        return merged

    except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
        logger.warning(
            f"  [CHUNK MERGE] FAILED ({type(e).__name__}: {e}) — keeping first chunk only"
        )
        logger.debug(_THIN)
        return similar_chunks[0]


def execute_nac_documents(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    sw = get_switches(state)
    accumulated_chunks = state.get("dedup_merged_document_chunks") or []
    logger.info("[COMPRESS] running NAC_documents on %d chunk(s)", len(accumulated_chunks))

    if not accumulated_chunks:
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"nac_output_document_chunks": [], "nac_merge_pairs_documents": []}

    if not sw["ENABLE_NAC_COMPRESSION"]:
        logger.debug("[NAC] disabled — passing through %d chunk(s)", len(accumulated_chunks))
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {"nac_output_document_chunks": accumulated_chunks, "nac_merge_pairs_documents": []}

    logger.debug(f"\n{_THIN}")
    logger.debug(f"  [NAC] Neighbor-Aware Compression — scanning {len(accumulated_chunks)} chunk(s)")
    logger.debug(_THIN)

    eligible = [
        (i, c) for i, c in enumerate(accumulated_chunks)
        if isinstance(c.get("chunk_seq"), int)
    ]
    ineligible = [
        (i, c) for i, c in enumerate(accumulated_chunks)
        if not isinstance(c.get("chunk_seq"), int)
    ]

    if not eligible:
        logger.warning("  [NAC] No chunks carry chunk_seq — skipping compression.")
        logger.debug(_THIN)
        return {"nac_output_document_chunks": accumulated_chunks, "nac_merge_pairs_documents": []}

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
    logger.debug(
        f"  [NAC] {len(neighbor_runs)} neighbor run(s) found | "
        f"{len(solo_runs)} singleton(s) pass through unchanged"
    )
    for run in neighbor_runs:
        seqs = [c["chunk_seq"] for _, c in run]
        logger.debug(
            f"    run: source={run[0][1]['source']}  "
            f"seq={seqs[0]}→{seqs[-1]}  ({len(run)} chunks)"
        )

    result_chunks: list[dict] = []
    nac_merge_pairs: list[dict] = []

    for run in runs:
        if len(run) == 1:
            result_chunks.append(run[0][1])
            continue

        source_chunks_for_merge = [c for _, c in run]
        candidate = _merge_similar_chunks(
            source_chunks_for_merge,
            llm,
            embedding_manager,
            output_fix_enabled=sw["ENABLE_COMPRESSION_OUTPUT_FIX"],
            switches=sw,
            config=config,
        )
        candidate["chunk_seq_start"] = run[0][1]["chunk_seq"]
        candidate["chunk_seq_end"] = run[-1][1]["chunk_seq"]
        candidate.pop("chunk_seq", None)
        result_chunks.append(candidate)
        nac_merge_pairs.append({"source_chunks": source_chunks_for_merge, "merged": candidate})
        logger.info(
            "  [NAC MERGE] merged %d chunks from '%s' seq %d→%d",
            len(run), run[0][1]["source"],
            run[0][1]["chunk_seq"], run[-1][1]["chunk_seq"],
        )

    result_chunks.extend(c for _, c in ineligible)

    saved = len(accumulated_chunks) - len(result_chunks)
    logger.debug(
        f"\n  [NAC] compression done: {len(accumulated_chunks)} → {len(result_chunks)} "
        f"chunk(s) ({saved} eliminated)"
    )
    logger.debug(_THIN)
    logger.info("[COMPRESS] NAC_documents complete — %d chunk(s) remain", len(result_chunks))

    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {"nac_output_document_chunks": result_chunks, "nac_merge_pairs_documents": nac_merge_pairs}


def validate_nac_documents(state: GraphState, config=None) -> dict:
    _t0 = time.perf_counter()
    sw = get_switches(state)
    pairs = state.get("nac_merge_pairs_documents", [])  # type: ignore[attr-defined]
    if not pairs:
        logger.info("[validate_NAC_documents] no merge pairs to validate")
        timing_tracker.record("Compression", time.perf_counter() - _t0)
        return {}
    for i, pair in enumerate(pairs):
        check = validate_merge(pair["source_chunks"], pair["merged"], judge_llm, config=config, switches=sw)
        logger.info(
            "[validate_NAC_documents] pair %d: verdict=%s  fabricated=%d  dropped=%d",
            i, check["verdict"],
            len(check["fabricated_claims"]),
            len(check["dropped_claims"]),
        )
    timing_tracker.record("Compression", time.perf_counter() - _t0)
    return {}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "NAC Compression", exclude={"execute_nac_documents", "validate_nac_documents"})

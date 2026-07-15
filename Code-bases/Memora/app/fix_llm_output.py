from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    from json_repair import repair_json  # type: ignore
    _HAS_JSON_REPAIR = True
except ImportError:  # graceful degradation if dep missing
    _HAS_JSON_REPAIR = False

try:
    from llm_caller import llm_invoke as _llm_invoke  # type: ignore
    _HAS_LLM_REPAIR = True
except ImportError:
    _HAS_LLM_REPAIR = False

from llm_setup import json_fix_llm
from config import _JSON_REPAIR_TRIES
from prompts import _VALUE_VERIFY_PROMPT, _JSON_REPAIR_PROMPT

llm_data_check_logger = logging.getLogger("llm_data_check")
llm_json_tries_logger = logging.getLogger("llm_json_tries")

# ════════════════════════════════════════════════════════════════════════════
# Pydantic schemas 
# ════════════════════════════════════════════════════════════════════════════

class _BaseStrict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _none_to_empty_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


# ── merge step ───────────────────────────────────────────────────────────────
class MergeSchema(_BaseStrict):
    content: str
    sources: list[str] = Field(default_factory=list)
    merged_from: int = 0

    @field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        return []

    @field_validator("merged_from", mode="before")
    @classmethod
    def _coerce_merged_from(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

# ── DC scan (redundancy proposals) ───────────────────────────────────────────
class RedundancyMember(_BaseStrict):
    chunk_index: int
    sentence: str

    @field_validator("sentence")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("sentence must be non-empty")
        return v.strip()

class RedundancyGroupProposal(_BaseStrict):
    members: list[RedundancyMember]

    @field_validator("members")
    @classmethod
    def _at_least_two(cls, v: list[RedundancyMember]) -> list[RedundancyMember]:
        if len(v) < 2:
            raise ValueError("a redundancy group must have at least 2 members")
        return v

# ── Redundancy judge verdicts ────────────────────────────────────────────────
class RedundancyJudgeItem(_BaseStrict):
    group_index: int
    verdict: Literal["CONFIRMED", "REJECTED"]
    reason: str = ""

    @field_validator("reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.upper().strip()
        return v

# ── Retrieval judge ──────────────────────────────────────────────────────────
class PerChunkItem(_BaseStrict):
    index: int
    relevant: bool
    reason: str = ""

    @field_validator("reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("relevant", mode="before")
    @classmethod
    def _coerce_relevant(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"true", "yes", "1", "relevant"}
        if isinstance(v, (int, float)):
            return bool(v)
        return False

class RetrievalJudgeSchema(_BaseStrict):
    verdict: Literal["PASS", "PARTIAL", "FAIL", "UNKNOWN"]
    per_chunk: list[PerChunkItem] = Field(default_factory=list)
    overall_reason: str = ""

    @field_validator("overall_reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, v: Any) -> str:
        if not isinstance(v, str):
            return "UNKNOWN"
        v = v.upper().strip()
        return v if v in {"PASS", "PARTIAL", "FAIL", "UNKNOWN"} else "UNKNOWN"

# ── Merge judge ──────────────────────────────────────────────────────────────
class MergeJudgeSchema(_BaseStrict):
    fabricated_claims: list[str] = Field(default_factory=list)
    dropped_claims: list[str] = Field(default_factory=list)
    overall_reason: str = ""

    @field_validator("overall_reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("fabricated_claims", "dropped_claims", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(x) for x in v if x is not None and str(x).strip()]
        return []

# ── LBC compress output ──────────────────────────────────────────────────────
class LBCCompressSchema(_BaseStrict):
    compressed: str
    dropped_count: int = 0
    reason: str = ""

    @field_validator("reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("dropped_count", mode="before")
    @classmethod
    def _coerce_dropped(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

# ── LBC judge ────────────────────────────────────────────────────────────────
class LBCJudgeSchema(_BaseStrict):
    verdict: Literal["SAFE", "OVER_COMPRESSED", "FABRICATED", "UNKNOWN"]
    fabricated_claims: list[str] = Field(default_factory=list)
    lost_relevant_facts: list[str] = Field(default_factory=list)
    overall_reason: str = ""

    @field_validator("overall_reason", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return _none_to_empty_str(v)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> str:
        if not isinstance(v, str):
            return "UNKNOWN"
        v = v.upper().strip()
        return v if v in {"SAFE", "OVER_COMPRESSED", "FABRICATED", "UNKNOWN"} else "UNKNOWN"

    @field_validator("fabricated_claims", "lost_relevant_facts", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(x) for x in v if x is not None and str(x).strip()]
        return []

# ── Distillation QA pairs ────────────────────────────────────────────────────
class QAPair(_BaseStrict):
    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v.strip()

# ── Registry: schema tag → (pydantic model, top-level type) ──────────────────
# top-level type is "dict" or "list" — drives the empty-fallback shape
_SCHEMA_REGISTRY: dict[str, tuple[type[BaseModel], str]] = {
    "merge":            (MergeSchema,             "dict"),
    "merge_judge":      (MergeJudgeSchema,        "dict"),
    "retrieval_judge":  (RetrievalJudgeSchema,    "dict"),
    "lbc_compress":     (LBCCompressSchema,       "dict"),
    "lbc_judge":        (LBCJudgeSchema,          "dict"),
    "dc_scan":          (RedundancyGroupProposal, "list"),
    "redundancy_judge": (RedundancyJudgeItem,     "list"),
    "distill_qa":       (QAPair,                  "list"),
}


# ════════════════════════════════════════════════════════════════════════════
# Text preprocessing 
# ════════════════════════════════════════════════════════════════════════════

# Code fences: ```json ... ``` or ``` ... ```  (also ```python sometimes wraps)
_FENCE_RE = re.compile(r"```(?:json|javascript|js|python|yaml)?\s*\n?", re.IGNORECASE)
_FENCE_END_RE = re.compile(r"\n?```\s*$", re.MULTILINE)

# Common LLM "thinking" preambles to strip
_THINKING_PATTERNS = [
    re.compile(r"^\s*(?:thinking|let me think|reasoning|analysis)[:.\s].*?(?=[{\[])",
               re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*(?:first|then|finally|step \d+)[^{\[]*?(?=[{\[])",
               re.IGNORECASE | re.DOTALL),
]

# Function-call wrappers: submit_answer({...}) or tool_call({...})
_FUNC_CALL_RE = re.compile(r"^\s*\w+\s*\(\s*(.*?)\s*\)\s*$", re.DOTALL)

# Markdown blockquote prefix
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)


def _strip_code_fences(s: str) -> str:
    """Remove all ``` / ```json / ```python / etc. fences anywhere in the text."""
    s = _FENCE_RE.sub("", s)
    s = _FENCE_END_RE.sub("", s)
    s = re.sub(r"```", "", s)  # any leftover fence backticks
    return s

def _strip_blockquotes(s: str) -> str:
    """`> {json}` style — common when LLMs format inside markdown quotes."""
    return _BLOCKQUOTE_RE.sub("", s)

def _unwrap_function_call(s: str) -> str:
    """`submit_answer({...})` → `{...}`."""
    m = _FUNC_CALL_RE.match(s.strip())
    if m:
        return m.group(1)
    return s

def _fix_python_literals(s: str) -> str:
    """
    Replace Python literals (True/False/None) with JSON ones (true/false/null)
    BUT only when they appear outside of string literals. We use a state-machine
    walk rather than naive regex to avoid corrupting strings like "True story".
    """
    out: list[str] = []
    i = 0
    in_str = False
    str_char = ""
    while i < len(s):
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if ch == str_char:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            out.append(ch)
            i += 1
            continue
        # Try to match a Python literal at this position (must be word-bounded)
        for py, js in (("True", "true"), ("False", "false"),
                       ("None", "null"), ("NaN", "null"), ("Infinity", "null")):
            if s.startswith(py, i):
                # boundary check
                before_ok = i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")
                after_idx = i + len(py)
                after_ok = after_idx >= len(s) or not (s[after_idx].isalnum() or s[after_idx] == "_")
                if before_ok and after_ok:
                    out.append(js)
                    i = after_idx
                    break
        else:
            out.append(ch)
            i += 1
            continue
    return "".join(out)

def _strip_json_comments(s: str) -> str:
    """Remove // line comments and /* block comments */ outside strings."""
    out: list[str] = []
    i = 0
    in_str = False
    str_char = ""
    while i < len(s):
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if ch == str_char:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            out.append(ch)
            i += 1
            continue
        # // line comment
        if ch == "/" and i + 1 < len(s) and s[i + 1] == "/":
            nl = s.find("\n", i)
            i = nl if nl != -1 else len(s)
            continue
        # /* block */
        if ch == "/" and i + 1 < len(s) and s[i + 1] == "*":
            end = s.find("*/", i + 2)
            i = end + 2 if end != -1 else len(s)
            continue
        out.append(ch)
        i += 1
    return "".join(out)

def _extract_balanced_json(text: str) -> str | None:
    n = len(text)
    # Find first '{' or '['
    start = -1
    open_ch = ""
    for i, c in enumerate(text):
        if c in "{[":
            start = i
            open_ch = c
            break
    if start == -1:
        return None
    close_ch = "}" if open_ch == "{" else "]"

    depth = 0
    in_str = False
    str_char = ""
    i = start
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == str_char:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None  # never balanced — let repair layer handle truncation

def _preprocess(raw: str) -> str:
    """Apply all the cheap, lossless text cleanups before parse attempts."""
    if not raw:
        return ""
    s = raw.strip()
    # If it's an escaped JSON string (case #16), unescape once.
    if s.startswith('"') and s.endswith('"') and ('\\"' in s or "\\n" in s):
        try:
            inner = json.loads(s)
            if isinstance(inner, str) and (inner.lstrip().startswith("{")
                                            or inner.lstrip().startswith("[")):
                s = inner
        except json.JSONDecodeError:
            pass
    s = _strip_code_fences(s)
    s = _strip_blockquotes(s)
    s = _unwrap_function_call(s)
    s = _strip_json_comments(s)
    s = _fix_python_literals(s)
    # Strip any "thinking" preamble that ends before the JSON starts
    for pat in _THINKING_PATTERNS:
        s = pat.sub("", s, count=1)
    return s.strip()

# ════════════════════════════════════════════════════════════════════════════
# Parsing 
# ════════════════════════════════════════════════════════════════════════════

def _try_json_loads(s: str) -> Any | None:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None

def _try_repair(s: str) -> Any | None:
    if not _HAS_JSON_REPAIR or not s:
        return None
    try:
        result = repair_json(s, return_objects=True)
        # repair_json returns "" for unrecoverable input
        if result == "" or result is None:
            return None
        return result
    except Exception:
        return None

def _parse_to_python(raw: str) -> Any | None:
    cleaned = _preprocess(raw)
    if not cleaned:
        return None

    # Tier 1: fast direct parse on the cleaned text
    obj = _try_json_loads(cleaned)
    if obj is not None:
        return obj

    # Tier 2: pull out a balanced top-level structure and try again
    extracted = _extract_balanced_json(cleaned)
    if extracted:
        obj = _try_json_loads(extracted)
        if obj is not None:
            return obj
        obj = _try_repair(extracted)
        if obj is not None:
            return obj

    # Tier 3: full json_repair on the whole cleaned text — handles truncation,
    # unbalanced brackets, stray prose between JSON candidates, etc.
    obj = _try_repair(cleaned)
    if obj is not None:
        return obj

    return None


# ════════════════════════════════════════════════════════════════════════════
# LLM-based JSON repair (last resort when all heuristics fail)
# ════════════════════════════════════════════════════════════════════════════

def _LLM_Json_Repair(
    raw_response: str,
    model: type[BaseModel] | None,
    top_level: str,
    llm: Any = None,
) -> Any | None:
    prompt: str = ""
    llm_raw: str = ""
    parsed: Any = None
    skip_reason: str = ""

    if not _HAS_LLM_REPAIR:
        skip_reason = "llm_caller not importable"
    elif llm is None:
        llm = json_fix_llm
    if not skip_reason:
        if model is not None:
            schema = model.model_json_schema()
            if top_level == "list":
                schema_block = (
                    f"Array of objects, each matching:\n{json.dumps(schema, indent=2)}"
                )
            else:
                schema_block = json.dumps(schema, indent=2)
        else:
            schema_block = f"any valid JSON {top_level}"

        prompt = (
            _JSON_REPAIR_PROMPT.format(top_level=top_level, schema_block=schema_block)
            + raw_response[:4000]
        )

        result = _llm_invoke(
            llm,
            [{"role": "system", "content": prompt}],
            caller_tag="JSON-REPAIR",
        )
        if result.ok and result.content:
            llm_raw = result.content
            parsed = _parse_to_python(result.content)
        else:
            skip_reason = (
                f"LLM call failed ({result.error_kind}): {result.error_message[:120]}"
            )

    details = [
        "",
        "=" * 72,
        f"timestamp : {datetime.now().isoformat()}",
        f"schema    : {model.__name__ if model else 'None'}",
        f"top_level : {top_level}",
        f"raw_input : {raw_response[:300]!r}",
    ]
    if skip_reason:
        details.append(f"skipped   : {skip_reason}")
    else:
        details.extend([
            f"--- PROMPT ---\n{prompt}",
            f"--- LLM RESPONSE ---\n{llm_raw}",
        ])
    details.append(f"--- RESULT ---\n{parsed!r}")
    llm_json_tries_logger.debug("\n".join(details))

    return parsed


# ════════════════════════════════════════════════════════════════════════════
# Top-level shape coercion
# ════════════════════════════════════════════════════════════════════════════

def _coerce_top_level(obj: Any, expected_top: str) -> Any | None:
    if expected_top == "list":
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # array-as-object: {"0": ..., "1": ...}
            if obj and all(str(k).isdigit() for k in obj.keys()):
                return [obj[k] for k in sorted(obj.keys(), key=lambda x: int(x))]
            # single inner list value
            list_vals = [v for v in obj.values() if isinstance(v, list)]
            if len(list_vals) == 1:
                return list_vals[0]
            # the dict itself is probably a single intended item
            return [obj]
        return None

    if expected_top == "dict":
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            # single-item list wrapping the real object
            if len(obj) == 1 and isinstance(obj[0], dict):
                return obj[0]
        return None

    return obj

# ════════════════════════════════════════════════════════════════════════════
# Schema validation with Pydantic
# ════════════════════════════════════════════════════════════════════════════

def _validate_with_pydantic(
    obj: Any,
    model: type[BaseModel],
    top_level: str,
) -> Any | None:
    try:
        if top_level == "dict":
            if not isinstance(obj, dict):
                return None
            instance = model.model_validate(obj)
            return instance.model_dump(mode="json")

        if top_level == "list":
            if not isinstance(obj, list):
                return None
            out: list[dict] = []
            for item in obj:
                if not isinstance(item, dict):
                    continue
                try:
                    out.append(model.model_validate(item).model_dump(mode="json"))
                except ValidationError:
                    # Drop the bad item; don't fail the whole list
                    continue
            # Empty list is allowed (LLMs legitimately return [] when nothing
            # matches the criterion, e.g. "no redundancy found").
            return out
    except ValidationError:
        return None
    return None

# ════════════════════════════════════════════════════════════════════════════
# Public entrypoint
# ════════════════════════════════════════════════════════════════════════════

def _resolve_expected(expected_output: Any) -> tuple[type[BaseModel] | None, str]:
    # Schema tag string
    if isinstance(expected_output, str):
        tag = expected_output.strip().lower()
        if tag in _SCHEMA_REGISTRY:
            model, top = _SCHEMA_REGISTRY[tag]
            return model, top
        # unknown tag → no schema, default to dict
        return None, "dict"

    # Pydantic model class directly
    if isinstance(expected_output, type) and issubclass(expected_output, BaseModel):
        return expected_output, "dict"

    # Shape specimen — dict or list instance
    if isinstance(expected_output, dict):
        return None, "dict"
    if isinstance(expected_output, list):
        return None, "list"

    # None or unknown → repair-only, default dict
    return None, "dict"

def _empty(top_level: str) -> Union[dict, list]:
    return {} if top_level == "dict" else []

def fix_llm_output(
    expected_output: Any,
    raw_response: str,
    correct: bool = False,
    llm: Any = None,
) -> tuple[Union[dict, list], bool]:
    model, top_level = _resolve_expected(expected_output)

    # Reject obviously-bad inputs up front
    if not isinstance(raw_response, str) or not raw_response.strip():
        return _empty(top_level), False

    # Parse the raw text into a Python object 
    # json.loads → balanced extract → json_repair.
    obj = _parse_to_python(raw_response)
    for _ in range(_JSON_REPAIR_TRIES):
        if obj is not None:
            break
        obj = _LLM_Json_Repair(raw_response, model, top_level, llm)
    if obj is None:
        return _empty(top_level), False

    # Reshape the top-level container if the LLM nested or flattened it wrong.
    obj = _coerce_top_level(obj, top_level)
    if obj is None:
        return _empty(top_level), False

    # If no schema was supplied, return the parsed object as-is. We still
    # consider this "correct" because the JSON itself parsed cleanly.
    if model is None:
        if (top_level == "dict" and isinstance(obj, dict)) or \
           (top_level == "list" and isinstance(obj, list)):
            return obj, True
        return _empty(top_level), False

    # Schema-validate with Pydantic.
    validated = _validate_with_pydantic(obj, model, top_level)
    if validated is None:
        return _empty(top_level), False

    result = _Verify_And_Correct(validated, raw_response, llm)

    # Empty list for a list-typed schema is a legitimate answer (e.g. "no
    # redundancy groups found"). Treat it as correct.
    return result, True


# ════════════════════════════════════════════════════════════════════════════
# Value-level verification & correction (post-validation pass)
# ════════════════════════════════════════════════════════════════════════════

def _Verify_And_Correct(
    validated: Union[dict, list],
    raw_response: str,
    llm: Any = None,
) -> Union[dict, list]:
    if not _HAS_LLM_REPAIR:
        return validated

    _llm = llm if llm is not None else json_fix_llm

    prompt = _VALUE_VERIFY_PROMPT.format(
        raw_response=raw_response[:4000],
        validated_json=json.dumps(validated, indent=2),
    )

    result = _llm_invoke(
        _llm,
        [{"role": "system", "content": prompt}],
        caller_tag="VALUE-VERIFY",
    )

    corrected = _parse_to_python(result.content) if result.ok and result.content else None

    # Keep only if the top-level type matches — never silently change shape.
    if corrected is not None:
        if isinstance(validated, dict) and isinstance(corrected, dict):
            final = corrected
        elif isinstance(validated, list) and isinstance(corrected, list):
            final = corrected
        else:
            final = validated
    else:
        final = validated

    details = [
        "",
        "=" * 72,
        f"timestamp          : {datetime.now().isoformat()}",
        f"llm_ok             : {result.ok}",
    ]
    if not result.ok:
        details.append(
            f"llm_error          : {result.error_kind} - {result.error_message[:200]}"
        )
    details.extend([
        f"raw_response       : {raw_response[:300]!r}",
        f"--- VALIDATED INPUT ---\n{json.dumps(validated, indent=2)}",
        (
            "--- PARSED CORRECTED ---\n"
            f"{json.dumps(corrected, indent=2) if corrected is not None else 'None'}"
        ),
        f"correction_applied : {final is not validated}",
    ])
    llm_data_check_logger.debug("\n".join(details))

    return final

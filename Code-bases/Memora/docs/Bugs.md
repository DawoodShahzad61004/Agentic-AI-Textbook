### BUG-001 · Tool-Call Overflow Silently Drops Requests

| Field | Detail |
|---|---|
| **Issue** | Tool-call overflow — LLM responses exceeding `MAX_TOOL_CALLS_PER_ITERATION` are silently truncated |
| **Found Date** | 2026-05 (Batch 9 dry run) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | When the LLM generates more tool calls than `MAX_TOOL_CALLS_PER_ITERATION` (default 5) in one response, the extra calls are silently dropped. The assistant message still contains all tool calls, but only the processed calls receive tool responses. This creates an invalid tool-call history (unmatched `tool_call_id`s) and can silently discard retrieval calls or the `compress_context` call. Observed in Q57 where 7 tool calls were generated (6 retrievals + compress), but only 5 were processed. |
| **Root Cause** | `resp_tool_calls[:MAX_TOOL_CALLS_PER_ITERATION]` slice without trimming the assistant message or providing stub responses for skipped call IDs. |
| **Solution** | Either (a) trim `assistant.tool_calls` to the same slice before appending to messages, or (b) append `"skipped due to cap"` tool responses for every unprocessed `tool_call_id`. |
| **Date Resolved** | — |

---

### BUG-002 · Retrieval Judge Over-Lenient on Bibliography Chunks

| Field | Detail |
|---|---|
| **Issue** | `validate_retrieval` passes bibliography/citation-list chunks as relevant |
| **Found Date** | 2026-05 (Batch 9 dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `validators.py` |
| **Description** | Chunks that are pure reference lists (e.g., "Vaccine 2014;32:3623-9") are being judged as PASS by the retrieval validator. This pollutes the compression pipeline with citation metadata instead of substantive facts, degrading answer quality. Confirmed in Q57 (prevalence query) and Q4 (vaccines). |
| **Root Cause** | The retrieval judge prompt has no rule to identify bibliography-only chunks as irrelevant. |
| **Solution** | Add a rule to `validate_retrieval`: if a chunk consists primarily of citations, author names, and publication references with no substantive factual sentences, return IRRELEVANT unless the user query is explicitly about references or bibliography. |
| **Date Resolved** | — |

---

### BUG-003 · DC Redundancy Judge Creates False Positives (Deletes Non-Duplicate Content)

| Field | Detail |
|---|---|
| **Issue** | Deduplication Compression (DC) marks semantically distinct sentences as redundant and removes them |
| **Found Date** | 2026-05 (Batch 9 dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `context_compression.py`, `validators.py` |
| **Description** | In Q57, the DC stage treated "gender and racial factors shape who is recognized…" as redundant with "providers should be trained to recognize masking…" and removed content. These sentences carry different factual claims. The `validate_redundancy` judge is confirming groups where members are topically adjacent but not semantically entailing each other. |
| **Root Cause** | The DC validator uses topic similarity rather than semantic entailment to confirm redundancy. A "confirmed" verdict should require both sentences to convey identical information in both directions. |
| **Solution** | Make DC deletion require exact semantic entailment both ways. Alternatively, disable LLM sentence deletion unless the sentence match is high-confidence by embedding similarity + NLI/LLM judge. Raise the confirmation threshold significantly. |
| **Date Resolved** | — |

---

### BUG-004 · LBC Can Expand Chunks Instead of Compressing

| Field | Detail |
|---|---|
| **Issue** | LLM-Based Compression (LBC) produces output longer than its input, causing negative reduction |
| **Found Date** | 2026-05 (Batch 9 dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `context_compression.py` |
| **Description** | In Q57, LBC produced compressed chunks that expanded badly: 367 → 1134 chars and 170 → 2130 chars. Total context went from 5,488 → 7,471 chars, reported as negative reduction. The existing over-compression guard (blocks output < 35% of input) does not catch over-expansion. |
| **Root Cause** | No over-expansion guard. The LBC stage only checks that compression isn't too aggressive; it doesn't check that the LLM hasn't padded or elaborated the content. |
| **Solution** | Add guard: `if len(compressed_text) > len(original_content): keep original`. This is a one-line fix in `_llm_based_compression`. |
| **Date Resolved** | — |

---

### BUG-005 · check_answer_quality Judge Blind to Semantic Extension / Hallucination

| Field | Detail |
|---|---|
| **Issue** | `check_answer_quality` passes answers that hallucinate facts not in retrieved chunks |
| **Found Date** | 2026-04 (early dry runs), recurring across Batches 5–9 |
| **Status** | Open |
| **Severity** | CRITICAL |
| **File** | `tools.py` |
| **Description** | The CAQ judge verifies grounding (does the answer follow from retrieved text?) but not scope (did the retrieved text actually cover the question domain?). Multiple confirmed false-positive verdicts: Q72 — LLM substituted "medical equipment" for "sensitive equipment" (source never mentioned medical); Q73 — fabricated longitudinal outcome studies; Q70 — fabricated "mathematics or music" exceptional abilities; Q5 — invented therapy names (ABA, OT, Speech Therapy) not in any chunk; Q22 — hallucinated 2023 CDC ADDM report details using 2016 data. |
| **Root Cause** | Quality check uses word-overlap heuristic or a loose LLM judge, neither of which detects semantic extension — where the LLM adds plausible-sounding facts adjacent to the topic that no chunk actually states. |
| **Solution** | (1) Add a named-entity grounding check: every named entity in the answer must appear in a retrieved chunk. (2) Add a temporal grounding check: if the query specifies a year/report, retrieved chunks must match that time period. (3) Detect context-length mismatch: if `len(answer) > len(context) * 3` and `len(context) < 200`, flag as suspicious. (4) Strengthen minimum context-length threshold from 50 to 100 chars. |
| **Date Resolved** | — |

---

### BUG-006 · No Dataset/Schema Awareness — Data Interpretation Questions Produce Clinical Hallucinations

| Field | Detail |
|---|---|
| **Issue** | System answers CSV/dataset-schema questions using clinical knowledge, producing wrong answers |
| **Found Date** | 2026-05 (Batch 9 dry run, Q71) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `agent_query.py`, `retriever.py` |
| **Description** | Q71 asked why `ASD_Diagnosis=No` patients have `ASD_Severity=NaN`. The correct answer is "no diagnosis means no severity is applicable — this is expected dataset behavior." Instead, the system retrieved DSM-5 clinical criteria chunks and fabricated a clinical explanation about diagnostic specificity. The `check_answer_quality` judge passed this as OK. |
| **Root Cause** | The knowledge base contains no document describing the CSV schema or the logical relationship between dataset columns. When no relevant schema chunks are retrieved, the LLM bridges the gap with plausible clinical content instead of triggering `NO_CONTEXT_ANSWER`. |
| **Solution** | (1) Add a schema/data-dictionary document to the knowledge base. (2) Detect data-schema questions by pattern (column name references, `NaN`, data type questions) and route them to a dedicated handler that checks the dataset metadata first. (3) Lower the CAQ threshold for this question category. |
| **Date Resolved** | — |

---

### BUG-007 · Retrieval Near-Synonym Loop Not Programmatically Enforced

| Field | Detail |
|---|---|
| **Issue** | LLM generates semantically identical queries across iterations, burning the retrieval budget |
| **Found Date** | 2026-05 (Batches 3, 9; confirmed in Q73) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `agent_query.py` |
| **Description** | In Q73, the agent used all 6 iterations and all 5 retrieval slots, with 4 out of 5 queries being near-synonyms: "early diagnosis ASD outcomes", "ASD diagnosis timing impact", "impact of delayed ASD diagnosis on long-term outcomes", "consequences of delayed ASD diagnosis on quality of life." The system prompt says "Never generate two queries with identical words" but this only catches lexical overlap; semantic duplicates slip through. |
| **Root Cause** | No programmatic deduplication of queries by semantic similarity. The constraint is self-regulated by the LLM, which ignores it under retrieval pressure. |
| **Solution** | Add an embedding-based pre-check before dispatching each queued query: if cosine similarity against any prior query in this turn is above ~0.85, skip it and log `[REDUNDANT VARIANT] skipped`. Infrastructure for `[FAILED VARIANT] recorded` already exists and can be extended. |
| **Date Resolved** | — |

---

### BUG-008 · Confidence Field Self-Reported by LLM, Not Grounded in Metrics

| Field | Detail |
|---|---|
| **Issue** | Answer confidence is self-assessed by the LLM rather than computed from retrieval quality |
| **Found Date** | 2026-04 (early dry runs, Q3 Group 2) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `agent_query.py` |
| **Description** | The LLM reports HIGH confidence even when it has essentially no real retrieved data. In one case it reported "HIGH — The knowledge base contains relevant documents" while producing a near-complete hallucination. The confidence field backfired: the model fills it based on its own parametric certainty, not actual retrieval quality. |
| **Root Cause** | Confidence is prompted as a free-text field in the output format, allowing the LLM to self-assess. |
| **Solution** | Compute confidence programmatically before returning the answer: `avg_score` and `total_chars` of retrieved chunks → HIGH/MEDIUM/LOW. Never let the LLM self-report it. |
| **Date Resolved** | — |

---

### BUG-009 · Thumbdown Query Matching Requires Exact String Equality

| Field | Detail |
|---|---|
| **Issue** | Thumbdown feedback does not carry over to semantically equivalent follow-up queries |
| **Found Date** | 2026-05 (Batch 1, Q7/Q8) |
| **Status** | Open |
| **Severity** | LOW |
| **File** | `feedback_store.py` |
| **Description** | If a user thumbs-down "What is ASD?" and later asks "What is ASD and what are its main characteristics?", these are different normalized strings and the thumbdown does not transfer. The pivot/retry mechanism is never triggered for semantically equivalent but lexically different queries. |
| **Root Cause** | Feedback lookup uses exact string normalization, not semantic similarity. |
| **Solution** | Implement fuzzy or embedding-based thumbdown matching. Compare new queries against the stored thumbdown set using cosine similarity above a threshold (e.g. 0.85). |
| **Date Resolved** | — |

---

### BUG-010 · Coverage Checker Too Weak for Multi-Part Queries

| Field | Detail |
|---|---|
| **Issue** | `check_answer_quality` returns OK even when only some sub-questions of a multi-part query are answered |
| **Found Date** | 2026-05 (Batch 9, Q58) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `tools.py` |
| **Description** | Q58 asked for clinical criteria, patient characteristics, management strategies, and diagnostic impact. The final answer mostly covered patient traits and management but barely addressed clinical criteria or diagnostic impact. CAQ still returned OK. |
| **Root Cause** | The quality judge does not decompose the user query into sub-questions and verify each one is answered. |
| **Solution** | Add a coverage checklist: extract explicit sub-questions or facets from the user query (via LLM or heuristic), require each to be addressed before returning OK. |
| **Date Resolved** | — |

---

### BUG-F001 · Merge LLM JSON Escaping Bug (Windows Backslash Paths)

| Field | Detail |
|---|---|
| **Issue** | `_merge_similar_chunks` fails on Windows file paths with backslashes in JSON strings |
| **Found Date** | 2026-04 (Batch 1, Q1) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `context_compression.py` (formerly in `agent_query.py`) |
| **Description** | The chunk-merge LLM returned JSON where source paths used unescaped Windows backslashes inside double-quoted strings (e.g., `"C:\Users\..."`) causing `json.loads()` to throw `JSONDecodeError`. Fallback returned only `similar_chunks[0]`, silently discarding other chunks. |
| **Root Cause** | LLM inconsistently quoted Windows paths inside JSON strings; JSON requires inner double quotes to be escaped as `\"`. |
| **Solution** | Normalize source paths to forward slashes before passing to the merge LLM. Apply path normalization at ingest time and during chunk-merge JSON serialization. |
| **Date Resolved** | 2026-05 (confirmed fixed in Batch 2 log) |

---

### BUG-F002 · `OPENAI_BASE_URL` Resolved at Module Import Time Before `load_dotenv()`

| Field | Detail |
|---|---|
| **Issue** | `OPENAI_BASE_URL` evaluated at module scope before `.env` was loaded, causing silent fallback to OpenAI's real endpoint and a 401 error |
| **Found Date** | 2026-05 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | A patch added `OPENAI_BASE_URL = _normalize_openai_base_url(os.getenv("CUSTOM_API_BASE"))` at module top-level. But `load_dotenv()` only runs inside `main()`. At the time the module-level line executed, `CUSTOM_API_BASE` was `None`. `ChatOpenAI(base_url=None)` fell back to `api.openai.com`, causing 401 rejections with the custom API key. |
| **Root Cause** | Module-level constant resolved before environment was populated. |
| **Solution** | Move `api_key`, `api_base`, and `model` resolution inside `main()`, immediately after `load_dotenv()`. Added explicit `RuntimeError` if either env var is missing. Added `[LLM] endpoint=...` startup log line as a sanity check. |
| **Date Resolved** | 2026-05-14 |

---

### BUG-F003 · `CUSTOM_API_BASE` Double-Appends `/chat/completions` → 404

| Field | Detail |
|---|---|
| **Issue** | API calls returned 404 because LangChain appended `/chat/completions` to a base URL that already ended with `/chat/completions` |
| **Found Date** | 2026-05-14 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | The `.env` value for `CUSTOM_API_BASE` was the full endpoint (`http://host:port/v1/chat/completions`), which `test_run.py` POSTs to directly. `ChatOpenAI` treats `base_url` as a root and appends `/chat/completions` itself, resulting in `.../chat/completions/chat/completions` → 404. |
| **Root Cause** | Two consumers (`requests.post` in `test_run.py` and LangChain's `ChatOpenAI`) had incompatible expectations of the `base_url` format. |
| **Solution** | Added `_normalize_openai_base_url()` helper that strips trailing `/chat/completions`, `/completions`, and `/responses` suffixes before passing to `ChatOpenAI`. Function is idempotent — already-correct root URLs are unchanged. |
| **Date Resolved** | 2026-05-14 |

---

### BUG-F004 · Local Server Returns `function.arguments` as Dict Instead of JSON String

| Field | Detail |
|---|---|
| **Issue** | HuggingFace TGI server returned tool call `arguments` as a JSON object instead of a JSON-encoded string, causing Pydantic validation failure in LangChain |
| **Found Date** | 2026-05-14 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` (HTTP client layer) |
| **Description** | OpenAI spec requires `function.arguments` to be a JSON-encoded string (e.g., `"{\"location\": \"Lahore\"}"`). The local TGI server returned it as a raw dict object. LangChain's response-parsing layer raised a Pydantic validation error before the application code could see the message. |
| **Root Cause** | TGI server non-compliance with OpenAI tool-call response format. |
| **Solution** | Intercepted the HTTP response via a custom `httpx.Client` hook before LangChain's Pydantic parsing. Coerced `arguments` to `json.dumps(arguments)` if it arrived as a dict. Wired via `ChatOpenAI(http_client=build_tolerant_http_client())`. |
| **Date Resolved** | 2026-05-14 |

---

### BUG-F005 · DC Stage Silently Fails JSON Parse and Treats Truncation as "No Duplicates"

| Field | Detail |
|---|---|
| **Issue** | Truncated DC scan JSON is silently treated as zero redundancies found |
| **Found Date** | 2026-05 (Batch 1, Q5) |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `context_compression.py` |
| **Description** | The LLM-generated JSON for the dedup scan was truncated mid-output. The pipeline caught the `JSONDecodeError` and silently coerced to "0 redundant passages found," leaving duplicate content in context. This happened twice in the same compression call (windows `[0:3]` and `[3:5]`). |
| **Root Cause** | `max_tokens` on the DC scan call was too low for larger windows; truncation was not distinguished from a legitimate empty-list response. |
| **Solution** | Increased `max_tokens` on the DC scan call. Added greedy regex fallback to recover partial JSON arrays. Added explicit log warning on parse failure rather than silent coercion. The `fix_llm_output.py` module now handles multiple JSON repair tiers. |
| **Date Resolved** | 2026-05 |

---

### BUG-F006 · DC Judge Outputs Python Code Instead of JSON

| Field | Detail |
|---|---|
| **Issue** | `llama-3.1-8b-instant` responded to the redundancy-scan prompt with Python code instead of a JSON array |
| **Found Date** | 2026-05 (Batch 1, Q5; recurring) |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `context_compression.py` |
| **Description** | The DC scan prompt contained words like "detect," "filter," "redundant" which the small model pattern-matched as a coding task, generating `def detect_redundancy(chunks):` instead of the required JSON output. The safe fallback (treat all groups as REJECTED) triggered, meaning no deduplication ran. |
| **Root Cause** | Small instruction-tuned models (8B class) pattern-match on programming-adjacent verbs in prompts and respond with code. |
| **Solution** | Rewrote the DC scan prompt to remove all programming vocabulary. Added explicit instruction: "Your response must be a JSON array only. Do not write code." Added `fix_llm_output.py` with a balanced-bracket JSON extraction tier to recover JSON literals embedded in Python code as a fallback. |
| **Date Resolved** | 2026-05 |

---

### BUG-F007 · `compression.py` Shadows Python 3.14 Standard Library Module

| Field | Detail |
|---|---|
| **Issue** | Module named `compression.py` in `app/` shadowed Python 3.14's new `compression` stdlib package, causing circular import crash on startup |
| **Found Date** | 2026-05-13 |
| **Status** | Closed |
| **Severity** | CRITICAL |
| **File** | `compression.py` → renamed to `context_compression.py` |
| **Description** | Python 3.14 introduced a stdlib package named `compression` (used by `bz2`, `gzip`). Because `app/` was on `sys.path` ahead of the stdlib, `bz2` did `from compression._common import _streams` and found the project file instead. This triggered a circular import chain through `tempfile → shutil → bz2` and caused `AttributeError: partially initialized module 'tempfile'` on every startup. |
| **Root Cause** | File naming conflict with a new Python 3.14 stdlib module. |
| **Solution** | Renamed `compression.py` → `context_compression.py`. Updated all import statements in `tools.py` and `agent_query.py`. |
| **Date Resolved** | 2026-05-13 |

---

### BUG-F008 · Early COMPRESS Trigger Fires After First Retrieval, Preventing Multi-Query Retrieval

| Field | Detail |
|---|---|
| **Issue** | Orchestrator forced COMPRESS phase after just 1 retrieval, preventing the LLM from issuing its 2nd and 3rd queries |
| **Found Date** | 2026-05-18 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | Guard `if total_retrievals >= 1 and agent_state.get("accumulated_chunks"): phase = "COMPRESS"` fired immediately after the first successful retrieval. This meant only 1 chunk from 1 source was ever retrieved, resulting in hallucinated answers drawn from the LLM's parametric memory. Old runs used 3 retrievals → 3 sources → full NAC/DC/LBC pipeline. New runs used 1 retrieval → 1 source → skipped compression (below 500-token threshold). |
| **Root Cause** | Guard was added to reduce unnecessary LLM round-trips but was too aggressive — fired unconditionally after any single retrieval. |
| **Solution** | Added `MIN_RETRIEVALS_BEFORE_COMPRESS = 2` constant. Changed the early-COMPRESS guard to only trigger when `total_retrievals >= MIN_RETRIEVALS_BEFORE_COMPRESS`. Below that, the loop stays in RETRIEVE phase and allows sequential tool calls from smaller models. |
| **Date Resolved** | 2026-05-18 |

---

### BUG-F009 · `json-repair` Not in `requirements.txt` — Repair Tier Silently Offline

| Field | Detail |
|---|---|
| **Issue** | `fix_llm_output.py` repair tier silently disabled when `json-repair` package was not installed |
| **Found Date** | 2026-05-21 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `fix_llm_output.py`, `requirements.txt` |
| **Description** | `fix_llm_output.py` has a `try/except ImportError` that sets `_HAS_JSON_REPAIR = False` and degrades gracefully — but silently. 7/99 test cases failed with no obvious error, all on cases requiring the repair tier (trailing commas, single quotes, missing commas, truncated JSON). Root cause was only identified after investigation: `json-repair` was not in `requirements.txt` and not installed. |
| **Root Cause** | Missing dependency declaration. |
| **Solution** | Added `json-repair >= 0.30` to `requirements.txt` / `pyproject.toml` via `uv add json-repair`. Patched `test_output_fixes.py` to emit a visible warning when `_HAS_JSON_REPAIR = False`. Added import-time warning to `fix_llm_output.py` itself. |
| **Date Resolved** | 2026-05-21 |

---

### BUG-F010 · Inconsistent Source Path Formatting Pollutes `learned_qa` Store

| Field | Detail |
|---|---|
| **Issue** | Mixed forward/back slashes in source citation paths cause false negatives when deduplicating the `learned_qa` store |
| **Found Date** | 2026-05 (Batch 1, Q1) |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `context_compression.py`, `self_learner.py` |
| **Description** | Retriever stored Windows-style paths (`\..\data\pdfs\...`). The merge LLM sometimes rewrote them as forward-slash paths (`../data/pdfs/...`) and sometimes left them mixed. Result: `learned_qa` stored non-canonical source strings; downstream code deduplicating by source path would see false negatives. |
| **Root Cause** | No single normalization point — paths were written at ingest with OS separators, then re-processed inconsistently at merge time. |
| **Solution** | Applied `str.replace("\\", "/")` normalization at ingest time and again in the chunk-merge serialization step. All source paths now stored with forward slashes. |
| **Date Resolved** | 2026-05 |

---

### BUG-F011 · DRAFT Phase Sent Full Tool-Call History to Local Server → HTTP 500

| Field | Detail |
|---|---|
| **Issue** | DRAFT phase passed the full `messages` history (containing prior tool calls) to the local inference server, causing HTTP 500 |
| **Found Date** | 2026-05 (local server testing) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | The DRAFT LLM call used `llm_invoke(llm, messages, ...)` where `messages` contained the full conversation history including all retrieval tool calls and results. The local TGI server crashed (HTTP 500) when receiving this history. Retrieval and compression phases succeeded; only DRAFT failed. |
| **Root Cause** | Local server does not handle tool-call history in a stateless completion request. |
| **Solution** | Made DRAFT call stateless: replaced `messages` with a fresh `draft_messages` list containing only a system prompt and a single user message with `USER QUERY` + `RETRIEVED CONTEXT`. Removed the `messages.pop()` cleanup that was no longer needed. |
| **Date Resolved** | 2026-05 |

---

### BUG-F012 · `BadRequestError` / `tool_use_failed` from Groq API on Critical Iterations

| Field | Detail |
|---|---|
| **Issue** | Groq API rejected tool-call payload mid-session with `BadRequestError`, causing agent to exit with "Unable to generate a clean answer" |
| **Found Date** | 2026-05 (Batch 1, Q2) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `llm_caller.py`, `agent_query.py` |
| **Description** | The Groq API returned `tool_use_failed` at a critical moment, and the fallback stripped non-tool content and exited immediately. No retry, no graceful fallback answer, just a hard abort. |
| **Root Cause** | No retry logic for transient `BadRequestError` / `tool_use_failed`; fallback was too aggressive (hard exit). |
| **Solution** | Implemented `LLMErrorKind` taxonomy in `llm_caller.py` (RATE_LIMIT, SERVER_ERROR, CONNECTION, TIMEOUT, BAD_REQUEST, etc.). Added transient-error retry loop with exponential backoff (1s, 2s, 4s, 8s, max 4 retries) for recoverable error kinds. Non-retryable errors fail fast with a structured log. |
| **Date Resolved** | 2026-05-11 |

---

### BUG-F013 · Runaway Agent Loop (40+ Iterations on Single Query)

| Field | Detail |
|---|---|
| **Issue** | Agent looped 40+ times on a single query, burning through Groq's 6,000 TPM rate limit |
| **Found Date** | 2026-04 (early dry runs) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | With no guardrails on per-iteration tool calls, the agent generated increasingly redundant queries across 40+ iterations. The accumulated chunks in `messages` triggered Groq's TPM limit (413: Requested 6785, Limit 6000). |
| **Root Cause** | No iteration cap, no per-turn query deduplication, no context-size pruning. |
| **Solution** | Added `MAX_ITERATIONS = 6`, `MAX_TOOL_CALLS_PER_ITERATION = 5`, `MAX_TOTAL_RETRIEVALS = 5`. Added in-batch dedup check (`seen_queries` set). Refactored compression pipeline to replace raw chunk messages with a single formatted context, preventing context window explosion. |
| **Date Resolved** | 2026-04 |

---

### BUG-F014 · Distillation Overgeneralizes Mouse-Model Study as Human Causal Evidence

| Field | Detail |
|---|---|
| **Issue** | Self-learning distillation stored a QA pair that overstates a mouse-model study as evidence of a causal vaccine–autism link |
| **Found Date** | 2026-05 (Batch 1, post-Q6 distillation run) |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `self_learner.py` |
| **Description** | After Q6, the distillation run processed a citation-fragment chunk about maternal immune activation (mouse model) and produced a learned QA pair that overgeneralized it as evidence of a causal link to autism in humans. The pair was stored in `learned_qa`. |
| **Root Cause** | Distillation LLM prompt did not require the model to stay within the evidential scope of the source chunk (animal vs. human study distinction). |
| **Solution** | Added evidential-scope constraint to the distillation prompt: require the LLM to faithfully represent the evidence type (animal model, observational, RCT, meta-analysis) and prohibit extrapolation across study types. |
| **Date Resolved** | 2026-05 |

---

### BUG-015 · `GROQ_API_BASE` Env Var Causes Double-Path URL in Auto-Instantiated `ChatGroq`

| Field | Detail |
|---|---|
| **Issue** | Auto-instantiated `ChatGroq` objects in `_LLM_Json_Repair` and `_Verify_And_Correct` send requests to `/openai/v1/openai/v1/chat/completions`, resulting in HTTP 404 on every LLM repair call |
| **Found Date** | 2026-06-08 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `fix_llm_output.py` — `_LLM_Json_Repair()`, `_Verify_And_Correct()` |
| **Description** | When `.env` contains `GROQ_API_BASE=https://api.groq.com/openai/v1`, `langchain_groq` passes this directly to the underlying `groq` SDK as `base_url`. The SDK then appends its standard path suffix to that value, doubling the `/openai/v1` segment. Observed in `run_logs/llm_data_check.txt`: `Error code: 404 — Unknown request URL: POST /openai/v1/openai/v1/chat/completions`. |
| **Root Cause** | `.env` sets `GROQ_API_BASE` for a different integration context. `langchain_groq` passes the full value verbatim as `base_url`; the `groq` SDK then appends its standard endpoint path suffix, producing a doubled path. |
| **Solution** | `os.environ.pop("GROQ_API_BASE", None)` immediately before `ChatGroq(...)` in both auto-instantiation blocks. The `groq` SDK defaults to `https://api.groq.com` when `base_url` is unset, which is the correct base. |
| **Date Resolved** | 2026-06-08 |

---

### BUG-016 · `_LLM_Json_Repair` Log File Never Written — Write Block Was Unreachable

| Field | Detail |
|---|---|
| **Issue** | `run_logs/llm_json_tries.txt` was never created even when LLM repair calls were being made |
| **Found Date** | 2026-06-08 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `fix_llm_output.py` — `_LLM_Json_Repair()` |
| **Description** | The `os.makedirs` / `open` log-write block was placed after early-return guards (`if llm is None: return None` and `if not result.ok`), making it unreachable in all normal execution paths. The function returned before the log block could execute regardless of whether the LLM call succeeded or failed. |
| **Root Cause** | Log write was placed inside a conditional branch rather than at the function's single exit point. |
| **Solution** | Restructured `_LLM_Json_Repair` so the log write executes unconditionally at the function's end. Runs that skip the LLM call write a `skipped: no LLM provided` entry so the file is created on the very first call, confirming the logging path is live. |
| **Date Resolved** | 2026-06-08 |

---

### BUG-017 · `fix_llm_output` Returned Failure for Every Successful Parse — Inverted Guard Condition

| Field | Detail |
|---|---|
| **Issue** | Majority of `test_output_fixes.py` cases were failing immediately — `fix_llm_output` returned `(_empty, False)` even when `_parse_to_python` returned a valid object |
| **Found Date** | 2026-06-08 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `fix_llm_output.py` — `fix_llm_output()` |
| **Description** | The early-exit guard after `_parse_to_python` was written as `if obj is not None: return _empty, False` — exactly inverted. This caused the function to return the empty fallback precisely when parsing succeeded, and to continue processing only when parsing failed. Test pass rate was near-zero immediately after the first build. |
| **Root Cause** | Logic inversion in the original stub — `is not None` instead of `is None`. |
| **Solution** | Corrected to `if obj is None: return _empty(top_level), False`. |
| **Date Resolved** | 2026-06-08 |

---

### BUG-018 · 12 Test Case Expected-Outcome Flags Not Updated After LLM Repair Was Added

| Field | Detail |
|---|---|
| **Issue** | 12 test cases in `test_output_fixes.py` had `expect_correct=False` but were now passing after LLM repair was added — causing false test failures |
| **Found Date** | 2026-06-08 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `test_output_fixes.py` |
| **Description** | Test expectations were written for the pre-LLM-repair pipeline. After `_LLM_Json_Repair` was added, cases involving XML output, YAML output, PascalCase key remapping, dataclass syntax, and nested object unwrapping were correctly reconstructed by the LLM — but still marked `expect_correct=False`, so the test harness reported them as failures even though the code was behaving correctly. |
| **Root Cause** | Test expectations not updated when the pipeline's capability set changed. |
| **Solution** | Updated 12 cases to `expect_correct=True`: C14-merge (nested unwrap), C23-merge (XML), C24-merge (YAML), C32-merge (PascalCase keys), PC02-merge (dataclass syntax), C36-rj (partial hallucination unwrap), C32-rj (PascalCase keys), PC04-rj/mj/lc/lj/dc (class attribute syntax). Cases kept `False`: refusals, pure functions with no data, missing required fields with no source data in the raw text, null required fields, set/comprehension/f-string/lambda syntax — all cases where the LLM would have to fabricate rather than reconstruct. |
| **Date Resolved** | 2026-06-08 |

---

### BUG-019 · `_Verify_And_Correct` Hallucinates Source Filenames for Empty `sources` Fields

| Field | Detail |
|---|---|
| **Issue** | The value-verification LLM occasionally populates `sources: []` with invented noun phrases when no filename appears in the raw response |
| **Found Date** | 2026-06-08 |
| **Status** | Open |
| **Severity** | LOW |
| **File** | `fix_llm_output.py` — `_VALUE_VERIFY_PROMPT` |
| **Description** | Observed in `run_logs/llm_data_check.txt`: for inputs where `sources` is empty and no source filenames (`*.pdf`, `*.txt`) appear in the raw response, `llama-3.1-8b-instant` at `temperature=0.0` sometimes infers a source from noun phrases in the content (e.g. `sources: ["the retrieved chunks"]`). The output is structurally valid but fabricated — no actual filename was present in the raw text. |
| **Root Cause** | `_VALUE_VERIFY_PROMPT` instructs the LLM to use existing defaults for genuinely missing fields, but does not give explicit guidance on how to identify a "source filename" field vs a general string field. The model treats it as a string it can populate from context. |
| **Solution** | Add an explicit rule to `_VALUE_VERIFY_PROMPT`: "If a field contains source filenames (e.g. `sources`) and no string matching a filename pattern (ending in `.pdf`, `.txt`, `.docx`, etc.) appears in the RAW RESPONSE, set it to `[]`." Monitor `correction_applied` rate in `llm_data_check.txt` after the change. |
| **Date Resolved** | — |

---

### BUG-020 · Validators Crash on `'str' object has no attribute 'get'` When `*_OUTPUT_FIX` Flag Is Off

| Field | Detail |
|---|---|
| **Issue** | Every LLM-as-judge validator (`validate_retrieval`, `validate_merge`, `validate_redundancy`, `validate_lbc`) crashes with `AttributeError: 'str' object has no attribute 'get'` when its per-stage `*_OUTPUT_FIX` flag or the global `ENABLE_GLOBAL_LLM_OUTPUT_FIX` flag is off |
| **Found Date** | 2026-06-09 (`run_combinations.py` ladder runs 3–9) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `validators.py` — affects `validate_retrieval` (line 134), `validate_merge` (line 252), and the same fall-through pattern in `validate_redundancy` and `validate_lbc` |
| **Description** | Each validator has a two-branch structure: if both the per-validator `_OUTPUT_FIX` flag and the global flag are on, it calls `fix_llm_output(...)` and the result is a dict; otherwise the else branch executes `llm_result = raw` — assigning the raw LLM response string directly. The very next line then calls `llm_result.get("verdict", ...)` (or `.get("fabricated_claims", ...)` in the merge validator) which crashes because strings have no `.get()` method. Confirmed in ladder runs 3 (validate_merge), 4–9 (validate_retrieval): each crashed at iteration 1 of the RETRIEVE phase the moment the first validator fired with its output-fix flag off. Runs 1, 2 (no validators enabled), and 10 (everything on) completed. There is also a minor logging bug in the success branch — the print line reads "failed to fix malformed LLM output" when fix actually succeeded. |
| **Root Cause** | The else branch assumes the validator can consume the raw LLM string directly, but the downstream code is dict-only. The branch was a hold-over from before `fix_llm_output` was introduced and was never updated to call `json.loads(raw)` (or `_safe_json_parse`) as a minimum-effort fallback. |
| **Solution** | In each validator's else branch, replace `llm_result = raw` with a `json.loads(raw)` call wrapped in a try/except that returns the `verdict="UNKNOWN"` empty-result on failure (mirroring the same return path used when `fix_llm_output` fails). Audit all four validators for this pattern. Also fix the inner-else log message to say "successfully parsed LLM output" instead of "failed to fix". |
| **Date Resolved** | — |

---

### BUG-021 · `ENABLE_AUTO_DISTILLATION` Flag Defined but Never Read

| Field | Detail |
|---|---|
| **Issue** | `ENABLE_AUTO_DISTILLATION` is exported from `config.py` and toggled by `run_combinations.py`, but `agent_query.py` never imports or checks it — distillation fires unconditionally on `should_learn()` regardless of the flag |
| **Found Date** | 2026-06-09 (post-ladder code review) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `agent_query.py` (callsites at lines 1045 and 1128 around `self_learner.run_distillation()`) |
| **Description** | The ladder harness toggles all 18 flags in `BOOL_FLAGS`, including `ENABLE_AUTO_DISTILLATION`. The flag's intended effect is to gate the automatic `run_distillation()` calls that fire after every `LEARN_EVERY_N` successful interactions. However, `agent_query.py` does not import `ENABLE_AUTO_DISTILLATION` from `config`, and the two distillation callsites have no `if ENABLE_AUTO_DISTILLATION:` guard. Result: ladder runs that should be measuring the pipeline *without* distillation still trigger distillation, polluting the `learned_qa` collection across runs and making per-step ladder comparisons noisier than intended. |
| **Root Cause** | Flag was added to `config.py` during the centralisation pass but the corresponding `if ENABLE_AUTO_DISTILLATION:` guards were not added at the two distillation callsites in `agent_query.py`. |
| **Solution** | Import `ENABLE_AUTO_DISTILLATION` from `config` in `agent_query.py` and wrap both `self_learner.run_distillation()` callsites with `if ENABLE_AUTO_DISTILLATION:`. Verify by re-running the ladder and confirming the `learned_qa` count stays constant for steps where the flag is off. |
| **Date Resolved** | — |

---

### BUG-022 · Raw LLM Responses Used When Output Repair Disabled

| Field | Detail |
| --- | --- |
| **Issue** | Multiple validator and compression fallback paths assumed structured Python objects even when `ENABLE_GLOBAL_LLM_OUTPUT_FIX` (or stage-specific output-fix flags) was disabled. Raw LLM responses could reach downstream code that immediately called `.get()`, iterated results, or accessed expected JSON fields.                                                       | **Found Date** | 2026-06-10 (during `run_combinations.py` dry-run ladder testing) | 
| **Status** | Resolved |
| **Severity** | HIGH |
| **File** | `validators.py`, `context_compression.py`, and other fallback parsing paths that bypass `fix_llm_output()`|                                          |
| **Description** | The newly introduced configuration architecture allows the output-repair layer to be disabled independently. Dry runs revealed that several fallback branches still assumed repaired JSON output and attempted to operate directly on raw LLM strings. Depending on the response shape, this produced failures such as `AttributeError: 'NoneType' object has no attribute 'get'`, `AttributeError: 'list' object has no attribute 'get'`, and iteration-related crashes. As a result, disabling output repair could break otherwise functional retrieval, validation, merge, and compression flows. |
| **Root Cause** | The original implementation was written assuming all structured LLM outputs would pass through `fix_llm_output()`. When the output-repair flags were later added, fallback branches were introduced but were not updated to perform JSON parsing before downstream consumption. |
| **Solution** | Updated fallback paths to route responses through `_parse_to_python()` whenever output repair is disabled. This ensures validators and compression stages still receive parsed Python objects instead of raw LLM text while preserving the ability to disable the repair layer for experimentation and ladder testing. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-023 · Shared `_merge_similar_chunks()` Logic Created Cross-Pipeline Coupling

| Field | Detail |
| --- |
| **Issue** | `_merge_similar_chunks()` was being used by both retrieval deduplication/merge and Neighbor-Aware Compression (NAC), but recent modifications assumed a single execution path. |
| **Found Date** | 2026-06-10 (during configuration-combination dry runs) |
| **Status** | Resolved |
| **Severity** | MEDIUM |
| **File** | `context_compression.py` |
| **Description** | While validating feature combinations, inconsistent behavior appeared depending on whether retrieval deduplication or NAC compression invoked `_merge_similar_chunks()`. The function had effectively become shared infrastructure, but some logic changes only considered one caller. This created subtle execution differences when specific pipeline stages were enabled or disabled. |
| **Root Cause** | Architectural coupling emerged because the same merge implementation serves multiple subsystems. The merge code evolved as if it belonged to a single feature area, despite being reused across distinct retrieval and compression flows. |
| **Solution** | Updated merge handling to correctly support both retrieval deduplication and NAC execution paths. Future modifications should treat `_merge_similar_chunks()` as shared infrastructure and validate both callers during testing. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-024 · Rate-Limit Retries Ignored Backoff Delays

| Field | Detail |
| --- |
| **Issue** | Transient Groq rate-limit failures (`HTTP 429`) retried immediately without respecting exponential backoff or provider retry guidance. |
| **Found Date** | 2026-06-10 (observed during high-volume ladder and dry-run execution) |
| **Status** | Resolved |
| **Severity** | HIGH |
| **File** | `llm_caller.py` |
| **Description** | Extended dry-run execution triggered Groq token-per-day rate limits across retrieval validation, merge validation, chunk merging, and agent retrieval phases. Retries occurred immediately after failure, causing repeated 429 responses and unnecessary API pressure. In some cases, repeated retries exhausted the retry budget without allowing sufficient recovery time. |
| **Root Cause** | Retry logic handled transient failures but did not properly implement exponential backoff behavior or honor provider-supplied `retry-after` guidance. |
| **Solution** | Implemented exponential backoff with jitter and support for `retry-after` headers. Added dedicated test coverage validating retry-after handling, exponential delay growth, retry exhaustion, and successful recovery after transient rate-limit failures. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-025 · Configuration Flags Could Not Truly Disable Output-Repair Paths

| Field | Detail |
| --- |
| **Issue** | Several stage-specific output-repair flags existed in `config.py`, but disabling them exposed execution paths that had never been exercised independently. |
| **Found Date** | 2026-06-10 (during `run_combinations.py` feature-combination testing) |
| **Status** | Resolved |
| **Severity** | HIGH |
| **File** | `validators.py`, `context_compression.py`, `self_learner.py` |
| **Description** | The new configuration architecture introduced independent output-repair switches for retrieval validation, merge validation, compression validation, QA generation, and global repair. Dry-run combinations revealed that many code paths only functioned correctly when output repair remained enabled. Turning off repair exposed hidden dependencies and assumptions throughout the validation and compression layers. As a result, several feature combinations crashed or returned invalid execution states despite being considered supported configurations. |
| **Root Cause** | The architecture was originally built around mandatory `fix_llm_output()` usage. The later addition of feature flags created configuration states that had never been tested independently. |
| **Solution** | Audited all structured-output callsites and ensured that disabling repair still routes responses through a safe parsing layer before downstream consumption. Added feature-combination testing to validate both repaired and non-repaired execution paths. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-026 · Feature Combination Testing Exposed Hidden Pipeline Coupling

| Field | Detail |
| --- |
| **Issue** | Multiple supposedly independent pipeline stages contained implicit dependencies on upstream stages being enabled. |
| **Found Date** | 2026-06-10 (during randomized configuration testing) |
| **Status** | Resolved |
| **Severity** | MEDIUM |
| **File** | Multiple pipeline modules |
| **Description** | `run_combinations.py` generated feature combinations that disabled various retrieval, compression, validation, and learning stages. Several combinations failed despite no direct dependency being documented. Components assumed that earlier stages had already normalized, validated, compressed, or repaired data before execution. This created unexpected failures when intermediate stages were bypassed. |
| **Root Cause** | Architectural assumptions accumulated organically as features were added. Modules consumed data in forms guaranteed by earlier stages without independently validating their own inputs. |
| **Solution** | Added defensive handling throughout the pipeline and updated fallback paths to operate correctly regardless of which optional stages are enabled. Configuration combinations are now treated as first-class supported execution modes rather than edge cases. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-027 · Dry Runs Produced Non-Isolated Experimental Results

| Field | Detail |
| --- | 
| **Issue** | Repeated ladder and configuration-combination runs could influence later runs through shared system state. |
| **Found Date** | 2026-06-10 (during repeated dry-run execution) |
| **Status** | Resolved |
| **Severity** | MEDIUM |
| **File** | Testing infrastructure and execution workflow |
| **Description** | While validating multiple configuration combinations, it became apparent that some pipeline behavior could be affected by state accumulated during earlier runs. This reduced confidence when comparing feature combinations because changes in observed results could originate from previous execution history rather than the configuration currently under test. |
| **Root Cause** | Experimental execution assumed isolation between runs while some system components persisted state across executions. |
| **Solution** | Updated testing workflow and configuration handling to better isolate experimental runs and ensure that feature-combination comparisons reflect only the currently active configuration. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-028 · Missing Test Coverage for Configuration-Specific Execution Paths

| Field | Detail |
| --- |
| **Issue** | Existing tests validated the primary execution path but did not exercise alternate paths created by configuration switches. |
| **Found Date** | 2026-06-10 (during dry-run analysis) |
| **Status** | Resolved |
| **Severity** | MEDIUM |
| **File** | Project-wide testing strategy |
| **Description** | The introduction of a large number of feature toggles significantly increased the number of possible execution paths. Existing testing focused on the fully enabled pipeline and therefore failed to detect issues that only appeared when specific stages were disabled. Several bugs discovered today existed solely because these alternate execution paths had never been exercised. |
| **Root Cause** | Test coverage evolved around the default production configuration rather than around the full configuration space. |
| **Solution** | Introduced configuration-combination testing through `run_combinations.py` and used it as a systematic mechanism for validating alternative execution paths. |
| **Date Resolved** | 2026-06-10 |

---

### BUG-029 · Final Result/Feedback Returned Last Retrieval Only, Not Accumulated Per-Track State
 
| Field | Detail |
|---|---|
| **Issue** | The returned answer's evidence and the persisted feedback record contained only the chunks from the most recent `retrieve_documents` call, not the accumulated per-track chunks that actually supported the answer. |
| **Found Date** | 2026-06-11 (first post-separation dry run) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py`, `feedback_store.py` |
| **Description** | The dry-run log showed the answer drafted from `documents=6 | learned_qa=1` accumulated across multiple retrieval calls, with the final answer repeatedly citing `[Source: learned_qa]`. However, the last retrieval in the loop returned `learned_qa=0`, and `interactions.jsonl` recorded `learned_qa_chunks: []` for that interaction. `_last_retrieval_fields()` in `agent_query.py` was projecting from `retriever.get_last_document_chunks()` / `retriever.get_last_learned_qa_chunks()` — which expose the most recent retrieval call only — instead of from the accumulated tracks. The same projection was reused on both the success and failure result paths, and on the feedback persistence path. Net effect: when learned-QA chunks supported an answer from an earlier retrieval iteration but were absent from the final retrieval, they disappeared from feedback, self-learning, and audit. |
| **Root Cause** | `_last_retrieval_fields()` consumed the retriever's per-call last-state getters instead of the orchestrator's `agent_state["accumulated_document_chunks"]` and `agent_state["accumulated_learned_qa_chunks"]`. The result and feedback shapes therefore reflected a single retrieval call, not the post-validation/compression state that actually informed the answer. |
| **Solution** | Replaced `_last_retrieval_fields()` with an accumulated-state projection that reads both tracks from `agent_state`, strips embeddings, and normalises each chunk to `{content, source}`. Wired the projection into every successful and failed result path. Updated `FeedbackStore.log()` to accept the normalised shape and split legacy single-list `chunks` records by `source` at read time for backward compatibility. Added regression coverage in `test_retrieval_separation.py`. |
| **Date Resolved** | 2026-06-11 |
 
---
 
### BUG-030 · `learned_qa` Collection Persisted with L2 Distance While `documents` Uses Cosine
 
| Field | Detail |
|---|---|
| **Issue** | The live `learned_qa` Chroma collection was using L2 distance while `documents` was using cosine, but both were ranked by `similarity_score = 1 - dist` and filtered through the same `MIN_SIMILARITY = 0.5` threshold. |
| **Found Date** | 2026-06-11 (first post-separation dry run) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `agent_query.py`, `self_learner.py`, `retriever.py`, new `learned_qa_store.py` |
| **Description** | Runtime collection inspection showed `documents` configured with `hnsw:space = cosine` and `learned_qa` configured with `hnsw:space = l2`. The dry-run log showed relevant learned-QA results barely surviving the threshold around 0.523–0.533, while other queries returned zero learned-QA results despite the collection containing semantically relevant entries. `retriever.py` computed `similarity_score = 1 - distance` for both collections, which is correct for cosine on unit-normalised vectors but produces `2·cos(θ) − 1` for L2 (Research topic 27). Therefore learned-QA chunks were being ranked and threshold-filtered under incompatible score semantics, potentially dropping high-priority learned answers before the ADR-030 precedence rule could even apply. Root cause was a startup ordering bug: `agent_query.py` created the collection without `hnsw:space`, defaulting to L2; `self_learner.py` later requested cosine on the same name, but `get_or_create_collection()` does not migrate distance metric — the HNSW index has to be rebuilt. |
| **Root Cause** | `learned_qa` was created without specifying `hnsw:space`, and Chroma's default is L2. The `self_learner.py` request for cosine after the fact had no effect because metadata changes do not rebuild the HNSW index. The system had no single canonical creation point that enforced cosine. |
| **Solution** | Added `learned_qa_store.py` providing `get_or_create_learned_qa_collection()` — a single factory that guarantees cosine, with a snapshot/restore/verify/rollback migration path for existing L2 collections (see ADR-031). Wired the factory into both `agent_query.py` startup and `self_learner.py` so the two code paths share one canonical collection handle. Live production migration completed successfully: 374 L2 entries → 374 cosine entries, all IDs preserved. Regression test added in `test_retrieval_separation.py` covering the L2→cosine migration. |
| **Date Resolved** | 2026-06-11 |
 
---
 
### BUG-031 · Quality Judge Loses Document Track Due to 3000-Char Combined-Context Truncation
 
| Field | Detail |
|---|---|
| **Issue** | `check_answer_quality` is called with `context[:3000]`. Because the precedence-aware combined context writes the learned-QA section first, a large learned-QA block can push the entire document section out of the truncation window — so the judge approves an answer without ever seeing the document chunks that supported its document-grounded claims. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `tools.py` (judge callsite), `context_compression.py` (`format_precedence_context_for_llm`) |
| **Description** | Dry-run lines 576–590 show a query that produced `documents=6, learned_qa=7` and a 6,478-character combined context. `format_precedence_context_for_llm()` emits `[CONFLICT RESOLUTION RULE]` → `[LEARNED QA CONTEXT - HIGH PRIORITY]` → `[DOCUMENT CONTEXT - SECONDARY]` in that fixed order. The judge then sliced the first 3,000 chars and returned `OK`. In this case the learned-QA section alone exceeded 3,000 chars, so the document section was entirely outside the slice. The draft answer contained document-supported claims; the judge approved them without ever seeing the supporting evidence. This is the inverse of the failure mode that the precedence ordering was designed to prevent: precedence ordering correctly steers the *answer*, but the *judge* sees only the head of the combined string. |
| **Root Cause** | The judge call uses a single combined context with a single character cap, applied to a string whose two tracks are concatenated in a fixed order. Truncating a structured two-section input as if it were undifferentiated text discards one section whenever the first section exceeds the cap. |
| **Solution** | Format two independently-bounded sections for the judge — give each track its own character/token allowance and include both, rather than truncating the head of the combined string. The simplest implementation is a `format_precedence_context_for_judge(learned_qa_chunks, document_chunks, per_track_budget)` helper that produces the same labelled-section layout but with per-section caps. The judge prompt may also need a small update so it knows it may be receiving an excerpt of each section rather than the full context. |
| **Date Resolved** | — |
 
---
 
### BUG-032 · Final-Answer Generation Bypasses Grounding and Conflict-Precedence Validation
 
| Field | Detail |
|---|---|
| **Issue** | The DRAFT answer is validated by `check_answer_quality`, but a subsequent final-answer generation step runs after the judge and the resulting string is returned directly without any further validation for grounding or learned-QA precedence. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `agent_query.py` |
| **Description** | The dry-run log at lines 602–606 shows the draft answer judged `OK`, then a new final-answer generation runs at lines 612–620 producing the string actually returned to the user. No validator runs between the final generation and the return path. The final generation can therefore alter the approved draft, introduce unsupported claims, drop the learned-QA precedence behaviour, or pick a conflicting document claim — and no part of the pipeline detects it. ADR-030's conflict-resolution rule is enforced as a *prompt instruction* in the final-answer prompt, so the precedence behaviour is best-effort rather than verified. This is structurally the same risk as a CAQ that judges a draft and then accepts a regenerated answer without re-judging. |
| **Root Cause** | The pipeline contains two answer-producing steps (DRAFT and final) but only one quality gate, sitting between the two. The final answer is treated as a formatting/cleanup pass rather than as a generation step that could diverge from the approved draft. |
| **Solution** | Two options. (a) Run a final-answer validator with an explicit conflict-precedence criterion — pass it the final answer, the per-track contexts, and a check that the final answer's claims are either grounded in the documents or supported by (or at least not contradicted by) the learned-QA track. (b) Drop the post-judge final-answer generation entirely and return the already-approved draft directly — cheaper and removes the divergence risk, at the cost of forfeiting any formatting/prose-cleanup the final step was performing. (b) is the smaller change and is the recommended starting point; if its output quality is acceptable, (a) is unnecessary. |
| **Date Resolved** | — |
 
---
 
### BUG-033 · Thumbdown Variants Store Pre-Validation Chunks
 
| Field | Detail |
|---|---|
| **Issue** | `failed_variants.json` and the chunk snapshots inside `user_thumbdowns.json` are captured from the raw retrieval output, before per-track relevance validation drops irrelevant chunks. Replay logic therefore treats rejected chunks as if they had supported the failed answer. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `agent_query.py` |
| **Description** | For the first query in the dry run, raw retrieval produced `learned_qa=5, documents=3`, but `_validate_track()` kept only `learned_qa=3/5, documents=2/3`. Variant capture happens at the retrieval callsite (before `_validate_track`), so the variant record stores 5+3 chunks where the actual answer was built from 3+2. If the user later thumbs-down this answer, the avoid-prior-failure injection will list two chunks that the validator already rejected as not supporting the answer in the first place. The downstream effect is that the model is steered away from retrieval directions it had already correctly rejected, which can both waste retrieval budget on diversification away from non-issues and miss the actual failure direction. |
| **Root Cause** | Variant capture is positioned at the raw retrieval boundary rather than after validation. The original single-stream architecture captured "what was retrieved" as the unit of evidence; the new two-track architecture needs to capture "what survived validation per track" as the unit of evidence, but the capture site was not moved. |
| **Solution** | Either (a) move variant capture to after `_validate_track()` so the recorded chunks are validation-survivors, or (b) record both `raw_*` and `validated_*` fields per variant and have the avoid-prior-failure injection consume `validated_*`. (a) is the minimal change and matches the answer's actual evidence. |
| **Date Resolved** | — |
 
---
 
### BUG-034 · "Sources Searched" Preview Hides Document Retrieval
 
| Field | Detail |
|---|---|
| **Issue** | Per-variant "sources searched" previews are taken as `result[:200]` of a string whose learned-QA section is written first. The preview therefore always shows the head of the learned-QA section and never reveals that any documents were retrieved. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `agent_query.py` (sources/preview construction), `tools.py` (tool-result string ordering) |
| **Description** | Dry-run lines 625–637 show every source preview beginning with `[LEARNED QA RESULTS - HIGH PRIORITY]`, even for variants where the final answer explicitly cited document sources. The tool-result string is intentionally ordered learned-QA-first to support the precedence rule (ADR-030), but the preview slice `result[:200]` then reflects only that ordering decision, not the actual retrieval distribution. Result: feedback summaries, console output, and audit displays all under-report document retrieval and can give the false impression that the system is operating learned-QA-only. |
| **Root Cause** | The preview is derived from the head of a single concatenated string instead of from the structured per-track data. The ordering rule (precedence) and the preview rule (representativeness) have incompatible requirements when the preview is a head slice. |
| **Solution** | Replace the single `preview` field with structured `learned_qa_preview` and `document_preview` fields, each derived from its own track and bounded independently. Console/audit output reads both. The combined string remains learned-QA-first for the LLM, but never feeds the preview. |
| **Date Resolved** | — |
 
---
 
### BUG-035 · Retrieval Validator Returns PASS Even When `per_chunk` Counts Are a Minority
 
| Field | Detail |
|---|---|
| **Issue** | The retrieval-validation LLM returns a top-level `verdict: PASS` while its own `per_chunk` array shows a minority of chunks relevant (e.g. 2/5). The orchestrator trusts the top-level field directly, so the agent never receives the PARTIAL/FAIL retry guidance it should have received. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `prompts.py` (`_RETRIEVAL_JUDGE_PROMPT`), `validators.py` (`validate_retrieval`), `agent_query.py` (verdict consumption) |
| **Description** | Dry-run line 314 reports `verdict=PASS relevant=2/5`. The retrieval judge prompt defines `PASS` as requiring a majority of chunks to be relevant, but the LLM emitted `PASS` while its own per-chunk verdicts show 2/5 — a minority. The orchestrator consumes the top-level `verdict` field rather than deriving it from the per-chunk counts, so the FAIL/PARTIAL retry guidance never fires, and the agent does not reformulate. The same risk applies to the inverse case (LLM emits `FAIL` while `per_chunk` shows majority relevant). Trusting an LLM-emitted summary field that disagrees with its own structured evidence is a general anti-pattern. |
| **Root Cause** | The validator's overall verdict is consumed as-emitted instead of being computed from the verifiable `per_chunk` array. There is no internal consistency check between the two. |
| **Solution** | Derive the overall verdict deterministically from `per_chunk` after the LLM call returns and the schema is repaired by `fix_llm_output`. Treat the LLM's top-level verdict as advisory only — log a warning if it disagrees with the computed verdict. A reasonable rule: `PASS` when ≥ ⌈n/2⌉ chunks are relevant, `PARTIAL` when 1 ≤ relevant < ⌈n/2⌉, `FAIL` when 0 are relevant. Same fix lets the orchestrator's PARTIAL/FAIL retry path operate on a stable signal. |
| **Date Resolved** | — |
 
---
 
### BUG-036 · Legacy-Format Splitter Misclassifies Merged Learned-QA Chunks
 
| Field | Detail |
|---|---|
| **Issue** | When `_merge_similar_chunks()` merges multiple learned-QA chunks, it joins their `source` fields into `"learned_qa, learned_qa, ..."`. The legacy feedback splitter, which matches only the exact string `source == "learned_qa"`, then misclassifies these merged chunks as document chunks. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `context_compression.py` (`_merge_similar_chunks` source field construction), `feedback_store.py` (legacy splitter at line ~39) |
| **Description** | The merge implementation in `context_compression.py` produces chunks whose `metadata.source` is the comma-joined list of input sources, e.g. `"learned_qa, learned_qa"` or `"learned_qa, learned_qa, learned_qa"`. The legacy splitter in `feedback_store.py` — which exists to convert old single-list `chunks` records into the new per-track shape at read time — only routes chunks to the learned-QA list when `source == "learned_qa"` exactly. A merged chunk with `source = "learned_qa, learned_qa"` does not match and falls through into the documents track. The same issue affects merged document chunks whose sources concatenate (e.g. `"file_a.pdf, file_b.pdf"`), but mis-routing within the documents track is less consequential than mis-routing across tracks. |
| **Root Cause** | The chunk-merge step loses the *track* (provenance bucket) by encoding it into a free-form joined string field that was originally meant only for document filename. The legacy splitter then has to reverse-engineer track membership from that string, with a substring match that misses every multi-source case. |
| **Solution** | Preserve an explicit `track` field (e.g. `"documents"` or `"learned_qa"`) on every chunk through retrieval, validation, merge, and compression. Make the legacy splitter route by `track` when present, and fall back to the exact `source == "learned_qa"` rule only when `track` is absent. The merge step then no longer has to encode provenance into the source string; the source string can keep its filename-list semantics for documents while learned-QA chunks carry their track explicitly. |
| **Date Resolved** | — |
 
---
 
### BUG-037 · Validator Repair Logging Prints "Failed" On Success
 
| Field | Detail |
|---|---|
| **Issue** | The validator-side log message emitted around `fix_llm_output` repair calls prints `failed to fix malformed LLM output` even when the repair pass succeeds and a valid verdict is produced. |
| **Found Date** | 2026-06-11 (second post-separation dry run) |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `app_workflow/services/validators.py` (`validate_retrieval()`) |
| **Description** | Dry-run logs repeatedly show the line `failed to fix malformed LLM output` immediately followed by a successfully parsed verdict being consumed by downstream code. The log message is on the wrong branch — the success path is printing the failure-path text. The functional behaviour is correct; only the diagnostics are misleading. The cost is real: ladder runs, dry-run reviews, and debugging sessions all rely on log messages to triage failures, and a repair layer that prints "failed" on every success makes its actual failure mode (when repair *really* fails) impossible to spot. |
| **Root Cause** | Inverted (or mistyped) log message on the success branch of the validator's repair-handling block. |
| **Solution** | Swap the log message on the `_ok is True` branch to indicate successful repair (or remove the line entirely on success). Keep the failure-path message exclusively on the `_ok is False` branch. One-line fix. **Resolved 2026-07-01**: fixed in `validate_retrieval()` — moved the `WARNING: failed to fix` message into the actual failure branch and added `INFO: successfully fixed` on the success branch. Investigation at fix time found the bug was isolated to `validate_retrieval()`; `validate_merge`, `validate_redundancy`, and `validate_lbc` were already logging correctly, so this was narrower than originally filed. |
| **Date Resolved** | 2026-07-01 |

---
 
### BUG-038 · Mechanical `print`→`logger` Migration Dropped Debug `print`/`write` Blocks → Empty Diagnostic Files

| Field | Detail |
|---|---|
| **Issue** | The initial `print()` → `logger.<level>()` conversion pass during the 2026-06-15 logging refactor mechanically replaced single-line `print()` calls but *removed* (rather than converted) several multi-line `print()` and `f.write(...)` debug blocks. After the migration, the diagnostic output files (`agent_query.debug.log`, `agent_query.error.log`, `llm_data_check.txt`, `llm_json_tries.txt`) were all created on startup but stayed completely empty across complete agent runs. |
| **Found Date** | 2026-06-15 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `fix_llm_output.py`, `agent_query.py`, `logger_config.py` |
| **Description** | The mechanical migration covered ~370 single-line `print(...)` calls successfully but missed two categories of pre-migration output: (a) the multi-line `with open("run_logs/llm_data_check.txt", "a") as _f: _f.write(...)` and `..._llm_json_tries.txt..., _f.write(...)` blocks in `fix_llm_output.py` that produced the `_Verify_And_Correct` and `_LLM_Json_Repair` per-call payload traces; and (b) several detailed `print(...)` blocks that had been collateral-deleted during the cleanup pass rather than rewritten. The result was that the new file handlers in `logger_config.py` opened the target files (creating them with zero bytes) but no module ever emitted a record into them, so they remained empty after a successful end-to-end run. The detailed debug content (LLM input/output, retrieved chunks, draft preview, system-prompt assembly traces, `_Verify_And_Correct` payloads, `_LLM_Json_Repair` attempts) had simply been deleted from the codebase. |
| **Root Cause** | The migration regex matched only inline `print(...)` patterns and did not handle multi-line `with open() as f: f.write(...)` blocks. The cleanup pass that followed the regex conversion was performed manually and deleted several debug blocks that the operator interpreted as redundant rather than translating them to `logger.debug(...)`. There was no automated check that the new logger handlers were actually receiving records before the migration was declared complete. |
| **Solution** | Restored the full `_Verify_And_Correct` payload trace (raw input, schema, repaired output, correction-applied flag) and the full `_LLM_Json_Repair` attempt trace (raw input, repair prompt, attempts, final outcome) through dedicated `llm_data_check_logger.debug(...)` and `llm_json_tries_logger.debug(...)` calls using `logging.getLogger("llm_data_check")` and `logging.getLogger("llm_json_tries")`. Set `propagate=True` on both diagnostic loggers in `logger_config.py` so their records reach the root logger and through it the timestamped debug file. Verified by re-running `agent_query.py` and confirming the per-run debug file (`agent_query_20260615_171551.debug.log`) contains the expected full DEBUG trace. The `agent_query.error.log` and old `agent_query.debug.log` files (from the brief dual-file design before the timestamped-per-run pattern was adopted) are now stale and can be deleted. |
| **Date Resolved** | 2026-06-15 |

---
 
### BUG-039 · Severity-Level Mismatches In `context_compression.py` And `self_learner.py` After Print→Logger Conversion

| Field | Detail |
|---|---|
| **Issue** | The mechanical `print()` → `logger.<level>()` conversion pass assigned uniform default levels (mostly `debug` or `warning`) that did not match the semantic meaning of several messages. Non-retryable errors logged at `warning`; "gave up on a chunk after retries" logged at `debug`; messages already prefixed `[ERROR]` in their text logged at `debug` or `warning`. |
| **Found Date** | 2026-06-15 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `context_compression.py`, `self_learner.py` |
| **Description** | An audit pass over the converted code found six callsites where the assigned level was semantically wrong. In `context_compression.py`: the three "non-retryable error" branches in CHUNK MERGE, DC, and LBC (each representing a stage giving up after a fatal LLM call) were emitting at `warning` rather than `error`, and the LBC "parse failed after N attempts" branch (representing the function giving up on a chunk after retry exhaustion) was emitting at `debug`, making it invisible on the console at the new INFO threshold. In `self_learner.py`: three callsites whose message text already begins with `[ERROR]` (the LLM-distillation-failed branch and two QA-pair-parse-failed branches) were emitting at `debug` or `warning`, so the prefix and the level disagreed. The functional behaviour was correct — the failures still fell through to the right error path — but the diagnostics were inconsistent with the level filtering the rest of the codebase had been organised around, and would have hidden real failures from the console at INFO. |
| **Root Cause** | The conversion script applied a default level (`warning` for messages that looked like fallbacks, `debug` for everything else) without inspecting the surrounding control flow or the message text. The audit step in the migration plan was supposed to catch this but was skipped on the first pass. |
| **Solution** | Promoted three `context_compression.py` messages (CHUNK MERGE / DC / LBC non-retryable error) from `warning` to `error`. Promoted the LBC "parse failed after N attempts" message from `debug` to `warning`. Promoted three `self_learner.py` `[ERROR]`-prefixed messages from `debug`/`warning` to `error`. No prompt or control-flow changes were required. Audit-pass discipline added to the migration checklist: after a mechanical level assignment, every `error`/`warning`/`debug` callsite must be re-read against the surrounding code path and the message text. |
| **Date Resolved** | 2026-06-15 |

---

### BUG-040 · DC Stage Shape Mismatch When `ENABLE_COMPRESSION_VALIDATION=False`

| Field | Detail |
|---|---|
| **Issue** | When `ENABLE_COMPRESSION_VALIDATION` is `False`, the DC stage's `valid_groups` is `list[list[dict]]` (each entry is the members list directly), but the consumption loop always expects `list[{"members": [...]}]` (each entry is a dict with a `"members"` key). The loop raises `TypeError` on the `False` branch. |
| **Found Date** | 2026-06-17 (surfaced while expanding `tempFile.py` to call `context_compression` functions directly) |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app/context_compression.py` (DC consumption loop, ~line 401) |
| **Description** | When `ENABLE_COMPRESSION_VALIDATION=True`, `confirmed_groups` comes from `validate_redundancy()` as `list[RedundancyGroupResult]` — each entry is a dict with a `"members"` key. When `ENABLE_COMPRESSION_VALIDATION=False`, `confirmed_groups = valid_groups` which is `list[list[dict]]` — each entry is the raw members list. The consumption loop at the merge step always does `group["members"]`, so the `False` branch breaks as soon as more than zero groups are confirmed. This was invisible in `app/agent_query.py` during recent runs because `ENABLE_DC_COMPRESSION` and `ENABLE_COMPRESSION_VALIDATION` were toggled together in the same ladder step; it only became observable when `tempFile.py` called the function with validation explicitly disabled. |
| **Root Cause** | The two branches of the `confirmed_groups` assignment produce different shapes, and the consumption loop was only written for the validated-output shape. |
| **Solution** | One-line fix: when `ENABLE_COMPRESSION_VALIDATION=False`, wrap `valid_groups` items as `[{"members": group} for group in valid_groups]` before the consumption loop, so both branches produce the same `list[{"members": [...]}]` shape. |
| **Date Resolved** | 2026-06-17 |

---

### BUG-041 · `chunk_seq` Not Promoted From `metadata` In `tempFile.py` Retrieve Node → NAC Skips Neighbor Detection

| Field | Detail |
|---|---|
| **Issue** | NAC checks `c.get("chunk_seq")` at the top level of each chunk dict. The raw retriever output stores `chunk_seq` at `c["metadata"]["chunk_seq"]`. When the retrieve node passed raw retriever output directly to `compress_neighbor_chunks`, NAC never found `chunk_seq` and therefore could not perform any neighbor-aware merge. |
| **Found Date** | 2026-06-17 (surfaced while building `tempFile.py`) |
| **Status** | Closed |
| **Severity** | LOW (only affected the sandbox `tempFile.py`; `app/agent_query.py` was never affected — `_accumulate_track()` already promoted `chunk_seq` to the top level before calling compression) |
| **File** | `tempFile.py` retrieve node (now deleted); root cause is a documentation/convention gap — the required chunk shape for compression callers is not formally specified anywhere |
| **Description** | `app/agent_query.py`'s `_accumulate_track()` helper explicitly promotes `chunk_seq` from `metadata` to the top of the chunk dict when building `accumulated_document_chunks`. This normalisation step is not part of `retriever.retrieve()` or `retriever.retrieve_separate()` — it is the caller's responsibility. `tempFile.py`'s retrieve node passed the raw `retriever.retrieve()` output straight into `compress_neighbor_chunks`, skipping the normalisation. The symptom was that NAC ran without error but performed zero merges (no chunks had `chunk_seq`, so no neighbors were identified). |
| **Root Cause** | The chunk-shape contract required by compression callers (`chunk_seq` at the top level) is implicit — it lives only in `_accumulate_track()` in `agent_query.py` and is not documented or enforced at the retriever API boundary. |
| **Solution** | In `tempFile.py`'s retrieve node, flatten each retrieved doc to the shape compression expects: `{"content": ..., "source": ..., "chunk_seq": c["metadata"].get("chunk_seq", 0), ...}` before storing in state. For `app_workflow/`, the `retrieve.py` node applies the same flattening so `validate_retrieval.py` and downstream compression nodes always receive normalised chunks. |
| **Date Resolved** | 2026-06-17 |

---

### BUG-042 · `httpx.HTTPStatusError` (429) and `httpx.ConnectError` Not Caught by `llm_caller.py` in `app_workflow/`

| Field | Detail |
|---|---|
| **Issue** | Two HTTP error types surfaced in `app_workflow/`'s debug log that were not caught by the existing `llm_caller.py` error handlers and therefore propagated as unhandled exceptions, crashing the LangGraph node. |
| **Found Date** | 2026-06-18 (observed in `rag_langgraph_20260618_183140.debug.log`) |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/services/llm_caller.py` |
| **Description** | The existing handlers in `llm_caller.py` caught `_groq.APIStatusError` (for Groq-SDK-wrapped 429s) and `_groq.APIConnectionError` (for Groq-SDK-wrapped connection failures). In some cases the Groq SDK's internal retry loop exhausted its own retries and re-raised the underlying `httpx.HTTPStatusError` (with status 429) and `httpcore.ConnectError` (DNS resolution failure, `[Errno 11001] getaddrinfo failed`) directly, bypassing the SDK wrappers. These fell through to the generic `Exception` catch-all which logged them with `logger.exception` but did not map them to a structured `LLMErrorKind` — causing the caller to receive an unstructured error path and, in the LangGraph context, crash the node. |
| **Root Cause** | `httpx.HTTPStatusError` and `httpx.ConnectError` are lower-level than the Groq SDK exception types and are only raised when the SDK's own retry logic is exhausted. They were not included in the original `llm_caller.py` exception hierarchy because they were not observed in early dry runs. |
| **Solution** | Added two `except` blocks before the generic `Exception` catch-all in `app_workflow/services/llm_caller.py`: `except httpx.HTTPStatusError as e` — maps `e.response.status_code == 429` → `LLMErrorKind.RATE_LIMIT` (so the existing retry loop backs off and retries), 5xx → `LLMErrorKind.SERVER_ERROR`, other → `LLMErrorKind.UNKNOWN`; `except httpx.ConnectError` — maps to `LLMErrorKind.CONNECTION`, same as `_groq.APIConnectionError`. Added `import httpx` at the top of the file. |
| **Date Resolved** | 2026-06-18 |

---

### BUG-043 · `app_workflow/` Does Not Write `failed_variants.json` After Each Run
 
| Field | Detail |
|---|---|
| **Issue** | `app_workflow/nodes/user_input.py` reads `failed_variants.json` on startup (to pre-populate `blocked_variants` in state) but no node ever writes newly discovered failing variants back to the file. In `app/agent_query.py`, this write happened after each `run_agent()` call. |
| **Found Date** | 2026-06-18 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/` — missing write-back; compare `app/agent_query.py` lines ~1200–1201 |
| **Description** | After a run completes (whether via `generate_answer` or `no_context_answer`), the workflow accumulates a set of query variants that were tried and produced no useful context. In `app/`, these are saved to `data/feedback/failed_variants.json` so that future runs can pre-block those trajectories. `app_workflow/`'s graph has no node that performs this save. The consequence is that the thumbdown-blocking mechanism works within a session (variants are in state) but does not persist across sessions — the same failing trajectories can be attempted again on the next process start. |
| **Root Cause** | The write-back was not ported during the June 17–18 build. It requires access to the variants tried during the run and a call to `feedback_store._save_failed_variants()` (or equivalent) after `generate_answer`/`no_context_answer` complete. |
| **Solution** | Added `load_failed_variants()` / `save_failed_variants()` to `services/feedback_store.py`. `retrieve.py` now emits `newly_failed_variants: Annotated[list[str], operator.add]` (zero-chunk variants, accumulated across all parallel `Send` branches) into state. `generate_answer.py` and `no_context_answer.py` both call `feedback_store.save_failed_variants()` at the end of their run. |
| **Date Resolved** | 2026-06-19 |
 
---
 
### BUG-044 · `app_workflow/` Thumbdown Records Written With Empty `variants` Field
 
| Field | Detail |
|---|---|
| **Issue** | `cmd_bad` in `app_workflow/nodes/commands.py` calls `feedback_store.mark_last_bad(feedback=...)` but does not pass a `variants` argument. Thumbdown entries are written to `user_thumbdowns.json` with an empty `variants` array, so the future blocked-variant injection has nothing to block. |
| **Found Date** | 2026-06-18 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/nodes/commands.py` (`cmd_bad` node) |
| **Description** | In `app/agent_query.py` line ~1117, `mark_last_bad()` is called with `variants=last_result.get("variants", [])` — the list of query variants that were tried in the last run. `app_workflow/`'s `cmd_bad` node has access to `state` but the variants tried in the most recent run are not currently stored in a state field accessible after the fact. The `query_variants` field in state holds the variants generated by `generate_query_variants` for the current invocation, which is the correct source, but `cmd_bad` runs in a *separate* graph invocation (the user types `bad` as a new input) — by the time `cmd_bad` runs, the previous run's state is gone. |
| **Root Cause** | The workflow does not persist the last run's `query_variants` between invocations. `cmd_bad` runs in its own graph invocation and cannot see the prior invocation's state without an explicit persistence mechanism. |
| **Solution** | `retrieve.py` now emits `variants_with_chunks: Annotated[list[dict], operator.add]` (every variant's retrieved chunks, both tracks) into state. `generate_answer.py` and `no_context_answer.py` cache `state["variants_with_chunks"]` into a new module-level `services.last_variants_with_chunks` sidecar at the end of each run. `cmd_bad` now reads `services.last_variants_with_chunks` and passes it as `variants=` to `mark_last_bad()`, the same sidecar pattern `app/agent_query.py`'s REPL loop uses for `last_result`. |
| **Date Resolved** | 2026-06-19 |
 
---
 
### BUG-045 · Bare Intra-Package Imports in `app_workflow/services/` Break on Startup (`ModuleNotFoundError: embedding_manager`)
 
| Field | Detail |
|---|---|
| **Issue** | `services/services.py`, `services/retriever.py`, `services/validators.py`, `services/self_learner.py`, and `services/fix_llm_output.py` imported sibling modules with bare names (`from embedding_manager import ...`) instead of relative imports, raising `ModuleNotFoundError: No module named 'embedding_manager'` the moment `app_workflow/main.py` was run |
| **Found Date** | 2026-06-19 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/services/services.py`, `retriever.py`, `validators.py`, `self_learner.py`, `fix_llm_output.py` |
| **Description** | `services/` is a Python package, so its modules can only resolve sibling imports as `from .embedding_manager import ...` (relative) or via the fully-qualified `app_workflow.services.embedding_manager` path. The bare-name imports inherited from `app/`'s flat-module convention only worked there because `app/` modules are not packaged — they're imported with `app/` itself on `sys.path`. The June 17–18 port carried the bare-import style over unchanged. |
| **Root Cause** | `app/`'s flat module layout (no `__init__.py`, modules imported with the directory on `sys.path`) and `app_workflow/services/`'s package layout (`services/` has package semantics once `app_workflow.services.services` is imported as a dotted path) require different import styles; the port copied the source files without adjusting imports for the new layout. |
| **Solution** | Converted all five files' intra-`services/` imports to relative form (`from .embedding_manager import EmbeddingManager`, etc.). |
| **Date Resolved** | 2026-06-19 |
 
---
 
### BUG-046 · `app_workflow/main.py` Run From Inside `app_workflow/` Cannot Resolve `from app_workflow.config import ...` (`ModuleNotFoundError: app_workflow`)
 
| Field | Detail |
|---|---|
| **Issue** | After fixing BUG-045, a second `ModuleNotFoundError: No module named 'app_workflow'` surfaced from `services/retriever.py`'s `from app_workflow.config import RETRIEVAL_TOP_K, RETRIEVAL_TOP_L, MIN_SIMILARITY` |
| **Found Date** | 2026-06-19 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/main.py` |
| **Description** | `main.py` is launched with the working directory set to `app_workflow/` (`python .\main.py` from inside that folder), so `app_workflow/` itself is on `sys.path` — which lets bare imports like `from graph import build_graph` resolve, but does *not* put the project root (`RAG-work/`) on `sys.path`. Several `services/` modules need the project root on the path to resolve `from app_workflow.config import ...` (a dotted, fully-qualified import used throughout `services/` and `nodes/`). |
| **Root Cause** | Two different import conventions are in play simultaneously: bare imports that assume `app_workflow/` is the working directory, and dotted imports that assume the project root is on `sys.path`. Only the first was satisfied by the normal `python .\main.py` invocation. |
| **Solution** | Inserted the project root (`RAG-work/`, derived from `__file__`) at the front of `sys.path` at the very top of `main.py`, before any other imports execute. `app_workflow/` (the CWD) remains on the path too, so the existing bare imports inside `main.py` continue to work alongside the now-resolvable dotted imports. |
| **Date Resolved** | 2026-06-19 |
 
---
 
### BUG-047 · `FAILED_VARIANTS_PATH` Resolves Outside the Project (Extra `../` in `app_workflow/config.py`)
 
| Field | Detail |
|---|---|
| **Issue** | `FAILED_VARIANTS_PATH` in `app_workflow/config.py` was built with one extra `../` relative to the other `data/feedback/` path constants, resolving outside the project root instead of to `data/feedback/failed_variants.json` |
| **Found Date** | 2026-06-19 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/config.py` |
| **Description** | All `data/feedback/` path constants (`FEEDBACK_PATH`, `USER_THUMBDOWNS_PATH`, `FAILED_VARIANTS_PATH`) were originally built as CWD-relative strings rather than resolved against an absolute project root, making them fragile to the directory the process happens to be launched from — `FAILED_VARIANTS_PATH` had drifted to use one more `../` than the sibling constants. |
| **Root Cause** | CWD-relative path construction instead of `__file__`-anchored resolution; `services/services.py` already used the safer `_project_root`-derived pattern for `VECTOR_STORE_PATH` and `_FEEDBACK_PATH`, but `config.py`'s own constants had not been brought in line with it. |
| **Solution** | Rewrote all `data/feedback/` path constants in `config.py` against a `__file__`-derived `_PROJECT_ROOT`, matching the resolution pattern already used in `main.py` and `services.py`, instead of CWD-relative strings. |
| **Date Resolved** | 2026-06-19 |

---

### BUG-048 · `app/llm_caller.py` Missing `httpx` Exception Handlers and Abort Guard — Out of Parity with `app_workflow/services/llm_caller.py`

| Field | Detail |
|---|---|
| **Issue** | `app/llm_caller.py`'s `_invoke_once()` did not handle `httpx.HTTPStatusError` or `httpx.ConnectError`, and `llm_invoke()`'s abort guard was never reachable despite the `LLMRateLimitAbortError` class and `rate_limit_max_delay_seconds` parameter already existing in the file |
| **Found Date** | 2026-06-20 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app/llm_caller.py` |
| **Description** | The June 18 BUG-042 fix added `httpx.HTTPStatusError` and `httpx.ConnectError` handlers to `app_workflow/services/llm_caller.py`, but the equivalent `app/llm_caller.py` was not updated at the same time. A comparison revealed three gaps: (1) `httpx` was never imported; (2) `_invoke_once()` fell through to bare `except Exception` for `httpx.HTTPStatusError`/`httpx.ConnectError`, meaning 429s from the httpx layer were classified as UNKNOWN rather than RATE_LIMIT and never triggered the retry loop correctly; (3) the abort guard in `llm_invoke()` — `if delay >= rate_limit_max_delay_seconds: raise LLMRateLimitAbortError(delay)` — was missing despite the class and parameter being present, so `app/` would continue sleeping through arbitrarily long delays rather than aborting. |
| **Root Cause** | BUG-042 was scoped to `app_workflow/` only; `app/llm_caller.py` was not updated in the same session. |
| **Solution** | Added `import httpx as _httpx`; added `httpx.HTTPStatusError` (429 → RATE_LIMIT, 5xx → SERVER_ERROR, other → UNKNOWN) and `httpx.ConnectError` (CONNECTION) except blocks in `_invoke_once()` before the bare `except Exception`; added the abort guard in `llm_invoke()`. Both files are now fully in parity. |
| **Date Resolved** | 2026-06-20 |

---

### BUG-049 · `app/api.py` Log File Never Created — `setup_logging` Called After Pipeline Imports

| Field | Detail |
|---|---|
| **Issue** | Running `app/api.py` via uvicorn produced no log file under `app/run_logs/`, even though `setup_logging` was called in the file |
| **Found Date** | 2026-06-20 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `app/api.py` |
| **Description** | `setup_logging(app_name="langchain_api")` was invoked after `from agent_query import run_agent` and other pipeline imports. `logger_config.py`'s `setup_logging` uses a "configure once" guard — it checks `getattr(root_logger, "_CONFIGURED_ATTR", False)` and returns immediately if already set. Any earlier import that caused `setup_logging` to be called first (e.g. `agent_query.py` or another module that calls it at module load) would win the race, configure the root logger without a file handler aimed at `app/run_logs/`, and cause `api.py`'s call to be silently skipped. The result was that log output went only to the console with no persistent log file. |
| **Root Cause** | Idempotent "configure once" guard in `setup_logging` combined with `api.py` calling it after all pipeline imports instead of before. |
| **Solution** | Moved `setup_logging(log_dir=_APP_DIR / "run_logs", app_name="langchain_api")` to immediately after `logger_config` is imported and before any other pipeline module is imported. Log files now appear correctly in `app/run_logs/`. |
| **Date Resolved** | 2026-06-20 |

---

### BUG-050 · `app_workflow/nodes/nac.py` — `caller_tag="MERGE"` Ambiguous in DEBUG Logs After Timing Instrumentation

| Field | Detail |
|---|---|
| **Issue** | `_merge_similar_chunks()` in `app_workflow/nodes/nac.py` passed `caller_tag="MERGE"` to `llm_invoke()`, producing DEBUG log lines tagged `[MERGE]` — indistinguishable from any other merge-type call if similarly named tags were used in other nodes. |
| **Found Date** | 2026-06-22 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `app_workflow/nodes/nac.py` |
| **Description** | After the June 22 addition of per-attempt duration logging to `llm_caller.py` (logging `[{caller_tag}] LLM call attempt N took X.XXXs`), the granularity of `caller_tag` values became directly visible in run logs. The tag `"MERGE"` used by NAC's `_merge_similar_chunks()` does not identify the calling node, making NAC's LLM calls indistinguishable from any future merge node that might use the same string. |
| **Root Cause** | The initial `caller_tag` value was assigned before DEBUG timing instrumentation existed; tag distinctiveness was not a concern at the time. |
| **Solution** | Renamed `caller_tag` from `"MERGE"` to `"NAC-MERGE"` in `_merge_similar_chunks()` so NAC's LLM calls are unambiguously identified in DEBUG logs. |
| **Date Resolved** | 2026-06-22 |

---

### BUG-051 · Timeout Constants in Both `config.py` Files Initially Set Without Empirical Calibration

| Field | Detail |
|---|---|
| **Issue** | `LLM_RESPONSE_TIMEOUT_SECONDS`, `RETRIEVAL_TIMEOUT_SECONDS`, and `EMBEDDING_ENCODING_TIMEOUT_SECONDS` were initially set based on documentation estimates rather than measured latencies, making the values overly conservative. They were revised after the June 22 benchmark runs revealed the actual p95 figures. |
| **Found Date** | 2026-06-22 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `app/config.py`, `app_workflow/config.py` |
| **Description** | When the three timeout constants were first introduced, no timing baseline existed for this hardware and workload, so documentation figures were used as placeholders. The initial values were larger than warranted — a pathological hang would have been tolerated far longer than necessary before the timeout mechanism triggered. |
| **Root Cause** | No empirical timing data was available at the time the constants were introduced; documentation-based estimates were used as a temporary placeholder. |
| **Solution** | After running 10 benchmark queries per pipeline with per-module DEBUG timing enabled, empirical p95 latencies were established: LLM calls up to ~75 s; ChromaDB `.query()` up to ~0.704 s; `model.encode()` up to ~0.019 s. Constants revised to `LLM_RESPONSE_TIMEOUT_SECONDS = 150` (2× observed max), `RETRIEVAL_TIMEOUT_SECONDS = 10` (~14× p95), `EMBEDDING_ENCODING_TIMEOUT_SECONDS = 10` (~500× p95). Asymmetric margins reflect that LLM latency has higher variance while retrieval and embedding are stable sub-second operations. |
| **Date Resolved** | 2026-06-22 |

---

### BUG-052 · `app_workflow/services/logger_config.py` Relative Import Creates Orphaned Timing-Tracker Singleton

| Field | Detail |
|---|---|
| **Issue** | The JSON timing file produced by each `app_workflow/` run remained empty after every query, despite `set_json_path()` being called at startup and `record()` being called from every instrumented node. |
| **Found Date** | 2026-06-23 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/services/logger_config.py` |
| **Description** | `logger_config.py` used `from .timing_tracker import timing_tracker` (a relative import). Python registered this module under the key `services.timing_tracker` in `sys.modules` — without the `app_workflow.` prefix, because the module was loaded as a side-effect of importing `logger_config` before the `app_workflow` package namespace was fully established. Node files importing `from app_workflow.services.timing_tracker import timing_tracker` used the fully-qualified key `app_workflow.services.timing_tracker`, which is a different cache entry and therefore a different object instance. `set_json_path()` was called on the orphaned `services.timing_tracker` instance; all `record()` calls from nodes went to the uninitialized `app_workflow.services.timing_tracker` instance, which had no `_json_path` set and never wrote anything to disk. |
| **Root Cause** | Python's import system registers modules under the exact dotted name used in the import statement. A relative import inside a package loaded without its parent fully initialised can produce a `sys.modules` key that differs from the fully-qualified `package.module` path used by other importers, yielding two separate objects for the same file. |
| **Solution** | Replaced `from .timing_tracker import timing_tracker` in `logger_config.py` with `import importlib; _tt = importlib.import_module("app_workflow.services.timing_tracker")`, then called `_tt.set_json_path(json_path)`. `importlib.import_module` always uses the canonical absolute dotted path as the `sys.modules` key, so it retrieves the same object that node files access via `from app_workflow.services.timing_tracker import timing_tracker`. |
| **Date Resolved** | 2026-06-23 |

---

### BUG-053 · Concurrent `POST /query` Requests Cause One Thread to Silently Exhaust All Retry Attempts on 429

| Field | Detail |
|---|---|
| **Issue** | Submitting two simultaneous `POST /query` requests to `app/api.py` causes one to silently fail — `llm_invoke()` returns a rate-limit error after exhausting all retry attempts, every one of which was a 429, because the concurrent thread consumed the available Groq token quota. |
| **Found Date** | 2026-06-24 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app/llm_caller.py`, `app/api.py`, `app_workflow/services/llm_caller.py`, `app_workflow/api.py` |
| **Description** | When two requests arrive at `POST /query` simultaneously, `asyncio.to_thread()` dispatches both `run_agent()` calls into the thread pool concurrently. Both threads eventually reach `llm_invoke()` at roughly the same time. The first thread proceeds normally and its LLM calls consume most or all of the Groq token-per-minute quota. Every retry attempt in the second thread hits a 429 rate-limit response. Once `LLM_RATE_LIMIT_MAX_ATTEMPTS` is exhausted, `llm_invoke()` returns `LLMResult(ok=False, error_kind=RATE_LIMIT)` with no successful call. The pipeline produces an erroneous or empty answer — no exception is raised at the HTTP boundary, and no HTTP 429 is returned to the caller. The only evidence is the debug log showing all retry attempts hitting 429. |
| **Root Cause** | The `asyncio.Lock` (`_query_lock`) in `api.py`'s `/query` handler appeared to serialize concurrent requests but is not a cross-thread mutex — it operates within a single asyncio event loop thread. `asyncio.to_thread()` dispatches the blocking work to the thread pool immediately upon entry, releasing the lock before `run_agent()` begins executing. Both pipeline executions therefore run concurrently inside the thread pool with no mutual exclusion at the `llm_invoke()` level, where Groq calls actually occur. |
| **Solution** | Introduced a FIFO serialization gate inside `llm_invoke()` in both `app/llm_caller.py` and `app_workflow/services/llm_caller.py`: a `queue.Queue` of per-thread `threading.Event` objects ensures only one thread calls Groq at a time, in strict arrival order. A thread that receives a 429 holds the gate rather than re-enqueuing, sleeps the full token-reset window from Groq's response headers, then retries directly. The `async with _query_lock:` block was removed from both `api.py` files — serialization is delegated to `llm_invoke()`'s FIFO gate in both pipelines. `max_retries=0` set on all `ChatGroq` instances in both packages so LangChain's built-in retry loop is fully disabled. Adaptive cooldown (`_cooldown_floor`) added to absorb residual token-rate variance between consecutive calls. Branch `setup_async_lock` merged into `master` on 2026-06-25 (13 files changed). See ADR-044, ADR-045, and Research topic 35. |
| **Date Resolved** | 2026-06-25 |

---

### BUG-054 · `IndexKeySpecsConflict` on `app_workflow/` Startup — `sparse=True` Mismatch on `request_id` Index

| Field | Detail |
|---|---|
| **Issue** | `app_workflow/services/db.py` raised `pymongo.errors.OperationFailure: IndexKeySpecsConflict` on startup because it tried to create the `request_id_1` unique index with `sparse=True`, while `app/db.py` had already created that index without `sparse=True` in the shared `rag_db` database. |
| **Found Date** | 2026-06-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/services/db.py` |
| **Description** | Both `app/db.py` and `app_workflow/services/db.py` call `_ensure_indexes()` on the same shared MongoDB database (`rag_db`). `app/db.py` creates `db["feedback_interactions"].create_index([("request_id", ASCENDING)], unique=True)` — no `sparse` argument, so the index is non-sparse by default. `app_workflow/services/db.py` initially called the same line with an additional `sparse=True`. When `app/api.py` started first, the non-sparse index was registered under the name `request_id_1`. When `app_workflow/api.py` started afterward, its `_ensure_indexes()` attempted to create `request_id_1` with `sparse=True` — MongoDB rejected this with `IndexKeySpecsConflict` because `sparse` is an immutable option that cannot be changed on an existing index without dropping and recreating it. The exception propagated out of the collection accessor, preventing all MongoDB operations and crashing `app_workflow/` startup. |
| **Root Cause** | `sparse=True` was added to `app_workflow/services/db.py` to avoid potential unique-index violations from CLI-path interactions that have no `request_id`. That problem was actually solved in `feedback_store.py` by generating `request_id = request_id or str(uuid.uuid4())`, making `sparse=True` both unnecessary and harmful. |
| **Solution** | Removed `sparse=True` from `app_workflow/services/db.py`'s `request_id` index call. Both `db.py` files now issue identical `create_index([("request_id", ASCENDING)], unique=True)` calls. MongoDB's `create_index` is idempotent when the spec exactly matches the existing index — the second call is a no-op. See Research topic 36 for background on replica-set index creation. |
| **Date Resolved** | 2026-06-27 |

---

### BUG-055 · `DuplicateKeyError` in `feedback_store.log()` When LangGraph Retries `generate_answer` Node

| Field | Detail |
|---|---|
| **Issue** | After the MongoDB migration, `feedback_store.log()` raised `pymongo.errors.DuplicateKeyError` and crashed the `generate_answer` node when LangGraph's retry machinery re-executed the node within the same graph invocation. |
| **Found Date** | 2026-06-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app/feedback_store.py`, `app_workflow/services/feedback_store.py` |
| **Description** | LangGraph's `run_with_retry` can re-execute a node after a transient failure. `generate_answer` calls `feedback_store.log()` before returning to the graph. If the node fails after `log()` but before returning successfully, LangGraph retries it — calling `log()` again with the same `request_id`. The `feedback_interactions` collection has a unique index on `request_id`. The second `insert_one` violates this index and raises `DuplicateKeyError`, which propagates out of the node as an unhandled exception. The flat-file predecessor (`interactions.jsonl`) was append-only and never raised on a duplicate `request_id`, so this retry case was never observable before the MongoDB migration. |
| **Root Cause** | `insert_one` had no handler for the scenario where the same `request_id` was already inserted in the current invocation by an earlier (successful) execution of the same node. The unique index enforces a correctness invariant that is correct at the HTTP-request level but must be treated as an idempotency guard rather than a fatal error at the LangGraph-node level. |
| **Solution** | Wrapped `interactions_col().insert_one(record)` in `try/except DuplicateKeyError` in both `app/feedback_store.py` and `app_workflow/services/feedback_store.py`. On `DuplicateKeyError`, `log()` emits `logger.warning("Duplicate interaction log skipped (node retry): request_id=...")` and returns cleanly — the first insert already persisted the correct record. See Research topic 37 for the general idempotency-via-DuplicateKeyError pattern. |
| **Date Resolved** | 2026-06-27 |

---

### BUG-056 · `fix_llm_output.py` Hardcodes `model_name="llama-3.1-8b-instant"` — Will Break on 2026-08-16 Groq Deprecation

| Field | Detail |
|---|---|
| **Issue** | `_LLM_Json_Repair` and `_Verify_And_Correct` in both `app/fix_llm_output.py` and `app_workflow/services/fix_llm_output.py` construct fresh `ChatGroq` instances with `model_name="llama-3.1-8b-instant"` hardcoded at class instantiation time. Groq has announced `llama-3.1-8b-instant` will be deprecated on 2026-08-16. After that date, any `fix_llm_output.py` repair call will fail with a Groq provider error, crashing the LLM output-fix path. |
| **Found Date** | 2026-06-30 |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `app/fix_llm_output.py`, `app_workflow/services/fix_llm_output.py` |
| **Description** | Unlike the main pipeline LLM clients (`llm`, `merge_llm`, `judge_llm`) which are instantiated in `services/services.py` (or `agent_query.py`) and can be updated at a single config-driven location, the two auto-repair classes in `fix_llm_output.py` each create their own `ChatGroq(model_name="llama-3.1-8b-instant", ...)` instance internally. They are therefore not affected by any change to `LLM_MODEL_NAME` in `config.py` or by swapping the model reference in `services.py`. After 2026-08-16, every call to `_LLM_Json_Repair.repair()` and `_Verify_And_Correct.verify()` will fail at the Groq provider level. The failure surface is the output-fix path — triggered only when the primary LLM returns malformed JSON or a schema violation — so it may go undetected in runs where the primary LLM output is already well-formed, only surfacing under stress or after prompt changes that increase schema violation frequency. |
| **Root Cause** | `fix_llm_output.py` was written before the centralised service-registry pattern (`services/services.py`) was established. The repair classes take no LLM client as a constructor parameter and instead hard-construct their own. The `"llama-3.1-8b-instant"` string was never extracted to a config constant. |
| **Solution** | Refactor both `_LLM_Json_Repair` and `_Verify_And_Correct` in both `fix_llm_output.py` files to accept an LLM client as a constructor parameter (injected from the service registry) rather than hard-constructing their own. Alternatively, at minimum, extract `"llama-3.1-8b-instant"` to a `FIX_LLM_MODEL_NAME` constant in `config.py` so the model can be changed at config-level before the 2026-08-16 deadline without touching the class logic. The injection-based approach is preferable as it removes the second hidden `ChatGroq` construction entirely. |
| **Date Resolved** | — |

---

### BUG-057 · NVIDIA GPU Driver Failure (Code 43) Forces Embedding Fallback to CPU

| Field | Detail |
|---|---|
| **Issue** | `all-MiniLM-L6-v2` embedding runs on CPU instead of the RTX 5050 Laptop GPU despite a correctly CUDA-built PyTorch install |
| **Found Date** | 2026-07-01 |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | N/A — Windows NVIDIA driver / Device Manager, not project code |
| **Description** | `embedding_manager.py` logged `Model 'all-MiniLM-L6-v2' loaded on cpu` and `CUDA not available; running on CPU`. `python -c "import torch; print(torch.cuda.is_available())"` confirmed `torch==2.11.0+cu128` (CUDA 12.8 build) but `torch.cuda.is_available()` returned `False`. `nvidia-smi` failed with a permissions error (exit code 4). `Get-CimInstance Win32_VideoController` showed the RTX 5050 Laptop GPU with `Status: Error` and `ConfigManagerErrorCode = 43` ("Windows has stopped this device because it reported problems"), while the integrated Intel UHD Graphics reported `Status: OK`. Installed driver version 32.0.15.9595 (≈ NVIDIA 559.95) is suspected too old for proper Blackwell-generation (RTX 50-series) laptop GPU support. |
| **Root Cause** | Windows NVIDIA kernel driver in a crashed/error state (Code 43), most likely a driver-version mismatch for the Blackwell-architecture RTX 5050 Laptop GPU. Not a PyTorch or project-code issue — the CUDA-enabled wheel is correctly installed. |
| **Solution** | Clean driver reinstall recommended: boot into Safe Mode, run Display Driver Uninstaller (DDU) to fully remove the existing driver, then install the latest Game Ready driver (576.xx+) from nvidia.com for the RTX 5050 Laptop GPU, choosing a clean installation. Re-verify with `nvidia-smi` and `torch.cuda.is_available()` after reboot. If Error 43 persists after a clean driver install, check for a BIOS-level GPU MUX/Optimus switch. Not yet performed as of the found date — embeddings currently run on CPU (functionally correct, slower). |
| **Date Resolved** | — |

---

### BUG-058 · `_LLM_Json_Repair` Cannot Recover Python Class/Attribute-Assignment Syntax — Returns `{}` (Data Loss)

| Field | Detail |
|---|---|
| **Issue** | When an LLM emits a Python class definition with attribute assignments instead of a dict/JSON literal, `fix_llm_output()` returns an empty object across every affected schema — in three of four observed cases the LLM repair tier never even fires |
| **Found Date** | 2026-07-01 (via `app_workflow/test_output_fixes.py` run, log `test_output_fixes_20260701_184529.log`) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `app_workflow/services/fix_llm_output.py` |
| **Description** | Test cases `PC04-mj`, `PC04-rj`, `PC04-lj` (merge_judge, retrieval_judge, lbc_judge schemas) return `{}` in ~0.1ms — meaning the escalation heuristic never recognizes the input as needing the LLM repair tier at all, despite the deterministic tiers (preprocessing, balanced extraction, `json_repair`) having no ability to parse Python class syntax. `PC04-lc` (lbc_compress schema) does escalate (671ms, consistent with an LLM repair call being made) but *still* returns `{}` — so the LLM repair tier itself also fails to reconstruct the data from class-attribute syntax when it is actually invoked. Test notes for all four cases state the expectation "LLM reads class attribute assignments and emits the JSON object," but none do. This is effectively two separate defects: a missing escalation trigger for this failure shape, and a genuine LLM-repair capability gap once escalation does occur. |
| **Root Cause** | None of the deterministic tiers (string preprocessing, balanced-bracket extraction, `json_repair`) recognize `ClassName(): self.field = value` syntax as JSON-adjacent, so most cases fall straight through to the empty-result path without ever reaching `_LLM_Json_Repair()`. Where escalation does happen, the `_JSON_REPAIR_PROMPT` (schema + raw text) is apparently insufficient to reliably guide reconstruction from this syntax shape, unlike the XML/YAML/dataclass/PascalCase cases it demonstrably does handle (per BUG-018's closure notes). |
| **Solution** | Add a preprocessing-tier detection heuristic for `class \w+.*:\s*\n\s+self\.\w+\s*=` patterns (or similar) so these inputs are routed to `_LLM_Json_Repair()` rather than falling through to the empty result immediately. Separately, strengthen or add a worked example to `_JSON_REPAIR_PROMPT` specifically demonstrating class-attribute-to-JSON reconstruction, since the existing prompt structure (Research topic 19) evidently does not generalize to this input shape from its current examples. |
| **Date Resolved** | — |

---

### BUG-059 · `merged_from` Coercer Only Handles `None → 0`, Contradicting Its Own Documented Fallback Behavior

| Field | Detail |
|---|---|
| **Issue** | Pydantic `mode="before"` coercion for the `merged_from` field (and likely similarly-documented numeric coercers) is documented/annotated as falling back to `0` for any bad value, but only actually does so for `None` — a truncated value becomes `""` and a non-numeric string passes through unchanged |
| **Found Date** | 2026-07-01 (via `app_workflow/test_output_fixes.py` run, log `test_output_fixes_20260701_184529.log`) |
| **Status** | Open |
| **Severity** | LOW |
| **File** | `app_workflow/services/fix_llm_output.py` |
| **Description** | Test cases `C07-merge` and `C11-merge` carry notes claiming the `merged_from` coercer "falls back to 0" for bad values. Empirically: a truncated numeric value coerces to `""` (empty string, not `0`), and the string `"two"` passes through unmodified (not coerced to `0`). A separate passing case, `C13-merge` (a `None` input), does correctly coerce to `0`, confirming the `None` path works as documented — only the empty-string and non-numeric-string paths are missing. |
| **Root Cause** | The `mode="before"` validator for this field (see Research topic 18 for the general coercion pattern) implements only the `None → 0` branch; it was never extended to cover empty-string or non-numeric-string inputs despite inline documentation/comments implying broader coverage. |
| **Solution** | Extend the `merged_from` (and any sibling numeric-field) coercer's `mode="before"` validator to also catch empty string and non-numeric string inputs, coercing them to `0` alongside the existing `None` case — e.g. `if v is None or (isinstance(v, str) and not v.strip().lstrip("-").isdigit()): return 0`. Update or remove the inline documentation if the intended behavior is actually narrower than what it currently states. |
| **Date Resolved** | — |

---

### BUG-060 · LLM Repair Tier Fabricates Plausible JSON for Inputs With No Real Answer Data

| Field | Detail |
|---|---|
| **Issue** | When the raw LLM response contains no actual answer data at all (bare function definitions, generator/comprehension syntax, f-string templates, lambda-valued dicts, pure prose, or an explicit refusal message), `_LLM_Json_Repair()` still returns a fabricated JSON object instead of signaling extraction failure |
| **Found Date** | 2026-07-01 (via `app_workflow/test_output_fixes.py` run, log `test_output_fixes_20260701_184529.log`) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `app_workflow/services/fix_llm_output.py` |
| **Description** | Observed across multiple schemas and input shapes: `PC01-dc` (pure Python function, no dict), `PC06-dc`/`PC09-dc` (generator/list-comprehension syntax), `PC11-rj` (comprehension syntax), `PC20-merge` (an f-string template with no literal values), `PC10-rj` (a lambda-valued dict), `C01-merge` (pure prose, no JSON anywhere), and `C18-dc` (an outright LLM refusal message). In every case, `_LLM_Json_Repair()` returns a plausible-looking populated object rather than an empty/failure result — meaning downstream consumers receive fabricated values with no signal that the source data never existed. This is functionally identical to the risk already documented for `_Verify_And_Correct()` in BUG-019 (hallucinated `sources` field), but occurs earlier in the pipeline and across a much broader set of field types, not just `sources`. |
| **Root Cause** | `_JSON_REPAIR_PROMPT` instructs the model to reconstruct JSON matching the target schema from the raw text, but does not give the model an explicit "no data present — return null/empty" escape hatch, nor examples demonstrating when *not* to produce output. A schema-aware LLM under those instructions defaults to satisfying the schema by inventing plausible values rather than reporting absence. |
| **Solution** | Add an explicit negative instruction and worked example to `_JSON_REPAIR_PROMPT`: "If the RAW RESPONSE contains no data corresponding to a required field — no dict/object literal, no key-value pairs resembling the schema, only code, prose, or a refusal — return `null` (or the schema's designated empty/failure marker) rather than inventing values." Cross-reference with the `_VALUE_VERIFY_PROMPT` fix already proposed for BUG-019, since both stem from the same underlying "invent rather than admit absence" failure mode. |
| **Date Resolved** | — |

---

### BUG-061 · Balanced-JSON Extraction Selects the Wrong Candidate When Multiple JSON-Like Blobs Are Present

| Field | Detail |
|---|---|
| **Issue** | When a raw LLM response contains both an explanatory/example JSON object and the actual answer JSON object, the extraction tier sometimes grabs the wrong one |
| **Found Date** | 2026-07-01 (via `app_workflow/test_output_fixes.py` run, log `test_output_fixes_20260701_184529.log`) |
| **Status** | Open |
| **Severity** | LOW |
| **File** | `app_workflow/services/fix_llm_output.py` |
| **Description** | Test cases `PC14-merge` and `PC11-lc` both include an example/illustrative JSON blob alongside the real answer in the raw response. Extracted output picked up the example values instead of the real ones (e.g. `content: 'wrong'` instead of the intended `'x'`; `compressed: 'wrong'` instead of the intended `'correct'`). The balanced-bracket extraction tier (Tier 2, per the `fix_llm_output.py` module description in `Architecture.md`) takes the first top-level `{...}`/`[...]` it finds, which is correct when there is exactly one candidate object but ambiguous when there are two. |
| **Root Cause** | The extraction heuristic has no notion of "which candidate object is the actual answer" — it is positional (first-found) rather than content-aware, so a well-formed example placed before the real answer in the response wins. |
| **Solution** | When balanced extraction finds more than one top-level candidate object, prefer the one that best matches the target schema's required-field set (e.g. score each candidate by count of expected keys present) rather than defaulting to the first one found. Alternatively, bias toward the *last* candidate object on the theory that LLMs typically place worked examples before their final answer — would need empirical validation against a broader sample before committing to either heuristic. |
| **Date Resolved** | — |

---

### BUG-062 · `combine_tracks` Fires Once Per Predecessor Instead of Waiting for Both Tracks (Non-Barrier Fan-In)

| Field | Detail |
|---|---|
| **Issue** | `combine_tracks` executes once for each completing predecessor track rather than once as a true fan-in barrier, because the document and learned-QA tracks have unequal depth |
| **Found Date** | 2026-07-02 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/graph.py`, `app_workflow/nodes/combine_tracks.py` |
| **Description** | `combine_tracks` has two incoming edges (`validate_LBC_documents`, `validate_LBC_learned_qa`). The document track is NAC → DC → LBC (3 compression stages); the learned-QA track is DC → LBC (2 stages). Because of this depth mismatch the two tracks land in different LangGraph supersteps, and LangGraph's default fan-in only merges predecessors completing in the *same* superstep — so `combine_tracks` fired once when the faster learned-QA track finished and again once the slower document track finished. Confirmed in `langgraph_api_20260702_140345.debug.log`: `[COMBINE_TRACKS] learned_qa=4 documents=0 combined=4` immediately followed later by `[COMBINE_TRACKS] learned_qa=4 documents=2 combined=6` for the same request. Each premature firing routed straight into `generate_draft` (since `compressed_docs` was already non-empty), producing an initial draft built from partial context before the document track had finished compressing — the direct cause of the "many drafts/answers per request" and "draft generated before retrieval/compression completed" symptoms observed across that log. |
| **Root Cause** | The node was wired as a fan-in point but not registered with the barrier semantics LangGraph requires for predecessors of unequal path length. |
| **Solution** | Registered the node with `defer=True` in `graph.py`'s `add_node("combine_tracks", combine_tracks, defer=True)` call — LangGraph now holds execution until every other pending task in the run has completed, so the node fires exactly once with both tracks fully populated. |
| **Date Resolved** | 2026-07-02 |

---

### BUG-063 · `generate_answer` Returns `draft` Verbatim Instead of Using It as Synthesis Input

| Field | Detail |
|---|---|
| **Issue** | Whenever a draft existed in state, `generate_answer` returned it unmodified as the final answer instead of using it as working material for one more LLM synthesis call |
| **Found Date** | 2026-07-02 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/nodes/generate_answer.py` |
| **Description** | The intended design (already implemented correctly in `app/agent_query.py`'s `_generate_final_answer`) is: when a draft exists, pass it as working material into one more LLM call that reconciles it against the full compressed context and produces the polished final answer, falling back to the literal draft only if that synthesis call itself fails. The actual code instead did `if draft: answer = draft` — a hard short-circuit skipping the synthesis call entirely. Confirmed byte-for-byte in `langgraph_api_20260702_140345.debug.log`: the `[GENERATE_DRAFT] draft:` text at 14:11:10 and the `[GENERATE_ANSWER] RESPONSE:` text at 14:11:12 are identical. This also meant `check_answer_quality`'s verdict was computed over text that then shipped completely unmodified — judge and answer were the same LLM output with no refinement step between them. |
| **Root Cause** | Draft short-circuit was written as the terminal path instead of the fallback path; no synthesis prompt existed for the draft-present case at all. |
| **Solution** | Added `_GENERATE_ANSWER_FROM_DRAFT_PROMPT` (`prompts.py`) and rewired `generate_answer.py`: if a draft exists, call the LLM with the draft as working material plus full context to produce the actual answer; fall back to the literal draft only if that call fails (`result.ok is False`). No-draft path (`_GENERATE_ANSWER_PROMPT` from flattened context) is unchanged. |
| **Date Resolved** | 2026-07-02 |

---

### BUG-064 · `GEN_MODEL_NAME` Set to a Hugging-Face-Style Model Path While `llm` Is a `ChatGroq` Client → HTTP 404 `model_not_found`

| Field | Detail |
|---|---|
| **Issue** | `.env`'s `GEN_MODEL_NAME` was set to an HF Hub-style model path consumed by the Groq-backed `llm` client, which has no model by that name |
| **Found Date** | 2026-07-02 |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `.env`, `app_workflow/services/llm_setup.py` |
| **Description** | `.env` had `GEN_MODEL_NAME=Qwen/Qwen2.5-7B-Instruct`, but `llm` in `llm_setup.py` is constructed as `ChatGroq(model=GEN_MODEL_NAME, ...)` — Groq's catalog has no model under that name. Confirmed in log: `[NAC-MERGE] NotFoundError — HTTP 404: ... 'The model qwen/qwen2.5-7b-instruct does not exist or you do not have access to it.'`. Unrelated to the HF-router models added for `judge_llm`/`json_fix_llm` on 2026-07-01 (ADR-054/055) — `GEN_MODEL_NAME` feeds the separate, Groq-only main `llm` instance. |
| **Root Cause** | Env value appears to have been copied from the HF-router naming convention (used for `judge_llm`/`json_fix_llm`) into a variable consumed by the Groq client, which expects Groq's own model catalog naming. |
| **Solution** | Set `GEN_MODEL_NAME` to a valid Groq model ID. `.env` now sets `GEN_MODEL_NAME=llama-3.1-8b-instant` (the invalid `Qwen/Qwen2.5-7B-Instruct` value is kept as a commented-out line rather than removed). |
| **Date Resolved** | 2026-07-06 (confirmed fixed in `.env`; exact fix date uncertain — `.env` is gitignored and untracked) |

---

### BUG-065 · HF Inference Providers Router Returns HTTP 402 Under Sustained Benchmark Load, Inflating Latency

| Field | Detail |
|---|---|
| **Issue** | Every benchmark run that routed validators/JSON-fix/CAQ through the HF Inference Providers router recorded at least one HTTP 402 response, and the two setups relying on it were markedly slower than the HF-free setup |
| **Found Date** | 2026-07-06 (`Execution Time Comparison.md` benchmark — Setups 1 and 3) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `app_workflow/services/llm_caller.py`, `app_workflow/services/llm_setup.py` (`judge_llm` / `json_fix_llm` on the HF router) |
| **Description** | Across the 3-setup × 3-query × 2-run benchmark, every run that sent validator/JSON-fix/CAQ traffic to the HF Inference Providers router (Setup 1: those roles on HF; Setup 3: those roles on HF, everything else on Groq) logged at least one HTTP 402 in its `Token_Limit` column in `Execution Time Comparison.md`. Setup 1's two complex-query averages (29:38, 31:22) were the slowest of all nine runs across all three setups; Setup 2, which made zero HF-router calls, logged no 402s and was the fastest setup on every query (2:22 avg best-case). See Research topic 46 for the full comparison. |
| **Root Cause** | The HF Inference Providers router's free/shared-tier serving returns `402 Payment Required` once request volume or context size for the selected model exceeds its free quota within a rolling window — a distinct failure mode from the `429` rate-limit path already handled by the `_groq.*`/`openai.*` exception blocks in `llm_caller.py`. It is not yet confirmed whether `_invoke_once()` currently classifies this as a generic `openai.APIStatusError`/`UNKNOWN` fallthrough, nor whether the FIFO-gate retry loop applies a sensible backoff before retrying — a `402` reflects quota exhaustion, not transient capacity, so retrying without a quota-aware wait (or retrying at all within the same window) can burn the retry budget without ever succeeding. |
| **Solution** | Add explicit handling for `openai.APIStatusError` with `status_code == 402` in `_invoke_once()`, classified as a new `LLMErrorKind` (e.g. `QUOTA_EXCEEDED`) rather than folded into `RATE_LIMIT`, since exponential backoff is the wrong remedy for quota exhaustion. Consider a longer fixed cooldown or a circuit-breaker (fail fast to `UNKNOWN` after N consecutive 402s within a run) instead of retrying repeatedly against a router that will not succeed until its quota window resets. |
| **Date Resolved** | — |

---

### BUG-066 · LBC Fabricates Full Paragraphs From Citation-Only Source Fragments — Caught Only By a Length-Ratio Guard, Not Semantic Validation

| Field | Detail |
|---|---|
| **Issue** | Given a short, citation-only source chunk (as little as 77 characters), LBC's compression call repeatedly invents a full, plausible-sounding paragraph of unrelated factual content rather than compressing what's actually present |
| **Found Date** | 2026-07-08 (debug-log audit of `langgraph_api_20260708_124129.debug.log`, pass 2) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `app_workflow/nodes/lbc.py`, `app_workflow/services/prompts.py` (`_LBC_COMPRESS_PROMPT`) |
| **Description** | Observed at least 6 times in a single pass: a 77-character source fragment reading only "...parameter for the assessment and treatment of children and adolescents with autism spectrum disorder [Source:...]" (a bare citation, no substantive content) produced a fabricated 1,366-character `compressed` output inventing a full ASD definition, a "1 in 54 children" prevalence statistic, causes, diagnosis process, treatment options, and disparities — none of which existed in the source. Directly violates the LBC prompt's rule: "Do NOT invent new sentences. Every sentence in your output must come from the original chunk." The same expansion pattern (77→1366, 319→1403, 242→710, 209→935, 152→1466, 285→1196 chars) repeated across the pass. Every instance was neutralized only by the existing over-expansion guard (`context_compression.py`, ADR-017/BUG-004: reject if `len(compressed) > len(original)`), which discards the fabricated output and keeps the tiny original fragment — a correct outcome, but a blunt length heuristic rather than a semantic check, so a same-length-but-still-fabricated compression would pass undetected. `validate_lbc()`, the stage's actual semantic safety judge, never caught any of these — but only because it was itself running as an HTTP-402 fallback (`verdict=UNKNOWN`) for 100% of calls in this pass; see BUG-065. |
| **Root Cause** | `_LBC_COMPRESS_PROMPT` gives the model a citation-fragment chunk with essentially no extractable content and asks it to produce query-relevant compressed text; a task-completion bias appears to make the model synthesize plausible domain content from its own parametric knowledge rather than emit `__IRRELEVANT__` or a near-empty result for a chunk with nothing to extract. |
| **Solution** | Add an explicit low-content escape hatch to `_LBC_COMPRESS_PROMPT`: "If the chunk contains no substantive sentences to extract (e.g. only a citation, heading, or fragment), output `__IRRELEVANT__` rather than generating new content." Since the length guard only catches *expansion*, add a lightweight semantic backstop independent of `validate_lbc()`'s availability — e.g. a cheap keyword/entity-overlap check between compressed output and source text — so fabrication is caught even when compressed length stays under the original. |
| **Date Resolved** | — |

---

### BUG-067 · DC Deletes Sentences Before `validate_redundancy` Can Reject Them — Destructive, Structurally Unrecoverable Redundancy Removal

| Field | Detail |
|---|---|
| **Issue** | DC applies its proposed sentence deletions to chunks immediately, before `validate_redundancy()`'s confirm/reject verdict is available; a rejected group's deletion is never rolled back, so a false-positive redundancy match permanently destroys content |
| **Found Date** | 2026-07-08 (debug-log audit of `langgraph_api_20260707_153607.debug.log`, an all-local run with zero HF-402 interference, isolating this as a genuine model/architecture defect rather than infra noise) |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `app_workflow/nodes/dc.py`, `app_workflow/nodes/validate_redundancy.py`, `app/validators.py` `validate_redundancy()` |
| **Description** | In one DC window, the LLM judged a sentence from the disparities essay — "Recent CDC surveillance data reported that ASD was identified far more often among boys than girls, with prevalence among boys about 3.4 times that among girls" — as redundant with an unrelated, more general sentence in another chunk, and DC deleted it (along with a related underrecognition-of-girls sentence). Confirmed via full-log grep that neither sentence reappears anywhere after the deletion point — permanently lost. `validate_redundancy()` subsequently ran for real (no 402 in this log) and correctly rejected the group, but by then the deletion had already been applied; no code path restores rejected content. The user's query in this run explicitly asked about "associated disparities," making this a direct, user-visible completeness loss in the final answer. A second, independent DC window in the same log proposed 17 similarly nonsensical redundancy pairings (e.g. flagging a definition sentence as a duplicate of a prevalence statistic) — harmless only by coincidence, because the string-replace step found no matching text to remove. Separately, `validate_redundancy` was itself observed to CONFIRM a group that was arguably not a true duplicate, suggesting the judge's own reliability is not a complete backstop even when it does run. |
| **Root Cause** | `validate_redundancy()` is wired as a logging-only, after-the-fact check with no rollback mechanism. DC's own redundancy-matching prompt uses topic/subject similarity rather than requiring bidirectional semantic entailment — the same underlying weakness already tracked as BUG-003, but this session's evidence shows it causing confirmed, irreversible content loss rather than a theoretical risk. |
| **Solution** | Either (a) make DC's deletion conditional on `validate_redundancy`'s verdict — hold the candidate groups, call the validator first, and only delete groups it confirms (inverting the current fire-then-check order), or (b) if pre-validation ordering is architecturally impractical, snapshot the pre-deletion chunk state per group and restore any chunk whose group is later rejected. Raising DC's own confirmation threshold (BUG-003's original recommendation) reduces the frequency of bad candidates but does not close the structural gap on its own. |
| **Date Resolved** | — |

---

### BUG-068 · No Quality Gate After `generate-answer-from-draft` — `check_answer_quality` Validates the Draft, Not the Actual Final Output

| Field | Detail |
|---|---|
| **Issue** | `check_answer_quality` (ANSWER-QUALITY) runs on the pre-synthesis draft; the subsequent `generate-answer-from-draft` synthesis call (BUG-063's fix) can silently drop content relative to the draft with no re-validation of the text actually returned to the user |
| **Found Date** | 2026-07-08 (debug-log audit of `langgraph_api_20260708_124129.debug.log`, pass 2) |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `app_workflow/graph.py`, `app_workflow/nodes/generate_answer.py`, `app_workflow/nodes/check_answer_quality.py` |
| **Description** | In the analyzed run, `check_answer_quality` passed the draft with verdict `GROUNDED, unsupported_claims=0`. The draft addressed 4 of the user's 6 requested subtopics (definition, diagnosis, treatment, disparities) and included a weak placeholder sentence acknowledging the prevalence gap. The subsequent `generate-answer-from-draft` synthesis call (BUG-063 — draft is correctly used as synthesis input rather than returned verbatim) produced a final answer that dropped both "causes" and "prevalence" entirely, including the draft's prevalence-gap disclosure, with no substitute disclosure — despite the generation prompt's own instruction to "state coverage honestly when it is partial or insufficient." Because no validator runs after this synthesis step, the drop was never caught anywhere in the pipeline; the user-visible answer is the least-validated text in the entire run. |
| **Root Cause** | The RETRIEVE→...→DRAFT→JUDGE→SYNTHESIZE node ordering places the only grounding/completeness judge before the last content-altering LLM call — an ordering gap introduced when `generate_answer` was changed (BUG-063, 2026-07-02) from "return draft verbatim" to "synthesize a new answer from the draft," without revisiting the quality-gate's placement. |
| **Solution** | Either move `check_answer_quality` to run after `generate-answer-from-draft` instead of before it, or add a lightweight second pass (e.g. a coverage-diff check comparing topics/claims present in the draft vs. the final synthesized answer) so any subtopic or disclosure dropped during synthesis is caught before the answer ships. |
| **Date Resolved** | — |

---

### BUG-069 · `main.py` CLI Entry Point Never Initialized Phoenix Tracing

| Field | Detail |
|---|---|
| **Issue** | The standalone CLI entry point never called `setup_phoenix_tracing()`, so Phoenix recorded nothing for non-API runs |
| **Found Date** | 2026-07-09 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/main.py` |
| **Description** | Only `api.py` called `setup_phoenix_tracing()` at module load. Running the CLI (`python app_workflow/main.py`) never registered an OpenTelemetry tracer provider, so `opentelemetry.trace.get_current_span().is_recording()` was always `False` for CLI runs and Phoenix received no spans at all, regardless of any other tracing configuration. |
| **Root Cause** | `setup_phoenix_tracing()` was added only to `api.py` when Phoenix instrumentation was first introduced; the CLI entry point was not updated in the same change. |
| **Solution** | Added a `setup_phoenix_tracing()` call to `app_workflow/main.py`, mirroring `api.py`, placed before `setup_logging()`. |
| **Date Resolved** | 2026-07-09 |

---

### BUG-070 · `_TracingHandler` Filtered Out DEBUG-Level Logs Before They Could Reach LangSmith/Phoenix

| Field | Detail |
|---|---|
| **Issue** | The new log-to-trace mirroring handler was set to the console handler's log level (`INFO`), so the majority of node-level `logger.debug(...)` calls never reached either trace backend |
| **Found Date** | 2026-07-09 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `app_workflow/services/logger_config.py` |
| **Description** | `_TracingHandler` (added to mirror `logging` records onto the active LangSmith run / Phoenix span) was set via `tracing_handler.setLevel(console_level)`, and `console_level` defaults to `INFO`. A grep across `app_workflow/nodes/*.py` found 67 of 127 `logger.*` calls are `logger.debug(...)` — the majority of per-node pipeline detail was silently dropped before ever reaching the mirroring handler. |
| **Root Cause** | The tracing handler's level was tied to the console handler's level instead of being independent. DEBUG-level suppression is appropriate for the terminal (to avoid third-party library noise — see `logger_config.py`'s existing `INFO` console level), but not appropriate for the trace-mirroring path, which only mirrors this project's own loggers. |
| **Solution** | `_TracingHandler` now runs at `logging.DEBUG` unconditionally, independent of `console_level`. Console and file handler behavior is unchanged. |
| **Date Resolved** | 2026-07-09 |

---

### BUG-071 · Phoenix Span Lookup via `opentelemetry.trace.get_current_span()` Always Returns a Non-Recording Span

| Field | Detail |
|---|---|
| **Issue** | The standard OTel "current span" lookup always returned a non-recording no-op span under Phoenix's LangChain instrumentation, so no log event was ever attached to a Phoenix span |
| **Found Date** | 2026-07-09 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `app_workflow/services/logger_config.py`, `app_workflow/services/phoenix_tracing.py` |
| **Description** | `_TracingHandler`'s first implementation looked up the "current" Phoenix span via `opentelemetry.trace.get_current_span()`, following standard OTel usage. In every real run (confirmed via temporary `[trace-debug]` print statements added to the handler), this returned `NonRecordingSpan(...)` (`is_recording() == False`) for the entire pipeline, while the equivalent LangSmith lookup (`get_current_run_tree()`) worked correctly for the same call sites in the same run. |
| **Root Cause** | Source inspection of `openinference-instrumentation-langchain`'s `OpenInferenceTracer` (`_tracer.py`) found it never calls `context.attach()` or `tracer.start_as_current_span()` — the calls that would populate OTel's ambient "current span" context var. Instead it stores every span it creates in an internal `self._spans_by_run: Dict[UUID, Span]` dict keyed by LangChain's own `run_id`, exposed only via `OpenInferenceTracer.get_span(run_id)`. This is an undocumented internal implementation detail of the package, confirmed only by reading its source — not a project-introduced defect. |
| **Solution** | `_TracingHandler`'s Phoenix branch now reuses the `run_id` obtained from the (already-working) LangSmith `run_tree` lookup and calls `LangChainInstrumentor()._tracer.get_span(run_id)` to retrieve the matching Phoenix span directly from its internal registry, then calls `.add_event(...)` on it. Verified end-to-end: a `logger.info(...)` call made inside a traced `RunnableLambda` was confirmed to appear in the span's `.events` list. |
| **Date Resolved** | 2026-07-09 |

---

### BUG-072 · LangSmith Web UI Does Not Render Custom Run Events Anywhere (Platform Limitation, Not a Code Defect)

| Field | Detail |
|---|---|
| **Issue** | Log events mirrored onto LangSmith runs via `RunTree.add_event` are fully persisted server-side but never rendered anywhere in the LangSmith web UI on this account/plan |
| **Found Date** | 2026-07-09 |
| **Status** | Closed (worked around; not fixable in this codebase) |
| **Severity** | LOW |
| **File** | N/A (LangSmith hosted UI); mitigated in `app_workflow/services/trace_events.py` |
| **Description** | After confirming `_TracingHandler` successfully attaches log records as events on the active LangSmith run, the events were not visible anywhere in the LangSmith web UI — not on the trace's Feedback/Input/Output tabs, not on a node's "Attributes" tab as expandable JSON, and not as markers on the waterfall timeline. Queried the LangSmith API directly (`Client().read_run(run_id)`) for a real run from a completed trace and confirmed 43 mirrored log events were fully persisted server-side, in order, with full messages — ruling out a code-side bug entirely. |
| **Root Cause** | LangSmith's hosted UI (on this account/plan) has no rendering surface for custom `events` on a run, even though the API/backend accepts and stores them. |
| **Solution** | Not fixable from this codebase. Wrote `app_workflow/services/trace_events.py` as a mitigation — a CLI (`python -m app_workflow.services.trace_events <run_id>`) that resolves a run's `trace_id`, fetches every run in that trace via the LangSmith API, and prints all mirrored log events in chronological order with their originating node name, bypassing the UI gap entirely. |
| **Date Resolved** | 2026-07-09 |

---

### BUG-073 · `trace_events.py` Crashes on Windows Console With `UnicodeEncodeError` on Non-cp1252 Characters

| Field | Detail |
|---|---|
| **Issue** | The new `trace_events.py` CLI crashed partway through printing whenever a mirrored log message contained a character outside Windows' default `cp1252` console encoding |
| **Found Date** | 2026-07-09 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | `app_workflow/services/trace_events.py` |
| **Description** | First real run of the CLI crashed with `UnicodeEncodeError: 'charmap' codec can't encode character '≈'...` — the Windows terminal's default `cp1252` code page cannot render characters such as `≈`, em-dashes, and arrows that appear in mirrored log messages (e.g. compression-stage arrows, approx-symbols in stats output). |
| **Root Cause** | Python's default stdout encoding on Windows is the console code page (`cp1252`), not UTF-8; `print()` raises instead of substituting when a character falls outside that code page. |
| **Solution** | Reconfigured the script's stdout stream to UTF-8 with error-tolerant encoding before printing any event line, so out-of-range characters no longer crash the script. |
| **Date Resolved** | 2026-07-09 |

---

### BUG-074 · Circular Import in `nodes/generate_answer.py` — Mixed Absolute/Relative Import Styles Load `nodes` Package Under Two Identities

| Field | Detail |
|---|---|
| **Issue** | `nodes/generate_answer.py`'s one intra-`nodes` cross-import uses the absolute `app_workflow.nodes.X` form while every other file in the package (and `nodes/__init__.py` itself) uses the bare `nodes.X` form, causing `ImportError: cannot import name 'generate_answer' from partially initialized module 'nodes.generate_answer'` whenever `graph.py`/`main.py` builds the graph |
| **Found Date** | 2026-07-10 |
| **Status** | Closed |
| **Severity** | HIGH — blocks graph construction via `main.py`'s import path; latent risk regardless of entry point |
| **File** | `app_workflow/nodes/generate_answer.py`, `app_workflow/nodes/__init__.py` |
| **Description** | Both `app_workflow/` and the project root sit on `sys.path`, so the `nodes` package can be imported under two distinct module identities: `nodes` (bare) and `app_workflow.nodes` (absolute). `nodes/__init__.py` and every other node file reference sibling modules as `nodes.X`, but `generate_answer.py:10` used `from app_workflow.nodes.check_answer_quality import QUALITY_PASS_VERDICT`. Because `nodes/__init__.py` imports `generate_answer` before `check_answer_quality` in its own import order, the absolute-path import re-enters the still-initializing `nodes` package under its other identity and fails to find `generate_answer` defined yet. Reproduced against unmodified master (`git stash` + rerun) to confirm the defect predated this session's changes — it was latent because `main.py`'s import path triggers it reliably, while `api.py` (run via uvicorn with `app_workflow/` as cwd) happened not to trigger it in this session's testing. |
| **Root Cause** | Mixed absolute (`app_workflow.nodes.X`) vs. bare-package (`nodes.X`) import styles for the one intra-`nodes` cross-reference in the codebase, causing the `nodes` package to load under two distinct module identities depending on import order. |
| **Solution** | Changed `generate_answer.py:10` to `from nodes.check_answer_quality import QUALITY_PASS_VERDICT`, matching the style used by every other file in the package. |
| **Date Resolved** | 2026-07-10 |

---

### BUG-075 · Langfuse `CallbackHandler` Was a No-Op — `config` Never Reached Any LLM Call

| Field | Detail |
|---|---|
| **Issue** | Passing `config={"callbacks": [langfuse_handler]}` to `rag_app.invoke(...)` produced zero Langfuse traces — the callback never reached any actual LLM call anywhere in the graph |
| **Found Date** | 2026-07-10 |
| **Status** | Closed |
| **Severity** | HIGH — Langfuse tracing was silently a complete no-op; the pipeline ran and answered normally with no errors, masking the failure |
| **File** | `app_workflow/services/llm_caller.py` (root fix), plus ~10 files at ~40 call sites: `services/fix_llm_output.py`, `services/validators.py`, `services/self_learner.py`, and node files `query_variants.py`, `check_answer_quality.py`, `generate_answer.py`, `generate_draft.py`, `dc.py`, `lbc.py`, `nac.py`, `validate_retrieval.py`, `dedup_merge.py`, `auto_distillation.py`, `commands.py` |
| **Description** | Unlike LangSmith (env-var ambient tracing) and Phoenix (OTel auto-instrumentation patched globally at import time), Langfuse's `langchain.CallbackHandler` requires the LangChain callbacks list to actually reach each `.invoke()` call. LangGraph only auto-injects `config` into a node function if that function's signature declares a `config` parameter; none of the project's ~14 node functions did. Even had that been fixed, `services/llm_caller.py`'s `llm_invoke()`/`_invoke_once()` never accepted or forwarded a `config` argument to `llm.invoke(...)`, and `_invoke_once()`'s `ThreadPoolExecutor`-wrapped `future.result(...)` call would have broken ambient contextvar-based propagation regardless of node-level wiring — confirmed by direct inspection that a plain `BaseCallbackHandler` passed the same way also failed to receive events. |
| **Root Cause** | The project's node functions and `llm_invoke()`/`_invoke_once()` were written before any callback-based (as opposed to ambient) tracing backend was in use, so no code path existed to carry an explicit `config`/`callbacks` object from the top-level `.invoke()` call down to the actual `llm.invoke(...)` calls nested several layers deep across nodes, validators, and repair functions. |
| **Solution** | Added an optional `config` parameter (type `RunnableConfig`) to every node function's signature and threaded it into the corresponding service-layer calls; updated `llm_caller.py`'s `llm_invoke()`/`_invoke_once()` to accept `config` and forward it explicitly as `llm.invoke(messages, config=config, **kwargs)`. Verified end-to-end: a live query produced a full Langfuse trace with populated `GENERATION` observations (model name, input/output, token usage) for every LLM call in the graph, confirmed via Langfuse's REST API (`/api/public/observations?type=GENERATION`). |
| **Date Resolved** | 2026-07-10 |

---

### BUG-076 · Langfuse Silently Evicts Phoenix's Span Exporter From the Shared Global `TracerProvider`

| Field | Detail |
|---|---|
| **Issue** | Initializing Langfuse's `CallbackHandler` while Phoenix's OTel tracer provider is already the process-global default silently removes Phoenix's span exporter from that shared `TracerProvider`; once Langfuse is active, Phoenix receives zero further spans regardless of `ENABLE_PHOENIX_TRACING` |
| **Found Date** | 2026-07-10 |
| **Status** | Open — root cause fully diagnosed and a fix verified against isolated throwaway scripts driving the real `build_graph()` pipeline; not yet applied to `phoenix_tracing.py`/`langfuse_tracing.py`, per explicit instruction to research and plan only this round |
| **Severity** | HIGH — defeats the "Phoenix primary, run in parallel" intent of ADR-063 the moment Langfuse is also enabled; the two backends are not actually independent when both `ENABLE_PHOENIX_TRACING` and `ENABLE_LANGFUSE_TRACING` are on |
| **File** | `app_workflow/services/phoenix_tracing.py`, `app_workflow/services/langfuse_tracing.py` |
| **Description** | `phoenix.otel.register()` installs a `SimpleSpanProcessor` on the process's global `TracerProvider` and flags it internally as a replaceable "default" processor (`_default_processor = True`; Phoenix's own startup log warns "Using a default SpanProcessor. `add_span_processor` will overwrite this default."). Langfuse's SDK (v3+, installed 4.13.2) is itself OTel-native: `get_langfuse_handler()` → `CallbackHandler()` → `_client/resource_manager.py`'s `_init_tracer_provider()` detects the existing global `TracerProvider` (Phoenix's) and correctly reuses it rather than creating a separate one, then calls `tracer_provider.add_span_processor(langfuse_processor)` on it. Because that provider is Phoenix's `phoenix.otel.otel.TracerProvider` subclass, `add_span_processor()` is overridden to check `self._default_processor`; since it is still `True`, the override calls `self._active_span_processor.shutdown()`, empties `_span_processors`, and only then appends the Langfuse processor — deleting Phoenix's exporter as a side effect of Langfuse politely trying to share the existing provider. Confirmed directly by inspecting the live processor list before/after `get_langfuse_handler()`: `(<phoenix.otel.otel.SimpleSpanProcessor ...>,)` → `(<langfuse._client.span_processor.LangfuseSpanProcessor ...>,)`. No exception is raised anywhere in this chain — `/query` requests and the graph itself run normally, so the failure is invisible without inspecting OTel internals directly. |
| **Root Cause** | Phoenix's `TracerProvider.add_span_processor()` override treats its own installed processor as disposable ("default", safe to replace) the first time any other library calls `add_span_processor()` on the shared global provider; Langfuse's SDK calls exactly that method as part of its normal (and otherwise correct) "reuse the existing global provider" behavior. |
| **Solution** | Verified but not applied: keep Phoenix off the global provider slot and pass it explicitly to the LangChain instrumentor instead of relying on provider-sharing — `register(project_name=..., endpoint=..., set_global_tracer_provider=False)` followed by `LangChainInstrumentor().instrument(tracer_provider=tp)`. With `set_global_tracer_provider=False`, `opentelemetry.trace.get_tracer_provider()` returns a `ProxyTracerProvider` rather than Phoenix's real provider, so when Langfuse's `_init_tracer_provider()` looks for an existing global provider it finds none and creates its own separate one instead of touching Phoenix's, eliminating the eviction path entirely. Verified end-to-end against the real `build_graph()` pipeline with a live Langfuse callback attached: both Phoenix (confirmed via Phoenix's REST API) and Langfuse received their expected spans from the same run. |
| **Date Resolved** | — |
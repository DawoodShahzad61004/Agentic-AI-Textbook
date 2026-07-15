## System Overview

The project is a **Self-Learning Agentic RAG Pipeline** — a retrieval-augmented generation system where an LLM acts as an autonomous agent, dynamically deciding when and how to retrieve, compress, validate, and answer, with a feedback loop that writes distilled knowledge back into the vector store over time.

The system began as a classic single-pass RAG (embed → retrieve → answer) and was iteratively evolved into a stateful, multi-phase agentic loop with context compression, multi-role LLM coordination, and a thumbdown-driven self-correction mechanism.

---

## High-Level Architecture

```
User Query
    │
    ▼
agent_query.py  ◄──────────────────────────────────────┐
    │  (orchestrator — drives state machine)            │
    │                                                   │
    ▼  PHASE 1: RETRIEVE  (two independent tracks)      │
tools.py → retrieve_documents()                         │
    │  → EmbeddingManager (all-MiniLM-L6-v2, CUDA)     │
    │  → RAGRetriever.retrieve_separate()               │
    │      ├── collection: "documents"   top_k=K        │
    │      └── collection: "learned_qa"  top_l=L        │
    │      (no cross-collection ranking, dedup, or merge)│
    │  → validators.py → validate_retrieval() per track │
    │  ← accumulated_document_chunks[]                  │
    │  ← accumulated_learned_qa_chunks[]                │
    │                                                   │
    ▼  PHASE 2: COMPRESS (per-track, gated at 500 tok)  │
tools.py → compress_context()                           │
    │  → context_compression.py (runs twice)           │
    │      ├── NAC  (Neighbor-Adjacent Compression)     │
    │      │     cosine-sim dedup at threshold 0.90     │
    │      │     → _merge_similar_chunks()              │
    │      │     → validate_merge() [judge_llm]         │
    │      ├── DC   (Deduplication Compression)         │
    │      │     sliding window = 3, LLM redundancy scan│
    │      │     → validate_redundancy() [judge_llm]    │
    │      └── LBC  (LLM-Based Compression)             │
    │            per-chunk compression + expansion guard│
    │            + over-compression guard               │
    │            → validate_lbc() [judge_llm]           │
    │                                                   │
    ▼  PHASE 3: DRAFT                                   │
    │  LLM called with tools=None (free-form prose)     │
    │  context = format_precedence_context_for_llm(     │
    │     learned_qa_chunks, document_chunks)           │
    │  → [LEARNED QA - HIGH PRIORITY] first,            │
    │    [DOCUMENT - SECONDARY] second,                 │
    │    [CONFLICT RESOLUTION RULE] header prepended    │
    │                                                   │
    ▼  PHASE 4: JUDGE                                   │
    │  check_answer_quality(answer, context, query)     │
    │  → judge_llm  (temperature=0.0)                   │
    │  ├── OK  → return final answer                    │
    └── INSUFFICIENT + budget → loop back ──────────────┘
          (inject failure reason, reset compress_done)

    ▼  POST-ANSWER
FeedbackStore.log()  →  MongoDB feedback_interactions
SelfLearner.should_learn()
    └── every N=5 good interactions → run_distillation()
            → learned_qa collection (ChromaDB)
```

---

## Module Breakdown

### `agent_query.py`
The central orchestrator. Manages the four-phase state machine (RETRIEVE → COMPRESS → DRAFT → JUDGE), enforces protocol ordering (compress must precede check_answer_quality), handles the user interaction loop, injects thumbdown history into the system prompt, tracks failed variants, and triggers self-learning distillation after every 5 successful interactions. Contains `run_agent()` and the `main()` CLI loop.

State is now maintained as two parallel tracks: `agent_state["accumulated_document_chunks"]` and `agent_state["accumulated_learned_qa_chunks"]`. The old single `accumulated_chunks` key is gone. Track-local helpers `_validate_track()`, `_accumulate_track()`, and `_compress_track()` run the same per-track pipeline twice — once for documents, once for learned QA — without any cross-track ranking, dedup, or merging. The two tracks are combined only at the LLM context boundary via `format_precedence_context_for_llm()`. Result-return paths (`_last_retrieval_fields()`) project from accumulated state, not from the retriever's `get_last_*` getters, so the answer's evidence reflects what survived validation/compression rather than the last raw retrieval call.

Key constants: `MAX_ITERATIONS = 6`, `MAX_TOTAL_RETRIEVALS = 5`, `MAX_TOOL_CALLS_PER_ITERATION = 7`, `LEARN_EVERY_N = 5`.

Early compress transition fires after the first successful retrieval (`total_retrievals >= 1`) rather than waiting for the LLM's full planned query set — a deliberate latency/token trade-off.

### `tools.py`
Defines the two agent-callable tools as LangChain-style function schemas plus their Python implementations:

- `retrieve_documents(query)` — calls `retriever.retrieve_separate()`, which queries the `documents` and `learned_qa` Chroma collections independently at `RETRIEVAL_TOP_K` and `RETRIEVAL_TOP_L` respectively. The two ranked lists are returned as separate keys and never merged. The tool serializes both into a single string response with explicit `[LEARNED QA RESULTS - HIGH PRIORITY]` and `[DOCUMENT RESULTS - SECONDARY]` section labels so the LLM can read both without losing the track distinction. The `top_k` parameter was removed from the tool schema in 2026-06-11 — the model can no longer override retrieval depth at runtime.
- `compress_context()` — reads `accumulated_document_chunks` and `accumulated_learned_qa_chunks` from `agent_state`, runs `_compress_track()` on each independently (each track checks its own `COMPRESS_MIN_TOKENS` gate before running NAC → DC → LBC), scrubs prior raw `retrieve_documents` tool-result messages from the conversation history (replaces with placeholder to keep context window lean), and writes the compressed per-track lists back to state.

Also contains `make_check_answer_quality()` which returns a direct Python callable (not an LLM tool) used as the judge gate.

### `context_compression.py`
Houses all three compression stages and the shared chunk-merge service. `_merge_similar_chunks()` is used by both retrieval deduplication and NAC compression, so merge behavior is now treated as shared infrastructure rather than compression-only helper logic. Named `context_compression.py` (not `compression.py`) to avoid collision with Python 3.14's stdlib `compression` package.

- **NAC**: pairwise cosine similarity scan, threshold 0.90. Merges similar adjacent chunks via `_merge_similar_chunks()` which calls `merge_llm` and retries up to `LLM_RESPONSE_RETRY_LIMIT` times. Merge output is JSON-validated by `validate_merge()`.
- **DC**: sliding window of 3 chunks, LLM-based redundancy grouping scan. Degenerate groups collapsed to the keeper chunk.
- **LBC**: per-chunk extraction/compression. Has both an over-compression guard (rejects output < 30% of original) and an over-expansion guard (rejects output > original length). Validated by `validate_lbc()`.
- Token-budget gate at 500 tokens: entire NAC → DC → LBC pipeline is skipped below this threshold. The gate is applied per track, so a 700-token document track and a 200-token learned-QA track run compression independently — the document track runs the pipeline, the learned-QA track is passed through unchanged.

Exposes `format_precedence_context_for_llm(learned_qa_chunks, document_chunks)` — the single point where the two tracks are combined into an LLM-consumable string. The output is structured as three labeled sections in fixed order: `[CONFLICT RESOLUTION RULE]` (an explicit instruction to prefer learned QA on conflict), `[LEARNED QA CONTEXT - HIGH PRIORITY]`, then `[DOCUMENT CONTEXT - SECONDARY]`. Empty tracks are omitted. This function is used by both the DRAFT and JUDGE phases.

### `retriever.py`
`RAGRetriever` wraps the vector store, the embedding manager, and the canonical learned-QA collection handle returned by `learned_qa_store.get_or_create_learned_qa_collection()`. Two retrieval entry points are exposed:

- `retrieve(query, top_k=RETRIEVAL_TOP_K, score_threshold)` — documents-only path. Used by callers that don't need the split (e.g. the standalone `query.py` CLI). The learned-QA last-state is explicitly reset to empty so downstream callers cannot accidentally consume stale learned-QA chunks from a previous query.
- `retrieve_separate(query, top_k=RETRIEVAL_TOP_K, top_l=RETRIEVAL_TOP_L, score_threshold)` — two-track path used by the agent. Embeds the query once via `EmbeddingManager`, queries the `documents` collection at `top_k` and the `learned_qa` collection at `top_l`, ranks and threshold-filters each list independently, and returns `{"documents": [...], "learned_qa": [...]}`. No cross-collection sort, no cross-collection dedup, no merging.

Last-retrieval state is exposed via the per-track getters `get_last_document_chunks()` and `get_last_learned_qa_chunks()`. The single mixed `get_last_chunks()` getter has been removed from all active code paths.
`_query_collection()` wraps the ChromaDB `.query()` call in a `ThreadPoolExecutor` thread with a `RETRIEVAL_TIMEOUT_SECONDS` deadline. On timeout, `RetrievalTimeoutError` is raised and caught within the method, returning `[]` so the calling pipeline continues without that collection's results. Collection name and query duration are logged at DEBUG before and after each call.

### `embedding_manager.py`
Loads `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional embeddings) onto CUDA (RTX 5050 Laptop GPU) or CPU as available. Exposes `generate_embedding(text)` used both during ingestion and at query time. Embedding dimension is 384.
`generate_embedding()` wraps `model.encode()` in a `ThreadPoolExecutor` thread with an `EMBEDDING_ENCODING_TIMEOUT_SECONDS` deadline. On timeout, `EmbeddingEncodingTimeoutError` is raised and re-raised to the caller — there is no meaningful embedding fallback. Model name and encode duration are logged at DEBUG.

### `vector_store.py`
`VectorStore` wraps ChromaDB `PersistentClient`. Manages two collections: `documents` (source material) and `learned_qa` (distilled Q&A from self-learning). Bulk-insert path (`add_documents_in_batches`) embeds all texts in one GPU pass then performs a single ChromaDB write — avoids per-batch write overhead that dominated earlier iterations.

### `ingest.py`
Discovers files across `../data/pdfs`, `../data/textfiles`, `../data/csv`, `../data/` directories. Routing by extension: `.pdf/.txt/.doc/.docx/.html/.htm` → `UnstructuredLoader`; `.csv/.xls/.xlsx` → pandas → JSON → `JSONLoader`; `.json` → `JSONLoader` with `jq_schema="."`. Splits via `RecursiveCharacterTextSplitter` (`chunk_size=1000`, `chunk_overlap=200`), embeds, and stores in batches of 512. Current corpus: **1,181 chunks**.

### `validators.py`
Four independent judge functions, all using `llm_invoke()` with `judge_llm` (temperature=0.0, max_tokens=1024):

- `validate_retrieval()` — checks chunk relevance to query.
- `validate_merge()` — faithfulness check: no fabricated claims, no dropped facts. Uses paired GOOD/BAD examples inline to anchor paraphrase reasoning.
- `validate_redundancy()` — confirms whether two chunks are genuinely redundant vs. same-domain-different-fact.
- `validate_lbc()` — checks that LBC compression preserved all key facts without hallucination.

All validators now support two structured-output paths:

- Repair path: `fix_llm_output("<schema_tag>", raw, llm=...)` when global and stage-specific output-fix flags are enabled.
- Fallback path: `_parse_to_python(raw)` when output repair is disabled.

This separates malformed-output repair from normal JSON parsing, allowing output repair to be ablated without breaking downstream validator contracts.

### `llm_caller.py`
Thin wrapper around LangChain `ChatOpenAI` that routes to Groq's OpenAI-compatible API endpoint. Returns typed `LLMResult` objects with `ok`, `content`, `error_kind` (`LLMErrorKind` enum), and `error_message`. Handles rate-limit, server error, connection, and timeout retries. Contains `llm_invoke()` used by all compression and validation paths.

Rate-limit handling (see ADR-044) uses a **FIFO serialization gate** in place of the prior random-jitter exponential backoff. Three module-level globals maintain gate state: `_llm_queue` (`queue.Queue[threading.Event]`), `_llm_gate_lock` (`threading.Lock`), `_llm_active` (`bool`). `_gate_acquire(caller_tag)` takes the gate immediately if idle, or enqueues a `threading.Event` and blocks on `.wait()`. `_gate_release_to_next()` pops the oldest waiter and calls `.set()` to wake it, or marks the gate free. Only the thread holding the gate may call Groq at any given time.

A thread that receives a 429 does NOT release the gate — it holds it, sleeps the full token-reset window derived from Groq response headers via `_groq_wait_seconds()` (`x-ratelimit-reset-tokens` → `x-ratelimit-reset-requests` → `retry-after`) and `_parse_groq_duration()` (Go-style duration parser for strings like `"1m30s"`, `"7.66s"`, `"500ms"`), then retries directly. `_token_reset_until` (monotonic float) stores the reset deadline written by any 429-receiving thread so the wait is paid exactly once per exhaustion event. After a successful call, `_apply_cooldown()` sleeps a `_cooldown_floor` (derived from `x-ratelimit-remaining-tokens`) when the queue is non-empty, then releases the gate. The floor doubles on 429-recovery, halves after 3 clean successes (`_clean_success_streak`), and resets to 0 when the queue empties; `MIN_COOLDOWN_TIME` / `MAX_COOLDOWN_TIME` bound it. `LLM_RATE_LIMIT_BACKOFF_JITTER_SECONDS` removed — unnecessary with a single-caller gate. If the computed delay would exceed `LLM_RATE_LIMIT_MAX_DELAY_SECONDS`, `llm_invoke()` raises `LLMRateLimitAbortError(delay)`.

`_invoke_once()` handles `httpx.HTTPStatusError` (429 → `RATE_LIMIT`, 5xx → `SERVER_ERROR`, other → `UNKNOWN`) and `httpx.ConnectError` (→ `CONNECTION`), and wraps `llm.invoke()` in a `ThreadPoolExecutor` thread enforced by `future.result(timeout=LLM_RESPONSE_TIMEOUT_SECONDS)`. On timeout, returns `LLMResult(ok=False, error_kind=TIMEOUT)` so the retry loop handles it uniformly. DEBUG logging records each attempt's wall-clock duration and total rate-limit sleep per `llm_invoke()` call, tagged with `caller_tag`.

### `db.py`
MongoDB client module shared by `feedback_store.py` and `api.py`. Lazy singleton `_client: MongoClient | None = None` initialised on first call to `get_client()` (reads `MONGODB_URI` and `MONGODB_DB_NAME` from env). `_ensure_indexes()` is guarded by a module-level `_indexes_ensured` flag so index creation runs once per process regardless of how many times a collection accessor is called. Indexes: `ts` ascending and `request_id` unique (non-sparse) on `feedback_interactions`; `normalized_query` ascending on `user_thumbdowns`; `normalized_query` unique on `failed_variants`. Three public accessors: `interactions_col()`, `thumbdowns_col()`, `failed_variants_col()` — each calls `_ensure_indexes()` before returning the collection handle.

### `feedback_store.py`
`FeedbackStore` writes every interaction to the MongoDB `feedback_interactions` collection via `interactions_col().insert_one(record)`. The record stores `ts`, `request_id`, `query`, `answer`, `quality`, `sources`, `document_chunks`, `learned_qa_chunks`, and `variants` (the list of query variants tried during the run, stored at log time so `/feedback/bad` can retrieve them later without in-memory state). `insert_one` is wrapped in `try/except DuplicateKeyError` to make `log()` idempotent — LangGraph's retry infrastructure can call `generate_answer` more than once per graph invocation with the same `request_id`.

`mark_last_bad()` and `mark_bad(request_id)` both open a MongoDB session and wrap their two writes in `session.start_transaction()` — the `update_one` (marks the interaction `USER_THUMBSDOWN`) and the `_append_thumbdown` `insert_one` (writes to `user_thumbdowns`) either both commit or both roll back. `_append_thumbdown` accepts an optional `session=` parameter to participate in the caller's transaction. `mark_bad(request_id)` is the primary path used by `app/api.py`'s `/feedback/bad` endpoint: it looks up the interaction by `request_id` from MongoDB rather than relying on in-memory last-result state.

Backward compatibility: older interaction records that wrote a single mixed `chunks` field are split by `source` at read time so downstream consumers (self-learning, thumbdown replay) see the same per-track contract regardless of record vintage. The legacy splitter is a known weak spot when a chunk's `source` was concatenated by a merge step (e.g. `"learned_qa, learned_qa"`) — see `Bugs.md` BUG-036.

### `self_learner.py`
`SelfLearner` distills high-quality Q&A pairs from `interactions.jsonl` back into the `learned_qa` ChromaDB collection. Triggered every `LEARN_EVERY_N` successful interactions, gated by `ENABLE_AUTO_DISTILLATION`. Uses an LLM to synthesize 1–3 semantically distinct question-answer rephrasings per interaction. Rephrasings are embedded and stored so the retriever surfaces them on future similar queries.

Reads both per-track lists separately from each interaction record. The distillation prompt now explicitly labels learned-QA chunks as high priority when both tracks are present, so distilled pairs preserve the answer's actual evidence hierarchy. The `learned_qa` collection is obtained through the shared `learned_qa_store.get_or_create_learned_qa_collection()` factory, which guarantees cosine distance regardless of how an older persisted collection was originally created.

Self-learning stat display now shows separate document and learned-QA chunk counts during distillation runs.

### `learned_qa_store.py`
Canonical factory for the `learned_qa` Chroma collection. Exposes `get_or_create_learned_qa_collection(client, collection_name, batch_size)` which guarantees the returned collection uses `hnsw:space = cosine`. The flow is:

1. Try `client.get_collection(name)`. If it doesn't exist, create it fresh with the canonical `LEARNED_QA_METADATA = {"description": "...", "hnsw:space": "cosine"}` and return it.
2. If it exists and is already cosine, return it as-is.
3. Otherwise migrate: snapshot every record (`ids`, `embeddings`, `metadatas`, `documents`) in `batch_size` pages; rename the original collection to a UUID-suffixed `<name>__distance_backup_<hex>` so the canonical name is free; create a new collection at the canonical name with cosine metadata; restore the snapshot in batches; verify `replacement.count() == len(records)`; delete the backup.
4. If migration raises at any point, delete the partial replacement (if it exists), rename the backup back to the canonical name, and re-raise. The original collection is never destroyed before the new one is fully restored and count-verified.

Used by both `agent_query.py` (during startup) and `self_learner.py` (when accessing the learned-QA collection for distillation upserts), so the two code paths share one collection handle and there is no "L2 created first, cosine requested later" race. Live production migration: 374 entries successfully moved L2 → cosine with all IDs preserved.

### `run_batch.py`
Test harness. Monkey-patches `sys.stdin` to feed scripted query sequences into `agent_query.main()`, enabling reproducible multi-query session testing without a live terminal.

### `fix_llm_output.py`
Production repair + validation layer that sits between every LLM call and its downstream consumer. All structured LLM outputs in the pipeline pass through this module before being used.

Implements a 5-stage tiered pipeline — each stage is a progressively more expensive fallback, so the common path (well-formed JSON) pays no LLM cost:

1. **Preprocessing** — strips code fences, blockquotes, function-call wrappers (`submit_answer({...})`), JS/Python comments, and Python literals (`True`/`False`/`None`/`NaN`). Uses a string-aware state machine so it never corrupts content inside quoted values. Also handles escaped stringified JSON (case: LLM double-encodes its output).
2. **Balanced extraction + `json.loads`** — string-state-aware bracket depth counter extracts the first top-level `{...}` or `[...]`; handles `[Source: foo.pdf]` citation tags inside strings without false-counting brackets.
3. **`json_repair`** — `repair_json(return_objects=True)` handles truncation, trailing commas, missing commas, single quotes, unquoted keys, and unbalanced brackets. Gracefully absent if package not installed.
4. **`_LLM_Json_Repair()`** — last-resort LLM call using `_JSON_REPAIR_PROMPT` with the schema injected via `model.model_json_schema()`. Invoked only when all heuristic stages fail (XML, YAML, dataclass syntax, PascalCase key remapping). Auto-instantiates `ChatGroq(llama-3.1-8b-instant, temperature=0.0)` if no LLM is passed. Logs all I/O to `run_logs/llm_json_tries.txt`.
5. **Pydantic validation + `_Verify_And_Correct()`** — schema enforcement with coercive `mode="before"` validators; followed by a dedicated value-verification LLM pass that checks whether extracted values actually match the raw text. Logs all I/O to `run_logs/llm_data_check.txt`.

Exposes a `_SCHEMA_REGISTRY` mapping 8 string tags to `(PydanticModel, top_level)` pairs covering all structured outputs in the project: `merge`, `merge_judge`, `retrieval_judge`, `lbc_compress`, `lbc_judge`, `dc_scan`, `redundancy_judge`, `distill_qa`.

Public API: `fix_llm_output(expected_output, raw_response, correct=False, llm=None) → (object, bool)`.

### `config.py`
Single source of truth for all pipeline constants and feature toggles. Holds path constants (`VECTOR_STORE_PATH`, `FEEDBACK_PATH`, `USER_THUMBDOWNS_PATH`, `FAILED_VARIANTS_PATH`, `SEARCH_ROOTS`, `JSON_DIR`), iteration/budget constants (`MAX_ITERATIONS`, `MAX_TOOL_CALLS_PER_ITERATION`, `MAX_TOTAL_RETRIEVALS`, `LEARN_EVERY_N`), retrieval depth constants (`RETRIEVAL_TOP_K` for documents, `RETRIEVAL_TOP_L` for learned QA — both configurable via env vars, both consumed by `RAGRetriever.retrieve_separate()` and the `retrieve_documents` tool), compression thresholds (`COMPRESS_MIN_TOKENS`, `MERGE_SIMILARITY_THRESHOLD`, `LBC_MIN_RETENTION_RATIO`, `DC_WINDOW_SIZE`), retry/IO constants (`LLM_RESPONSE_RETRY_LIMIT`, `LLM_RATE_LIMIT_MAX_ATTEMPTS`, `LLM_RATE_LIMIT_BACKOFF_*`, `LLM_RATE_LIMIT_MAX_DELAY_SECONDS`, `_JSON_REPAIR_TRIES`, `BATCH_SIZE`, `MIN_CHUNK_CHARS`, `MIN_SIMILARITY`, `MIN_ANSWER_LENGTH`, `MIN_FEEDBACK_LEN`), and chunking parameters (`CHUNK_SIZE`, `CHUNK_OVERLAP`).

Also exposes 18 boolean feature flags that gate optional pipeline stages: `ENABLE_SUB_QUERY_GENERATION`, `ENABLE_RETRIEVAL_DEDUP_MERGE` (+ its `_OUTPUT_FIX` and `_VALIDATION` + the validation's `_OUTPUT_FIX`), `ENABLE_RETRIEVAL_VALIDATION` (+ `_OUTPUT_FIX`), `ENABLE_NAC_COMPRESSION`, `ENABLE_DC_COMPRESSION`, `ENABLE_LBC_COMPRESSION`, `ENABLE_COMPRESSION_VALIDATION` (+ `_OUTPUT_FIX`), `ENABLE_ANSWER_DRAFT_CREATION`, `ENABLE_ANSWER_QUALITY_CHECK`, `ENABLE_AUTO_DISTILLATION`, `ENABLE_QA_PAIR_GENERATION` (+ `_OUTPUT_FIX`), and a master `ENABLE_GLOBAL_LLM_OUTPUT_FIX`. Every gateable stage in `agent_query.py`, `validators.py`, `context_compression.py`, and `self_learner.py` imports its flag from here. The flags exist to support ablation testing via `run_combinations.py`.

### `prompts.py`
Single source of truth for every long prompt string in the project. Holds `_CHUNK_MERGE_PROMPT` (NAC merge), `_DC_SCAN_PROMPT` (DC sliding-window scan), `_REDUNDANCY_JUDGE_PROMPT`, `_LBC_COMPRESS_PROMPT`, `_LBC_JUDGE_PROMPT`, `_MERGE_JUDGE_PROMPT`, `_RETRIEVAL_JUDGE_PROMPT`, the distillation prompt for `self_learner.py`, the agent role/process system-prompt halves (`_ROLE_AND_RULES`, `_PROCESS_INSTRUCTIONS`), and the `_THIN` / `_THICK` separator strings used by every module for log formatting. Centralising prompts here lets the prompts be revised in one place without grepping the whole tree.

### `api.py`
FastAPI HTTP server that exposes the classic agentic RAG pipeline over HTTP. Runs on port 8000 (`uvicorn api:app --host 0.0.0.0 --port 8000`). All pipeline objects (embedding manager, vector store, retriever, three `ChatGroq` instances, tools, feedback store, self-learner) are initialised once during `lifespan` startup and stored in a process-global `_ctx` dict. Blocking pipeline work runs in a thread via `asyncio.to_thread`. Each incoming request is assigned a `uuid4` `request_id` which is set via `set_request_id()` (injected into every log record by `_RequestIdFilter`) and passed through to `run_agent()` and `FeedbackStore.log()`. Concurrent `/query` serialization is delegated to `llm_invoke()`'s FIFO gate rather than a handler-level lock (prior `asyncio.Lock` block removed).

Endpoints:
- `POST /query` — runs `run_agent()` with blocked-variant and thumbdown injection; persists feedback; triggers auto-distillation if `ENABLE_AUTO_DISTILLATION` is on and `should_learn()` returns true. Returns `answer`, `quality`, `sources`, `document_chunks`, `learned_qa_chunks`.
- `POST /feedback/bad` — calls `feedback_store.mark_bad(request_id, feedback)` where `request_id` is a required field in the request body. Looks up the interaction by `request_id` in MongoDB; no longer requires the call to be made immediately after `/query`. Returns `{status, persisted}`.
- `GET /stats` — returns `{total_interactions, successful, learned_qa_pairs, auto_distillation_enabled, learn_every_n}`.
- `POST /learn` — triggers `self_learner.run_distillation()` on-demand. Returns `{added_qa_pairs}`.
- `POST /quit` — sends `SIGTERM` to the process for clean uvicorn shutdown. Returns `{status: "shutting down"}`.

`LLMRateLimitAbortError` is caught at the `/query` handler and surfaced as HTTP 429 with a `Retry-After: N` header (where N is the required wait in seconds).

### `run_combinations.py`
Progressive flag-ladder ablation harness. Generates 10 combos forming an evenly-spaced ladder from all-18-flags-OFF (step 0) to all-ON (step 9) using fixed left-to-right `BOOL_FLAGS` order — deterministic and reproducible, not random. Each combo is applied by regex-patching `config.py` in-place; the subprocess runs `agent_query.py` with the test query piped through stdin (`PYTHONUTF8=1` set so Windows stdout handles the box-drawing chars); stdout + stderr are captured and `config.py` is restored in a `finally`. One timestamped log per run is written to `app/run_logs/run_NNN_<ts>.txt`. Used to measure per-stage contribution to answer quality and total latency.

### `logger_config.py`
Central logging configuration. Exposes a single `setup_logging(log_dir, app_name, console_level)` function — the only place the project configures Python's `logging` module. The function is idempotent via a `_CONFIGURED_ATTR` flag on the root logger so calls from multiple entry points (`agent_query.py`, `ingest.py`, `run_batch.py`, `query.py`, `test_output_fixes.py`, `test_llm_caller.py`, `run_combinations.py`, top-level `main.py`) are safe.

Per-request tracing: `_request_id_var: ContextVar[str]` holds the current request ID (default `"-"`). `set_request_id(id)` and `get_request_id()` are the public accessors. `_RequestIdFilter(logging.Filter)` injects `record.request_id = _request_id_var.get()` into every log record before it is formatted; the filter is attached to both the console handler and the debug file handler. Console and file format strings updated to include `[%(request_id)s]` between log level and message.

Current configuration:

- **Console handler** at `logging.INFO` — INFO, WARNING, ERROR, CRITICAL are visible at the terminal; DEBUG is hidden to avoid third-party flood from `httpcore`, `httpx`, and `groq._base_client`.
- **Per-run debug file handler** at `logging.DEBUG`, writing to `run_logs/{app_name}_{YYYYMMDD_HHMMSS}.debug.log` — every level (including DEBUG and the full third-party trace) is captured for post-hoc inspection. The timestamp is captured at `setup_logging()` call time, so each run gets its own file rather than appending to a shared one.
- **No separate `.error.log` file** — errors are visible on console at ERROR level *and* captured in the per-run debug file. The original dual-file split (debug + error) was dropped after observing that it doubled the log-management surface area for no extra signal beyond what the timestamped debug file already provided.
- **Diagnostic loggers** `llm_data_check` and `llm_json_tries` (consumed by `fix_llm_output.py` to record `_Verify_And_Correct` and `_LLM_Json_Repair` payloads) have `propagate=True`, so their records reach both the console at their effective level and the timestamped debug file at DEBUG. The previous direct `open("run_logs/llm_data_check.txt", "a")` / `..._llm_json_tries.txt..., _f.write(...)` blocks in `fix_llm_output.py` were replaced with `llm_data_check_logger.debug(...)` and `llm_json_tries_logger.debug(...)` calls on these named loggers.

A custom `_DynamicStdoutHandler(logging.StreamHandler)` re-points `self.stream` to `sys.stdout` at emit time so batch-run tee/redirect setups (where `sys.stdout` is reassigned mid-process) still see console logs.

Every project module does `logger = logging.getLogger(__name__)` at module scope, giving each log line an automatic module-name attribution. The ~370 pre-migration `print()` calls across the pipeline are now `logger.debug/info/warning/error` calls; `print()` is preserved only for interactive REPL prompts, the batch-run progress UI, the test-console formatter, and JSON/JSONL data writes (feedback log, failed-variants store, thumbdown store, test transcripts) where the file is application data, not a log.

---

## Data Flow: Ingestion

```
Files (PDF, TXT, DOCX, HTML, CSV, JSON)
    │
    ▼  ingest.py
UnstructuredLoader / JSONLoader
    │
    ▼
RecursiveCharacterTextSplitter
chunk_size=1000, chunk_overlap=200
    │
    ▼  1,181 chunks
EmbeddingManager.generate_embedding()
all-MiniLM-L6-v2, dim=384, CUDA
    │
    ▼  batch_size=512
VectorStore.add_documents_in_batches()
ChromaDB collection: "documents"
path: ../data/vector_store
```

---

## Data Flow: Agentic Query

```
User Input (CLI)
    │
    ▼
Normalize query → check user_thumbdowns.json
    │
    ▼
Build system prompt
  ├── ROLE + RULES block
  ├── THUMBDOWN HISTORY block (if prior bad answers exist)
  └── ACTIVE PRIORITY block (most recent thumbdown appended last)
    │
    ▼
run_agent(query, llm, merge_llm, judge_llm, tools, ...)
    │
    ├── RETRIEVE phase  (two tracks, never mixed)
    │     retrieve_documents() × up to MAX_TOTAL_RETRIEVALS=5
    │     → retrieve_separate(): documents@top_k, learned_qa@top_l
    │     → cosine dedup per track → validate_retrieval() per track
    │     → accumulated_document_chunks[]
    │     → accumulated_learned_qa_chunks[]
    │
    ├── COMPRESS phase  [enforced if LLM skips, per track]
    │     _compress_track("documents",  document_chunks)
    │     _compress_track("learned_qa", learned_qa_chunks)
    │       → NAC → DC → LBC (each track gated independently)
    │     → scrub raw tool-result messages from history
    │
    ├── DRAFT phase  [LLM, no tools]
    │     context = format_precedence_context_for_llm(
    │                  learned_qa_chunks, document_chunks)
    │     → answer text
    │
    └── JUDGE phase
          check_answer_quality(answer, context, query)
          OK → final answer
          INSUFFICIENT → inject failure reason → loop back to RETRIEVE
    │
    ▼
FeedbackStore.log()
    │
    ▼  (if quality=OK and count % LEARN_EVERY_N == 0)
SelfLearner.run_distillation()
    └── → learned_qa collection
```
As of 2026-06-11, the two-track separation is implemented end-to-end (see Changelog and ADR-029): `documents` and `learned_qa` are queried, validated, deduplicated, merged, accumulated, and compressed as independent channels. They are combined only at the LLM context boundary via `format_precedence_context_for_llm()`, which prepends an explicit conflict-resolution rule preferring learned QA.

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| LLM (main agent) | `llama-3.1-8b-instant` via Groq | Optimized for low-latency agentic loops |
| LLM (merge/judge) | `llama-3.1-8b-instant` via Groq | temperature=0.0 for judge; same model, different config |
| LLM provider | Groq (OpenAI-compatible API) | Accessed via `ChatOpenAI` with custom `base_url` |
| LLM framework | LangChain (`langchain-openai`) | Wrapper/tool schema layer only |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, loaded via `sentence-transformers` |
| Embedding hardware | NVIDIA RTX 5050 Laptop GPU (CUDA) | Falls back to CPU |
| Vector database | ChromaDB (`PersistentClient`) | Two collections: `documents`, `learned_qa` |
| Document loaders | `UnstructuredLoader`, `JSONLoader` (LangChain) | Routed by file extension |
| Text splitting | `RecursiveCharacterTextSplitter` | chunk=1000, overlap=200 |
| Persistence | MongoDB (`pymongo`) | Three collections: `feedback_interactions`, `user_thumbdowns`, `failed_variants`; replica-set mode required for multi-document transactions |
| Runtime | Python 3.x (project uses 3.14; note: `compression.py` naming conflict avoided) | Virtual env managed with `uv` |
| Environment config | `.env` + `python-dotenv` | `GROQ_API_KEY` required |

---

## Memory Architecture

The system uses three distinct memory layers, kept intentionally separate:

**Working memory** — the LLM's live context window. Contains system prompt, conversation history (user + assistant + tool call/result turns), and compressed chunk context. Ephemeral; destroyed at session end.

**Semantic memory (source documents)** — ChromaDB `documents` collection. Written once during `ingest.py`. Read-only during agent runtime. 1,181 chunks at current corpus size.

**Episodic / learned memory** — ChromaDB `learned_qa` collection. Written by `SelfLearner.run_distillation()` after every 5 successful interactions (gated by `ENABLE_AUTO_DISTILLATION`). The collection handle is obtained through `learned_qa_store.get_or_create_learned_qa_collection()`, which guarantees `hnsw:space = cosine` and safely migrates any pre-existing L2 collection in-place with full snapshot/restore/rollback. The retriever queries this collection independently from the source `documents` collection on every retrieve_separate() call.

**Failure memory** — MongoDB `user_thumbdowns` and `failed_variants` collections. Written when users flag bad answers (thumbdown write path is atomic via a MongoDB session transaction). Injected as structured context into the system prompt on repeated queries to steer retrieval away from previously failed approaches.

## Configuration Architecture

The pipeline is now configuration-driven. Major subsystems are controlled by feature flags in `config.py`, including retrieval validation, retrieval dedup/merge, NAC, DC, LBC, compression validation, answer drafting, answer quality checking, auto-distillation, QA generation, and output repair.
These flags are not only runtime switches; they define supported experimental architectures for ablation testing. Optional stages must therefore fail safely when disabled and preserve downstream data contracts.

## Structured Output Processing Architecture
Structured LLM outputs follow one of two paths:
```text
Repair enabled:
LLM
  → fix_llm_output()
  → schema-normalized Python object
  → downstream consumer
Repair disabled:
LLM
  → _parse_to_python()
  → parsed Python object
  → downstream consumer
```
`fix_llm_output()` is responsible for repairing malformed or schema-drifting LLM output.
`_parse_to_python()` is responsible for ordinary parsing when repair is intentionally disabled.

---

## Agent Protocol Enforcement

The orchestrator enforces a strict tool-call ordering contract:

1. At least one `retrieve_documents` call must complete before compression.
2. `compress_context` must be called before `check_answer_quality`.
3. A final answer cannot be accepted before both compression and quality check have run.

If the LLM violates the ordering (e.g., calls `check_answer_quality` without prior `compress_context`, or emits a bare final answer), the orchestrator synthetically injects the missing tool call(s), appends the draft answer, and nudges the LLM to re-emit the final answer after the forced steps complete. This behavior was verified across three scenarios: happy path (LLM complies), skip-compress path, and skip-both path.

---

## LLM Role Separation

Three distinct LLM configurations are used concurrently within a single query session:

- **`llm`** (main agent): drives tool selection, query reformulation, and final answer drafting. Prioritizes speed.
- **`merge_llm`**: called inside `_merge_similar_chunks()` in NAC. Produces JSON-structured merge output. Retried up to `LLM_RESPONSE_RETRY_LIMIT` times on malformed output.
- **`judge_llm`** (temperature=0.0): called by all four validators and `check_answer_quality`. Zero temperature for deterministic verdicts.

A noted improvement direction is to use `llama-3.1-8b-instruct` (rather than `-instant`) for `merge_llm` and `judge_llm`, since those roles require stronger instruction-following and faithfulness reasoning over raw speed.

---

## Persistence Schema

All feedback persistence is now stored in MongoDB (database `rag_db` by default, configurable via `MONGODB_DB_NAME` env var). The MongoDB instance must be running in replica-set mode (`rs0`) to support multi-document session transactions used by the thumbdown write path.

**`feedback_interactions`** — one document per query interaction:
```json
{
  "ts": "<ISO-8601 UTC>",
  "request_id": "<uuid4 string>",
  "query": "...",
  "answer": "...",
  "quality": "OK | INSUFFICIENT | USER_THUMBSDOWN",
  "sources": [{"query": "...", "preview": "..."}],
  "document_chunks": [{"content": "...", "source": "..."}],
  "learned_qa_chunks": [{"content": "...", "source": "..."}],
  "variants": [{"query": "...", "document_chunks": [...], "learned_qa_chunks": [...]}]
}
```
Indexes: `ts` (ascending), `request_id` (unique, non-sparse — enforces idempotency for LangGraph node retries).

**`user_thumbdowns`** — one document per thumbdown event (written only when feedback ≥ `MIN_FEEDBACK_LEN` chars):
```json
{
  "ts": "<ISO-8601 UTC>",
  "request_id": "<uuid4 string>",
  "original_query": "...",
  "normalized_query": "...",
  "bad_answer": "...",
  "user_feedback": "...",
  "variants": [
    {
      "query": "...",
      "document_chunks": [{"content": "...", "source": "..."}],
      "learned_qa_chunks": [{"content": "...", "source": "..."}]
    }
  ]
}
```
Index: `normalized_query` (ascending) — used for lookup when injecting prior thumbdown context into the system prompt.

**`failed_variants`** — one document per normalized query, accumulates failed variant strings via `$addToSet`:
```json
{
  "normalized_query": "...",
  "variants": ["variant_query_1", "variant_query_2"]
}
```
Index: `normalized_query` (unique) — `$addToSet` upsert prevents duplicate variant strings per query.

---

## Architectural Evolution Log

**Stage 0 — Baseline RAG** (`query.py`): Single-pass pipeline. Fixed sequence: embed query → retrieve top-k → build prompt → LLM answer. No iteration, no self-correction, stateless.

**Stage 1 — Agentic Loop** (`agent_query.py` + `tools.py`): LLM given tool schemas for `retrieve_documents` and `check_answer_quality`. Multi-iteration loop up to `MAX_ITERATIONS`. LLM decides when to retrieve again vs. answer. Iteration budget enforced by orchestrator. `FeedbackStore` added.

**Stage 2 — Self-Learning** (`self_learner.py`, `learned_qa` collection): `SelfLearner` added. Good interactions distilled into `learned_qa` ChromaDB collection. Retriever updated to query both `documents` and `learned_qa` in parallel, merging and re-ranking results.

**Stage 3 — Context Compression** (`context_compression.py`, `compress_context` tool): Three-stage compression pipeline (NAC → DC → LBC) introduced. Token-budget gate added. `compress_context` promoted to a first-class agent tool. Chat history scrubbing (replacing raw tool-result messages post-compression) implemented to keep context window lean across multi-iteration sessions.

**Stage 4 — Failure Memory + Protocol Enforcement**: Thumbdown system implemented (`user_thumbdowns.json`, `failed_variants.json`). System prompt dynamically augmented with prior bad-answer context on repeated queries. Orchestrator upgraded with strict phase-ordering enforcement — synthetic tool injection for compress and judge steps when LLM deviates from protocol.

**Stage 4b — Naming / Stability Fix**: `compression.py` renamed to `context_compression.py` to resolve collision with Python 3.14's stdlib `compression` package (introduced in 3.14; caused `httpx`/`urllib` circular import cascade on startup).

**Stage 5 — LLM Output Repair Layer** (`fix_llm_output.py`, `test_output_fixes.py`): A weak spot was identified — every structured LLM call in validators and compressors was a silent failure point. LLMs intermittently returned Python/JS code, XML, YAML, markdown-fenced JSON, truncated JSON, or structurally valid JSON with semantically wrong values, and callers had no recovery path. A 5-stage tiered repair pipeline was built: string preprocessing → balanced extraction → `json_repair` → Pydantic schema validation → LLM-based repair (`_LLM_Json_Repair`) → LLM value-verification (`_Verify_And_Correct`). All 8 project output schemas modelled as Pydantic classes in `_SCHEMA_REGISTRY`. 40-case failure taxonomy catalogued; exhaustive test suite written. Next step: wire `fix_llm_output` into `validators.py` and the LBC parsing loop in `context_compression.py`.

**Stage 6 — Two-Track Retrieval Architecture** (`retriever.py`, `tools.py`, `agent_query.py`, `context_compression.py`, `feedback_store.py`, `self_learner.py`, new `learned_qa_store.py`): The single accumulated-chunks stream was split into two independent tracks — `documents` and `learned_qa` — that stay separate end-to-end through retrieval, validation, deduplication, merging, accumulation, and compression. They combine only at the LLM context boundary via `format_precedence_context_for_llm()`, which prepends an explicit `[CONFLICT RESOLUTION RULE]` instructing the model to prefer learned QA when the two sources disagree. The new `learned_qa_store.py` module guarantees the learned-QA Chroma collection uses `hnsw:space = cosine`, with a snapshot-and-rollback migration path for legacy L2 collections (374 entries successfully migrated in production). Retrieval depth is now controlled by `RETRIEVAL_TOP_K` and a new `RETRIEVAL_TOP_L`, both in `config.py`; the LLM no longer sets `top_k` via the tool schema. The change unifies what had previously been a planned architectural gap with a working implementation, and exposed a second wave of issues (`BUG-031` through `BUG-037`) that subsequent stages will address.

---

## Known Architectural Gaps (as of latest sessions)

**Thumbdown injection is structurally present but operationally inert**: The system prompt correctly receives prior bad-answer context (confirmed by token count delta ~547 tokens). However, the LLM's retrieval query reformulations are byte-for-byte identical whether or not thumbdown context is injected. The injected block tells the model what to *avoid*, not what to *seek* — the prompt needs positive redirection toward the specific missing content the user identified.

**Early compress transition may cut planned retrievals short**: The COMPRESS phase is triggered after the first successful retrieval (`total_retrievals >= 1`). The system prompt asks the LLM to plan 2–3 queries, but the orchestrator overrides after 1. The second planned query only executes if the JUDGE sends the agent back to RETRIEVE.

**`judge_llm` max_tokens=1024 may truncate large merge groups**: The merge validator (`validate_merge`) may produce truncated verdicts when chunk groups are large. The DC sliding window size of 3 partially mitigates this.

**`validators.py` and `context_compression.py` now route through `fix_llm_output`** (closed 2026-06-09): All four validators (`validate_retrieval`, `validate_merge`, `validate_redundancy`, `validate_lbc`), the chunk-merge call, the DC scan call, the LBC compression call, and the QA-distillation call now invoke `fix_llm_output("<schema_tag>", raw, llm=...)` instead of calling `json.loads` directly. This routing is controlled by per-stage `*_OUTPUT_FIX` flags and the master `ENABLE_GLOBAL_LLM_OUTPUT_FIX` flag. When these flags are enabled, malformed or non-compliant LLM outputs are repaired and normalized before parsing. When disabled, execution falls through to a raw-output path that currently contains a known defect (see `Bugs.md` BUG-020): the fallback branch assumes a parsed object and attempts `.get()` operations without first applying `json.loads` to valid JSON strings. The remaining fix is to make the fallback path safely parse well-formed JSON before accessing dictionary methods.

**`run_batch.py` path sensitivity**: `load_dotenv()` is resolved relative to working directory inside `agent_query.main()`. Running `run_batch.py` from a different directory causes silent `.env` miss, falling through to the real OpenAI endpoint.

**Remaining architectural gap — learned QA is still mixed with normal document retrieval** *(closed 2026-06-11)*: documents and learned QA are now queried, validated, deduplicated, accumulated, and compressed as two independent tracks throughout the pipeline. They combine only at the LLM context boundary, with an explicit conflict-resolution rule preferring learned QA. See ADR-029, ADR-030, and the 2026-06-11 changelog entry below.

**New gap — combined-context truncation at `check_answer_quality` can hide the document track**: the judge call passes `context[:3000]`. Because `format_precedence_context_for_llm()` writes the learned-QA section first, a large learned-QA block can push the entire document section out of the truncation window even though the draft answer was supported by documents. The judge may then return `OK` without ever seeing the supporting document chunks. See Bugs.md BUG-031. The fix direction is to give the judge two bounded sections (independent per-track character allowances) rather than one combined-and-truncated string.

**New gap — final-answer generation bypasses grounding and conflict-precedence validation**: the DRAFT is judged, but a separate final-answer generation step runs afterward and the final string is returned with no further validation. The final generation can alter the approved draft, introduce unsupported claims, or pick a conflicting document claim despite the learned-QA precedence rule, and nothing detects it. See Bugs.md BUG-032. The fix direction is either to add an explicit final-answer validator with a conflict-precedence criterion, or to return the already-approved draft directly.

**New gap — thumbdown variants capture chunks before validation**: variant snapshots stored in `failed_variants.json` and embedded in `user_thumbdowns.json` are taken from the raw retrieval output, before relevance validation drops irrelevant chunks. Replay logic then treats rejected chunks as if they participated in the failed answer, which can mislead the avoid-prior-failure injection. See Bugs.md BUG-033.

**New gap — retrieval validator trusts inconsistent LLM verdicts**: the JSON returned by the retrieval judge can carry a top-level `verdict: PASS` while the `per_chunk` array shows a minority of chunks relevant (e.g. 2/5 PASS). The orchestrator currently consumes the top-level verdict directly, so the agent never receives the PARTIAL/FAIL retry guidance it should have gotten. See Bugs.md BUG-035. The fix direction is to derive the overall verdict deterministically from the per-chunk counts and treat the LLM's top-level field as advisory.

---

## Changelog

### June 2026 — Stage 5: LLM Output Repair Layer

**`fix_llm_output.py`** — new module. Full 5-stage repair + validation pipeline for all structured LLM outputs. Covers 40 catalogued failure modes across 8 schemas. See Module Breakdown above for full detail.

**`test_output_fixes.py`** — new module. Exhaustive test suite for `fix_llm_output`. 40-case failure taxonomy × 8 schemas. Full I/O logging to timestamped log files.

**`validators.py`** — no code change yet; `json.loads` still in place. Integration with `fix_llm_output` is the next planned step.

**`context_compression.py`** — no code change yet; LBC parsing loop still uses bare `json.loads`. Integration with `fix_llm_output` is the next planned step.

**Architectural Evolution Log updated**: Stage 5 added above.

**Known Architectural Gaps updated**: `validators.py` / `context_compression.py` bare-`json.loads` gap documented below.

### 2026-06-09 — Stage 5 Integration + Configuration Centralisation

**`fix_llm_output` wired into production paths.** `validators.py` (`validate_retrieval`, `validate_merge`, `validate_redundancy`, `validate_lbc`), `context_compression.py` (NAC chunk-merge, DC scan, LBC compress), and `self_learner.py` (QA distillation) now route their raw LLM responses through `fix_llm_output("<schema_tag>", raw, llm=…)`. Closes the gap flagged in the 2026-06-08 entry.

**`config.py`** — new module. Centralises every previously-scattered constant (paths, iteration budgets, compression thresholds, retry counts, chunking parameters) plus 18 boolean feature flags that gate optional pipeline stages. Every module that previously hard-coded these constants now imports them from `config`.

**`prompts.py`** — new module. Centralises every prompt string in the project plus the `_THIN` / `_THICK` log separators.

**`run_combinations.py`** — new module. Progressive flag-ladder ablation harness; generates 10 combos all-OFF → all-ON, patches `config.py` in-place per run, subprocesses `agent_query.py`, logs each run to a timestamped file under `app/run_logs/`. The harness is now also used as an architecture stress-testing tool, not only an ablation benchmark. It detects hidden feature-flag coupling, unsupported execution paths, and modules that assume upstream stages are always enabled.

**`agent_query.py`, `validators.py`, `context_compression.py`, `self_learner.py`** — updated to import flags and constants from `config.py` and prompts from `prompts.py`. Gateable code paths now guarded by `if ENABLE_…:` checks.

**Known Architectural Gaps updated**: the bare-`json.loads` gap in validators/compression is closed; a new gap is added — when the per-stage `*_OUTPUT_FIX` flag is off, validators fall through to a `raw`-string path that crashes (see Bugs.md BUG-020).

### 2026-06-10 — Configuration Hardening + Execution Path Stabilisation

**Fallback parsing architecture introduced.** The original Stage 5 integration assumed that structured LLM outputs would either pass through `fix_llm_output()` or never reach downstream code. Dry-run testing exposed multiple execution paths where disabling `ENABLE_GLOBAL_LLM_OUTPUT_FIX` or stage-specific `*_OUTPUT_FIX` flags caused raw strings to reach validators and compression stages. The architecture now separates **output repair** from **structured parsing**. When repair is disabled, responses are routed through `_parse_to_python()` before entering downstream logic. Architectural contract changed from:

```
LLM → raw string → validator/compressor
```

to:

```
LLM → _parse_to_python() → validator/compressor
```

when output repair is disabled, and:

```
LLM → fix_llm_output() → validator/compressor
```

when repair is enabled.

**`llm_caller.py`** — retry subsystem upgraded. Previous retry behavior immediately retried transient failures, resulting in repeated 429 responses during long ladder runs. Architecture now includes configurable exponential backoff, jitter, retry-attempt limits, and provider-guided recovery via `retry-after` handling. Rate-limit recovery is now treated as a first-class infrastructure concern rather than simple exception handling.

**`context_compression.py`** — `_merge_similar_chunks()` formally becomes shared infrastructure. Dry-run analysis revealed the function is consumed by both retrieval deduplication and Neighbor-Aware Compression (NAC). The architecture now treats merge logic as a reusable service layer rather than a compression-specific helper. Future changes must preserve compatibility across both call paths.

**Feature-toggle architecture validated.** The 18-flag configuration system introduced in Stage 5 was exercised across progressively larger combinations using `run_combinations.py`. This exposed several hidden assumptions where modules expected upstream stages to have already normalized, repaired, validated, or transformed data. Optional pipeline stages are now treated as independently supported execution modes rather than alternate code paths.

**`run_combinations.py` role expanded.** Originally created as an ablation-testing harness, it now serves as an architectural validation framework. Beyond measuring answer-quality contributions, the harness is used to detect hidden coupling, unsupported execution paths, feature-flag regressions, and architecture-level assumptions that are invisible during normal fully-enabled execution.

**Execution-path resilience improved.** Validators, compression stages, and QA-distillation flows were hardened so that disabling optional subsystems no longer invalidates downstream contracts. The architecture now explicitly supports both:

* Fully-enabled production execution
* Partially-enabled experimental execution

without requiring separate code branches.

**Known Architectural Gaps updated**: BUG-020 (flag-off validator crashes) is closed. Fallback paths now correctly parse structured responses before consumption. The remaining architectural focus shifts toward measuring quality/latency contributions of individual stages, validating retrieval-vs-learned-QA precedence behavior, and reducing cross-stage coupling discovered through ladder testing.

### 2026-06-11 — Stage 6: Two-Track Retrieval Architecture (`documents` vs `learned_qa`)

**Closed prior gap.** The previously documented architectural gap that "learned QA is still mixed with normal document retrieval" is now closed. Documents and learned QA are independent end-to-end channels.

**`config.py`** — added `RETRIEVAL_TOP_L` for the learned-QA collection and finalised `RETRIEVAL_TOP_K = 5` and `RETRIEVAL_TOP_L = 5` as the working defaults. Both are env-overridable. `MAX_TOOL_CALLS_PER_ITERATION` settled at 7; `MAX_TOTAL_RETRIEVALS` settled at 5. `load_dotenv()` is now executed centrally from `config.py` and removed from the agent main.

**`retriever.py`** — `RAGRetriever.retrieve()` is now documents-only. New `retrieve_separate(query, top_k, top_l, score_threshold)` queries both Chroma collections independently and returns `{"documents": [...], "learned_qa": [...]}`. No cross-collection sort, no cross-collection dedup, no merging. Last-state getters split into `get_last_document_chunks()` and `get_last_learned_qa_chunks()`.

**`tools.py`** — `retrieve_documents` now consumes `retrieve_separate()`, serializes both tracks into a single tool-result string with explicit `[LEARNED QA RESULTS - HIGH PRIORITY]` and `[DOCUMENT RESULTS - SECONDARY]` section labels, and no longer accepts `top_k` from the LLM. `compress_context` runs `_compress_track()` independently for each track, with its own `COMPRESS_MIN_TOKENS` gate.

**`agent_query.py`** — single `accumulated_chunks` state replaced by `accumulated_document_chunks` and `accumulated_learned_qa_chunks`. Track-local helpers `_validate_track()`, `_accumulate_track()`, and `_compress_track()` keep the per-track code paths identical. `_last_retrieval_fields()` now projects from accumulated state (post-validation/compression), not from the retriever's raw `get_last_*` getters — so the evidence returned to the user and persisted in feedback reflects what actually informed the answer, not just the final retrieval call.

**`context_compression.py`** — added `format_precedence_context_for_llm(learned_qa_chunks, document_chunks)` as the single combine point. Emits three labeled sections: `[CONFLICT RESOLUTION RULE]`, `[LEARNED QA CONTEXT - HIGH PRIORITY]`, `[DOCUMENT CONTEXT - SECONDARY]`. Empty tracks are omitted. `compress_context_pipeline()` gained an early exit when all three of `ENABLE_NAC_COMPRESSION`, `ENABLE_DC_COMPRESSION`, and `ENABLE_LBC_COMPRESSION` are off.

**`learned_qa_store.py`** — new module. Provides `get_or_create_learned_qa_collection()` which guarantees `hnsw:space = cosine` and safely migrates an existing L2 collection in place (snapshot → rename original to UUID-suffixed backup → recreate canonical at cosine → restore in batches → verify count → delete backup; rollback on any failure). Wired into both `agent_query.py` startup and `self_learner.py` so the two code paths share one canonical collection handle. Live migration: 374 L2 → 374 cosine, IDs preserved.

**`feedback_store.py`** — interaction records and thumbdown variants now persist `document_chunks` and `learned_qa_chunks` as separate fields. Legacy mixed `chunks` records are split by `source` at read time. (Known weak spot: merged learned-QA chunks whose `source` ends up concatenated — e.g. `"learned_qa, learned_qa"` — fall through the legacy splitter. Tracked as `BUG-036`.)

**`self_learner.py`** — reads the per-track lists separately. Distillation prompt labels learned-QA chunks as high priority. Uses `learned_qa_store.get_or_create_learned_qa_collection()` for collection access. Self-learning stat display now shows separate document and learned-QA chunk counts.

**`prompts.py`** — agent role/process system-prompt halves explain the separate retrieval tracks. Learned-QA precedence rules added to retrieval, compression, drafting, judging, and final-answer prompts. The `retrieve_documents` tool description was updated; the `top_k` parameter was removed from its schema and docstring.

**Closed gap.** The "learned QA mixed with normal document retrieval" gap recorded in earlier versions of this file is closed; the section in Known Architectural Gaps has been updated accordingly.

**New open gaps recorded.** A second dry-run analysis against the post-separation build surfaced a follow-on cluster of issues, now recorded in Known Architectural Gaps and in `Bugs.md`:
* `BUG-031` — `check_answer_quality` truncates the combined context at 3,000 chars and can lose the document track entirely (HIGH, open).
* `BUG-032` — the final-answer generation step runs after the draft is judged and is itself not validated for grounding or conflict precedence (HIGH, open).
* `BUG-033` — thumbdown variants capture chunks before retrieval validation, so rejected chunks are recorded as if they had supported the failed answer (MEDIUM, open).
* `BUG-034` — the "sources searched" preview takes `result[:200]` of a string whose learned-QA section is written first, hiding document retrieval from output and audit (MEDIUM, open).
* `BUG-035` — the retrieval validator's top-level `verdict: PASS` is trusted even when `per_chunk` shows minority relevance (MEDIUM, open).
* `BUG-036` — legacy chunk-list splitter misclassifies merged learned-QA chunks whose `source` becomes `"learned_qa, learned_qa, ..."` (MEDIUM, open).
* `BUG-037` — validator repair logger prints a "failed to fix malformed LLM output" message on the success branch (LOW, open).

**Tests.** `test_retrieval_separation.py` added — covers two-track separation, configured per-track limits, learned-QA precedence in the formatted context, per-track compression, FeedbackStore legacy-record compatibility, and the L2→cosine migration. Discovered suite passes 13/13 against the live store.

### 2026-06-15 — Stage 7: Centralised Logging Module (`logger_config.py`)

The previous output architecture relied on ~370 scattered `print()` calls across 14+ production modules plus a handful of direct `open()`/`write()` blocks (notably `fix_llm_output.py` for `llm_data_check.txt` and `llm_json_tries.txt`). These produced unstructured terminal output with no level filtering, no timestamps, no per-module attribution, and no way to retain a run's full trace except by capturing terminal scrollback.

**`logger_config.py`** — new module. Single `setup_logging(log_dir, app_name, console_level)` function, idempotent via a root-logger flag, installs one console handler at INFO and one timestamped per-run debug file handler at DEBUG (`{app_name}_{YYYYMMDD_HHMMSS}.debug.log` under `run_logs/`). Diagnostic loggers `llm_data_check` and `llm_json_tries` have `propagate=True` so their output reaches both the console (at effective level) and the debug file (at DEBUG). Custom `_DynamicStdoutHandler` re-points to `sys.stdout` at emit time to survive batch-run tee redirection. See Module Breakdown above for full detail.

**Cross-module conversion.** Every production module (`agent_query.py`, `tools.py`, `context_compression.py`, `validators.py`, `retriever.py`, `embedding_manager.py`, `vector_store.py`, `ingest.py`, `llm_caller.py`, `feedback_store.py`, `self_learner.py`, `learned_qa_store.py`, `fix_llm_output.py`, plus the test harnesses and entry points) now does `logger = logging.getLogger(__name__)` at module scope and routes its diagnostic output through `logger.debug/info/warning/error`. `print()` is preserved only for: interactive REPL prompts, the batch-run progress UI, the test-console formatter, and JSON/JSONL data writes (feedback, failed variants, thumbdowns, test transcripts) — none of which are log content.

**Severity-level audit.** After the mechanical conversion, several messages were re-leveled to match their semantic meaning: in `context_compression.py`, the three "non-retryable error" branches (CHUNK MERGE, DC, LBC) were promoted from `warning` to `error`, and LBC "parse failed after N attempts" was promoted from `debug` to `warning`. In `self_learner.py`, three `[ERROR]`-prefixed messages (LLM distillation failure plus two QA-parse failures) were promoted from `debug`/`warning` to `error` so their level matches the prefix. Tracked as `BUG-039`, closed same day.

**`fix_llm_output.py`** — the direct `open("run_logs/llm_data_check.txt", "a") as _f: _f.write(...)` blocks for `_Verify_And_Correct` and `_LLM_Json_Repair` payloads are now `llm_data_check_logger.debug(...)` and `llm_json_tries_logger.debug(...)` calls on the named diagnostic loggers configured by `logger_config.py`. These had been collateral-deleted by the initial mechanical migration; the restoration closed `BUG-038`.

**`agent_query.py`** — `setup_logging()` callsite updated to `setup_logging(app_name="agent_query")` so the per-run debug file is named `agent_query_<timestamp>.debug.log` rather than falling through to the `sys.argv[0]` stem.

**Two bugs closed.** `BUG-038` (the mechanical conversion dropped — rather than converted — several `print()` and `file.write()` debug blocks, leaving the diagnostic log files empty after a complete run) and `BUG-039` (severity-level mismatches inherited from the conversion) were both opened and closed during this work.

**LangGraph evaluation (no code change).** Researched LangGraph as a possible replacement for the hand-rolled state machine in `agent_query.py`. Concluded that the project's compression/draft/judge tail is strictly sequential and would gain nothing from LangGraph orchestration; the genuine opportunities (parallel sub-query retrieval, parallel per-track validation, durable checkpoint-recovery) require either independent additional infrastructure (durable checkpoint store) or refactors that haven't been prioritised yet. Decision: defer. See ADR-034. `langgraph` remains a declared-but-unused dependency in `requirements.txt` and can be removed by a follow-on cleanup if no migration is planned in the near term.

### 2026-06-16 — LangGraph Migration Attempt Started, Then Paused; Non-Architectural Practice Sandbox (`tempFile.py`)
 
Following the 2026-06-15 LangGraph evaluation (ADR-034, Research topic 30), a direct migration attempt began: `app/AgentState.py` was created as a `TypedDict` mirroring the production agent's full runtime shape (`query`, `messages`, `phase`, `accumulated_document_chunks`, `accumulated_learned_qa_chunks`, token counters, etc.) for an eventual LangGraph port of `agent_query.py`. The attempt was paused before any node/edge wiring against the real pipeline was built — see ADR-035 — and `AgentState.py`, plus the accompanying toy debugging script `agent_workflow.py`, were deleted.
 
**No production module changed.** `agent_query.py`, `tools.py`, `retriever.py`, and the rest of the architecture described above are unaffected by today's work.
 
**`tempFile.py` (project root, non-architectural).** A disposable two-node practice graph (`retrieve` → `generate_answer`, with a conditional edge to `END` on empty retrieval) wired to the project's real `EmbeddingManager`, `VectorStore`, `RAGRetriever`, and `learned_qa_store.get_or_create_learned_qa_collection()`. Exists solely to build hands-on familiarity with `StateGraph` compilation, conditional routing, and graph visualization (`draw_mermaid_png()`, which requires `playwright` plus a downloaded Chromium build) ahead of any real migration. Will be deleted once its purpose is served; it is not part of the tracked module set in Module Breakdown above and is not referenced by any other module.+

### 2026-06-17 — LangGraph Sandbox Finalised and Deleted; `app_workflow/` Package Bootstrapped (Stage 1)

`tempFile.py` (the disposable practice sandbox from June 16, ADR-035) was expanded to a fuller LangGraph pipeline — parallel sub-query dispatch via `Send`, NAC / DC / LBC node chain, `judge_llm` — then deleted once its learning purpose was served. No production module in `app/` was touched.

The `app_workflow/` package was created as a parallel, non-interfering LangGraph implementation of the same RAG pipeline. The day-1 layout was flat: `graph.py`, `state.py`, `routes.py`, a monolithic `nodes/nodes.py`, and a `services/` folder with a `services.py` instance registry plus service module copies from `app/`.

**`state.py`** — `GraphState` TypedDict with `user_input`, `query`, `query_variants`, `answer`, `retry_count`, `command: NotRequired[str]`, `user_feedback: NotRequired[str]`, `blocked_variants: NotRequired[list[str]]`, `prior_thumbdowns: NotRequired[list[dict]]`, and `retrieved_docs: Annotated[list[dict], operator.add]` (fan-in reducer for parallel retrieval branches).

**`services/services.py`** — instance registry; patches `sys.path` to include `app/` so bare imports inside `app/` modules resolve; instantiates `EmbeddingManager`, `VectorStore`, `RAGRetriever`, LLM clients (`llm`, `merge_llm`, `judge_llm`), `FeedbackStore`, `SelfLearner`, and `learned_collection`.

**`nodes/nodes.py`** (monolithic, day 1) — five command/REPL nodes: `user_input_node` (normalises input, sets `command`), `cmd_stats`, `cmd_learn`, `cmd_bad`, `cmd_exit` (raises `SystemExit(0)` — propagates through LangGraph as `BaseException`); plus `generate_query_variants`, `retrieve`, NAC/DC/LBC compression nodes, `generate_answer`, `no_context_answer`.

**`routes.py`** — `route_user_input` (dispatches to a command node or `generate_query_variants`), `fan_out_retrievals` (emits one `Send("retrieve", {...})` per variant), `route_after_compression` (routes to `generate_answer` or retry).

**`graph.py`** — `START → user_input → conditional(route_user_input) → {cmd_stats|cmd_learn|cmd_bad|cmd_exit|generate_query_variants} → fan_out → retrieve → [NAC → DC → LBC] → combine → generate_answer/no_context_answer → END`.

**Two bugs found and fixed in `app/context_compression.py`** while expanding the sandbox (surfaced because `tempFile.py` called these functions directly): `valid_groups` shape mismatch — when `ENABLE_COMPRESSION_VALIDATION=False`, the DC stage produced `list[list[dict]]` but the consumption loop always expected `list[{"members": [...]}]`; fixed by wrapping items in the same shape. `chunk_seq` not promoted from `metadata` to the top level in the retrieve node — NAC looks for `c.get("chunk_seq")` at the top of the chunk dict but `tempFile.py` passed raw retriever output whose `chunk_seq` lives at `c["metadata"]["chunk_seq"]`; fixed by flattening in the retrieve node to match what `_accumulate_track()` does in `agent_query.py`.

**`logger_config.py`** — `llm_io` diagnostic logger made to `propagate=True` and its separate file handler removed; LLM I/O now flows into the shared timestamped debug file alongside all other app logs.

---

### 2026-06-18 — `app_workflow/` Restructured Into Modular Per-Node Files + Full Dual-Track LangGraph Pipeline (Stage 2)

`app_workflow/` was substantially refactored from its day-1 monolithic shape into the production-grade package structure that now constitutes the LangGraph pipeline. `app/` was not touched.

**Package layout (post-refactor):**

```
app_workflow/
├── config.py               # promoted to root (was services/config.py)
├── api.py                  # FastAPI HTTP server — port 8001, same 5 endpoints as app/api.py
├── graph.py                # full graph wiring — ~30 nodes, conditional fan-out/fan-in
├── state.py                # GraphState — dual-track fields at every pipeline stage
├── routes.py               # conditional routing functions
├── main.py                 # REPL entry point; setup_logging; graph.invoke() loop
├── nodes/
│   ├── __init__.py         # re-exports all public node functions
│   ├── user_input.py
│   ├── commands.py         # cmd_stats, cmd_learn, cmd_bad, cmd_exit
│   ├── query_variants.py   # generate_query_variants
│   ├── retrieve.py         # retrieve (fan-out target)
│   ├── post_retrieve.py    # post_retrieval_filter_node (chunk-fingerprint dedup barrier after fan-in)
│   ├── validate_retrieval.py  # validate_document_retrieval, validate_learned_qa_retrieval
│   ├── dedup_merge.py      # dedup_merge_documents, dedup_merge_learned_qa,
│   │                       # validate_dedup_merge_documents, validate_dedup_merge_learned_qa
│   ├── nac.py              # execute_nac_documents, validate_nac_documents
│   ├── dc.py               # execute_dc_documents, validate_dc_documents,
│   │                       # execute_dc_learned_qa, validate_dc_learned_qa
│   ├── lbc.py              # execute_lbc_documents, validate_lbc_documents,
│   │                       # execute_lbc_learned_qa, validate_lbc_learned_qa
│   ├── combine_tracks.py   # combine_tracks (fan-in barrier)
│   ├── generate_draft.py   # generate_draft (drafts the answer, stores state["draft"])
│   ├── check_answer_quality.py  # check_answer_quality (grounding judge, stores state["quality_verdict"])
│   ├── generate_answer.py  # generate_answer (terminal node — finalises answer, logs feedback)
│   ├── auto_distillation.py  # auto_distillation (calls self_learner.run_distillation())
│   └── no_context_answer.py
└── services/
    ├── services.py         # instance registry (EmbeddingManager, VectorStore,
    │                       # RAGRetriever, LLM clients, FeedbackStore, SelfLearner,
    │                       # learned_collection); sys.path patching for app/ bare imports
    ├── config.py           # (copy from app/)
    ├── retriever.py
    ├── vector_store.py
    ├── embedding_manager.py
    ├── llm_setup.py
    ├── llm_caller.py       # hardened with httpx.HTTPStatusError + httpx.ConnectError handlers
    ├── prompts.py
    ├── tools.py
    ├── validators.py
    ├── fix_llm_output.py
    ├── db.py               # MongoDB client singleton + index init (identical to app/db.py)
    ├── feedback_store.py
    ├── learned_qa_store.py
    ├── self_learner.py
    └── context_compression.py
```

**`state.py` (overhauled)** — carries per-track fields at every pipeline stage:

| Field group | Fields |
|---|---|
| Raw retrieval (fan-in) | `retrieved_document_chunks: Annotated[list[dict], operator.add]`, `retrieved_learned_qa_chunks: Annotated[list[dict], operator.add]` |
| Post-filtered (dedup barrier) | `post_filtered_document_chunks: NotRequired[list[dict]]`, `post_filtered_learned_qa_chunks: NotRequired[list[dict]]` |
| Validated | `validated_document_chunks`, `validated_learned_qa_chunks` |
| Dedup-merged | `dedup_merged_document_chunks`, `dedup_merged_learned_qa_chunks`, `dedup_merge_document_pairs: NotRequired`, `dedup_merge_learned_qa_pairs: NotRequired` |
| Document compression (NAC→DC→LBC) | `nac_output_document_chunks`, `dc_output_document_chunks`, `compressed_document_chunks`, `nac_merge_pairs_documents: NotRequired`, `dc_groups_per_window_documents: NotRequired`, `lbc_validation_pairs_documents: NotRequired` |
| Learned-QA compression (DC→LBC) | `dc_output_learned_qa_chunks`, `compressed_learned_qa_chunks`, `dc_groups_per_window_learned_qa: NotRequired`, `lbc_validation_pairs_learned_qa: NotRequired` |
| Final combined | `compressed_docs` (written by `combine_tracks`) |

**Dual-track graph topology** — the LangGraph pipeline runs both compression pipelines in parallel after the retrieval fan-in barrier:

```
START → user_input → route_user_input
    ├── cmd_stats / cmd_learn / cmd_bad / cmd_exit → END
    └── generate_query_variants
            │ fan_out_retrievals (one Send per variant)
            ▼
          retrieve (parallel)
            │
     post_retrieval_filter
            │
            ├── validate_document_retrieval ──────────────────────────────────┐
            │       └── dedup_merge_documents                                 │
            │               └── validate_dedup_merge_documents                │
            │                       └── NAC_documents                        │
            │                           ↕ route_nac_documents_to_validator   │
            │                           validate_NAC_documents               │
            │                               └── DC_documents                 │
            │                                   ↕ route_dc_documents_to_validator
            │                                   validate_DC_documents        │
            │                                       └── LBC_documents        │
            │                                           └── validate_LBC_documents
            │                                                     │           │
            └── validate_learned_qa_retrieval                     │           │
                    └── dedup_merge_learned_qa                     │           │
                            └── validate_dedup_merge_learned_qa   │           │
                                    └── DC_learned_qa             │           │
                                        ↕ route_dc_learned_qa_to_validator   │
                                        validate_DC_learned_qa    │           │
                                            └── LBC_learned_qa   │           │
                                                └── validate_LBC_learned_qa  │
                                                          │                   │
                                                          └────── combine_tracks ◄┘
                                                                      │
                                                        route_after_combine
                                                          ├── generate_draft ──[ENABLE_ANSWER_QUALITY_CHECK]──► check_answer_quality
                                                          │         │                                                  │
                                                          │         └──[else]──► generate_answer                       │
                                                          │                                                 ┌──[OK / no budget]──► generate_answer
                                                          │                                                 └──[INSUFFICIENT + budget]──► generate_query_variants (retry)
                                                          ├── generate_answer  ──[ENABLE_AUTO_DISTILLATION & should_learn()]──► auto_distillation → END
                                                          │                   ──[else]───────────────────────────────────────► END
                                                          ├── retry → generate_query_variants
                                                          └── no_context_answer → END
```

**`graph.py`** — wires the full topology above using `add_node`, `add_edge`, and `add_conditional_edges`. `validate_LBC_documents` and `validate_LBC_learned_qa` are always-present pass-through nodes so `combine_tracks` has a fixed two-predecessor fan-in regardless of whether LBC validation is enabled.

**`services/llm_caller.py`** — two `except` blocks inserted on June 18 before the generic `Exception` catch-all: `httpx.HTTPStatusError` (maps 429 → `RATE_LIMIT`, 5xx → `SERVER_ERROR`, other → `UNKNOWN`); `httpx.ConnectError` (maps to `CONNECTION`). On 2026-06-25, the full FIFO serialization gate + adaptive cooldown system was ported from `app/llm_caller.py` (ADR-044) — identical gate mechanics (`_gate_acquire`, `_gate_release_to_next`, `_apply_cooldown`), header parsing (`_groq_wait_seconds`, `_parse_groq_duration`), shared state (`_llm_queue`, `_llm_gate_lock`, `_llm_active`, `_token_reset_until`, `_cooldown_floor`, `_clean_success_streak`), and `max_retries=0` on all `ChatGroq` instances. `LLM_RATE_LIMIT_BACKOFF_JITTER_SECONDS` removed from `app_workflow/config.py`. See ADR-045.

**Answer pipeline (2026-06-19 split)** — `generate_draft` produces a thorough draft from `compressed_docs` and stores it as `state["draft"]`. `check_answer_quality` runs the grounding judge (`GROUNDING_PROMPT` + `judge_llm`) and stores the verdict as `state["quality_verdict"]` — it does not refine the draft itself; `routes.py`'s `route_after_quality_check` decides whether to retry retrieval (`INSUFFICIENT` + budget remaining, per the same `budget_ok = ENABLE_SUB_QUERY_GENERATION and retry_count < LLM_RESPONSE_RETRY_LIMIT` check used in `app/agent_query.py`'s JUDGE phase) or fall through to `generate_answer` (`OK`, or `INSUFFICIENT` with no budget left). `generate_answer` is the single terminal node: uses `state["draft"]` when present, otherwise generates directly from context; always logs feedback via `feedback_store.log()`, deriving `quality` from `quality_verdict` rather than hardcoding `"OK"`. `auto_distillation` is a thin node that calls `self_learner.run_distillation()`. `generate_draft.py` and `generate_answer.py` use `llm_invoke()` (the structured `services/llm_caller.py` wrapper) rather than raw `llm.invoke()`, consistent with the rest of `app_workflow/`.

**`data/feedback/` parity (2026-06-19) — closes the two gaps below.** `retrieve.py` now emits two additional accumulating state fields via `Annotated[..., operator.add]`: `newly_failed_variants` (zero-chunk query variants, written by `generate_answer`/`no_context_answer` to `failed_variants.json` via new `feedback_store.save_failed_variants()`) and `variants_with_chunks` (every variant's retrieved chunks, both tracks). Because `cmd_bad` runs in a separate graph invocation from the run it's flagging, the terminal answer nodes cache `state["variants_with_chunks"]` into a module-level `services.last_variants_with_chunks` sidecar, which `cmd_bad` reads when calling `feedback_store.mark_last_bad(variants=...)` — mirroring the `last_result` sidecar pattern in `app/agent_query.py`'s REPL loop.

**Known gaps in `app_workflow/` vs `app/`:** none currently tracked as open — the `user_thumbdowns.json` empty-`variants` gap and the `failed_variants.json` never-written-back gap (both noted after the June 17–18 build) were closed on 2026-06-19 (see Bugs.md BUG-043, BUG-044).

**`app/` architecture unchanged.** All modules (`agent_query.py`, `tools.py`, `retriever.py`, `context_compression.py`, etc.) remain fully functional and were not modified on either June 17 or June 18.

---

### 2026-06-19 — Answer Pipeline Split (Stage 3); `data/feedback/` Parity Closed; Startup Import/Path Bugs Fixed

`generate_answer` was split into `generate_draft` → `check_answer_quality` → `generate_answer` (terminal) → `auto_distillation`, with `check_answer_quality` routing `INSUFFICIENT` verdicts back to `generate_query_variants` when retry budget remains rather than refining inline — see ADR-038 and the updated Module Breakdown / graph topology above. The two outstanding `app_workflow/` vs `app/` parity gaps (empty thumbdown `variants`, unwritten `failed_variants.json`) were closed (BUG-043, BUG-044).

**Startup bugs fixed (BUG-045, BUG-046, BUG-047):** bare intra-package imports across `services/services.py`, `retriever.py`, `validators.py`, `self_learner.py`, and `fix_llm_output.py` were converted to relative imports; `main.py` now inserts the project root onto `sys.path` before any other imports so dotted `from app_workflow.config import ...` imports resolve regardless of working directory; `FAILED_VARIANTS_PATH` and the other `data/feedback/` path constants in `config.py` are now resolved against a `__file__`-derived `_PROJECT_ROOT` instead of CWD-relative strings.

**`benchmark.py`** (project root, non-architectural) — a subprocess-isolated comparison tool that runs a fixed query through either `app_workflow.main` or `app.agent_query` three times and appends timing + answer results to `benchmark_results.txt`. Exists to support performance comparison between the two pipelines; not part of either production package. See ADR-039 for the subprocess-isolation rationale and the rate-limiting issue that made today's side-by-side runs unreliable.

`app/` was not modified except for read-only log inspection used to confirm `COMPRESS_MIN_TOKENS`-gated compression skipping was working as designed, not a defect.

---

### 2026-06-20 — HTTP API Layer + LLMRateLimitAbortError

`LLMRateLimitAbortError` introduced in both `app/llm_caller.py` and `app_workflow/services/llm_caller.py` — raised by `llm_invoke()` when the computed exponential-backoff delay would exceed `LLM_RATE_LIMIT_MAX_DELAY_SECONDS` (1800 s), aborting rather than sleeping for half an hour. `LLM_RATE_LIMIT_MAX_DELAY_SECONDS = 1800.0` added to both `config.py` files. `agent_query.py` and both `main.py` files updated to catch `LLMRateLimitAbortError` and surface it as an actionable message instead of crashing.

`app/api.py` (263 lines) — FastAPI HTTP server on port 8000 for the classic LangChain pipeline. Startup: `EmbeddingManager`, `VectorStore`, `RAGRetriever`, three `ChatGroq` instances (`llm`, `merge_llm`, `judge_llm`), `make_tools()`, `make_check_answer_quality()`, `FeedbackStore`, `SelfLearner` all initialised in `asynccontextmanager lifespan`. `_query_lock = asyncio.Lock()` serialises concurrent `/query` calls (shared `agent_state` dict is not thread-safe). Blocking `run_agent()` call dispatched via `asyncio.to_thread()`. `LLMRateLimitAbortError` caught at `/query` → HTTP 429 with `Retry-After` header. `newly_failed` variants persisted back to `failed_variants.json` after each call. Auto-distillation behind `ENABLE_AUTO_DISTILLATION` gate. Five endpoints: `POST /query`, `POST /feedback/bad`, `GET /stats`, `POST /learn`, `POST /quit`. `app/` paths remain CWD-relative; `os.chdir(_APP_DIR)` called at module load so they resolve correctly when uvicorn changes the working directory.

`app_workflow/api.py` (175 lines) — FastAPI HTTP server on port 8001 for the LangGraph pipeline. Startup: `build_graph()` + imports from `services/services.py` registry. `_COMMAND_INPUTS = {"bad", "stats", "learn", "exit", "quit"}` — reserved CLI words rejected at `/query` with HTTP 400 and a hint to use the dedicated endpoints. `_build_initial_state(query)` constructs a zero-valued `GraphState` with all required fields. Same five endpoints, same `LLMRateLimitAbortError` catch / HTTP 429 pattern. `app_workflow/` paths resolved from `__file__`-derived `_PROJECT_ROOT` (unchanged from BUG-045 fix).

`API_ENDPOINTS.txt` (143 lines) — full human-readable reference covering request/response schemas, error codes, and `curl` examples for all ten endpoints across both servers.

**`app/llm_caller.py` httpx parity (BUG-048)** — `import httpx as _httpx` added; `_invoke_once()` received the same two except blocks already present in `app_workflow/services/llm_caller.py` since June 18: `httpx.HTTPStatusError` (429 → RATE_LIMIT, 5xx → SERVER_ERROR, other → UNKNOWN) and `httpx.ConnectError` (CONNECTION). The abort guard inside `llm_invoke()` (`if delay >= rate_limit_max_delay_seconds: raise LLMRateLimitAbortError(delay)`) was also wired up — previously `LLMRateLimitAbortError` and the `rate_limit_max_delay_seconds` parameter were present in the file but the guard was never reached. Both `llm_caller.py` files are now fully in sync.

**`app/api.py` logging fix (BUG-049)** — `setup_logging(log_dir=_APP_DIR / "run_logs", app_name="langchain_api")` moved above all pipeline imports. The "configure once" guard on the root logger (`_CONFIGURED_ATTR`) meant that any earlier import that triggered `setup_logging` first (e.g. `agent_query.py`'s own module-level setup path) would absorb the call and leave `api.py` with no file handler. Log files now appear in `app/run_logs/` as expected.

---

### 2026-06-22 — Timeout Infrastructure + Per-Module Timing Instrumentation

Three new typed exception classes introduced: `LLMResponseTimeoutError` (both `llm_caller.py` files), `RetrievalTimeoutError` (both `retriever.py` files), `EmbeddingEncodingTimeoutError` (both `embedding_manager.py` files). Each module wraps its blocking I/O call in a `concurrent.futures.ThreadPoolExecutor(max_workers=1)` thread and enforces a per-module deadline via `future.result(timeout=…)` — the only cross-platform, library-agnostic option available, since `signal.alarm` is POSIX-only and neither ChromaDB nor SentenceTransformers expose native timeout parameters (see ADR-042).

Timeout behaviour per module: `llm_caller.py`'s `_invoke_once()` catches `LLMResponseTimeoutError` and returns `LLMResult(ok=False, error_kind=TIMEOUT)` so the existing retry loop handles it uniformly. `retriever.py`'s `_query_collection()` catches `RetrievalTimeoutError` and returns `[]` (empty hit list, pipeline continues). `embedding_manager.py`'s `generate_embedding()` raises `EmbeddingEncodingTimeoutError` without catching it — no meaningful fallback exists for a missing embedding vector.

Three new constants in both `config.py` files: `LLM_RESPONSE_TIMEOUT_SECONDS = 150`, `RETRIEVAL_TIMEOUT_SECONDS = 10`, `EMBEDDING_ENCODING_TIMEOUT_SECONDS = 10`. Initial values were set conservatively from documentation, then revised after empirical benchmarking revealed p95 latencies well below those estimates — LLM ~75 s max, ChromaDB retrieval ~0.704 s, embedding ~0.019 s (BUG-051).

DEBUG timing instrumentation added to all three module pairs: `llm_caller.py` logs each `_invoke_once()` attempt's wall-clock duration and per-`llm_invoke()` total rate-limit sleep, tagged with `caller_tag`. `retriever.py` logs collection name and per-call query duration. `embedding_manager.py` logs model name and `model.encode()` duration.

`app_workflow/nodes/nac.py`: `caller_tag="MERGE"` renamed to `"NAC-MERGE"` in `_merge_similar_chunks()` for unambiguous DEBUG log attribution (BUG-050).

---

### 2026-06-23 — Per-Run JSON Timing Files; Benchmark Automation Scripts

**`app_workflow/services/timing_tracker.py`** (new) — thread-safe singleton timing tracker. Class-based singleton protected by a `threading.Lock`, holding `_data: dict[str, list[float]]` and `_json_path: Path`. Nine categories: Sub-Query Generation, Total DB Retrieval Time, Total DB Retrieval Validation Time, Total Merge Time for Retrieved Chunks, Total Validation Time for Merged Chunks, Compression, Draft Generation, CAQ, Final Generation. `set_json_path(path)` called once from `logger_config.py` at startup; creates the JSON file immediately with empty lists for all categories. `record(category, duration)` appends a rounded float and calls `_flush_unlocked()` which writes `json.dumps(_data, indent=2)` to the path on every record — every measurement is durable on disk before the next stage begins. JSON file named identically to the debug log with `.json` suffix (e.g. `rag_langgraph_20260623_143022.debug.json`) and lives alongside it in `run_logs/`.

**`app/timing_tracker.py`** (new) — module-level (not class-based) singleton using module globals `_data`, `_json_path`, `_lock`. Same nine categories. `initialize(json_path)` resets all accumulated data and sets the path; called by `app/logger_config.py` immediately after `.debug.log` creation. `record(category, duration)` appends and flushes. `record_llm(caller_tag, duration)` provides a tag-to-category mapping for `llm_caller.py` call sites: AGENT-RETRIEVE → "Total DB Retrieval Time"; AGENT-DRAFT → "Draft Generation"; AGENT-FINAL → "Final Generation"; CAQ-JUDGE / CAQ-JUDGE-TD → "CAQ".

**`app_workflow/services/logger_config.py`** (modified) — after `.debug.log` creation, now calls `importlib.import_module("app_workflow.services.timing_tracker")` to retrieve the canonical singleton (avoiding the `sys.modules` key mismatch described in BUG-052), then calls `.set_json_path(json_path)` to create the companion JSON file for the run.

**`app/logger_config.py`** (modified) — after `.debug.log` creation, now calls `import app.timing_tracker as _timing; _timing.initialize(debug_file.with_suffix(".json"))`.

**Instrumentation — `app_workflow/nodes/`**: all node files wrap their primary execution body with `time.perf_counter()` probes and call `timing_tracker.record(category, t1 - t0)`. Wall-clock scope for each probe covers the entire node including retries, backoff delays, LLM output-fix attempts, and failed attempts — the recorded duration equals what a caller waiting on the node would observe.

**Instrumentation — `app/`**: `llm_caller.py`'s `_invoke_once()` records each attempt duration via `record_llm(caller_tag, duration)`; backoff sleep durations are also accumulated to the same caller's category so rate-limit wait time is not hidden from the timing totals. `embedding_manager.py` records `model.encode()` duration to "Total DB Retrieval Time". `retriever.py` records ChromaDB `.query()` duration to "Total DB Retrieval Validation Time". `agent_query.py`'s `_accumulate_track()` records `merge_similar_chunks()` calls to "Total Merge Time for Retrieved Chunks" and `validate_merge()` calls to "Total Validation Time for Merged Chunks". `context_compression.py` records all NAC/DC/LBC execution and validation durations to "Compression".

**`run_app_queries.py`** (new, project root) — automation script for `app/api.py` (port 8000). Per query: `subprocess.Popen` to start the server, 2-minute startup wait, `POST /query` with `timeout=None`, `POST /quit`, 5-minute cooldown; 10-minute gap between queries. Runs 7 ASD/motor queries.

**`run_workflow_queries.py`** (new, project root) — identical flow targeting `app_workflow/api.py` (port 8001).

**`app/config.py` and `app_workflow/config.py`** — `ENABLE_AUTO_DISTILLATION` set to `False` in both to disable self-learning overhead during benchmark timing runs.

---

### 2026-06-24 — FIFO Serialization Gate, Adaptive Cooldown, and `request_id` Tracing (Branch `setup_async_lock`)

**Parallel-query 429 failure discovered (BUG-053):** submitting two simultaneous `POST /query` requests causes one to silently exhaust all `LLM_RATE_LIMIT_MAX_ATTEMPTS` retries on 429 responses. Both threads reach `llm_invoke()` concurrently via `asyncio.to_thread()`; the first thread consumes the Groq token quota; the second thread hits 429 on every attempt. The prior `asyncio.Lock` in `api.py`'s `/query` handler was ineffective — it covered only the async handler body and was released before the blocking `to_thread()` work executed.

**`app/llm_caller.py` — FIFO serialization gate (replaces jitter backoff):** `_gate_acquire(caller_tag)` / `_gate_release_to_next()` implement a strict-arrival-order gate backed by `queue.Queue[threading.Event]` + `threading.Lock`. A thread that receives a 429 holds the gate, sleeps the token-reset window (from Groq headers via `_groq_wait_seconds()` / `_parse_groq_duration()`), and retries directly — no re-enqueue, no competing calls during the reset window. `_token_reset_until` (monotonic) tracks the reset deadline so the wait is paid exactly once per exhaustion event. `_apply_cooldown()` adds a derivative `_cooldown_floor` sleep between consecutive successful calls when the queue is non-empty (doubles on 429-recovery, halves after 3 clean successes, resets to 0 on empty queue). `LLM_RATE_LIMIT_BACKOFF_JITTER_SECONDS` removed. `MIN_COOLDOWN_TIME = 0.0` / `MAX_COOLDOWN_TIME = 30.0` added to `app/config.py`. See ADR-044.

**`app/api.py` — lock removal + `request_id` tracing:** `async with _query_lock:` block removed (serialization delegated to `llm_invoke()`'s FIFO gate). Each incoming request generates a `uuid4` `request_id` via `str(uuid.uuid4())`, sets it with `set_request_id()`, and passes it to `run_agent()` and `FeedbackStore.log()`.

**`app/logger_config.py` — per-request log injection:** `ContextVar[str]` (`_request_id_var`, default `"-"`), `set_request_id()`, `get_request_id()`, and `_RequestIdFilter` added. The filter injects `record.request_id` into every log record before formatting; attached to both console and debug file handlers. Format strings updated to include `[%(request_id)s]`.

**`app/agent_query.py`** — `run_agent()` accepts `request_id: str = ""` and stores it in `agent_state`.

**`app/feedback_store.py`** — `log()` and `_save_thumbdown()` accept and persist `request_id` in JSONL records.

`app_workflow/` and its `services/llm_caller.py` are not modified — the branch targets `app/` only. Benchmark session continued; `10 Query Interaction Times.txt` updated with additional runs. `requirements.txt` updated (≈4 KB → 10 KB) to sync the full installed environment.

---

### 2026-06-25 — FIFO Gate + Adaptive Cooldown Merged to Master; Ported to `app_workflow/`

Branch `setup_async_lock` validated and merged into `master` (13 files changed). All changes described in the June 24 Changelog entry are now in production.

**`app/llm_caller.py`** — `max_retries=0` set on all three `ChatGroq` instances (`llm`, `merge_llm`, `judge_llm`) so LangChain's built-in retry loop is fully disabled; the FIFO gate owns all retry and 429-recovery logic end-to-end. `MIN_COOLDOWN_TIME = 0.0` / `MAX_COOLDOWN_TIME = 30.0` in `app/config.py` are production constants.

**`app_workflow/services/llm_caller.py`** — identical FIFO gate + adaptive cooldown system ported (~450 lines changed). Gate mechanics (`_gate_acquire`, `_gate_release_to_next`, `_apply_cooldown`), header parsing (`_groq_wait_seconds`, `_parse_groq_duration`), and shared state (`_llm_queue`, `_llm_gate_lock`, `_llm_active`, `_token_reset_until`, `_cooldown_floor`, `_clean_success_streak`) are in full parity with `app/llm_caller.py`. `max_retries=0` on all `ChatGroq` instances. `LLM_RATE_LIMIT_BACKOFF_JITTER_SECONDS` removed. See ADR-045.

**Supporting `app_workflow/` updates:** `api.py` (handler-level lock removed, per-request `uuid4` `request_id` generated, set via `set_request_id()`, passed to graph state and `FeedbackStore.log()`); `config.py` (`MIN_COOLDOWN_TIME` / `MAX_COOLDOWN_TIME` added, jitter constant removed); `feedback_store.py` (`request_id` persisted in JSONL records); `logger_config.py` (`ContextVar[str]` `_request_id_var` + `_RequestIdFilter` added for per-request log injection); `state.py` (`request_id: NotRequired[str]` added to `GraphState`).

**BUG-053 closed.** The concurrent-request token-quota starvation described on June 24 is resolved in both pipelines.

Cross-pipeline benchmark (10 queries per pipeline, query *"What can u tell me about adjustable speed?"*): `app_workflow` averaged 13 min 51 s total vs. `app`'s 28 min 28 s. Retrieval dominates the gap — LangGraph's parallel `Send` fan-out cuts retrieval from 18:16 to 5:16; compression is comparable between both (≈8–9 min). Results in `10 Query Interaction Times.txt` at project root.

---

### 2026-06-27 — MongoDB Migration; Request-ID-Based `/feedback/bad`; Transaction-Hardened Thumbdown Write Path

All three flat-file feedback stores (`interactions.jsonl`, `user_thumbdowns.json`, `failed_variants.json`) replaced with MongoDB collections in both `app/` and `app_workflow/` — see ADR-046.

**New `app/db.py`** — MongoDB client module (lazy singleton, `_ensure_indexes()` idempotency guard, three collection accessors). Identical file created at **`app_workflow/services/db.py`**, with the `request_id` unique index created without `sparse=True` to avoid `IndexKeySpecsConflict` against the index already registered by `app/db.py` in the shared database — see BUG-054.

**`app/feedback_store.py` rewritten** — no file I/O. `log()` does `insert_one(record)` wrapped in `try/except DuplicateKeyError` for idempotency (BUG-055). `mark_last_bad()` and new `mark_bad(request_id)` wrap their two MongoDB writes in a single session transaction. `_append_thumbdown(session=None)` accepts the caller's session so it participates in the transaction. Variants are stored in the `feedback_interactions` document at `log()` time, making them available to `/feedback/bad` without any in-memory state.

**`app/api.py` updated** — `failed_variants_store` dict and JSON helpers removed; direct `failed_variants_col()` calls for lookup (`find_one`) and save (`update_one` with `$addToSet`, upsert). `FeedbackRequest` now requires `request_id: str`. `/feedback/bad` calls `mark_bad(request_id)` instead of `mark_last_bad()` — see ADR-047. `API_ENDPOINTS.txt` updated accordingly.

**`app_workflow/services/feedback_store.py` rewritten** — same MongoDB pattern as `app/`. `load_failed_variants` / `save_failed_variants` retained for workflow node callers. `log()` uses `request_id = request_id or str(uuid.uuid4())` so CLI-path records always get a unique ID and never violate the non-sparse unique index. `mark_last_bad()` uses MongoDB session transaction. `app_workflow/services/services.py` — `FeedbackStore()` constructor takes no arguments. `app_workflow/nodes/generate_answer.py` — `feedback_store.log()` passes `request_id` and `variants` from state.

**Module Breakdown, Technology Stack, and Persistence Schema** sections updated above to reflect MongoDB as the persistence layer.

---

### 2026-06-29 — Redundant Variant Management; Separate Per-Collection Similarity Thresholds

All changes are in `app_workflow/`. `app/` is unmodified.

**`nodes/query_variants.py` — adaptive budget and pre-retrieval filter added.**

- `adaptive_branch_budget(query)` — zero-LLM heuristic. Returns 1 for queries at or below `BRANCH_BUDGET_SHORT_WORD_COUNT` (4) words; 3 for queries containing any term in `BRANCH_BUDGET_CONJUNCTION_KEYWORDS` (signals multi-clause intent regardless of length); 2 for queries between 5 and `BRANCH_BUDGET_MEDIUM_WORD_COUNT` (8) words; 3 for longer queries. See ADR-049.
- `pre_retrieval_filter(variants, query_embedding)` — two-phase cosine filter applied after LLM variant generation: (1) pairwise inter-variant cosine dedup at `PRE_RETRIEVAL_SIM_THRESHOLD = 0.95` (first survivor of each near-duplicate pair is kept); (2) surviving variants ranked by cosine to the original query embedding and capped to the adaptive budget. Prevents near-duplicate sub-queries from reaching retrieval. See ADR-050 and Research topic 38.
- `_build_system_prompt(max_variants)` — updated signature; now appends a `RETRIEVAL BUDGET: <n>` line so the LLM is notified of its variant limit before generating.
- `generate_query_variants()` — now calls `adaptive_branch_budget()` before the LLM call and `pre_retrieval_filter()` on the LLM output before returning variants to the graph.

**`nodes/post_retrieve.py` — new file.**

`post_retrieval_filter_node(state)` runs as a barrier node after the retrieve fan-in. For each variant's accumulated chunks, it computes a `frozenset((content, source))` fingerprint. Variants whose fingerprint exactly matches a prior survivor's fingerprint are marked duplicate and their chunk contributions are stripped from the accumulator. Clean chunks are written to `post_filtered_document_chunks` and `post_filtered_learned_qa_chunks` in state. Handles the case where two variants with cosine < 0.95 (escaped pre-retrieval filtering) still retrieve exactly the same top-K chunks due to corpus coverage limits. See ADR-051.

**`state.py` — two new fields:**
- `post_filtered_document_chunks: NotRequired[list[dict]]`
- `post_filtered_learned_qa_chunks: NotRequired[list[dict]]`

**`graph.py` — topology updated.** `post_retrieval_filter_node` inserted as a barrier between retrieve fan-in and the two parallel validation nodes. Previous: `retrieve → {validate_document_retrieval, validate_learned_qa_retrieval}`. New: `retrieve → post_retrieval_filter → {validate_document_retrieval, validate_learned_qa_retrieval}`.

**`nodes/validate_retrieval.py`** — both validation functions now read `post_filtered_*` first (`state.get("post_filtered_document_chunks")` / `state.get("post_filtered_learned_qa_chunks")`), falling back to the raw `retrieved_*` accumulators when the filter node was bypassed.

**`nodes/__init__.py`** — `post_retrieval_filter_node` added to public re-exports.

**`services/retriever.py`** — `retrieve_separate()` signature updated: the single `score_threshold` parameter replaced by `doc_score_threshold` (default `DOCUMENTS_MIN_SIMILARITY`) and `learned_score_threshold` (default `LEARNED_QA_MIN_SIMILARITY`), each applied independently to its collection. See ADR-052.

**`nodes/retrieve.py` and `services/tools.py`** — call sites updated to pass `doc_score_threshold=DOCUMENTS_MIN_SIMILARITY` and `learned_score_threshold=LEARNED_QA_MIN_SIMILARITY` from config.

**`config.py` — six new constants:**
- `PRE_RETRIEVAL_SIM_THRESHOLD = 0.95` — inter-variant cosine threshold for pre-retrieval dedup
- `BRANCH_BUDGET_SHORT_WORD_COUNT = 4` — word-count cutoff for budget 1
- `BRANCH_BUDGET_MEDIUM_WORD_COUNT = 8` — word-count cutoff for budget 2 vs 3
- `BRANCH_BUDGET_CONJUNCTION_KEYWORDS` — list of terms that force budget 3
- `DOCUMENTS_MIN_SIMILARITY = 0.5` — cosine floor for the `documents` collection
- `LEARNED_QA_MIN_SIMILARITY = 0.5` — cosine floor for the `learned_qa` collection

---

### 2026-06-30 — Config Constants Tuned; `extract_logs.py` Diagnostic Utility Added

All changes are in `app_workflow/config.py` and at the project root. No node logic, graph topology, or `app/` module was modified.

**`app_workflow/config.py` — four constants updated** based on five-log A/B comparison (Research topic 40 / ADR-053):

| Constant | Old | New |
|---|---|---|
| `RETRIEVAL_TOP_K` | 5 | 4 |
| `RETRIEVAL_TOP_L` | 5 | 4 |
| `DOCUMENTS_MIN_SIMILARITY` | 0.50 | 0.53 |
| `LEARNED_QA_MIN_SIMILARITY` | 0.50 | 0.57 |

The intermediate thresholds 0.53/0.57 were identified in `langgraph_api_20260630_125641.debug.log` as the pair that avoids both INSUFFICIENT-verdict inflation (the 0.50/0.50 failure mode) and retrieval starvation on multi-domain queries (the 0.55/0.60 failure mode), while matching or beating both extremes on total LLM call count. Previous conservative initial values (0.50/0.50) and the tentative targets from Research topic 39 (0.55/0.58) are superseded.

**`extract_logs.py`** (project root, non-architectural) — 443-line standalone diagnostic script that parses `app_workflow/run_logs/*.debug.log` files via regex and extracts per-run retrieval events, validation verdicts, and timing summaries. Not imported by any production module; intended for manual log analysis between runs.

---

### 2026-07-01 — Second LLM Provider: Hugging Face Inference Providers Router (`judge_llm`, new `json_fix_llm`); `fix_llm_output.py` Dead-Parameter Removal

All changes are in `app_workflow/`, with one explicit exception noted below. `app/` is unmodified.

**`services/llm_setup.py`** — `judge_llm` moved off `ChatGroq(llama-3.1-8b-instant)` onto `langchain_openai.ChatOpenAI(base_url=HF_API_BASE, api_key=HF_TOKEN, model="Qwen/Qwen2.5-7B-Instruct")`, reached after two rejected candidates (`google/gemma-3-4b-it:featherless-ai`, then `mistralai/Mistral-7B-Instruct-v0.3` — the latter rejected by the router with `model_not_supported`, since the HF Inference Providers router only exposes a curated subset of the Hub over `/v1/chat/completions`). A new module-level `json_fix_llm` instance was added specifically for the `fix_llm_output.py` repair tier — `Qwen/Qwen2.5-Coder-3B-Instruct` (originally `Qwen/Qwen2.5-3B-Instruct`, which returned HTTP 400 from the router in practice). Both instances are constructed the same way `llm`/`merge_llm`/`judge_llm` always have been — one line each, no change to the surrounding module structure. `HF_TOKEN` and `HF_API_BASE` are new required env vars alongside `GROQ_API_KEY`. See ADR-054.

A separate Colab-notebook-plus-`localtunnel` deployment was wired into `llm_setup.py` earlier in the same session (a `_LocalJudgeLLM` class wrapping `requests.post` against a `loca.lt` tunnel URL) and then removed once the HF router integration proved reliable — see ADR-054 and Research topics 42–43 for why it was abandoned. While it was active, two related fixes were made and retained: the inner `requests.post(timeout=...)` in `llm_setup.py` was raised to `max(60, LLM_RESPONSE_TIMEOUT_SECONDS - 5)` so it fires (and is classified) before the outer `concurrent.futures` timeout in `llm_caller.py`; and `llm_caller.py`'s `_invoke_once()` gained `requests.exceptions.Timeout` / `ConnectionError` handlers ahead of the generic `Exception` catch-all.

**`services/llm_caller.py`** — `_invoke_once()` extended with a full `openai` SDK exception block (`BadRequestError`, `RateLimitError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `UnprocessableEntityError`, `InternalServerError`, `APITimeoutError`), inserted ahead of the generic `Exception` catch-all and ordered so `APITimeoutError` (a subclass of `APIConnectionError`) is checked first. This is the same pattern already used for `_groq.*` and `httpx.*` exceptions (BUG-042, BUG-048) — a new provider's exception hierarchy gets its own parallel block rather than a rewrite of the dispatch logic. The FIFO gate and retry loop in `llm_invoke()` needed no changes; they already operate generically on `LLMErrorKind` and provider-agnostic `retry-after` headers.

**`services/fix_llm_output.py`** — `llm: Any = None` removed from `_LLM_Json_Repair()`, `_Verify_And_Correct()`, and the public `fix_llm_output()` signature. The parameter had been dead code: `_LLM_Json_Repair()` overwrote it with `llm = json_fix_llm` on the line immediately after the signature, so every caller's `llm=...` argument was silently discarded. Both repair functions now call the module-level `json_fix_llm` directly, retaining their existing `ChatGroq` auto-instantiation fallback for when `json_fix_llm` itself is `None`. All 8 call sites (`nodes/dc.py`, `nodes/lbc.py`, `nodes/nac.py`, `services/self_learner.py`, four sites in `services/validators.py`) had their now-meaningless `llm=...` argument removed. **`app/fix_llm_output.py` was explicitly left untouched** — its `llm` parameter has no overwrite bug and is still load-bearing there. See ADR-055.

**`services/validators.py`** — `validate_retrieval()`'s `fix_llm_output` repair branch had an inverted log message (`WARNING: failed to fix malformed LLM output` printed on the *success* path). Fixed by moving the warning into the real failure branch and logging `INFO: successfully fixed` on success, matching the pattern already used by `validate_merge`, `validate_redundancy`, and `validate_lbc`. This closes BUG-037 — investigation at fix time found the defect was isolated to `validate_retrieval()`, not systemic across all four validators as originally filed.

**Diagnostic findings (no code change from these, tracked as new bugs).** A log-forensics pass against `app_workflow/run_logs/langgraph_api_20260701_144027.debug.log` found that, under the new HF-router-hosted `judge_llm`, 100% of successful `judge_llm` calls (14/14) required `fix_llm_output` JSON repair — a materially higher repair-tier engagement rate than the Groq-hosted baseline. A full run of `app_workflow/test_output_fixes.py` (the existing 40-failure-mode × 8-schema suite) against the new repair stack surfaced four previously-undocumented `fix_llm_output.py` defects, independent of the new provider itself: Python class/attribute-assignment syntax is unrecoverable (returns `{}`, BUG-058); the `merged_from` coercer's documented `None`-and-bad-value → `0` fallback only actually covers `None` (BUG-059); the LLM repair tier fabricates plausible JSON for inputs with no real answer data rather than signaling failure (BUG-060); and balanced-bracket extraction can select the wrong candidate object when a response contains both an example blob and the real answer (BUG-061). See Research topic 44.

**Known environment issue (not a code change).** `embedding_manager.py` is currently falling back to CPU for `all-MiniLM-L6-v2` despite a correctly CUDA-built `torch==2.11.0+cu128` — traced to the RTX 5050 Laptop GPU's Windows driver being in `ConfigManagerErrorCode 43` (crashed/error state), likely a Blackwell-generation driver mismatch. Not yet resolved; a clean driver reinstall is the recommended fix. See BUG-057. The Technology Stack table's "Embedding hardware" row (NVIDIA RTX 5050 Laptop GPU, CUDA) reflects the intended/normal configuration — as of this entry the system is running on the CPU fallback path it already supported.

---

### 2026-07-02 — Answer-Quality Judge Restructured to Multi-Verdict JSON; `combine_tracks` Made a True Fan-In Barrier; Draft Now Feeds a Synthesis Pass Rather Than Being Returned As-Is

All changes are in `app_workflow/`. `app/` is unmodified.

**`services/prompts.py` / `nodes/check_answer_quality.py` — `GROUNDING_PROMPT` restructured** from a free-text `OK`/`INSUFFICIENT — <reason>` line into a JSON object: `{"verdict": "GROUNDED" | "PARTIALLY_FABRICATED" | "OVERCLAIMED" | "OFF_TOPIC" | "UNKNOWN", "unsupported_claims": [...], "scope_mismatch": "...", "overall_reason": "..."}`. Three judging rules now apply: exhaustive per-sentence traceability (not just "key claims"), relevance, and a new completeness/calibration rule requiring answer scope and confidence to match the volume of retrieved evidence. Parsed through a new `GroundingJudgeSchema` registered in `fix_llm_output.py`'s existing 8-schema registry (now 9). `check_answer_quality()` exports `QUALITY_PASS_VERDICT = "GROUNDED"` as the single pass/fail source of truth, and falls back to `"UNKNOWN"` (not the previous fail-open `"OK"`) on any judge-call or parse failure. See ADR-056.

**`routes.py`, `nodes/generate_answer.py`, `api.py` — updated to the new verdict shape.** `route_after_quality_check` now branches on `verdict == QUALITY_PASS_VERDICT` instead of the old `.startswith("INSUFFICIENT")` prefix check; two other call sites reading the same `quality_verdict` state field with the same stale assumption (`generate_answer.py`'s feedback-log `quality` label, `api.py`'s `/query` response `quality` field) were updated in the same pass — both would otherwise have silently reported `"OK"` for every answer once the verdict format changed.

**`graph.py` — `combine_tracks` registered with `defer=True`.** The node has two predecessors of unequal depth (document track: NAC→DC→LBC, 3 stages; learned-QA track: DC→LBC, 2 stages), so under LangGraph's default fan-in behavior — which only merges predecessors completing in the same superstep — the node fired once per completing track instead of once as a true barrier. `defer=True` holds the node until every other pending task in the run has finished. See ADR-057, Bugs.md BUG-062.

**`nodes/generate_answer.py` — draft-handling flow corrected to match the intended design already implemented in `app/agent_query.py`'s `_generate_final_answer`.** Previously `if draft: answer = draft` returned the draft text unmodified as the final answer, bypassing the DRAFT → (synthesis) → FINAL design entirely. Now: draft present → one more LLM call using the new `_GENERATE_ANSWER_FROM_DRAFT_PROMPT` (draft as working material + full compressed context) produces the actual final answer, with the literal draft used only as a fallback if that call fails; draft absent → unchanged direct-from-context path via `_GENERATE_ANSWER_PROMPT`. See ADR-058, Bugs.md BUG-063.

**`services/prompts.py` — three new conservative-grounding prompts** (`_GENERATE_ANSWER_PROMPT`, `_GENERATE_ANSWER_FROM_DRAFT_PROMPT`, `_GENERATE_DRAFT_PROMPT`), all requiring explicit FULL/PARTIAL/INSUFFICIENT coverage self-classification, claims restricted to verbatim/direct paraphrase of context, and paired GOOD/BAD worked examples — the same structural pattern Research topic 19 identified as most reliable, applied to the generation side for the first time (previously only judge-side prompts used it). `nodes/generate_draft.py` rewired onto `_GENERATE_DRAFT_PROMPT`, replacing an inline prompt that had explicitly instructed "Be thorough and complete." See ADR-059.

**`services/llm_setup.py` — dead-code cleanup.** Removed commented-out remnants of the pre-2026-07-01 Groq `judge_llm` and an abandoned `InferenceClient` stub; `json_fix_llm` settled on `Qwen/Qwen2.5-Coder-3B-Instruct` as its permanent default (see ADR-055).

**Known issue, not yet fixed.** `.env`'s `GEN_MODEL_NAME` is set to an HF Hub-style path (`Qwen/Qwen2.5-7B-Instruct`) but feeds the Groq-backed `llm` client, which has no such model — `HTTP 404 model_not_found`. See Bugs.md BUG-064.

**New env vars:** `HF_TOKEN`, `HF_API_BASE` — required for `app_workflow/services/llm_setup.py`'s `judge_llm` and `json_fix_llm` instances. `GROQ_API_KEY` remains required for `llm`/`merge_llm` and the `ChatGroq` fallbacks inside `fix_llm_output.py`.

---

### 2026-07-03 — `llm_setup.py` Consolidated Onto a Single Custom OpenAI-Compatible Endpoint; Groq Narrowed to Tool-Calling Only

All changes are in `app_workflow/`. `app/` is unmodified.

**`services/llm_setup.py` rewritten.** Sets aside the 2026-07-01 Hugging Face Inference Providers router adoption (ADR-054) for `judge_llm`/`json_fix_llm`. `llm`, `judge_llm`, and `json_fix_llm` are now all built as `ChatOpenAI(base_url=CUSTOM_API_BASE, api_key=CUSTOM_API_KEY, model=CUSTOM_API_MODEL_NAME, max_retries=0)`, with `CUSTOM_API_MODEL_NAME` defaulting to `"llama-3.1-8b-instruct"`. Per-role temperature/max_tokens unchanged (`llm`: 0.1/2048; `judge_llm`/`json_fix_llm`: 0.0/1024). The prior Groq `ChatGroq(model_name=GEN_MODEL_NAME)` instance is retained under a new name, `llm_tool`, reserved for tool-calling paths whose support on the custom endpoint is unconfirmed. See ADR-060.

**`nodes/query_variants.py`** — `generate_query_variants()` now imports and calls `llm_tool` instead of `llm`, so query-variant generation (which relies on tool schemas) stays on Groq while the free-form reasoning/judging load moves to the custom endpoint.

**`config.py`** — `ENABLE_ANSWER_QUALITY_OUTPUT_FIX = True` re-added under `ENABLE_ANSWER_QUALITY_CHECK` (see the 2026-07-02 entry's config churn note above for the same-day add/remove history one day earlier).

**Research side-note.** "Continual Harness: Online Adaptation for Self-Improving Foundation Agents" was read in depth this session — a self-improving-agent-scaffolding paper whose "harness" concept (prompt + memory + skills + sub-agents, refined online by a Refiner role) maps loosely onto this project's `config.py`/`prompts.py`/`tools.py`/`learned_qa` collection, but the project has no automated equivalent of the paper's Refiner — all threshold/prompt tuning to date (e.g. ADR-053) has been a human-driven log-analysis loop, not agent-driven. No architecture changes resulted from the reading; see Research topic 45.

**New env vars:** `CUSTOM_API_BASE`, `CUSTOM_API_KEY`, `CUSTOM_API_MODEL_NAME` — required for `app_workflow/services/llm_setup.py`'s `llm`, `judge_llm`, and `json_fix_llm` instances. `HF_TOKEN`/`HF_API_BASE` (added 2026-07-01) are no longer consumed by this module. `GROQ_API_KEY` remains required for `llm_tool` and the `ChatGroq` fallbacks inside `fix_llm_output.py`.

---

### 2026-07-06 — Tool-Calling Removed from Query-Variant Generation; `app_workflow/services/tools.py` Deleted; LLM-Provider Split Reverted Toward the Pre-ADR-060 Split

All changes are in `app_workflow/`. `app/` is unmodified.

**`nodes/query_variants.py` — tool-calling removed.** `generate_query_variants()` no longer passes `tools=[RETRIEVE_DOCUMENTS_TOOL_SCHEMA]` to `llm_invoke()`; the LLM is instead asked to return a plain JSON array (`[{"query": "..."}, ...]`), parsed via `fix_llm_output("query_variants", raw, llm=llm_tool)` (or `_parse_to_python()` as a fallback when `ENABLE_QUERY_VARIANTS_OUTPUT_FIX` / `ENABLE_GLOBAL_LLM_OUTPUT_FIX` is off). `_build_system_prompt()`'s injected budget line changed from "Call retrieve_documents exactly N time(s)" to "Generate exactly N query variant(s)" to match. See ADR-061.

**`services/fix_llm_output.py`** — new `QueryVariantSchema(_BaseStrict)` (single required non-empty `query: str` field) registered under the tag `"query_variants"` in `_SCHEMA_REGISTRY` (10th schema).

**`config.py`** — new flag `ENABLE_QUERY_VARIANTS_OUTPUT_FIX = True`.

**`services/prompts.py`** — `_ROLE_AND_RULES` and `_PROCESS_INSTRUCTIONS` rewritten from scratch. The prior versions described the node driving a full RETRIEVE→COMPRESS loop via `retrieve_documents`/`compress_context` tool calls, plus a final-answer OUTPUT FORMAT block — all leftover from before retrieval/compression/answering were split into separate graph nodes. The new prompt states the node's only responsibility is producing query variants, removes all tool/retrieval/answering language, and closes with an explicit first-character JSON anchor (must be `[`, "parsed directly using `json.loads()`").

**`services/tools.py` deleted (−342 lines).** Its sole export, `RETRIEVE_DOCUMENTS_TOOL_SCHEMA`, has no remaining importers now that `query_variants.py` no longer uses tool-calling.

**`services/llm_setup.py`** — `llm` reverted from the ADR-060 custom-`ChatOpenAI`-endpoint construction back to `ChatGroq(llama-3.1-8b-instant)` (the custom-endpoint block is commented out in place, not deleted). `judge_llm` and `json_fix_llm` moved from the custom endpoint back onto the HF Inference Providers router (`Qwen/Qwen2.5-7B-Instruct`, `Qwen/Qwen2.5-Coder-3B-Instruct` — same models as ADR-054), reading `HF_API_BASE`/`HF_TOKEN` again instead of `CUSTOM_API_BASE`/`CUSTOM_API_KEY`. `llm_tool` (Groq) is unchanged in the file but has no remaining call site. Net effect: today's provider split is Groq (`llm`, unused `llm_tool`) + HF router (`judge_llm`, `json_fix_llm`) — a partial reversal of the 2026-07-03 single-custom-endpoint consolidation. See ADR-061.

**`services/llm_caller.py`** — `_invoke_once()` gained two new debug-only helpers, `_message_text()` / `_messages_char_len()`, logging estimated input size (char count and a ~4-chars/token estimate) and the target model's `max_tokens` before each call, and `response.response_metadata["token_usage"]` after a successful call. Added to support this session's benchmarking; no control-flow change.

**New root-level file, `Execution Time Comparison.md`** — not a production module; a 3-setup × 3-query × 2-run latency benchmark comparing which backend (Groq / HF router / local-custom LLM) serves which pipeline role. See Status.md and Research topic 46 for the full breakdown; Bugs.md BUG-065 for the HF-402 finding.

---

### 2026-07-08 — Full LLM Backend Consolidation: `llm_tool`, `judge_llm`, `json_fix_llm` Moved to the Custom Endpoint; Groq and the HF Router Retired

All changes are in `app_workflow/`. `app/` is unmodified.

**`services/llm_setup.py` rewritten again.** `llm_tool` (previously `ChatGroq(llama-3.1-8b-instant)`, unused since ADR-061 removed its only call site) and `judge_llm`/`json_fix_llm` (previously the HF Inference Providers router, per the 2026-07-06 entry) are now all `ChatOpenAI(base_url=CUSTOM_API_BASE, api_key=CUSTOM_API_KEY, model=CUSTOM_API_MODEL_NAME, max_retries=0)`, joining `llm` (already on the custom endpoint since ADR-060/2026-07-03). Per-role temperature/max_tokens unchanged (`llm`/`llm_tool`: 0.1/2048; `judge_llm`/`json_fix_llm`: 0.0/1024). The `ChatGroq` construction blocks for `llm_tool` and `llm` are commented out in place, following the file's established rollback pattern rather than being deleted. See ADR-062.

**Known inconsistency, not yet fixed.** `judge_llm`/`json_fix_llm`'s `model=` fallback default strings still read `"Qwen/Qwen2.5-7B-Instruct"`/`"Qwen/Qwen2.5-Coder-3B-Instruct"` — leftover HF-router-era defaults. Since `CUSTOM_API_MODEL_NAME` is set in `.env`, all four LLM instances currently resolve to the same model regardless of role; the per-role fallback strings are dead code unless `CUSTOM_API_MODEL_NAME` is ever unset.

**Motivating evidence.** Completion of the `Execution Time Comparison.md` benchmark (Setups 4–5, Research topic 50) and a same-day debug-log quality audit (Research topic 51, BUG-066/067/068) of the exact log files those benchmark runs produced — the all-local Setup 5 run had zero infra errors, while the HF-router Setup 4 run showed most validators silently degrading to fallback verdicts (BUG-065).

**New env vars:** none added. `HF_TOKEN`/`HF_API_BASE` and `GROQ_API_KEY` are no longer consumed by `llm_setup.py`; `GROQ_API_KEY` remains required only for the `ChatGroq` fallbacks inside `fix_llm_output.py`'s `_LLM_Json_Repair`/`_Verify_And_Correct`, which construct their own client independently of `llm_setup.py`.

---

### 2026-07-09 — Phoenix Tracing Added (`phoenix_tracing.py`); Log-to-Trace Mirroring Handler (`_TracingHandler`); `trace_events.py` CLI

All changes are in `app_workflow/`. `app/` is unmodified.

**New `services/phoenix_tracing.py`.** `setup_phoenix_tracing()` registers Arize Phoenix via its OTel collector endpoint (`PHOENIX_COLLECTOR_ENDPOINT`, default `http://localhost:4317`) and calls `LangChainInstrumentor().instrument()` to auto-instrument every LangChain/LangGraph call. Called at startup in `api.py` (already present) and, as of this session, also in `main.py` — the CLI entry point had never called it, so Phoenix recorded nothing for standalone runs (Bugs.md BUG-069). See ADR-063.

**`services/logger_config.py` — new `_TracingHandler`, a third `logging.Handler` registered alongside the existing console and per-run debug-file handlers.** On every log record it: (1) looks up the active LangSmith run via `langsmith.run_helpers.get_current_run_tree()` and calls `.add_event(...)` if one is active; (2) using that same run's `run_id`, looks up the matching Phoenix span via `LangChainInstrumentor()._tracer.get_span(run_id)` (not `opentelemetry.trace.get_current_span()` — see Bugs.md BUG-071 for why the ambient-context lookup doesn't work against this specific package) and calls `.add_event(...)` on it with `log.level`/`log.logger`/`log.request_id` attributes. Both lookups are wrapped in `try/except: pass`, so the handler is a strict no-op whenever neither tracer is active. Runs at `logging.DEBUG` unconditionally, independent of the console handler's `INFO` level, so the majority of `logger.debug(...)` calls across `nodes/*.py` (67 of 127 total `logger.*` calls, per a repo-wide grep) are mirrored rather than silently dropped (Bugs.md BUG-070). See ADR-064.

**New `services/trace_events.py`** — a small CLI (`python -m app_workflow.services.trace_events <run_id>`) added after confirming, via a direct LangSmith API query, that mirrored events are fully persisted server-side (43 events on one real run) but never rendered anywhere in the LangSmith web UI on this account/plan (Bugs.md BUG-072). Resolves the given run's `trace_id`, fetches every run in that trace, and prints all mirrored log events in chronological order with their originating node name — bypassing the UI gap entirely. Required a stdout re-encode to UTF-8 after an initial crash on Windows' default `cp1252` console encoding (Bugs.md BUG-073).

**`services/llm_setup.py`** — brief same-session oscillation: `llm`/`llm_tool` switched from `CUSTOM_API_BASE` to `HF_API_BASE`/`HF_TOKEN` (testing HF for the main LLM, with all four instances keyed off `JUDGE_MODEL_NAME`), then reverted back to `CUSTOM_API_BASE`/`CUSTOM_API_KEY` for all four instances in the same commit — consistent with this file's established pattern of trying and rolling back provider configurations in place (ADR-054/060/061/062).

**Comparative research completed this session, no further code impact:** a beginner-level walkthrough of OpenTelemetry/OpenInference/semantic-convention fundamentals (Research topic 53); a self-hosting comparison of LangSmith vs. Langfuse vs. Phoenix under the project's no-data-egress constraint, concluding Phoenix is the better fit for now with Langfuse deferred as a future candidate (Research topic 54); and the investigation into why stdlib `logging` doesn't automatically reach either tracing backend (Research topic 55, the basis for `_TracingHandler`'s design).

Tracked in: new `app_workflow/services/phoenix_tracing.py`, `app_workflow/services/trace_events.py`; `app_workflow/services/logger_config.py`, `app_workflow/main.py`, `app_workflow/services/llm_setup.py` modified; new Decisions.md ADR-063, ADR-064; new Bugs.md BUG-069 through BUG-073; new Research.md topics 53, 54, 55.

---

### 2026-07-10 — `app/llm_setup.py` Diverges From `app_workflow/`: Reverted to Native Groq for `llm`/`merge_llm`/`judge_llm`; `json_fix_llm` Moved to the HF Router

Change is scoped to `app/llm_setup.py` only. `app_workflow/` is unmodified and remains on the full `CUSTOM_API_BASE` consolidation from ADR-062.

**`llm_setup.py` rewritten.** `llm`, `merge_llm`, and `judge_llm` are now built as native `langchain_groq.ChatGroq(api_key=GROQ_API_KEY, model_name=MODEL_NAME, ...)` instances (`MODEL_NAME` defaults to `"llama-3.1-8b-instant"`), replacing the `ChatOpenAI(base_url=CUSTOM_API_BASE, api_key=CUSTOM_API_KEY, model=CUSTOM_API_MODEL_NAME, ...)` construction those three roles had carried since `app/` was synced to `app_workflow/`'s state in the prior commit (`610c4b8`). `json_fix_llm` stays on `langchain_openai.ChatOpenAI` but moves from `CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME` onto the Hugging Face Inference Providers router (`base_url=HF_API_BASE`, `api_key=HF_TOKEN`), reading a new dedicated `JSON_FIX_MODEL_NAME` env var (default `"Qwen/Qwen2.5-Coder-3B-Instruct"`) instead of the shared `CUSTOM_API_MODEL_NAME`. Per-role temperature/max_tokens are unchanged. No commented-out fallback block was left for the prior `CUSTOM_API_BASE` wiring — unlike `app_workflow/services/llm_setup.py`'s established practice of preserving prior provider blocks in place. See ADR-065.

**Consequence for `llm_caller.py`'s description above:** the "thin wrapper around `ChatOpenAI` that routes to Groq's OpenAI-compatible endpoint" summary now only accurately describes `json_fix_llm`'s HF-router traffic within `app/`. `llm`/`merge_llm`/`judge_llm` bypass `ChatOpenAI`/`llm_caller.py`'s OpenAI-compatible routing model entirely, going through `langchain_groq.ChatGroq` directly; `llm_caller.py` itself is unmodified and still handles whatever LLM client object it's given generically via `.invoke()`, so no code change was required there.

**New env vars for `app/`:** `GROQ_API_KEY`, `MODEL_NAME`, `HF_API_BASE`, `HF_TOKEN`, `JSON_FIX_MODEL_NAME`. `CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME` are no longer consumed by `app/llm_setup.py` (they remain required for `app_workflow/`).

Tracked in: `app/llm_setup.py` modified; new Decisions.md ADR-065.

---

### 2026-07-10 — Langfuse Callback-Based Tracing Added as a Third Backend; `config` Threading Through the LLM Call Chain; Circular Import Fix

All changes are in `app_workflow/`. `app/` is unmodified.

**New `services/langfuse_tracing.py`.** `get_langfuse_handler()` returns a `langfuse.langchain.CallbackHandler`, reading `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_BASE_URL` (falls back to `LANGFUSE_HOST`) from env. Unlike `phoenix_tracing.py`'s `setup_phoenix_tracing()` (an ambient, OTel-auto-instrumentation call made once at startup), the Langfuse handler is an explicit LangChain callback object that must be passed into every `.invoke()` call it should trace. See ADR-066.

**`config.py`** — new `ENABLE_LANGFUSE_TRACING = True` flag, alongside the existing `ENABLE_PHOENIX_TRACING`.

**`main.py` / `api.py`** — both construct `langfuse_handler = get_langfuse_handler() if ENABLE_LANGFUSE_TRACING else None` at startup and pass `{"callbacks": [langfuse_handler] if langfuse_handler else []}` into every `rag_app.invoke(...)` call; `api.py`'s `/learn` endpoint passes the same callbacks list into `self_learner.run_distillation()`.

**`services/llm_caller.py` — `llm_invoke()` and `_invoke_once()` signatures extended with an optional `config: RunnableConfig` parameter**, forwarded explicitly as `llm.invoke(messages, config=config, **kwargs)`. This is the root fix for Langfuse tracing actually reaching LLM calls (see ADR-067, Bugs.md BUG-075): LangGraph only auto-injects `config` into node functions that declare a `config` parameter, and `_invoke_once()`'s `ThreadPoolExecutor`-wrapped call would have dropped ambient contextvar-based propagation regardless of node-level wiring.

**`config` threaded through ~40 call sites across 11 files** to reach the `llm_invoke()` fix above: every node function (`query_variants.py`, `check_answer_quality.py`, `generate_answer.py`, `generate_draft.py`, `dc.py`, `lbc.py`, `nac.py`, `validate_retrieval.py`, `dedup_merge.py`, `auto_distillation.py`, `commands.py`) now accepts and forwards an optional `config` parameter; `services/validators.py`'s four validators (`validate_retrieval`, `validate_merge`, `validate_redundancy`, `validate_lbc`) and `services/fix_llm_output.py`'s repair functions gained the same parameter to keep the propagation unbroken through nested LLM-repair calls; `services/self_learner.py`'s distillation path was updated identically.

**Circular import fixed in `nodes/generate_answer.py`** — its one intra-`nodes` cross-import (`QUALITY_PASS_VERDICT`) used the absolute `app_workflow.nodes.X` form while every other file in the package uses the bare `nodes.X` form; the two styles load the package under separate module identities, crashing `graph.py`'s import chain whenever it was hit. Aligned to the bare-import style used everywhere else. See Bugs.md BUG-074.

**Known, diagnosed-but-unapplied issue: Phoenix and Langfuse cannot both be enabled without one silently losing spans.** `phoenix.otel.register()`'s exporter is installed on the process-global `TracerProvider` as a replaceable "default" processor; Langfuse's OTel-native SDK detects and reuses that same global provider, and its `add_span_processor(...)` call triggers Phoenix's own provider subclass to shut down and discard its existing processor before attaching Langfuse's. From that point, only Langfuse receives spans, with no exception raised anywhere to signal it. A fix (`register(set_global_tracer_provider=False)` + `LangChainInstrumentor().instrument(tracer_provider=tp)`, giving Langfuse its own separate provider) was verified against the real `build_graph()` pipeline in isolated scripts but not applied to `phoenix_tracing.py`. See Bugs.md BUG-076.

**New env vars:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` (or `LANGFUSE_HOST`) — required for `services/langfuse_tracing.py`.

Tracked in: new `app_workflow/services/langfuse_tracing.py`; `app_workflow/config.py`, `app_workflow/main.py`, `app_workflow/api.py`, `app_workflow/services/llm_caller.py`, `app_workflow/services/fix_llm_output.py`, `app_workflow/services/validators.py`, `app_workflow/services/self_learner.py`, `app_workflow/nodes/*.py` modified; new Decisions.md ADR-066, ADR-067; new Bugs.md BUG-074, BUG-075, BUG-076.
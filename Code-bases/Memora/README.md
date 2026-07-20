# Memora: Self-Learning Agentic RAG

A locally-running, self-improving Retrieval-Augmented Generation system with an agentic query loop, LLM-as-judge context compression, and a thumbdown-driven feedback mechanism that gets better with use.

Two independent agent implementations share one ingestion pipeline and one vector store — see [Two Implementations, One Knowledge Base](#two-implementations-one-knowledge-base) below.

---

## What Problem It Solves

Standard single-pass RAG pipelines have three hard limits: they cannot self-correct when the first retrieval is poor, they repeat the same bad answers across sessions, and they never learn from user feedback. This project addresses all three by replacing the linear retrieve → prompt → answer flow with an **agentic loop**, a **three-stage context compression pipeline** (NAC → DC → LBC), and a **self-learning mechanism** that distills verified Q&A pairs back into the knowledge base.

The system was built and stress-tested on a domain-specific corpus (ASD clinical data, research PDFs, patient datasets, and engineering documents), but the architecture is corpus-agnostic.

---

## Two Implementations, One Knowledge Base

**Ingestion is a single, shared pipeline** (`app/ingest.py`) — it discovers documents, chunks them, embeds them, and writes them into one ChromaDB store at `data/vector_store/` (two collections: `documents` and `learned_qa`). You run it once, regardless of which agent you use afterward.

Two separate agent implementations are built **on top of** that same store:

| | `app/` | `app_workflow/` |
|---|---|---|
| Orchestration | Hand-rolled 4-phase state machine | LangGraph `StateGraph` |
| Query fan-out | Sequential | Parallel (`Send` per query variant) |
| Observed latency (10-query benchmark, see `Status.md` 2026-06-25) | ~28 min total avg | ~14 min total avg (~2× faster; retrieval is the dominant gap) |
| HTTP API | `app/api.py` — port 8000 | `app_workflow/api.py` — port 8001 |
| Status | Original implementation, fully maintained | Actively developed; recommended for new work |

They are functionally independent (separate `config.py`, `llm_setup.py`, `feedback_store.py`, etc.) but read and write the **same** `data/vector_store/` and the **same** MongoDB database, so a document ingested once, or a Q&A pair distilled by one pipeline, is immediately visible to the other.

---

## Key Features

- **Agentic retrieval loop** — iterative query reformulation and evidence accumulation; stops when quality is satisfied or the retrieval budget is exhausted
- **Two-track retrieval** — source `documents` and self-learned `learned_qa` are retrieved, validated, deduplicated, and compressed as independent channels, combined only at the LLM context boundary with an explicit learned-QA-takes-precedence rule
- **Three-stage context compression** — Neighbor-Aware Compression → Deduplication Compression → LLM-Based Compression, each with an LLM-as-judge validator
- **Self-learning** — after every N successful interactions, verified Q&A pairs are distilled back into the `learned_qa` ChromaDB collection and used in future retrievals
- **Multi-tier LLM output repair** — a 5-stage pipeline (`fix_llm_output.py`) recovers structured JSON from malformed LLM output (markdown fences, truncation, wrong types, code instead of JSON, etc.) before it reaches Pydantic validation
- **Thumbdown persistence** — bad answers are logged with full query variants and user feedback; subsequent identical queries block the entire prior failing search trajectory
- **Single custom LLM endpoint (`app_workflow/`)** — all four roles (`llm`, `llm_tool`, `judge_llm`, `json_fix_llm`) are routed to one self-hosted, OpenAI-compatible endpoint (`CUSTOM_API_BASE`). Groq and the Hugging Face Inference Providers router were both evaluated for `judge_llm`/`json_fix_llm` and retired after a head-to-head latency/reliability benchmark showed the HF router degrading validator quality under quota pressure (see `Status.md` 2026-07-08). Query-variant generation no longer uses tool-calling — it asks the LLM for a plain JSON array, parsed via `fix_llm_output`. `app/` uses Groq (`llama-3.1-8b-instant`) exclusively for all roles.
- **Three tracing backends (`app_workflow/`)** — LangSmith, Langfuse, and self-hosted Arize Phoenix are supported. Langfuse and Phoenix capture the shared LangChain/LangGraph operation hierarchy; application log records are also mirrored into active traces. See [Setting Up Tracing](#setting-up-tracing) for credentials, feature flags, and the current backend-combination limitation.
- **Structured error handling** — `LLMResult` dataclass with an `LLMErrorKind` taxonomy, a FIFO serialization gate, and adaptive-cooldown retry across both pipelines
- **MongoDB-backed persistence** — interaction history, thumbdowns, and failed query variants are stored transactionally (replacing the original flat-file JSON/JSONL design)
- **HTTP API for both pipelines** — `POST /query`, `POST /feedback/bad`, `GET /stats`, `POST /learn`, `POST /quit` on both `app/api.py` and `app_workflow/api.py`

---

## Technology Stack

| Layer | Technology |
|---|---|
| Embedding model | `all-MiniLM-L6-v2` (SentenceTransformers, 384-dim) |
| Embedding hardware | CUDA GPU when available, falls back to CPU automatically |
| Vector store | ChromaDB — local persistent HNSW index, two collections (`documents`, `learned_qa`), shared by both pipelines |
| LLM inference (`app/`, all roles) | Groq (`llama-3.1-8b-instant`) via LangChain `ChatOpenAI` |
| LLM inference (`app_workflow/`, all four roles: `llm`, `llm_tool`, `judge_llm`, `json_fix_llm`) | Self-hosted/custom OpenAI-compatible endpoint (`CUSTOM_API_BASE`, default model `llama-3.1-8b-instruct`) via `langchain_openai.ChatOpenAI`; the prior Groq and HF Inference Providers router wiring is commented out in place, not deleted |
| Observability (`app_workflow/`) | LangSmith, Langfuse, and Arize Phoenix (self-hosted, OTel/OpenInference) |
| Interaction persistence | MongoDB — `feedback_interactions`, `user_thumbdowns`, `failed_variants` collections, replica-set mode (`rs0`) required for transactional thumbdown writes |
| JSON repair | `json_repair` + Pydantic — multi-tier recovery for malformed LLM output |
| HTTP API | FastAPI + uvicorn |
| Orchestration (`app_workflow/`) | LangGraph `StateGraph` |
| Document loading | Unstructured + JSONLoader (PDF, TXT, DOCX, HTML, CSV, JSON) |
| Chunking | `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap) |
| Runtime | Python 3.14 |

---

## Project Structure

```
app/                          # LangChain implementation
├── ingest.py                 # Shared ingestion — discovery, chunking, embedding, storage
├── agent_query.py            # Orchestrator — 4-phase state machine + REPL
├── api.py                    # FastAPI server — port 8000
├── tools.py                  # LLM tool definitions (retrieve_documents, compress_context)
├── retriever.py               # Separate document + learned_qa retrieval tracks
├── embedding_manager.py       # SentenceTransformer wrapper
├── vector_store.py            # ChromaDB wrapper, batched upsert
├── context_compression.py     # NAC → DC → LBC three-stage pipeline
├── validators.py              # LLM-as-judge validators (retrieval, merge, LBC, redundancy)
├── llm_caller.py              # Structured LLM call wrapper — error taxonomy, FIFO gate, retry
├── llm_setup.py                # LLM instance construction (llm, merge_llm, judge_llm)
├── fix_llm_output.py          # Multi-tier JSON repair + Pydantic schema validation
├── db.py                      # MongoDB client singleton + index setup
├── feedback_store.py          # Interaction log + thumbdown persistence (MongoDB)
├── self_learner.py            # Distillation engine — writes to learned_qa collection
├── learned_qa_store.py        # Canonical learned_qa collection factory (cosine metric)
├── config.py                  # Constants + feature flags
├── prompts.py                  # All prompt strings
├── logger_config.py            # Central logging setup
├── timing_tracker.py           # Per-stage timing instrumentation
├── query.py                    # Standalone single-pass RAG CLI (no agent loop)
└── run_batch.py                # Non-interactive batch runner for test suites

app_workflow/                  # LangGraph implementation
├── main.py                    # REPL entry point
├── api.py                     # FastAPI server — port 8001
├── graph.py                   # Graph wiring (~30 nodes, conditional fan-out/fan-in)
├── state.py                   # GraphState — dual-track fields at every pipeline stage
├── routes.py                  # Conditional routing functions
├── config.py                  # Constants + feature flags (independent of app/config.py)
├── nodes/                     # One file per graph node (retrieve, nac, dc, lbc,
│                               #   validate_retrieval, dedup_merge, generate_draft,
│                               #   check_answer_quality, generate_answer, ...)
└── services/                  # Same roles as app/'s flat modules, packaged
    ├── services.py             # Instance registry (embedding manager, retriever, LLMs, ...)
    ├── llm_setup.py             # llm, llm_tool, judge_llm, json_fix_llm — all on one custom OpenAI-compatible endpoint
    ├── llm_caller.py             # FIFO gate + retry, Groq/OpenAI/httpx exception handling
    ├── fix_llm_output.py         # Same repair pipeline as app/, own json_fix_llm
    ├── langfuse_tracing.py        # Langfuse callback construction
    ├── langfuse_logging.py        # LangfuseHandler — mirrors logging records as Langfuse events
    ├── phoenix_tracing.py         # Arize Phoenix OTel/OpenInference instrumentation (setup_phoenix_tracing)
    ├── operation_tracing.py       # instrument_namespace() + TraceSpec — central function-level tracing policy
    ├── trace_events.py            # Retrieve LangSmith trace log events by run ID
    ├── db.py, feedback_store.py, learned_qa_store.py, self_learner.py, ...

data/
├── vector_store/               # ChromaDB: chroma.sqlite3 + UUID HNSW folder (keep together)
│                                #   — shared by app/ and app_workflow/
└── <source documents>          # Raw PDFs / text / CSV / etc. consumed by app/ingest.py

useful_but_not_valuable_Files/  # Diagnostic/analysis scripts, not part of either pipeline
```

---

## Quick Setup

**Prerequisites:** Python 3.14, a running MongoDB instance configured as a single-node replica set (`rs0` — required for transactional thumbdown writes), a Groq API key, and access to a self-hosted/custom OpenAI-compatible LLM endpoint if you plan to run `app_workflow/` (all four of its LLM roles route through `CUSTOM_API_BASE`). Tracing accounts or a local Phoenix collector are optional; see [Setting Up Tracing](#setting-up-tracing).

```powershell
# 1. Create environment
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install GPU PyTorch first if you have a CUDA GPU (skips to CPU automatically otherwise)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 3. Install remaining dependencies
pip install -r requirements.txt

# 4. Configure environment — create a .env file at the project root with:
#   GROQ_API_KEY=...
#   CUSTOM_API_BASE=...               # required for app_workflow/'s llm / llm_tool / judge_llm / json_fix_llm
#   CUSTOM_API_KEY=...
#   CUSTOM_API_MODEL_NAME=llama-3.1-8b-instruct   # optional, this is the default
#   MONGODB_URI=mongodb://localhost:27017
#   MONGODB_DB_NAME=rag_db
#   Tracer variables are documented in "Setting Up Tracing" below.

# 5. Initialise the MongoDB replica set (one-time)
#   add `replSetName: "rs0"` to mongod.cfg, restart MongoDB, then:
mongosh --eval "rs.initiate()"

# 6. Ingest documents (populates the shared vector store — run once)
cd app
python ingest.py

# 7a. Run the LangChain agent
python agent_query.py

# 7b. ...or the LangGraph agent
cd ../app_workflow
python main.py
```

**Verify GPU is active (optional):**
```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# Expected: True 12.x — if False, embeddings fall back to CPU automatically
```

---

## Setting Up Tracing

Tracing applies to the `app_workflow/` LangGraph implementation. Install the project dependencies first. If `langfuse` is not already available in the active environment, install its SDK separately:

```powershell
pip install -r requirements.txt
pip install langfuse arize-phoenix-otel openinference-instrumentation-langchain
```

Choose the backend configuration below, then start either `python app_workflow/main.py` or the port-8001 API. Both entry points initialize tracing at process startup.

### 1. LangSmith

Create a LangSmith API key and add the following values to the root `.env` file:

```dotenv
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-api-key>
LANGCHAIN_PROJECT=rag-work
# LANGCHAIN_ENDPOINT=https://api.smith.langchain.com  # optional override
```

LangSmith uses LangChain's environment-driven instrumentation, so it has no separate feature flag in `app_workflow/config.py`. Set `LANGCHAIN_TRACING_V2=false` (or remove it) to disable uploads. To print the log events mirrored into a stored LangSmith trace, pass one of its run IDs to:

```powershell
python -m app_workflow.services.trace_events <run-id>
```

### 2. Langfuse

Create a Langfuse project, copy its public and secret keys into `.env`, and set the host for Langfuse Cloud or your self-hosted deployment:

```dotenv
LANGFUSE_PUBLIC_KEY=<your-public-key>
LANGFUSE_SECRET_KEY=<your-secret-key>
LANGFUSE_BASE_URL=https://cloud.langfuse.com
# LANGFUSE_HOST=<your-langfuse-url>  # supported fallback to LANGFUSE_BASE_URL
```

Enable the callback in `app_workflow/config.py`:

```python
ENABLE_LANGFUSE_TRACING = True
ENABLE_PHOENIX_TRACING = False
```

The CLI, API `/query`, and API `/learn` paths pass this callback through to the graph and nested LLM calls. Set `ENABLE_LANGFUSE_TRACING = False` to disable it.

A dedicated `LangfuseHandler` (`services/langfuse_logging.py`) is also registered as a fourth root log handler at `DEBUG` level, alongside console, file, and `_TracingHandler`. It mirrors every log record onto the active Langfuse trace as an `event` observation, independent of the callback above — so per-function detail is visible in the Langfuse UI even without inspecting `.debug.log` files directly.

### 3. Arize Phoenix

Start or otherwise provide a Phoenix instance with an OTLP gRPC collector reachable by the application. The default collector address expected by this repository is `http://localhost:4317`; the Phoenix UI is commonly exposed separately by the Phoenix deployment.

Add the collector and project name to `.env`:

```dotenv
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
PHOENIX_PROJECT_NAME=rag-work
```

Then select Phoenix in `app_workflow/config.py`:

```python
ENABLE_PHOENIX_TRACING = True
ENABLE_LANGFUSE_TRACING = False
```

Phoenix is registered once at startup and auto-instruments LangChain/LangGraph through OpenInference. Set `ENABLE_PHOENIX_TRACING = False` to disable it.

> **Backend compatibility:** LangSmith can remain enabled alongside either callback backend. Do not enable Langfuse and Phoenix together in the current implementation: both attach to the process-global OpenTelemetry provider, and one exporter can silently replace the other. Select exactly one of `ENABLE_LANGFUSE_TRACING` and `ENABLE_PHOENIX_TRACING` until tracer-provider isolation is implemented.

After startup, run one query and confirm a new trace appears in the selected backend/project. Trace payloads are bounded by the policy in `app_workflow/services/operation_tracing.py`; credentials, callback/config objects, and client/handler arguments are excluded.

---

## Running the HTTP APIs

Both pipelines expose the same five endpoints on different ports:

```powershell
# LangChain pipeline — port 8000
cd app
uvicorn api:app --host 0.0.0.0 --port 8000

# LangGraph pipeline — port 8001
cd app_workflow
uvicorn api:app --host 0.0.0.0 --port 8001
```

| Endpoint | Purpose |
|---|---|
| `POST /query` | Run the agent on a query; returns answer, quality, sources, per-track chunks |
| `POST /feedback/bad` | Flag an interaction as bad by `request_id`; persists a thumbdown |
| `GET /stats` | Interaction counts and self-learning status |
| `POST /learn` | Trigger distillation on-demand |
| `POST /quit` | Clean shutdown |

---

## Usage (CLI)

```
Your question: What are the main components of an ASD evaluation?

Commands:
  bad    — flag the last answer (opens feedback prompt; ≥10 chars recommended)
  stats  — show interaction counts and self-learning status
  learn  — force distillation now (normally auto-triggers every N good interactions)
  quit   — exit
```

Both `app/agent_query.py` and `app_workflow/main.py` support the same command set.

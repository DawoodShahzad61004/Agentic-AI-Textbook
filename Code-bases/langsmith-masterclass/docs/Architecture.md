# Architecture

## System Overview

`langsmith-masterclass` is a set of standalone teaching scripts that follow along with a
LangSmith observability course (see Research.md topic 1). Each numbered script is a
self-contained demo — a simple LLM call, a sequential chain, four progressive versions of a
PDF RAG app, a ReAct tool-using agent, and a LangGraph fan-out/fan-in essay grader — used to show
how LangSmith traces projects, traces, and runs as complexity increases.

## High-Level Architecture

```
.env (CUSTOM_API_BASE / CUSTOM_API_KEY / HF_TOKEN / LANGCHAIN_*)   -- no OPENAI_API_KEY needed anymore
   |
   v
llm_setup.py  --(single shared `llm` client)-->  1_simple_llm_call.py
   |                                             2_sequential_chain.py
   |                                             3_rag_v1.py / v2 / v3 / v4
   |                                             4_agent.py
   |                                             5_langgraph.py

3_rag_v1.py → v2 → v3 → v4   (PDF RAG, progressively adds LangSmith `@traceable` tracing,
                               then FAISS index caching — see Research.md topic 1)
   PDF (islr.pdf) -> PyPDFLoader -> RecursiveCharacterTextSplitter
        -> HuggingFaceEndpointEmbeddings (HF Inference router) -> FAISS
        -> retriever -> RunnableParallel(context, question) -> ChatPromptTemplate -> LLM
        -> StrOutputParser

4_agent.py     : ReAct agent (DuckDuckGo search tool + weatherstack tool) via AgentExecutor
5_langgraph.py : StateGraph fan-out (3 parallel essay-evaluation nodes) -> fan-in (final
                 evaluation node), structured output via prompt + PydanticOutputParser
```

Every script now runs entirely on the local TGI Proxy (chat) + HF Inference router (embeddings)
stack — there is no remaining runtime dependency on the OpenAI API anywhere in the project. See
ADR-003.

## Module Breakdown

### `llm_setup.py`
Centralizes LLM client construction so scripts don't hardcode credentials. Points at a local
OpenAI-compatible **TGI Proxy** server via `CUSTOM_API_BASE` / `CUSTOM_API_KEY`
(`llama-3.1-8b-instruct` by default). As of 2026-07-09 this defines a single client, `llm` —
the previously-defined-but-unused `llm_tool`, `judge_llm`, `json_fix_llm` clients and the
commented-out `ChatGroq` block were removed as part of an intentional cleanup pass. Every script
in the project now imports this one `llm`.

The local TGI Proxy server only implements `/v1/chat/completions`, `/v1/completions`, and
`/health` — **no embeddings endpoint** (confirmed via its `/openapi.json`; see Bugs.md BUG-001,
Decisions.md ADR-001). Any embeddings client must go elsewhere (currently the Hugging Face
Inference router).

### `1_simple_llm_call.py`
One-line `PromptTemplate` → `llm` (from `llm_setup`) → `StrOutputParser`. Minimal LangSmith demo:
tracing appears automatically from `.env` config, no explicit LangSmith code needed.

### `2_sequential_chain.py`
Two-step chain: generate a detailed report on a topic, then summarize it into 5 points, both
through `llm` from `llm_setup`. Passes an explicit `run_name`, `tags`, and `metadata` via the
`config` dict on `.invoke()` — demonstrates LangSmith trace labeling.

### `3_rag_v1.py` — baseline PDF RAG
Loads `islr.pdf`, chunks with `RecursiveCharacterTextSplitter` (1000/150), embeds with
`HuggingFaceEndpointEmbeddings` (`sentence-transformers/all-MiniLM-L6-v2` via the HF Inference
router, `provider="hf-inference"`), indexes in-memory with FAISS, answers via `llm` from
`llm_setup`. No `@traceable` instrumentation — LangSmith only sees the LangChain-runnable part
of the chain (retriever/prompt/LLM/parser), not the PDF-load/chunk/embed setup steps. No index
persistence — rebuilds the FAISS index on every run. See Bugs.md BUG-001 for how the embeddings
client arrived at HF instead of the local server.

### `3_rag_v2.py` — adds `@traceable` setup tracing
Same pipeline as v1, but `load_pdf`, `split_documents`, and `build_vectorstore` are each wrapped
in `@traceable` (with per-step tags/metadata), and called from a parent `@traceable
setup_pipeline` function. Makes the previously-invisible setup phase show up in LangSmith as its
own traced sub-tree. Still rebuilds the index on every run (no caching yet).

### `3_rag_v3.py` — adds a single root trace
Same as v2, but the whole pipeline (`setup_pipeline` + retrieval chain + query) is wrapped in one
top-level `@traceable(name="pdf_rag_full_run")` function, so a single LangSmith trace covers
setup and query together instead of two disconnected traces.

### `3_rag_v4.py` — adds FAISS index persistence/caching
Solves v1–v3's "rebuild the index every run" latency problem: computes a cache key from a
SHA-256 file fingerprint of the PDF plus chunk size/overlap/embedding-model, stores/loads the
FAISS index under `.indices/<key>/` via `FAISS.save_local` / `FAISS.load_local`
(`allow_dangerous_deserialization=True`), and only rebuilds when the fingerprint or parameters
change. As of 2026-07-09, embeddings and generation both run on the same local/HF-router stack as
v1–v3 (`HuggingFaceEndpointEmbeddings`, default model `sentence-transformers/all-MiniLM-L6-v2`,
overridable via the `embed_model_name` param; `llm` from `llm_setup`) — previously this version
used real OpenAI `text-embedding-3-small` embeddings and a bare `ChatOpenAI(model="gpt-4o-mini")`,
which broke once the OpenAI API key stopped working (see ADR-003). The embedding-model name is
still part of the cache-key fingerprint, so switching providers naturally invalidates any
stale `.indices/` cache built under the old OpenAI embedding dimensions.

### `4_agent.py`
ReAct agent (`create_react_agent` + `AgentExecutor`, pulled from LangChain Hub prompt
`hwchase17/react`) with two tools: `DuckDuckGoSearchRun` and a custom `get_weather_data` tool
hitting the weatherstack API. Uses `llm` from `llm_setup` as of 2026-07-09 (previously a bare
`ChatOpenAI()`, see ADR-003) — the ReAct Thought/Action/Observation loop works correctly against
the local model. No `@traceable` — relies on LangSmith's native agent/tool tracing. Note: the
weatherstack API key hardcoded in `get_weather_data` currently returns
`usage_limit_reached` (monthly free-tier cap) — see Bugs.md BUG-003; this is independent of the
LLM backend.

### `5_langgraph.py`
`StateGraph` with `UPSCState` (`TypedDict`). Fans out from `START` into three parallel evaluation
nodes (`evaluate_language`, `evaluate_analysis`, `evaluate_thought`), each `@traceable`, calling a
shared `evaluate_dimension()` helper to produce `{feedback, score}`; scores merge into
`individual_scores` via `Annotated[List[int], operator.add]`. All three join into
`final_evaluation`, which summarizes feedback and averages the scores. Uses `llm` from
`llm_setup` as of 2026-07-09 (previously a bare `ChatOpenAI(model="gpt-4o-mini")`, see ADR-003).
Structured output no longer uses `with_structured_output` (LangChain's tool-calling-based
method) — the local TGI Proxy's tool-call response isn't OpenAI-compatible enough for it to work
reliably (see Bugs.md BUG-002). `evaluate_dimension()` instead prompts for JSON directly and
parses with `PydanticOutputParser`, which works against any plain chat-completions endpoint.

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Chat LLM (all scripts) | `llama-3.1-8b-instruct` via local TGI Proxy (`CUSTOM_API_BASE`) | OpenAI-compatible chat/completions only, no embeddings — see BUG-001. Every script (1, 2, 3_v1–v4, 4, 5) uses this via `llm_setup.llm` as of 2026-07-09 — see ADR-003 |
| Embeddings (3_v1–v4) | `sentence-transformers/all-MiniLM-L6-v2` via HF Inference router | `HuggingFaceEndpointEmbeddings`, `provider="hf-inference"`, `HF_TOKEN` — see ADR-001, ADR-003 |
| Structured output (5) | Prompt + `PydanticOutputParser` | Not `with_structured_output`/tool-calling — incompatible with the local proxy, see BUG-002 |
| Vector store | FAISS (`faiss-cpu`) | In-memory (v1–v3) or persisted to `.indices/<hash>/` (v4) |
| PDF loading | `PyPDFLoader` (`langchain_community`) | One `Document` per page |
| Observability | LangSmith (`LANGCHAIN_TRACING_V2`, `langsmith.traceable`) | Auto-traces LangChain runnables; `@traceable` needed for plain Python steps |
| Agent tools | DuckDuckGo search, weatherstack API | `4_agent.py` only; weatherstack currently rate-limited, see BUG-003 |
| Orchestration (5) | LangGraph `StateGraph` | Fan-out/fan-in with `operator.add` state merging |

**OpenAI API is no longer a runtime dependency anywhere in this project** (`OPENAI_API_KEY` was
removed from `.env`) — see ADR-003.

## Changelog

### 2026-07-08 — Local-server migration for chat, HF-router migration for embeddings (`3_rag_v1.py`)
`llm_setup.py` centralizes chat-LLM construction against a local TGI Proxy server
(`CUSTOM_API_BASE`/`CUSTOM_API_KEY`, `llama-3.1-8b-instruct`); `1_simple_llm_call.py` and
`2_sequential_chain.py` were already wired to import `llm` from it by the time this session's
work began. This session's concrete change: `3_rag_v1.py`'s embeddings client was pointed at the
local server first, discovered to 404 because the server has no embeddings route at all
(BUG-001), then switched to `HuggingFaceEndpointEmbeddings` over the HF Inference router
(ADR-001). A project `.venv` was created on Python 3.12 (ADR-002); `langchain-huggingface==0.3.1`
was added as a dependency, pinned below `1.0.0` to stay compatible with the existing
`langchain-core<1.0.0` pin used by `langchain`/`langchain-community`/`langchain-openai`.

---

### 2026-07-09 — OpenAI dependency removed project-wide; `llm_setup.py` trimmed to one client; tracking docs moved into `docs/`
`.env` was intentionally trimmed (dropping `GROQ_*`, `MODEL_NAME`, `GEN_MODEL_NAME`,
`JUDGE_MODEL_NAME`, `JSON_FIX_MODEL_NAME`, `OPENAI_API_KEY`) after the OpenAI API key stopped
working; `HF_TOKEN` was briefly dropped in the same pass and restored after review, since
`3_rag_v1`–`v4` depend on it for embeddings. `llm_setup.py` was trimmed from four clients down to
one (`llm`) — `llm_tool`, `judge_llm`, `json_fix_llm`, and the commented `ChatGroq` block were
unused and removed. To close the resulting gap, `3_rag_v4.py`, `4_agent.py`, and `5_langgraph.py`
were migrated off the OpenAI API onto the same local-TGI/HF-router stack as `3_rag_v1`–`v3`
(ADR-003); this required reworking `5_langgraph.py`'s structured output away from
`with_structured_output` (BUG-002). Dead `OpenAIEmbeddings`/`ChatOpenAI` imports left over in
`3_rag_v2.py`/`3_rag_v3.py` were also removed. Separately, `.gitignore` was trimmed (dropping the
Graphify/Claude section and the block excluding `Decisions.md`/`Architecture.md`/`Bugs.md`/
`Research.md`/`Status.md`), and those five tracking files plus the course transcript and tracking
guide were moved into a `docs/` folder — the tracking system is now committed to the repo rather
than kept local-only (ADR-004).

---

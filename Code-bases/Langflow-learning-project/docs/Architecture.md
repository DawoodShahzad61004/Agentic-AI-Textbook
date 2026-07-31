# Architecture

## System Overview

A Langflow learning project: a set of exported Langflow flows (`flows/*.json`) used to learn
Langflow's visual flow builder on Windows. The work covers standing up Langflow locally,
building basic prompting flows against a Groq LLM, probing whether Langflow supports cyclic
(looping) execution, and — the largest piece of work — porting an external agentic RAG system
("Memora": dual-track retrieval, NAC/DC/LBC context compression, LLM-judge validators,
feedback/self-learning) into Langflow as a single generated, Custom-Component flow
(`flows/LangGraph RAG Pipeline.json`, ADR-006). There is no custom *application* code in the
traditional sense — the "system" is the local Langflow runtime plus these flow definitions —
but the RAG pipeline's node bodies are substantial generated Python (Custom Components), not
stock Langflow wiring.

## High-Level Architecture

```
Host: Windows 11  ·  Python 3.12 venv (.venv)  ·  langflow 1.10.2  ·  served at http://127.0.0.1:7860

Flows (imported into the local Langflow runtime):

  1) Basic LLM Prompting  (acyclic baseline)
       Chat Input ──▶ Prompt Template ──▶ Groq (llama-3.1-8b-instant) ──▶ Chat Output

  2) Basic Prompting  (cyclic loop test)
       Read File ──(dataframe)──▶ Loop ──(data)
                                   │
                              (item) ▼
                             Type Convert ──▶ Prompt Template ◀──(user_input)── Chat Input
                                                   │ (task)
                                                   ▼
                                                 Groq ──▶ Type Convert (JSON) ──┐
                                                                                │ back-edge
                                                        Loop.Looping ◀──────────┘
                             Loop.done ──▶ Type Convert (Message) ──▶ Chat Output
       (A disconnected Prompt Template ▶ Language Model ▶ Chat Output branch is a leftover
        experiment and is not part of the running cycle.)

  3) Simple Agent
       Chat Input ─┐
       Calculator ─┼──▶ Agent ──▶ Chat Output
       URL ────────┘

  4) New Flow  (stub: a single Chat Input node, nothing wired)

  5) LangGraph RAG Pipeline  (Memora port — 47 Custom Components, 85 edges, acyclic)
       Chat Input ──▶ user_input ──▶ generate_query_variants ──▶ Knowledge×2 (Retrieve) ──▶ retrieve
         ──▶ post_retrieval_filter ──▶ validate_retrieval×2 ──▶ dedup_merge×2 ──▶ validate_dedup_merge×2
         ──▶ [documents: NAC → validate_NAC → DC → validate_DC → LBC → validate_LBC]
             [learned_qa:            DC → validate_DC → LBC → validate_LBC]
         ──▶ combine_tracks ──▶ generate_draft ──▶ check_answer_quality ──▶ generate_answer ──▶ Chat Output
       Side branches: cmd_stats / cmd_learn / cmd_bad / cmd_exit off `user_input`; an ingestion
       chain (`discover_files → marker_loader → split_documents → Knowledge·documents (Ingest)`)
       feeding the same Knowledge Bases the query path reads from. Three OpenAI-compatible
       local clients (Generation / Judge / JSON Repair) point to
       `http://192.168.1.13:3001/v1` and fan out to the LLM-calling nodes. Retry back-edges
       into `generate_query_variants` were present in early iterations but were later removed
       (ADR-009) — the flow is currently a single deterministic pass, not a retry loop.

  6) Vector Store RAG  (reference template, 7 nodes)
       Chat Input ──▶ Knowledge (Retrieve) ──▶ parser ──▶ Prompt ──▶ Groq ──▶ Chat Output
       Also wires a Memory Base node. Used as the worked example for the native `Knowledge` /
       `Memory Base` node shapes referenced by ADR-007 / ADR-008.
```

## Module Breakdown

### `flows/Basic LLM Prompting.json`
Acyclic baseline. `Chat Input → Prompt Template → Groq → Chat Output`. Groq model is
`llama-3.1-8b-instant`. Demonstrates the simplest forward-only prompting path. 6 nodes / 3 edges.

### `flows/Basic Prompting.json` and `flows/Basic Prompting (1).json`
The cyclic-loop test (see Research topic 1, ADR-005). A `Read File` supplies CSV rows as a
dataframe to a `Loop`; each `Loop.item` is JSON-converted, merged with the `Chat Input`
message in a `Prompt Template`, sent to `Groq`, converted back to JSON, and fed to
`Loop.Looping` to close the cycle. `Loop.done` converts the aggregate to a message for
`Chat Output`. The two files are near-duplicates (identical node set; edges differ slightly —
successive save iterations). Each contains a disconnected `Language Model` branch left over
from an OpenAI attempt. 14 nodes / 11 edges each. Note: the `description` field says "OpenAI"
but the live model is Groq (ADR-004, Research topic 3). Its `data/langflow_cycle_test.csv`
input file was deleted from the repository on 2026-07-27 as part of a broader cleanup — the
flow definition still references it by path, but the file must be re-created to re-run this
flow.

### `flows/Simple Agent.json`
An `Agent` component given two tools — `Calculator` and `URL` — with `Chat Input` in and
`Chat Output` out. Demonstrates tool-using agent wiring. 7 nodes (incl. 2 notes) / 4 edges.

### `flows/New Flow.json`
A stub containing a single unconnected `Chat Input` node. Placeholder / scratch flow.

### `flows/LangGraph RAG Pipeline.json`
The Memora RAG port (ADR-006). 51 total nodes / 85 edges, currently acyclic
(ADR-009). Every Memora-specific behavior — query-variant generation, per-track retrieval
filtering and LLM-judge validation, neighbour-aware / duplicate-content / line-by-line
compression (NAC/DC/LBC) with a validator after each stage, draft generation, grounding
check, final answer, and self-distillation — is a Custom Component whose Python body was
generated from, and unit-tested against, the original LangGraph node source files
(`user_input.py`, `query_variants.py`, `retrieve.py`, `post_retrieve.py`,
`validate_retrieval.py`, `dedup_merge.py`, `nac.py`, `dc.py`, `lbc.py`, `combine_tracks.py`,
`generate_draft.py`, `check_answer_quality.py`, `generate_answer.py`, `auto_distillation.py`,
`no_context_answer.py`, `commands.py`). Retrieval is backed by two native `Knowledge` nodes
(ADR-007) instead of a direct Chroma client; the original MongoDB feedback store's read side
was briefly a `Memory Base` node before being removed (ADR-008). A separate ingestion branch
(`discover_files` → `marker_loader` → `split_documents` → `Knowledge · documents (Ingest)`)
mirrors the source system's `ENABLE_MARKER_LOADER` / `ENABLE_CUSTOM_SPLITTER` switches. Three
role-scoped local `ChatOpenAI` clients (Generation / Judge / JSON Repair) fan out to every
LLM-calling node. They use `llama-3.1-8b-instant` through the `LOCAL-LLM` global variable and
the LAN API base in ADR-010. The auxiliary similarity model is a real local
`HuggingFaceEmbeddings` wrapper over cached `sentence-transformers/all-MiniLM-L6-v2`
(BUG-011, closed).

### `flows/1.json` – `flows/9.json`
Nine historical Playground/canvas exports of the `LangGraph RAG Pipeline` flow, captured
across the build-and-debug session (self-build → manual UI edits → a second assistant's DNS,
embeddings-provider, and routing fixes). Node/edge counts step down from 52/103 (`1.json`) to
47/85 (`9.json`), tracking the retry-cycle removal in ADR-009. Later local-embedding,
retrieval-fallback, and local-LLM changes exist only in the current
`flows/LangGraph RAG Pipeline.json`; all numbered snapshots are records, not flows to import.

### `flows/Vector Store RAG.json`
A small (7-node) reference flow — `Chat Input → Knowledge (Retrieve) → parser → Prompt → Groq
→ Chat Output`, plus a `Memory Base` node — used as the worked example for wiring Langflow's
native `Knowledge` and `Memory Base` nodes before they were adopted in the RAG pipeline port
(ADR-007, ADR-008).

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Flow runtime | Langflow 1.10.2 | Pinned to avoid the LiteLLM Windows build gap — ADR-002, BUG-005 |
| Language | Python 3.12.10 | In `.venv`; chosen over machine-default 3.14 — ADR-003 |
| Env / package manager | `uv` | `uv venv` + `uv pip install`; not Docker — ADR-001 |
| RAG LLM provider | Local OpenAI-compatible server · `llama-3.1-8b-instant` | `ChatOpenAI` at `http://192.168.1.13:3001/v1`; `LOCAL-LLM` global variable — ADR-010 |
| Legacy-flow LLM provider | Groq · `llama-3.1-8b-instant` | Older basic prompting/loop flows only — ADR-004 |
| Cyclic execution | Langflow `Loop` component | Bounded back-edge over CSV rows — ADR-005, Research topic 1 |
| Agent tools | `Calculator`, `URL` | Used in `Simple Agent.json` |
| Vector storage | Langflow `Knowledge` node (Chroma-backed) | Two KBs: `documents`, `learned_qa` — ADR-007, replaces a direct `chromadb.PersistentClient` |
| Long-term memory | *(removed)* Langflow `Memory Base` node | Considered, then dropped — ADR-008 |
| Auxiliary similarity embeddings | Local MiniLM (`sentence-transformers/all-MiniLM-L6-v2`) | Cached, normalized 384-dimensional embeddings; no API key — BUG-011 |
| Knowledge Base embeddings | Per-Knowledge-Base provider | Managed by Langflow's Knowledge Base metadata and separate from the auxiliary MiniLM node |
| Document ingestion | `discover_files` → `marker_loader` → `split_documents` → `Knowledge (Ingest)` | Mirrors `ENABLE_MARKER_LOADER` / `ENABLE_CUSTOM_SPLITTER` from the ported source |
| Host OS | Windows 11 | Served at `http://127.0.0.1:7860` |

## Changelog

### 2026-07-23 — Local Langflow environment and initial flows

Established the local runtime after abandoning Docker (ADR-001, closing BUG-001 and BUG-002
as off-path). Created a Python 3.12 `.venv` via `uv` (ADR-003) and installed
`langflow==1.10.2` with `--only-binary=litellm`, resolving `litellm==1.91.4` and fixing the
Windows build failure (ADR-002, BUG-005). Wired the prompting flows to Groq
`llama-3.1-8b-instant` (ADR-004). Built the cyclic loop test flow (`Read File → Loop → …Groq…
→ Loop.Looping`, `Loop.done → Chat Output`) with `data/langflow_cycle_test.csv` and confirmed
Langflow supports bounded cyclic execution (ADR-005, Research topics 1–2). New dependency on
`data/langflow_cycle_test.csv` as loop input.

### 2026-07-24 — Documentation and repository setup

Added the five-file Markdown tracking system under `docs/` (`Status`, `Architecture`,
`Decisions`, `Research`, `Bugs`) and a top-level `README.md`. Added `.gitignore`
(ignores `.venv/`, agent config files). No change to the flows or their runtime shape.

### 2026-07-27 — Port the Memora RAG system into Langflow, then debug it into (near) working order

Generated `flows/LangGraph RAG Pipeline.json`: 20+ Custom Components reproducing an external
LangGraph agentic-RAG app's node logic, assembled and validated by a script rather than built
by hand (ADR-006). Retrieval was rebuilt on native `Knowledge` nodes instead of a direct Chroma
client (ADR-007); a `Memory Base` node was added for feedback/history then removed at the
user's request (ADR-008). Added a document-ingestion branch (`discover_files` →
`marker_loader` → `split_documents` → `Knowledge (Ingest)`) and per-role Groq clients
(Generation / Judge / JSON Repair). An audit against the real source node files found and
fixed 13 behavioral divergences (retry-count semantics, chunk shape, missing pre-retrieval
dedup, validators mutating state, etc.) before the flow was ever opened in the Langflow UI.

Once imported, the flow needed several more rounds of debugging, captured as BUG-006 through
BUG-011: a live Groq key had leaked into the exported JSON (removed from the current export);
fresh
imports failed Langflow's pre-flight check because `Knowledge`/`Memory Base` selections are
per-user resources no export can carry; the Hugging Face embeddings node hit a local DNS
failure; a follow-on embeddings node had an empty required API key, aborting the run before
any Chat Output could build; a Chroma-distance-vs-similarity sign mismatch caused
`generate_draft` to never run; and the routing was flattened from a multi-branch retry cycle
to a single deterministic path (ADR-009) after conditional branches sharing an input field hit
a Langflow build-order hazard. BUG-011 was later closed with a true local MiniLM implementation;
retrieval now retains the best two ranked rows when fixed thresholds would discard every result;
and ADR-010 moved all RAG inference from Groq to the local OpenAI-compatible server.

Also removed the sample data added earlier the same day — `data_files/{csv,html,pdfs,word}/*`
(four autism-spectrum-disorder documents used to test the ingestion branch) and the old
`data/langflow_cycle_test.csv` — and added `data_files/` to `.gitignore`. New dependency: two
Langflow Knowledge Bases (`documents`, `learned_qa`) must exist in the target Langflow
instance's own storage for `flows/LangGraph RAG Pipeline.json` to run (Research topic 5).

---

# Langflow Learning Project

A hands-on project for learning [Langflow](https://www.langflow.org/)'s visual flow builder on
Windows. It started as a small set of exported flows (`flows/*.json`) built while learning
basic prompting, agents, and whether Langflow supports **cyclic (looping) execution** — and
grew to include a much larger experiment: porting an external agentic RAG system into Langflow
as a single generated, Custom-Component flow (`flows/LangGraph RAG Pipeline.json`).

There is no custom application code in the traditional sense. The "project" is the local
Langflow runtime plus these flow definitions, the documentation of how they came to be, and —
for the RAG pipeline — the generated Python Custom Components that back its nodes.

> **Status:** the current RAG export is structurally validated and uses a local
> OpenAI-compatible LLM server plus local MiniLM similarity embeddings. After each import,
> reselect the per-user Knowledge Bases and the `LOCAL-LLM` global variable. See
> [docs/Status.md](docs/Status.md) for the debugging trail and operational caveats.

## Quick Start

Prerequisites: Windows, Python 3.12 available, and [`uv`](https://docs.astral.sh/uv/).

```powershell
# Create and activate a Python 3.12 virtual environment
uv venv --python 3.12 .venv
.\.venv\Scripts\Activate.ps1

# Install Langflow (pinned — see docs/Decisions.md ADR-002)
uv pip install --only-binary=litellm "langflow==1.10.2"

# Run it
langflow run
# open http://127.0.0.1:7860
```

> **Why the pin?** The latest Langflow (1.11.0) pulls `litellm==1.93.0`, which has no Windows
> wheel and fails to compile without the MSVC linker. `langflow==1.10.2` resolves the
> wheel-having `litellm==1.91.4` and installs with no compiler. Full story in
> [docs/Bugs.md](docs/Bugs.md) (BUG-005) and [docs/Decisions.md](docs/Decisions.md) (ADR-002).

### Importing the flows

In the Langflow UI, use **Import** and select a file from [flows/](flows/). The older basic
prompting/loop flows still use Groq as recorded by ADR-004. The RAG pipeline now uses three
OpenAI-compatible local clients pointed at `http://192.168.1.13:3001/v1`; select the
`LOCAL-LLM` global variable on each client after import (ADR-010).

### Docker (alternative, secondary)

Docker works too but was set aside for this project (see ADR-001). If you use it, the current
image requires superuser credentials or it exits on startup:

```bash
docker run --name langflow -p 7860:7860 \
  -e LANGFLOW_AUTO_LOGIN=false \
  -e LANGFLOW_SUPERUSER=langflow \
  -e LANGFLOW_SUPERUSER_PASSWORD="<strong-password>" \
  langflowai/langflow:latest
```

For a private local instance you can instead pass `-e LANGFLOW_AUTO_LOGIN=true`. Details in
[docs/Research.md](docs/Research.md) topic 4.

## Flows

| File | What it is |
|---|---|
| [`flows/Basic LLM Prompting.json`](flows/) | Acyclic baseline: `Chat Input → Prompt Template → Groq → Chat Output`. |
| [`flows/Basic Prompting.json`](flows/) | The cyclic **Loop** test over CSV rows (see below). Its input CSV was later deleted — see [docs/Architecture.md](docs/Architecture.md). |
| [`flows/Basic Prompting (1).json`](flows/) | Near-duplicate save of the loop test. |
| [`flows/Simple Agent.json`](flows/) | An `Agent` with `Calculator` and `URL` tools. |
| [`flows/New Flow.json`](flows/) | Stub — a single unconnected `Chat Input`. |
| [`flows/LangGraph RAG Pipeline.json`](flows/) | Current 51-node RAG pipeline port, using local LLM clients and local MiniLM similarity embeddings. |
| [`flows/Vector Store RAG.json`](flows/) | Small reference flow showing native `Knowledge` + `Memory Base` node wiring. |
| [`flows/1.json`–`flows/9.json`](flows/) | Historical RAG build/debug snapshots. They no longer match the current export and are not meant to be imported independently. |

### The cyclic loop experiment

The headline experiment: **does Langflow support cyclic flows?** Yes — via the built-in `Loop`
component, which gives an explicit back-edge and a guaranteed stop condition:

```
Read File ──▶ Loop ──(item)──▶ Type Convert ──▶ Prompt Template ◀── Chat Input
                                                      │
                                                    Groq ──▶ Type Convert (JSON) ──┐
                                                                                   │ back-edge
                                            Loop.Looping ◀─────────────────────────┘
Loop.done ──▶ Type Convert ──▶ Chat Output
```

Fed with `data/langflow_cycle_test.csv` (3 rows, since deleted from the repo — recreate it to
re-run this flow), the looped section runs once per row and terminates when the list is
exhausted. One caveat learned along the way: `Chat Input` captures a single Playground message
and reuses it for every iteration — it does **not** re-prompt per row. Full findings in
[docs/Research.md](docs/Research.md) (topics 1–2) and the rationale in
[docs/Decisions.md](docs/Decisions.md) (ADR-005).

### The RAG pipeline port

`flows/LangGraph RAG Pipeline.json` reproduces an external agentic RAG system's retrieval →
compression → judging → answer pipeline as 47 Langflow Custom Components, generated and
unit-tested from the original Python node sources rather than hand-built in the UI
([docs/Decisions.md](docs/Decisions.md) ADR-006). Retrieval runs on two native `Knowledge`
nodes (`documents`, `learned_qa` — ADR-007); a `Memory Base` node for cross-run feedback was
tried and then removed (ADR-008).

**Before importing:**
1. Create two Knowledge Bases named exactly `documents` and `learned_qa` in your Langflow
   instance (any `Knowledge` node → **Create new Knowledge Base**). A flow export cannot carry
   these — see [docs/Research.md](docs/Research.md) topic 5.
2. Create a Langflow global variable named `LOCAL-LLM`, then select it on the three
   `Local LLM - *` nodes (Generation / Judge / JSON Repair). Their API base is
   `http://192.168.1.13:3001/v1` and their model ID is `llama-3.1-8b-instant` (ADR-010).
3. Ensure the local server supports `POST /v1/chat/completions`. Its `/v1/models` route was
   observed returning 404, so the model ID is configured explicitly rather than discovered.
4. The local MiniLM component requires the cached
   `sentence-transformers/all-MiniLM-L6-v2` model. It needs no embedding API key (BUG-011).

Full build and debugging history — including six bugs found along the way (a leaked API key, a
Chroma distance/similarity mismatch, a routing build-order hazard, and more) — is in
[docs/Status.md](docs/Status.md) (2026-07-27 entries) and [docs/Bugs.md](docs/Bugs.md)
(BUG-006–BUG-011).

## Repository Layout

```
.
├── flows/        Exported Langflow flows (*.json), including the RAG pipeline port
├── docs/         Project tracking system (see below)
└── README.md
```

## Documentation

This project uses a five-file Markdown tracking system — each file has one job:

| File | Answers |
|---|---|
| [docs/Status.md](docs/Status.md) | What happened, and when? (dated log) |
| [docs/Architecture.md](docs/Architecture.md) | What does the system look like now, and how did it get here? |
| [docs/Decisions.md](docs/Decisions.md) | Why did we choose X over Y? (ADRs) |
| [docs/Research.md](docs/Research.md) | What did we learn by investigating? |
| [docs/Bugs.md](docs/Bugs.md) | What broke, why, and how was it fixed? |

Entries cross-reference each other by ID (`ADR-NNN`, `BUG-NNN`, research topic numbers).

## Tech Stack

- **Langflow 1.10.2** on **Python 3.12** in a `uv`-managed `.venv`
- **Local OpenAI-compatible LLM server** at `http://192.168.1.13:3001/v1`, using
  `llama-3.1-8b-instant` for the RAG pipeline's Generation / Judge / JSON Repair roles
- **Groq** remains in the older basic prompting and loop experiments (ADR-004)
- **Langflow `Knowledge` nodes** (Chroma-backed) for RAG vector storage — `documents`,
  `learned_qa`
- **Local MiniLM** (`sentence-transformers/all-MiniLM-L6-v2`) for query-variant and
  deduplication similarity inside the flow
- Served locally at `http://127.0.0.1:7860`

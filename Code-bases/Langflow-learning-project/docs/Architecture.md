# Architecture

## System Overview

A Langflow learning project: a set of exported Langflow flows (`flows/*.json`) plus sample
data (`data/*.csv`) used to learn Langflow's visual flow builder on Windows. The work covers
standing up Langflow locally, building basic prompting flows against a Groq LLM, and probing
whether Langflow supports cyclic (looping) execution. There is no custom application code —
the "system" is the local Langflow runtime plus these flow definitions.

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
but the live model is Groq (ADR-004, Research topic 3).

### `flows/Simple Agent.json`
An `Agent` component given two tools — `Calculator` and `URL` — with `Chat Input` in and
`Chat Output` out. Demonstrates tool-using agent wiring. 7 nodes (incl. 2 notes) / 4 edges.

### `flows/New Flow.json`
A stub containing a single unconnected `Chat Input` node. Placeholder / scratch flow.

### `data/langflow_cycle_test.csv`
Three-row input for the loop test. A `text` header followed by
`"Reply with exactly: Item 1 processed"` … `Item 3 processed`. Each row drives one loop
iteration.

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Flow runtime | Langflow 1.10.2 | Pinned to avoid the LiteLLM Windows build gap — ADR-002, BUG-005 |
| Language | Python 3.12.10 | In `.venv`; chosen over machine-default 3.14 — ADR-003 |
| Env / package manager | `uv` | `uv venv` + `uv pip install`; not Docker — ADR-001 |
| LLM provider | Groq · `llama-3.1-8b-instant` | Via built-in Groq component; not OpenAI despite template text — ADR-004 |
| Cyclic execution | Langflow `Loop` component | Bounded back-edge over CSV rows — ADR-005, Research topic 1 |
| Agent tools | `Calculator`, `URL` | Used in `Simple Agent.json` |
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

---

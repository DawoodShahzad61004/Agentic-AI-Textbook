# Langflow Learning Project

A hands-on project for learning [Langflow](https://www.langflow.org/)'s visual flow builder on
Windows. It contains a small set of exported flows (`flows/*.json`) and sample data
(`data/*.csv`) built while learning basic prompting, agents, and — the main experiment —
whether Langflow supports **cyclic (looping) execution**.

There is no custom application code here. The "project" is the local Langflow runtime plus
these flow definitions and the documentation of how they came to be.

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

In the Langflow UI, use **Import** and select any file from [flows/](flows/). Prompting flows
use the **Groq** component (`llama-3.1-8b-instant`), so set a Groq API key in the model
component. (The flow `description` fields mention "OpenAI" — that's leftover template text;
the wired provider is Groq. See ADR-004.)

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
| [`flows/Basic Prompting.json`](flows/) | The cyclic **Loop** test over CSV rows (see below). |
| [`flows/Basic Prompting (1).json`](flows/) | Near-duplicate save of the loop test. |
| [`flows/Simple Agent.json`](flows/) | An `Agent` with `Calculator` and `URL` tools. |
| [`flows/New Flow.json`](flows/) | Stub — a single unconnected `Chat Input`. |

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

Fed with [`data/langflow_cycle_test.csv`](data/langflow_cycle_test.csv) (3 rows), the looped
section runs once per row and terminates when the list is exhausted. One caveat learned along
the way: `Chat Input` captures a single Playground message and reuses it for every iteration —
it does **not** re-prompt per row. Full findings in [docs/Research.md](docs/Research.md)
(topics 1–2) and the rationale in [docs/Decisions.md](docs/Decisions.md) (ADR-005).

## Repository Layout

```
.
├── flows/        Exported Langflow flows (*.json)
├── data/         Sample data (langflow_cycle_test.csv)
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
- **Groq** (`llama-3.1-8b-instant`) as the LLM provider
- Served locally at `http://127.0.0.1:7860`

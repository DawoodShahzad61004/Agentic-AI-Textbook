# Decisions

Numbered Architecture Decision Records (ADRs) for the Langflow learning project. IDs
(`ADR-NNN`) are sequential and never reused.

---

## ADR-001 · Run Langflow via a local `uv`/pip install instead of Docker

| Field | Detail |
|---|---|
| **Decision** | Abandon the Docker Desktop route and run Langflow from a local Python virtual environment. |
| **Date** | 2026-07-23 |
| **Context** | The Docker path hit two consecutive blockers on this Windows machine: a Docker Hub DNS resolution failure inside WSL2 (BUG-001) and an immediate container exit because the image now requires superuser credentials (BUG-002). Both were solvable, but added friction for a single-user local learning setup. |
| **Options Considered** | **A. Docker** — official one-liner, isolated, but fought WSL2 DNS state and mandatory-auth startup. · **B. Local `uv` venv + pip** — no daemon, direct `langflow run`, closer to the code, but exposed to Windows wheel/build issues. · **C. Langflow Desktop installer** — avoids Docker and Python entirely, but least transparent for a learning project. |
| **Chosen Solution** | Local install: `uv venv .venv --python 3.12`, activate, `uv pip install --only-binary=litellm "langflow==1.10.2"`, then `langflow run` → `http://127.0.0.1:7860`. |
| **Rationale** | A learning project benefits from the most transparent, quickest-to-iterate setup. Removing the Docker/WSL2 layer eliminated two whole classes of failure (BUG-001, BUG-002) at the cost of one Windows packaging issue (BUG-005) that turned out to be pinnable. |
| **Impact** | Establishes the `.venv` + `langflow run` workflow used throughout the project. Directly leads to ADR-002 (version pin) and ADR-003 (Python version). Supersedes the Docker approach; BUG-001/BUG-002 are closed as no-longer-on-the-path. |

---

## ADR-002 · Pin `langflow==1.10.2` with `--only-binary=litellm` instead of latest (1.11.0)

| Field | Detail |
|---|---|
| **Decision** | Install `langflow==1.10.2` and force binary-only resolution of `litellm`, rather than installing the latest `langflow 1.11.0`. |
| **Date** | 2026-07-23 |
| **Context** | `langflow 1.11.0` transitively requires `litellm==1.93.0`, which has no Windows wheel and fails to compile from source without the MSVC linker (BUG-005). |
| **Options Considered** | **A. Install MSVC C++ Build Tools** and build `litellm 1.93.0` from source for 1.11.0 — unblocks the latest version but is a multi-GB toolchain install for one native dependency. · **B. Pin `langflow==1.10.2`** — resolves `litellm==1.91.4`, which ships a `win_amd64` wheel and needs no compiler. · **C. Fall back to Docker** — reintroduces BUG-001/BUG-002. |
| **Chosen Solution** | `uv pip install --only-binary=litellm "langflow==1.10.2"` (resolves `litellm==1.91.4`); `--only-binary=litellm` makes pip fail loudly rather than silently attempting a source build. |
| **Rationale** | Fastest path to a working Langflow with zero native-build risk. 1.10.2 officially supports Python 3.12, and the learning tasks (basic prompting, loops, a simple agent) do not need 1.11.0-specific features. |
| **Impact** | Fixes BUG-005. Pins the runtime Langflow version documented in `Architecture.md`. Can be revisited if a 1.11.x feature is needed (then option A applies). |

---

## ADR-003 · Use Python 3.12 for the virtual environment instead of 3.14

| Field | Detail |
|---|---|
| **Decision** | Create the project `.venv` on CPython 3.12, not the machine-default 3.14. |
| **Date** | 2026-07-23 |
| **Context** | The system default is Python 3.14.2. A first `.venv` was accidentally built on 3.14, and several Langflow dependencies lack 3.14 wheels, pushing them toward source builds. |
| **Options Considered** | **A. Python 3.14.2** (system default) — newest, but too new; missing wheels force compilation. · **B. Python 3.12.10** (also installed) — officially supported by Langflow 1.10.2, broad wheel coverage. |
| **Chosen Solution** | `uv venv --python 3.12 --clear .venv` (the `--clear` recreates the mistakenly-3.14 venv), then verify with `python -V` showing 3.12.x before installing. |
| **Rationale** | Langflow 1.10.2 officially targets 3.12, and 3.12 has mature wheels across the dependency tree, avoiding avoidable source builds. (Note: 3.12 did **not** by itself fix `litellm` — that was a packaging gap regardless of interpreter; see BUG-005.) |
| **Impact** | Defines the interpreter for `.venv`. Prerequisite for ADR-002's clean install. |

---

## ADR-004 · Use Groq (`llama-3.1-8b-instant`) as the flow LLM provider

| Field | Detail |
|---|---|
| **Decision** | Wire the flows to Langflow's Groq component running `llama-3.1-8b-instant` rather than an OpenAI model. |
| **Date** | 2026-07-23 |
| **Context** | The flows needed a chat LLM. Two of the flow files carry the stock template description "Perform basic prompting with an OpenAI model", but the actual model node in every prompting flow is a `GroqModel`. |
| **Options Considered** | **A. OpenAI** — the template default, requires an OpenAI key. · **B. Groq** — fast inference, free-tier friendly for a learning project, drop-in via the built-in Groq component. |
| **Chosen Solution** | `GroqModel` component with `model_name = llama-3.1-8b-instant`, used in `Basic LLM Prompting.json` and the cyclic `Basic Prompting*.json` flows. |
| **Rationale** | Groq gives low-latency, low-cost iteration suitable for experimentation. The leftover "OpenAI" wording is a template artifact, not the running config. |
| **Impact** | The flow files' `description` fields are inaccurate (say OpenAI; actually Groq) — flagged in `Architecture.md` and Research topic 3. Affects `flows/Basic LLM Prompting.json`, `flows/Basic Prompting.json`, `flows/Basic Prompting (1).json`. |

---

## ADR-005 · Test cyclic support with the built-in Loop component, not a raw LLM feedback loop

| Field | Detail |
|---|---|
| **Decision** | Verify Langflow's cyclic-execution support using the dedicated `Loop` component over a bounded data list, rather than manually wiring an LLM's output back to its own input. |
| **Date** | 2026-07-23 |
| **Context** | The goal was to confirm Langflow accepts a real back-edge and re-executes a section. A naive cycle (LLM output → LLM input) can run away and keep making API calls if the stop condition fails. |
| **Options Considered** | **A. `Loop` component** — explicit back-edge (`Item → … → Looping`) with a guaranteed stop when the input list is exhausted; aggregates via `Done`. · **B. Unrestricted LLM feedback loop** — tests a cycle but risks runaway Groq calls with no reliable termination. |
| **Chosen Solution** | `Read File (dataframe) → Loop`; `Loop.item → Type Convert → Prompt Template (task) ← Chat Input (user_input) → Groq → Type Convert (JSON) → Loop.Looping` (back-edge); `Loop.done → Type Convert → Chat Output`. Fed by `data/langflow_cycle_test.csv` (3 rows). |
| **Rationale** | The Loop component gives a controlled, terminating cycle — enough to prove the back-edge is accepted and a section re-executes per row, without unbounded API spend. |
| **Impact** | Realized in `flows/Basic Prompting.json` / `Basic Prompting (1).json`. Produced the findings in Research topics 1 and 2 (cyclic support confirmed; per-iteration interactive input is *not* supported by this pattern). |

---

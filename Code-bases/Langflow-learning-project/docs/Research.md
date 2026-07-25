# Research

Numbered research topics for the Langflow learning project. Topics are numbered
sequentially and record what was learned by investigating or testing something.

---

## 1. Does Langflow support cyclic (looping) flows?

| Field | Detail |
|---|---|
| **Topic** | Whether Langflow can execute a real cycle (a back-edge that re-runs a section), starting from an acyclic `Chat Input → Groq → Chat Output` flow that only moves information forward. |
| **Date** | 2026-07-23 |
| **Findings** | Yes — Langflow supports **controlled** cyclic execution via the dedicated `Loop` component, which provides an explicit back-edge and a guaranteed stop condition. Confirmed by building it: `Read File.dataframe → Loop.data`; `Loop.item → Type Convert → Prompt Template → Groq → Type Convert (JSON) → Loop.Looping` closes the cycle; `Loop.done → Type Convert → Chat Output` emits the aggregate. Fed with a 3-row CSV, the looped section (Groq) executed once per row and terminated when the list was exhausted, aggregating three results. A visual backward connection is accepted, the same section re-executes, and the cycle ends deterministically. |
| **Conclusion** | Cyclic flows are supported for bounded, data-driven iteration through the `Loop` component (see ADR-005). Noted limitation: the current `Loop` cannot be combined directly with `If-Else` for conditional termination — Langflow recommends filtering the data *before* looping instead. |
| **Relevance to Project** | Implemented in `flows/Basic Prompting.json` and `flows/Basic Prompting (1).json`; test data in `data/langflow_cycle_test.csv`. Directly informs ADR-005. |

---

## 2. Why doesn't the loop take fresh user input on each iteration?

| Field | Detail |
|---|---|
| **Topic** | After the cyclic flow ran, investigating why the same Playground message was reused for all three CSV rows instead of prompting the user again per iteration. |
| **Date** | 2026-07-23 |
| **Findings** | `Chat Input` is **not** an interactive `input()` call. It captures one Playground message when the flow starts; the `Loop` then reuses that single value for every row. Effective behavior is `user_input = receive_message_once(); for task in rows: process(task, user_input)` — not `for task in rows: user_input = wait_for_message(); ...`. The empty `User → Message` entries seen per iteration are the `Chat Input` component being re-evaluated by the looping dependency while no new Playground message exists. So the flow is not malfunctioning: it tests an *automatic data cycle*, not repeated human interaction. |
| **Conclusion** | For one instruction applied across all rows (e.g. prefixing `"SUCCESS: "`), the current design is correct. For a genuine interactive cycle (send message → run → respond → send another), drop the CSV loop and use `Chat Input → Prompt Template → Groq → Chat Output` so each Playground message triggers a fresh run. True pause-per-iteration ("show task 1, wait for my answer, then task 2") is **not** achievable with `Loop` + `Chat Input`; it needs a stateful human-in-the-loop / custom component or an external app that pauses and resumes. Langflow's built-in Human-in-the-Loop is aimed at pausing *agents* for tool-call approval/edit, not repeated `Chat Input` inside a `Loop`. |
| **Relevance to Project** | Clarifies the intended use of `flows/Basic Prompting*.json`. Distinguishes "automatic data cycle" (what exists) from "interactive cycle" (would require a different architecture). |

---

## 3. LiteLLM Windows packaging and the "OpenAI" template label

| Field | Detail |
|---|---|
| **Topic** | Two adjacent facts uncovered during install and flow review: LiteLLM's Windows wheel availability, and whether the flows actually use OpenAI. |
| **Date** | 2026-07-23 |
| **Findings** | (a) **LiteLLM wheels:** `litellm==1.93.0` (pulled by `langflow 1.11.0`) publishes Linux wheels but **no `win_amd64` wheel**, forcing a Rust/pyo3 source build that needs the MSVC `link.exe` (BUG-005). `litellm==1.91.4` (pulled by `langflow 1.10.2`) *does* ship a Windows wheel and installs without a compiler. (b) **Provider label:** the `description` field of `Basic Prompting.json` / `Basic Prompting (1).json` reads "Perform basic prompting with an OpenAI model", but every prompting flow's model node is a `GroqModel` running `llama-3.1-8b-instant`. The "OpenAI" text is a leftover from the stock template, not the running configuration. |
| **Conclusion** | Pin `langflow==1.10.2` to avoid the LiteLLM build gap (ADR-002). Treat the flow `description` fields as unreliable — the true provider is Groq (ADR-004). |
| **Relevance to Project** | Grounds ADR-002 (version pin) and ADR-004 (Groq provider). Affects `flows/Basic Prompting.json`, `flows/Basic Prompting (1).json`, `flows/Basic LLM Prompting.json`. |

---

## 4. Langflow authentication model (Docker image)

| Field | Detail |
|---|---|
| **Topic** | Why the Langflow Docker container refused to start, and how its login is configured. |
| **Date** | 2026-07-23 |
| **Findings** | The current `langflowai/langflow:latest` image enables login by default and will not boot without superuser credentials, exiting with `ValueError: Username and password must be set` (BUG-002). Credentials are supplied via env vars: `LANGFLOW_AUTO_LOGIN=false`, `LANGFLOW_SUPERUSER=<user>`, `LANGFLOW_SUPERUSER_PASSWORD=<strong-password>`. The legacy default password `langflow` is explicitly rejected. Setting `LANGFLOW_AUTO_LOGIN=true` bypasses the login screen entirely (acceptable only for a private local instance). A foreground container holds the terminal; `-d` runs it detached. |
| **Conclusion** | For any port that could be reachable beyond localhost, run with explicit superuser credentials. For a throwaway local experiment, `LANGFLOW_AUTO_LOGIN=true` is fine. Mostly moot for this project after moving to the local install (ADR-001), where `langflow run` serves on `127.0.0.1`. |
| **Relevance to Project** | Explains BUG-002. Informs the (now secondary) Docker usage notes in `README.md`. |

---

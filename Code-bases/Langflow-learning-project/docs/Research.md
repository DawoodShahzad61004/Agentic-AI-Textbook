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

## 5. How does Langflow expose per-user resources (Knowledge Bases, Memory Bases) to an exported flow?

| Field | Detail |
|---|---|
| **Topic** | Whether a `flows/*.json` export can carry a fully-configured `Knowledge` / `Memory Base` selection, so a fresh import runs without manual setup. |
| **Date** | 2026-07-27 |
| **Findings** | No. `knowledge_base` dropdown values resolve against files under `~/.langflow/knowledge_bases/<user>/<kb_name>/` (a Chroma collection plus `embedding_metadata.json` and `schema.json`); `memory_base` resolves against a database row scoped to the *current flow ID*. Neither exists until created inside that specific Langflow instance/account. A flow export can pre-fill the *name* Langflow will look for on the dropdown (turning "create new" into a one-click re-select once a same-named resource exists), but it can never embed the resource itself. |
| **Conclusion** | For any flow using `Knowledge` or `Memory Base` nodes, "create a resource with this exact name after importing" is an unavoidable manual step — the only automatable part is pre-filling the name so the dropdown resolves once that resource exists. |
| **Relevance to Project** | Grounds ADR-007 and ADR-008, and explains BUG-007 and BUG-009. |

---

## 6. Chroma similarity vs. distance convention inside Langflow's `Knowledge` node

| Field | Detail |
|---|---|
| **Topic** | Why every retrieved row was rejected by the ported Memora similarity floors (`DOCUMENTS_MIN_SIMILARITY = 0.53`, `LEARNED_QA_MIN_SIMILARITY = 0.57`) despite the `documents` Knowledge Base holding 106 chunks. |
| **Date** | 2026-07-27 |
| **Findings** | The `Knowledge` node's `retrieve_data` output stamps each row with `_score = -1 × distance` from Chroma's `similarity_search_with_score` in cosine space — a value in roughly `[-2, 0]` where closer to `0` is better, not a `[0, 1]` similarity. The original Memora retriever returns a true `[0, 1]` cosine similarity, which is what the ported thresholds were written against. Comparing the raw `_score` directly to a `[0, 1]` floor meant every row failed the check. |
| **Conclusion** | Any component consuming `Knowledge` node output must convert with `similarity = clamp(1 + _score, 0, 1)` before applying a similarity-style threshold designed for a conventional cosine-similarity retriever. |
| **Relevance to Project** | Root cause of BUG-010. The conversion is now applied (and commented) inside the `retrieve` component of `flows/LangGraph RAG Pipeline.json`. |

---

## 7. Component build order under multiple conditional branches feeding one input field

| Field | Detail |
|---|---|
| **Topic** | Why `generate_draft has not been built yet` appeared with no red-bordered error node anywhere in the canvas. |
| **Date** | 2026-07-27 |
| **Findings** | Langflow builds a vertex's upstream dependencies in edge order, not "active conditional branch first". When several router-style outputs from different Custom Components (e.g. `combine_tracks.to_draft`, `combine_tracks.to_answer`, `combine_tracks.to_retry`, plus `generate_draft.to_answer`) are wired into the same downstream field across different consumers, Langflow can attempt to build an inactive branch's vertex before the active branch has produced a value — the consumer then reports the not-yet-built vertex by name rather than raising a component-level error. |
| **Conclusion** | Router-style Custom Components in Langflow (multiple `Output`s, exactly one populated per run via `self.stop()` on the rest) are safest when each output feeds exactly one downstream input field — routing two conditional outputs from different sources into the same field is a build-order hazard, not just a readability issue. |
| **Relevance to Project** | Motivated ADR-009's flattening of the answer path to a single deterministic route. |

---

## 8. A caught-and-swallowed exception is indistinguishable from a successful empty answer

| Field | Detail |
|---|---|
| **Topic** | Why Playground briefly showed an "AI" bubble that then vanished, leaving only the user's message, with the canvas reporting no errors. |
| **Date** | 2026-07-27 |
| **Findings** | `generate_answer`'s final synthesis call was wrapped in `try: answer = _llm_text(...) except Exception: answer = ""`, added deliberately so a failed synthesis call could fall back to the draft answer. When both the synthesis call *and* the draft were empty (e.g. because an upstream dependency like the embeddings node never finished building at all — BUG-009 / BUG-011), the component still returned `Message(text="")` successfully. No exception reached Langflow, so no node turned red — and Langflow's Playground does not persist an empty assistant message, so it renders briefly and then disappears from the transcript. |
| **Conclusion** | A caught exception that degrades to a *valid but empty* output is invisible to Langflow's error surfacing — from the Playground's point of view it looks identical to a legitimate empty answer. Any "catch and fall back through several layers" pattern needs an explicit `if not answer: raise ...` once every fallback is exhausted, or the real upstream failure never surfaces. |
| **Relevance to Project** | Root-causes the "no output, no red node" symptom reported across the debugging session. The current `generate_answer` keeps a grounded draft as its safe fallback, raises the underlying model error when no draft exists, and raises explicitly if both the final response and draft are empty. |

---

## 9. Local OpenAI-compatible LLM endpoint behavior

| Field | Detail |
|---|---|
| **Topic** | Replacing the RAG pipeline's Groq clients with the same model served from a LAN-hosted OpenAI-compatible API. |
| **Date** | 2026-07-27 |
| **Findings** | `langchain_openai.ChatOpenAI` accepts the configured base `http://192.168.1.13:3001/v1` and appends `/chat/completions`; therefore the base must not include `/models` or `/chat/completions`. The installed `langchain-openai` version requires Pydantic v2's `SecretStr`, not `pydantic.v1.SecretStr`. The server was reachable, but `GET /v1/models` returned 404, so automatic model discovery cannot be assumed. |
| **Conclusion** | Configure the model ID explicitly (`llama-3.1-8b-instant`), use the `LOCAL-LLM` Langflow global variable for the key, and validate the server through `POST /v1/chat/completions` rather than depending on `/v1/models`. |
| **Relevance to Project** | Grounds ADR-010 and the three `Local LLM - *` components in `flows/LangGraph RAG Pipeline.json`. |

---

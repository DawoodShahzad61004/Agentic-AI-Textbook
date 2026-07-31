## Chronological Log

### July 2026 — Standing up Langflow locally and probing cyclic flow support

- **Moved off Docker to a local install:** after Docker Hub DNS (BUG-001) and mandatory-auth
  startup (BUG-002) friction, switched to a `uv` + Python 3.12 virtual environment running
  `langflow==1.10.2` (ADR-001, ADR-002, ADR-003).
- **Wired flows to Groq:** all prompting flows use the Groq `llama-3.1-8b-instant` component,
  not OpenAI, despite leftover template wording (ADR-004).
- **Confirmed cyclic support:** Langflow supports bounded cyclic execution via the `Loop`
  component; it does not support fresh per-iteration human input (Research topics 1–2, ADR-005).
- **Ported an external agentic RAG system into Langflow:** generated and iteratively repaired
  `flows/LangGraph RAG Pipeline.json`, reproducing "Memora"'s retrieval, compression, judging,
  and answer pipeline. BUG-006–BUG-011 are now closed; the current export uses local MiniLM
  similarity and three local OpenAI-compatible LLM clients (ADR-006–ADR-010).

---

#### 2026-07-23 — Get Langflow running on Windows

* Set out to run Langflow locally to start learning the visual flow builder.
* Tried Docker first: the image pull failed with `lookup auth.docker.io: no such host` even
  though the Windows host resolved and reached Docker Hub fine — diagnosed as stale DNS inside
  Docker Desktop's WSL2 VM (BUG-001). After the pull recovered, the container exited with
  `ValueError: Username and password must be set` because the current image requires superuser
  credentials (BUG-002).
* Decided the Docker layer wasn't worth the friction for a single-user local setup and pivoted
  to a local `uv`/pip install (ADR-001). Hit and fixed a string of setup errors: a misinvoked
  `python3.14 uv venv` (BUG-003), `uv install` vs `uv pip install` (BUG-004), and — the real
  blocker — `litellm==1.93.0` failing to compile on Windows for lack of `link.exe` because it
  has no Windows wheel (BUG-005).
* Root-caused BUG-005 to LiteLLM's Windows packaging (not Python 3.14, which was a red herring)
  and resolved it by pinning `langflow==1.10.2` with `--only-binary=litellm`, which pulls the
  wheel-having `litellm==1.91.4` (ADR-002). Chose Python 3.12 over the machine-default 3.14 for
  wheel coverage (ADR-003). Confirmed `langflow run` served the UI at `http://127.0.0.1:7860`.
* Tracked in: `.venv`, `flows/`; new Decisions.md ADR-001, ADR-002, ADR-003, ADR-004;
  new Bugs.md BUG-001, BUG-002, BUG-003, BUG-004, BUG-005; new Research.md topics 3, 4.

---

#### 2026-07-23 — Test whether Langflow supports cyclic flows

* Set out to verify Langflow can run a real cycle, starting from the acyclic baseline
  `Chat Input → Groq → Chat Output` (`flows/Basic LLM Prompting.json`).
* Chose the built-in `Loop` component over a raw LLM feedback loop to keep the cycle bounded
  and avoid runaway Groq calls (ADR-005).
* Built the loop test in `flows/Basic Prompting.json` / `Basic Prompting (1).json`:
  `Read File → Loop`; `Loop.item → Type Convert → Prompt Template ← Chat Input → Groq →
  Type Convert (JSON) → Loop.Looping` (back-edge); `Loop.done → Type Convert → Chat Output`.
  Created `data/langflow_cycle_test.csv` (3 rows) as the loop input.
* Confirmed the back-edge is accepted, the looped section (Groq) executed once per row, and the
  cycle terminated when the list was exhausted — cyclic support verified (Research topic 1).
  Then investigated "why isn't it taking my input again each iteration?" and found `Chat Input`
  captures one Playground message and reuses it for all rows; genuine per-iteration interactive
  input needs a different (stateful HITL/custom) architecture (Research topic 2).
* Tracked in: `flows/Basic Prompting.json`, `flows/Basic Prompting (1).json`,
  `data/langflow_cycle_test.csv`; new Decisions.md ADR-005; new Research.md topics 1, 2.

---

#### 2026-07-24 — Set up documentation and repository hygiene

* Set out to capture the project's history in the five-file Markdown tracking system and add a
  README.
* Reviewed the flow JSON exports and CSV to reconstruct the architecture and decisions, and
  cross-checked the run logs / chat transcripts for the bug and decision timeline.
* Created `docs/Architecture.md`, `docs/Bugs.md`, `docs/Decisions.md`, `docs/Research.md`,
  `docs/Status.md`, and top-level `README.md`. Noted the flow files' inaccurate "OpenAI"
  descriptions and the two near-duplicate Basic Prompting exports.
* Confirmed all five docs follow the tracking-guide templates and cross-reference by ID; added
  `.gitignore` for `.venv/` and agent config files.
* Tracked in: `docs/Architecture.md`, `docs/Bugs.md`, `docs/Decisions.md`, `docs/Research.md`,
  `docs/Status.md`, `README.md`, `.gitignore`; no new ADR/BUG/Research entries (documentation
  session).

---

#### 2026-07-27 — Port the "Memora" agentic RAG system into Langflow

* Set out to reproduce an external LangGraph-based RAG application ("Memora": dual-track
  retrieval, NAC/DC/LBC context compression, four LLM-judge validators, MongoDB
  feedback/thumbdowns, self-learning distillation) as a Langflow flow, given only its docs and
  chat history at first, then its actual node source files (`user_input.py`, `query_variants.py`,
  `retrieve.py`, `post_retrieve.py`, `validate_retrieval.py`, `dedup_merge.py`, `nac.py`,
  `dc.py`, `lbc.py`, `combine_tracks.py`, `generate_draft.py`, `check_answer_quality.py`,
  `generate_answer.py`, `auto_distillation.py`, `no_context_answer.py`, `commands.py`) partway
  through.
* Chose to generate the Custom Component Python and the flow JSON from a script rather than
  build in the UI, so the result could be validated with `Graph.from_payload` and a fake-LLM
  test harness before ever opening Langflow (ADR-006). Built retrieval on native `Knowledge`
  nodes instead of a direct Chroma client (ADR-007), and briefly added — then removed at the
  user's request — a `Memory Base` node for the feedback/history read side (ADR-008). Added a
  document-ingestion branch and per-role Groq clients (Generation / Judge / JSON Repair).
* Once given the real node source files, re-audited the generated components against them and
  found 13 behavioral divergences (wrong retry-count semantics, wrong chunk shape, a missing
  pre-retrieval-filter dedup pass, validators that mutated state when the source only logs,
  wrong NAC run-boundary detection, missing LBC guards, and others) — all fixed and re-verified
  against a unit-test harness before export.
* Tracked in: `flows/LangGraph RAG Pipeline.json`, `flows/Vector Store RAG.json` (reference
  template), `data_files/{csv,html,pdfs,word}/*` (ingestion test data); new Decisions.md
  ADR-006, ADR-007, ADR-008; new Research.md topic 5.

---

#### 2026-07-27 — Debug the RAG pipeline from "no output" to a working answer path

* Set out to get `flows/LangGraph RAG Pipeline.json` producing an actual answer in the
  Playground after import, working from "why m I not seeing anything here?" through several
  rounds of symptom → root cause.
* Found a live Groq API key had been committed in plaintext across the generated flow exports
  (BUG-006) and redacted it (commit `f8bb1cf`, message "API removed"; key still requires
  rotation).
* Diagnosed the recurring "is missing Knowledge" / "is missing Memory Base" Playground error as
  a structural limit, not a flow bug: `Knowledge`/`Memory Base` selections are per-user
  resources that no flow export can carry (BUG-007, Research topic 5). Pre-filled the
  `knowledge_base` dropdown names in the generator so re-linking after import is one click.
* Chased the "vanishing AI bubble" symptom (Playground briefly shows "AI", then reverts to only
  the user message, no red node) through three layers: a Hugging Face embeddings DNS failure
  traced to the machine's router DNS timing out (BUG-008, environment fix); an embeddings
  node's required-but-empty API key, confirmed headlessly via `Graph.async_start()` to abort
  the run on the very first LLM-adjacent vertex (BUG-009); and a `generate_answer` component
  that silently swallows synthesis failures into an empty (not missing) message, which
  Langflow's Playground renders as a flash-and-disappear "AI" bubble rather than an error
  (Research topic 8, BUG-011).
* Root-caused `generate_draft` never running, despite a 106-chunk `documents` Knowledge Base and
  no red error node, to two compounding issues: the `Knowledge` node's `_score` is a Chroma
  distance (`[-2, 0]`, lower is better), not the `[0, 1]` similarity the ported thresholds
  expected (BUG-010, Research topic 6); and multiple conditional-router outputs converging on
  one downstream field created a build-order hazard (Research topic 7). Fixed the similarity
  conversion and flattened the routing to a single deterministic path, removing the retry
  back-edges into `generate_query_variants` (ADR-009).
* Subsequently closed BUG-011 by replacing the node's runtime implementation with local
  `HuggingFaceEmbeddings` using the cached `sentence-transformers/all-MiniLM-L6-v2` model.
  Removed the unused remote inference node and verified normalized 384-dimensional vectors.
* Tracked in: `flows/LangGraph RAG Pipeline.json`, `flows/1.json`–`flows/9.json` (iteration
  snapshots); new Decisions.md ADR-009; new Bugs.md BUG-006–BUG-011; new Research.md topics
  6–8.

---

#### 2026-07-27 — Finish the RAG runtime fixes and move inference to the local LLM server

* Confirmed from a run export that the answer path was intentionally selecting
  `no_context_answer`, then found that even corrected similarities could all fall below fixed
  provider-specific thresholds. Kept the thresholds as the primary filter but added a fallback
  to the two best vector-ranked rows whenever a populated search would otherwise be discarded.
* Replaced the three RAG Groq clients with `langchain_openai.ChatOpenAI` clients for Generation,
  Judge, and JSON Repair. Preserved `llama-3.1-8b-instant`, role-specific temperatures, and
  output-token limits.
* Configured API base `http://192.168.1.13:3001/v1` and a database-backed Langflow global
  variable reference named `LOCAL-LLM`; removed the embedded Groq credential from the current
  export. Constructor validation caught and fixed a Pydantic v1/v2 `SecretStr` incompatibility.
* Verified valid JSON, all Custom Component schemas via `Graph.from_payload`, local MiniLM
  output, unique-input DAG wiring, and the `ChatOpenAI` constructor. The server was reachable,
  though `GET /v1/models` returned 404, so the model ID remains explicit and runtime validation
  depends on `POST /v1/chat/completions`.
* Tracked in: `flows/LangGraph RAG Pipeline.json`; new ADR-010 and Research topic 9; BUG-011
  closed and BUG-010 solution updated.

---

#### 2026-07-27 — Repository hygiene: drop sample/test data, lock down `.gitignore`

* Set out to remove the sample and test data added earlier the same day now that the ingestion
  branch and its behavior were captured in the flow itself and in documentation.
* Deleted `data_files/{csv,html,pdfs,word}/*` — the four autism-spectrum-disorder documents
  (CSV, HTML essay, PDF, DOCX) used to exercise `discover_files`/`marker_loader`/
  `split_documents` — and the old `data/langflow_cycle_test.csv` left over from the cyclic-loop
  experiment.
* Added `data_files/` to `.gitignore` (with a trailing-blank-line fix) so the directory won't
  be re-tracked if it's recreated locally for further ingestion testing.
* Tracked in: `.gitignore`; commits `1d35c60` (delete `data_files/`), `63d7b7b` (delete
  `data/`), `fe84d7a` (update `.gitignore`); no new ADR/BUG/Research entries (hygiene session).

---

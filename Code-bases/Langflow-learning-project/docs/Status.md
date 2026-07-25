## Chronological Log

### July 2026 — Standing up Langflow locally and probing cyclic flow support

- **Moved off Docker to a local install:** after Docker Hub DNS (BUG-001) and mandatory-auth
  startup (BUG-002) friction, switched to a `uv` + Python 3.12 virtual environment running
  `langflow==1.10.2` (ADR-001, ADR-002, ADR-003).
- **Wired flows to Groq:** all prompting flows use the Groq `llama-3.1-8b-instant` component,
  not OpenAI, despite leftover template wording (ADR-004).
- **Confirmed cyclic support:** Langflow supports bounded cyclic execution via the `Loop`
  component; it does not support fresh per-iteration human input (Research topics 1–2, ADR-005).

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

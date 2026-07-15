# Markdown Tracking System — Setup Guide

This is the same 5-file tracking system used in `RAG-work`. Create these five files at the
root of `langsmith-masterclass` (or any project) and follow the patterns below. Each file has
one job; don't mix content between them.

| File | Answers | Entry unit |
|---|---|---|
| `Status.md` | "What happened, and when?" | Dated chronological log entries |
| `Architecture.md` | "What does the system look like right now, and how did it get here?" | A living description + a dated changelog |
| `Decisions.md` | "Why did we choose X over Y?" | Numbered ADRs (Architecture Decision Records) |
| `Research.md` | "What did we learn by investigating/reading something?" | Numbered research topics |
| `Bugs.md` | "What broke, why, and how was it fixed?" | Numbered bug records |

## Cross-referencing rules

- Every entry gets a permanent ID (`ADR-NNN`, `BUG-NNN`, topic number, or a date heading). IDs
  are never reused, even if an entry is later merged or found to be wrong — just mark it
  superseded/closed and move on.
- Entries should reference each other by ID where relevant ("see ADR-003", "see BUG-012",
  "see Research topic 7") instead of re-explaining. This is what makes the system worth having
  — five isolated logs are less useful than five logs that point at each other.
- Every `Status.md` entry should end with a **`Tracked in:`** line listing which files/modules
  changed and which of the other four docs got a new entry that session. This is the index that
  lets you answer "what happened on day X" without re-reading everything.
- Number ADRs, bugs, and research topics **sequentially within their own file** — `Decisions.md`
  and `Bugs.md` and `Research.md` each have their own counter, unrelated to each other.

## When to write to which file

- Wrote code that fixed something concrete → `Bugs.md` (+ a line in that day's `Status.md`).
- Made an irreversible-ish choice with real alternatives you rejected (library, architecture,
  provider, algorithm) → `Decisions.md` (+ a line in `Status.md`).
- Read a paper/library/transcript/benchmark, even if no code changed → `Research.md` (+ a line
  in `Status.md`).
- The system's actual shape changed (new module, new data flow, new env var, new dependency) →
  update `Architecture.md`'s relevant section AND add a dated changelog entry at its bottom.
- Anything happened at all in a working session → at least one `Status.md` entry, always.

---

## Template — `Status.md`

```markdown
## Chronological Log

### <Month Year> — <One-line theme for this stretch of work>

- **<What was decided/built/fixed, in bold lead-in>:** <one or two sentences of detail>.
- <Additional bullets as needed>

---

#### <YYYY-MM-DD> — <Title summarizing the session>

* <What you set out to do>
* <What you found/diagnosed>
* <What you changed, with file names>
* <What you tested/confirmed, and the result>
* Tracked in: `<file1>`, `<file2>`; new Decisions.md ADR-<N>; new Bugs.md BUG-<N>; new Research.md topic <N>.

---
```

## Template — `Architecture.md`

```markdown
## System Overview

<2-4 sentences: what is this project, in plain language.>

## High-Level Architecture

<ASCII or text diagram of the main flow, if there is one.>

## Module Breakdown

### `<file_or_module_name>`
<What it does, its key functions/classes, what it depends on.>

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| <e.g. LLM> | <e.g. provider/model> | <why> |

## Changelog

### <YYYY-MM-DD> — <Title>

<Prose description of what changed in the system's actual shape this session — new files,
new env vars, provider swaps, dependency changes. Reference ADRs/Bugs where relevant.>

---
```

## Template — `Decisions.md`

```markdown
## ADR-<NNN> · <Title: the decision itself, not the problem>

| Field | Detail |
|---|---|
| **Decision** | <One sentence: what was decided> |
| **Date** | <YYYY-MM-DD> |
| **Context** | <Why this decision was needed — the problem, constraint, or trigger> |
| **Options Considered** | <Option A (pros/cons)> · <Option B (pros/cons)> · <Option C> |
| **Chosen Solution** | <The option picked, stated concretely — actual code/config shape> |
| **Rationale** | <Why this option over the others — the deciding factor(s)> |
| **Impact** | <What files/modules this touches; what it unblocks or supersedes; related ADRs> |

---
```

## Template — `Research.md`

```markdown
## <N>. <Title: the subject investigated>

| Field | Detail |
|---|---|
| **Topic** | <What was being investigated and why> |
| **Date** | <YYYY-MM-DD> |
| **Findings** | <What was actually learned — be concrete: numbers, quotes, confirmed behavior, not just "it seems like"> |
| **Conclusion** | <What was decided as a result, or explicitly: "no action taken, filed for later"> |
| **Relevance to Project** | <Which files/modules/future work this bears on> |

---
```

## Template — `Bugs.md`

```markdown
### BUG-<NNN> · <Title: symptom + where>

| Field | Detail |
|---|---|
| **Issue** | <One-sentence symptom> |
| **Found Date** | <YYYY-MM-DD> |
| **Status** | Open / Closed |
| **Severity** | LOW / MEDIUM / HIGH / CRITICAL |
| **File** | <file(s) affected> |
| **Description** | <What happened, concretely — error text, reproduction, what was observed> |
| **Root Cause** | <The actual underlying reason, not just the symptom> |
| **Solution** | <What fixed it, or what would fix it if still open> |
| **Date Resolved** | <YYYY-MM-DD, or — if still open> |

---
```

# Project Context — Read This Before Doing Anything Else

> This file exists so that any AI agent working in this repository — Claude Code, Codex, GitHub Copilot, or otherwise — understands what this project actually *is* before touching a single file. If you are an agent reading this, read this entire file before running `graphify query`, editing `Book_Index.md`, or generating a chapter.

---

## 1. What This Repository Is

This is **not a software project**. It is the source material and working files for a **textbook**:

> **Self-Learning Agentic RAG System — A Step-by-Step Guide to Learn and Create**

It is, to the author's knowledge, one of the first textbooks written specifically about **agentic RAG systems** — RAG pipelines where an LLM autonomously decides when, what, and how many times to retrieve, self-corrects its own answers, compresses its own context, and learns from its own failures over time.

The book teaches this subject **by building a real, working system from scratch**, chapter by chapter, and explaining the reasoning behind every architectural decision — not just showing code, but showing *why* the code looks the way it does, including the mistakes, the bugs, and the refactors that shaped it.

## 2. The Author's Methodology — Why This Repo Looks the Way It Does

The author has been building this book for **several months** (and expects to continue for several more) using a specific, deliberate process:

1. **Everything gets captured.** Every conversation with Claude, Claude Code, ChatGPT, and Codex about this project — design discussions, debugging sessions, architecture arguments, refactors — gets saved as a raw transcript file.
2. **Everything gets kept.** Terminal output logs, dry-run traces, research papers studied, full source code (both current and superseded versions), notes, and documentation — all of it goes into this repository. Nothing is written from memory or assumption; everything is grounded in an actual artifact.
3. **A living index gets rebuilt.** Periodically, all of this raw material is fed to an AI assistant to regenerate `Book_Index.md` — a full table of contents mapping every chapter and section to the real material that will support it.
4. **Chapters get written one at a time**, in order, each one pulling from the raw material (conversations, code, bugs, decisions, research) that's relevant to that chapter's topic — never invented, always sourced.
5. **The system documented in this book (Memora) is itself a real, evolving codebase.** It didn't start as a finished design. It started as a simple RAG pipeline and was iteratively rebuilt — through dozens of bugs found and fixed, several architecture pivots, and ongoing tuning — into what it is now. The book's job is to teach readers to build the *same journey*, not just hand them the final answer.

This is why the repository contains things a normal software repo wouldn't: months of raw chat transcripts, five structured "ledger" markdown files (`Architecture.md`, `Decisions.md`, `Bugs.md`, `Status.md`, `Research.md`) that compress that history into durable records, dozens of dry-run trace `.txt` files, and multiple generations of the same source files as the system was refactored.

## 3. The Five Ledger Files — Treat These as Authoritative

If you need to understand *why* something in the code is the way it is, these five files are the fastest and most reliable path — more reliable than re-reading raw chat transcripts, because they are the **distilled, deliberate record** the author maintains specifically for this purpose:

| File | What it contains |
|---|---|
| `Architecture.md` | The current system design — pipelines, phases, data flow |
| `Decisions.md` | Every architecture decision as a numbered ADR, with context, alternatives considered, and rationale |
| `Bugs.md` | Every significant bug found, numbered (`BUG-XXX` / `BUG-FXXX`), with root cause and fix |
| `Status.md` | A chronological development diary — what changed, when, and why |
| `Research.md` | Findings from external research (papers, docs, tools evaluated) that informed decisions |

**If a `Decisions.md` entry and a raw chat transcript ever seem to disagree, the ledger wins** — it represents the author's considered, later judgment, not a mid-conversation exploration.

## 4. Current State of the Book

- **Some chapters are already written** and exist as finished `.pdf` files inside the **`Chapters Created So Far`** folder (Chapters 1–10, covering Foundations and the Ingestion Pipeline — Parts I and II of the book).
- **These chapters are considered final and should not be edited or refactored** unless the author explicitly asks. New material discovered later gets added to *later* chapters, not retrofitted into these.
- **`Book_Index.md`** is the current table of contents for the entire book and is the single source of truth for what chapter comes next and what it should cover.
- The underlying system itself has gone through a **major architecture evolution**: from a single imperative agent loop to a LangGraph state-machine pipeline with parallel two-track compression (documents + learned memory), a three-backend observability stack (Phoenix, LangSmith, Langfuse), multi-role LLM routing, and a growing MongoDB-backed feedback layer. Later chapters (13B onward) track this evolution; the first 10 chapters predate it and remain correct as written.

## 5. What "Help Me With This Project" Actually Means

When the author asks you to do something in this repository, it almost always falls into one of these:

- **"Update `Book_Index.md`"** — new files have been added or existing files changed since the index was last generated. Your job is to find what's *new or changed* that isn't yet reflected in the index, and add sections for it — without touching the sections that already cover written chapters (1–10) unless something has factually changed about them.
- **"Write Chapter N"** — produce the actual chapter content, following the book's established format (Times New Roman, specific margins, definition/analogy/pitfall callout boxes, embedded SVG diagrams, code listings), grounded in the real source material for that chapter's topics — never invented.
- **"Explain/trace X"** — the author is trying to remember or understand something from months of accumulated material. Use the graph (via `graphify query` / `graphify path` / `graphify explain`) to find it, rather than guessing or asking the author to re-explain something they've likely already documented somewhere in this repo.

## 6. A Working Rule

**This repository is not the finished truth — it is the evidence.** The book is the synthesis of everything in it. If you are ever unsure whether something is "done" or "still evolving," check `Status.md` first — it is the chronological record of exactly that.

---

*If you are an agent and have read this file, you now understand the project. Proceed with `Book_Index.md` or the requested chapter using this context, plus whatever the graph or project search surfaces as relevant.*

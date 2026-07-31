---
name: codebase-explorer
description: Maps a research codebase — folder structure, main files and their purpose, entry points, execution flow, and major components. Use whenever the user asks for an "overview of the codebase/repo", "folder structure", "where does execution start", "walk me through the code", "trace the flow", "what does this file do", or runs /codebase-explorer. Also use when the user provides a GitHub link for a paper's official implementation and wants to understand it.
---

# Codebase Explorer

Turns an unfamiliar research repo into a navigable mental map: structure → key files → entry points → execution flow.

## Commands

```
/codebase-explorer <path|.>              # full tour → .research/codebase_map.md
/codebase-explorer <path> --entry        # entry points + how to run it, nothing else
/codebase-explorer flow <script/entry>   # trace execution flow from a given entry point
/codebase-explorer file <path>           # deep-dive one file: purpose, key functions, who calls it
/codebase-explorer component "<name>"    # explain one subsystem (e.g. "the data pipeline", "the attention module")
/codebase-explorer <github-url>          # clone (shallow) into ./repo or ask where, then run the full tour
```

(In Codex: `$codebase-explorer …`.)

## Workflow for the full tour

1. **Run the mapper first**: `python scripts/repo_map.py <root>` → `.research/repo_map_raw.md`. This gives deterministic facts: tree with line counts, language breakdown, entry-point candidates (main guards, CLI decorators, Makefile targets, console_scripts), and config files. Read its output before opening files by hand.
2. **Read the README and top entry-point candidates** to confirm/correct the heuristics — the script finds *candidates*; you decide which are the real entry points (training vs. eval vs. demo vs. leftover experiments).
3. **Produce the tour**, proportionate to repo size:
   - Folder structure with one-line purpose per top-level item (from the raw map, annotated with judgment).
   - The **3–8 files that matter** for the paper's core contribution, each with a 1–3 sentence explanation. In research repos the core idea often lives in 1–2 files surrounded by boilerplate — say which is which.
   - **Entry points** with the actual commands to run them (from README/Makefile/configs), flagging any that look broken or undocumented.
   - **Execution flow**: a numbered call chain from entry point to result (`train.py → build_dataloader() in data.py → Model.forward() in model.py → loss in losses.py → …`). File + function names, not vague descriptions.
   - **Major components** and how they connect (data, model, training loop, evaluation, configs).
4. **Write `.research/codebase_map.md`** with the tour. Downstream skills (paper-to-code-mapper, reverse-engineering-assistant, production-readiness-reviewer) read it.
5. For large repos, map the path relevant to the paper's contribution deeply and the rest shallowly; say explicitly what you skipped.

## `flow`, `file`, `component`

Read the actual code — never describe from filenames alone. For `flow`, follow real call sites (grep for the function names) and note config-driven indirection (hydra/registry patterns) explicitly, since that's where research repos usually hide the wiring. For `file`, end with "who calls this / what breaks without it". Append findings to `.research/codebase_map.md` rather than overwriting the tour.

## Ongoing exploration

After the tour, the user will poke around and ask questions. Answer within the established map — extend it when questions reach unmapped territory instead of re-touring from scratch.

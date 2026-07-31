---
name: paper-dissector
description: Systematically extracts a paper's contributions, claims, assumptions, limitations, datasets, baselines, metrics, hyperparameters, and experimental setup into a structured dossier. Use when the user asks to "dissect", "break down", "extract the claims/contributions/datasets", "what are the assumptions/limitations", "make a summary sheet of this paper", or runs /paper-dissector. The dossier it produces (.research/dissection.md) is the input other skills (paper-to-code-mapper, question-generator, improvement-research-ideas) depend on.
---

# Paper Dissector

Turns a read (or unread) paper into a structured, checkable dossier. Precision over prose: every extracted claim must be traceable to a section/table in the paper.

## Commands

```
/paper-dissector <arxiv-url|id|pdf-path>   # full dissection → .research/dissection.md
/paper-dissector --claims                  # only the claims table
/paper-dissector --assumptions             # only stated + unstated assumptions
/paper-dissector --limitations             # only limitations (stated + unstated)
/paper-dissector --experiments             # datasets, baselines, metrics, hyperparameters, compute
/paper-dissector --update                  # re-run on the already-loaded paper, keeping user edits in dissection.md
```

(In Codex: `$paper-dissector …`.)

## Workflow

1. **Get the full text.** For arXiv links, run `scripts/fetch_arxiv.py <id> --pdf` and read the PDF (method + experiments sections especially — the abstract alone is not enough for dissection). For a local PDF, read it directly.
2. **Extract into the dossier**, with a source pointer (section/table/page) for every item:

   - **Contributions** — what the authors claim is new, verbatim intent in ≤1 line each.
   - **Claims table** — each specific, checkable claim with columns: `id | claim | where stated | evidence offered | strength (proven / supported / asserted)`. Give claims stable ids (C1, C2, …) — paper-to-code-mapper keys off these.
   - **Assumptions** — *stated* ones, then *unstated* ones you can infer (data regime, i.i.d.-ness, scale, hardware, "the baseline was tuned fairly"). Label which is which.
   - **Limitations** — the ones the authors admit, then ones visible from the setup that they don't mention. Label which is which; the unlabeled-by-authors ones are your analysis, mark them as such.
   - **Experimental setup** — datasets (with sizes/splits if given), baselines, metrics, key hyperparameters, compute/hardware, number of seeds/runs, and anything conspicuously *missing* (no variance reported, no ablation for component X).
   - **Threats to validity** — 3–5 bullets: where the results are most fragile.
3. **Be honest about extraction vs. inference.** Anything not literally in the paper is marked `(inferred)`. Never launder your own analysis as the authors' statements.
4. **Write `.research/dissection.md`** with the structure above. With `--update`, preserve any sections the user has manually edited (look for an `<!-- user -->` marker or obvious human edits) and only refresh the rest.

## Output style

The dossier is a reference document — tables and terse bullets are correct here. In the chat itself, give a short digest (top 3 contributions, the 2 shakiest claims, the biggest omission) and point to the file for the rest.

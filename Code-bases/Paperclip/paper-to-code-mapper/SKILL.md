---
name: paper-to-code-mapper
description: Links each claim/component in a research paper to its concrete implementation in the codebase, and highlights omissions, discrepancies, and undocumented extras. Use when the user asks "where is X from the paper implemented", "does the code match the paper", "what did they claim but not implement", "map the paper to the code", "find the differences between paper and code", or runs /paper-to-code-mapper. Requires (or will create) the paper dossier and codebase map.
---

# Paper-to-Code Mapper

The audit step: for every claim and component in the paper, find where it lives in the code — or prove it doesn't.

## Commands

```
/paper-to-code-mapper <repo-path|.>        # map all claims → .research/claim_map.md
/paper-to-code-mapper claim "<claim or C-id>"   # trace one claim to code
/paper-to-code-mapper eq "<equation ref>"  # find the code implementing a specific equation
/paper-to-code-mapper gaps                 # report only: claimed-but-missing + code-not-in-paper
/paper-to-code-mapper hyperparams          # compare paper's reported hyperparameters vs. code/config defaults
```

(In Codex: `$paper-to-code-mapper …`.)

## Prerequisites

- Claims list: use `.research/dissection.md` if present; otherwise extract a minimal claims table first (or suggest running `/paper-dissector`).
- Repo map: use `.research/codebase_map.md` if present; otherwise do a quick entry-point/structure scan first (or suggest `/codebase-explorer`).

## Workflow

1. For each claim/component (keyed by the dossier's C-ids), **search the actual code** — grep for names, formulas, distinctive constants, config keys. Never assert "implemented" from a filename or README; open the code and confirm the logic matches.
2. **Classify every claim** into exactly one of:
   - **Implemented as described** — cite `file:function` (line numbers if stable).
   - **Implemented differently** — cite the code AND state the discrepancy precisely (e.g. "paper says cosine schedule with warmup; code uses step decay", "eq. 4 normalizes by d; code normalizes by sqrt(d)").
   - **Claimed but absent** — the claim, ablation, variant, or result in the paper with no corresponding code. State what you searched for before concluding absence.
   - **In code but not in paper** — tricks, gradient clipping, label smoothing, hardcoded constants, data filtering, seeds — anything doing real work that the paper doesn't mention. These often matter more than the headline method.
3. **Hyperparameter diff** (`hyperparams` or as part of the full map): table of `parameter | paper value | code/config value | match?`. Config defaults that differ from the paper's reported values are a classic reproducibility trap — flag them loudly.
4. **Write `.research/claim_map.md`**: a table `claim id | claim | status | code location | notes`, followed by a "Discrepancies & omissions" section in prose ranked by how much each one threatens the paper's conclusions.
5. **Calibrate confidence.** Distinguish "I verified the math in the code matches eq. 3" from "the function is named like eq. 3". If code is too tangled to verify a mapping, say so — an honest "couldn't confirm" beats a confident wrong mapping.

## Output style

In chat: lead with the 3–5 most consequential findings (usually from categories 2–4), then point to the file. The full table lives in the artifact, not the chat.

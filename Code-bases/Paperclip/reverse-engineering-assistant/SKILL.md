---
name: reverse-engineering-assistant
description: Analyzes WHY a research codebase is built the way it is — design decisions, rejected alternatives, hidden assumptions, and implementation trade-offs. Use when the user asks "why did they do it this way", "what are the alternatives", "what trade-offs did they make", "what assumptions is this code making", "reverse engineer this design", or runs /reverse-engineering-assistant. Complements codebase-explorer (which maps WHAT the code does) by explaining the reasoning behind it.
---

# Reverse Engineering Assistant

Explorer answers *what*; this skill answers *why* — reconstructing the decisions behind the code and stress-testing them.

## Commands

```
/reverse-engineering-assistant <path|component>      # full analysis of a file/module/subsystem
/reverse-engineering-assistant decisions <target>    # enumerate the significant design decisions in the target
/reverse-engineering-assistant why "<decision>"      # deep-dive one decision: rationale, alternatives, trade-offs
/reverse-engineering-assistant assumptions <target>  # hidden assumptions baked into the code
/reverse-engineering-assistant tradeoffs <target>    # what was traded for what (speed/memory/simplicity/generality)
/reverse-engineering-assistant hacks <target>        # magic numbers, special cases, TODO/FIXME archaeology
```

(In Codex: `$reverse-engineering-assistant …`.)

## Method

1. **Ground everything in the actual code.** Read the target before theorizing. Use git history when available (`git log -p --follow <file>`, blame on suspicious lines) — commit messages and change sequences are primary evidence for *why*.
2. **For each significant decision**, reconstruct:
   - **The decision** — stated concretely ("they recompute attention instead of caching it").
   - **The plausible rationale** — memory limits, simplicity, deadline pressure, matching the paper's math exactly, framework constraints. Rank rationales by evidence (comments, commit messages, paper text, config remnants) and mark pure speculation as speculation.
   - **The alternatives** — 2–3 realistic other designs, each with one line on why the authors may have rejected it.
   - **The trade-off** — what was gained and what was paid (runtime, memory, generality, readability, reproducibility).
3. **Hidden assumptions**: things that make the code silently wrong outside its tested regime — fixed batch/sequence sizes, dataset-specific preprocessing, single-GPU assumptions, hardcoded paths, tokenizer coupling, numeric ranges, ordering assumptions. For each: where it lives, what breaks it, how you'd detect the breakage.
4. **Hacks archaeology** (`hacks`): magic constants, `if dataset == "x"` special cases, commented-out experiments, TODO/FIXME/XXX, dead code, seeds. For each, infer what experiment or failure produced it. These are fossils of the actual research process and often reveal what the paper glosses over.
5. **Cross-reference the paper** (via `.research/dissection.md` / `claim_map.md` if present): decisions that contradict or exceed the paper's description deserve extra attention — note them and, if the mapper hasn't recorded them, append to its findings.
6. **Epistemic honesty is the core discipline here.** You are inferring intent from artifacts. Use "likely / plausibly / one reading is" and give the evidence. When the user counter-argues, weigh their reading seriously — reverse engineering is a debate, not a verdict.

## Output

Append analyses to `.research/design_analysis.md` (decision, rationale-with-evidence, alternatives, trade-offs, assumptions). In chat, prose beats tables for this skill — the value is in the reasoning, and it should read like a design review, not a checklist.

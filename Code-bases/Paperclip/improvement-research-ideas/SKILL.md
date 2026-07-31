---
name: improvement-research-ideas
description: Proposes optimizations, extensions, new experiments, and future research directions grounded in a specific paper and its codebase. Use when the user asks "how could this be improved", "what experiments would you run", "what's the follow-up work", "research ideas based on this", "what would I optimize", or runs /improvement-research-ideas. Best used last in the workflow, after the dissection, codebase map, claim map, and design analysis exist — it feeds on their gaps and discrepancies.
---

# Improvement & Research Ideas

The payoff step: convert everything learned about the paper and code into concrete, feasible next moves — from engineering optimizations to publishable research directions.

## Commands

```
/improvement-research-ideas                # full ideation across all four categories → .research/ideas.md
/improvement-research-ideas --optimize     # engineering/perf improvements to the existing code
/improvement-research-ideas --extend       # method extensions (new domains, inputs, scales, combinations)
/improvement-research-ideas --experiments  # missing/next experiments and ablations, with expected outcomes
/improvement-research-ideas --research     # open questions and follow-up research directions
/improvement-research-ideas develop <id>   # flesh one idea into a mini-proposal
```

(In Codex: `$improvement-research-ideas …`.)

## Sources to mine (in priority order)

1. `.research/claim_map.md` — every "claimed but absent" and "implemented differently" entry is a ready-made experiment.
2. `.research/dissection.md` — stated limitations are the authors' own future-work list; unstated assumptions are yours.
3. `.research/design_analysis.md` — each rejected alternative is a candidate ablation or improvement.
4. `.research/prod_review.md` — perf findings become optimization ideas.
5. The paper's related-work section — gaps between what exists and what this paper did.
If these files don't exist, do a quick pass over the paper/repo first and label the ideas as based on a shallow read.

## Idea quality bar

Every idea must have:
- **What**: one crisp sentence.
- **Why it might work / matter**: the mechanism or evidence, tied to something specific in this paper/code ("the code already computes X per step and discards it, so…").
- **Cost**: rough effort + compute (hours-on-one-GPU vs. weeks-on-a-cluster).
- **How you'd know it worked**: the metric/experiment that validates it, including the comparison baseline.
- **Risk**: the most likely way it fails.

Rank ideas by (impact ÷ cost) within each category. Kill generic filler — "try more data", "use a bigger model", "add attention" are banned unless there's a paper-specific reason they'd behave interestingly here.

## Categories

- **Optimizations**: measurable speed/memory/simplicity wins in the existing code, each pointing at the file/function it targets.
- **Extensions**: apply/modify the method beyond the paper's scope; state which assumption from the dissection gets relaxed.
- **Experiments**: the ablations and stress tests the paper *should* contain — especially ones the claim map exposed — each with a predicted outcome and what each outcome would mean.
- **Research directions**: 3–5 larger questions this work opens, each framed as a falsifiable hypothesis with a first experiment, not a vibe.

## `develop <id>`

Expand one idea into a mini-proposal: motivation, method sketch, experimental design (datasets, baselines, metrics, ablations), expected results table skeleton, risks & fallbacks, and a week-by-week plan. Realistic scoping over grandiosity.

Write everything to `.research/ideas.md` with stable ids (I1, I2, …). In chat, present the top 2–3 per category, not the whole list.

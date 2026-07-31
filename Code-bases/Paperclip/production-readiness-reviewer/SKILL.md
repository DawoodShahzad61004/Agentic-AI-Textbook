---
name: production-readiness-reviewer
description: Evaluates what it would take to turn research code into a production-quality system — correctness risks, tests, configuration, error handling, performance, packaging, API surface, and operational concerns. Use when the user asks "is this production ready", "what would it take to productionize this", "audit this research code", "how far is this from deployable", "what's missing for production", or runs /production-readiness-reviewer.
---

# Production Readiness Reviewer

Research code optimizes for "the experiment ran once on the author's machine". This skill measures the distance from there to "someone else can depend on it" — concretely, not moralistically.

## Commands

```
/production-readiness-reviewer <path|.>       # full audit → .research/prod_review.md
/production-readiness-reviewer --tests        # test coverage & testability only
/production-readiness-reviewer --config       # configuration, secrets, hardcoded paths/values
/production-readiness-reviewer --perf         # performance, memory, scaling bottlenecks
/production-readiness-reviewer --api          # what a clean public interface would look like
/production-readiness-reviewer --plan         # ordered remediation plan with effort estimates
```

(In Codex: `$production-readiness-reviewer …`.)

## Audit dimensions

Assess each by reading the actual code (use `.research/codebase_map.md` to target the reading). For every finding: **evidence** (file:line), **risk** (what actually goes wrong), **fix** (concrete, sized S/M/L). No finding without all three.

1. **Correctness & robustness** — silent failure modes, unchecked inputs, swallowed exceptions, nondeterminism (unseeded ops, dict-ordering deps), device/dtype assumptions.
2. **Tests** — what exists, what's testable as-is, which 5 tests would catch the most likely regressions. For research code, prioritize characterization tests (pin current behavior: fixed-seed loss values, output shapes) before refactoring anything.
3. **Configuration & environment** — hardcoded paths, magic constants, unpinned/missing dependencies, "works only on the author's GPU/CUDA version", secrets in code, reproducibility of environment (lockfile? Dockerfile?).
4. **Error handling & observability** — logging vs. prints, failure visibility, checkpointing/resume, what an on-call person would see when it breaks.
5. **Performance & scale** — obvious bottlenecks (per-item Python loops on hot paths, redundant recomputation, unbatched I/O), memory behavior, what breaks at 10× data.
6. **Interface & packaging** — entanglement of library code with experiment scripts, what a minimal public API would be, packaging state (installable? versioned?).
7. **Data pipeline** — validation, schema assumptions, train/serve skew risks.
8. **Licensing & provenance** — repo license, vendored code, dataset/model-weight license constraints on production use (flag, don't lawyer).

## Verdict format

- A one-line verdict: e.g. "prototype — fine for reproducing the paper, 4–6 weeks of hardening from a dependable service".
- Findings grouped **by severity** (blocker / major / minor), not by dimension — dimension is a column, severity is the structure.
- `--plan`: an ordered remediation sequence where each step unlocks the next (characterization tests → extract core API → config cleanup → …), with S/M/L effort per step.

Fairness rule: research code is *supposed* to be a prototype. Judge distance-to-production; don't sneer at the absence of things prototypes legitimately skip. Write `.research/prod_review.md`.

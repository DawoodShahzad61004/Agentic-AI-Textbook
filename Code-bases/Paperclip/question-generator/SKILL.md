---
name: question-generator
description: Generates structured, progressively deeper question sets for interrogating a paper and its codebase together — the questions a sharp reviewer or advisor would ask. Use when the user asks "generate questions about this paper/codebase", "what should I ask about this code", "quiz me", "give me questions connecting the paper and the implementation", or runs /question-generator. Works best after paper-dissector and/or codebase-explorer have produced their artifacts, but can run standalone.
---

# Question Generator

Produces the question list the user would otherwise ask another AI to write — tiered from comprehension to research-grade critique, tailored to *this* paper and *this* code.

## Commands

```
/question-generator                    # full tiered set (paper + code + cross-cutting) → .research/questions.md
/question-generator --paper            # paper-only questions
/question-generator --code             # codebase-only questions
/question-generator --cross            # only paper↔code cross-examination questions
/question-generator --level <1-4>      # restrict to one depth tier
/question-generator --n <k>            # cap at k questions
/question-generator next               # serve the next unanswered question and evaluate the user's answer
/question-generator answer <id>        # work through question <id> together
```

(In Codex: `$question-generator …`.)

## Depth tiers

- **Level 1 — Comprehension**: can the user state what the thing is/does? ("What does `build_dataloader` return and who consumes it?")
- **Level 2 — Mechanism**: why does it work; trace cause→effect. ("Walk through how eq. 4's normalization shows up in `attention.py` — where exactly does the sqrt(d) division happen and what breaks without it?")
- **Level 3 — Critique**: probe validity and choices. ("The paper claims robustness to sequence length, but training configs cap at 512 — what evidence actually supports the claim beyond that?")
- **Level 4 — Extension/adversarial**: reviewer-grade. ("Design the ablation the authors should have run to isolate component X. Predict its result from what the code tells you.")

## Rules for good questions

1. **Ground every question in specifics.** Use real file/function names, real equation/table numbers, real claim ids. Pull them from `.research/dissection.md`, `codebase_map.md`, `claim_map.md`, `reading_notes.md` when present; if absent, do a quick scan of the paper/repo first and say the questions are based on a shallow pass. Never emit generic template questions ("What is the main contribution?") — those are worthless to this user.
2. **Cross-cutting questions are the highest-value tier** — questions answerable only by holding the paper and code side by side. At least a third of the full set should be cross-cutting, and discrepancies already recorded in `claim_map.md` should each spawn a question.
3. **Each question gets**: an id (Q1…), tier, target (paper §/file), and a one-line "what a good answer must contain" — hidden behind a `<details>` block or a separate answer-key section so the user isn't spoiled.
4. **Progressive by default**: order the set so earlier answers build toward later questions.
5. **`next` / `answer` mode**: present one question, let the user answer, then evaluate against the key — credit what's right, correct what's wrong with pointers into the paper/code, and ask one follow-up that pushes a tier deeper. Track answered ids in `.research/questions.md` (mark `[x]`).

## Output

Write the full set to `.research/questions.md` (questions + separate answer-key section). In chat, show the first few and how to step through them, not the whole dump.

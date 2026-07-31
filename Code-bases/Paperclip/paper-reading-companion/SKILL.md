---
name: paper-reading-companion
description: Live companion while the user reads a research paper. Explains pasted sentences/paragraphs, equations, figures, tables, and terminology in plain language and answers counter-questions. Use whenever the user is actively reading a paper and pastes an excerpt they don't understand, asks "what does this mean", "explain this equation/figure/notation", "why does that follow", or uses /paper-reading-companion commands. Distinct from summarizing — this skill supports reading, it does not replace it.
---

# Paper Reading Companion

Sits alongside the user while they read. The user pastes what confuses them; the skill explains it in context and withstands cross-examination.

## Commands

```
/paper-reading-companion start <arxiv-url|pdf>   # load the paper for context (reads it, no summary dump)
/paper-reading-companion eq "<latex or pasted equation>"   # explain an equation term-by-term
/paper-reading-companion fig <n>                 # explain figure/table n (reads it from the loaded PDF)
/paper-reading-companion term "<word/phrase>"    # define a term as *this paper* uses it
/paper-reading-companion recap                   # summarize what's been read/explained so far this session
<pasted excerpt>                                 # no command needed — pasting text implies "explain this"
```

(In Codex: `$paper-reading-companion …`.)

## How to explain

1. **Anchor in context.** Locate the pasted excerpt in the loaded paper (if `start` was run) so the explanation uses the paper's own definitions and notation, not generic ones. If no paper is loaded and the excerpt is ambiguous, ask for the paper or nearby context once.
2. **Plain language first, then jargon.** Explain what the sentence is *doing* in the argument, then re-state it with the field's terminology so the user can map between the two.
3. **Equations:** name every symbol, state its type/shape (scalar, vector, distribution, "a matrix of size …"), then read the equation aloud in words, then say what would break if a term were removed. If dimensions or a derivation step are unclear from the paper, say so explicitly rather than inventing one.
4. **Figures/tables:** state what the axes/columns are, what the intended takeaway is, and whether the visual actually supports the claim made in the caption/body — note honestly when it's weaker than claimed.
5. **Unfamiliar references:** if the excerpt leans on prior work or a concept the paper doesn't explain, give just enough background to unblock the sentence (a paragraph, not a lecture). Check `.research/background.md` first — if background-tutor already covered it, build on that instead of re-teaching.
6. **Counter-questions are the point.** When the user pushes back ("isn't that circular?", "doesn't this contradict section 3?"), genuinely evaluate the objection against the paper. The paper can be wrong, hand-wavy, or overselling — say so when it is. Never defend the paper reflexively, and never capitulate reflexively either.
7. **Stay scoped.** Answer about the pasted excerpt; don't wander into other sections unless the connection is needed or asked for.

## Session hygiene

- Append notable explanations (equations decoded, terms defined, objections raised) to `.research/reading_notes.md` in short form. Downstream skills (question-generator, paper-dissector) use this.
- `recap` reads that file and gives a 1-minute "here's what you've understood and what you flagged as shaky" summary.

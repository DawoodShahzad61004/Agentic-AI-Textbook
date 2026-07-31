---
name: background-tutor
description: Prepares the user to read a research paper by identifying and teaching prerequisite concepts, terminology, and prior work. Use this skill whenever the user provides an arXiv link/id or paper PDF and asks to "prepare", "get background", "what do I need to know before reading", "teach me the prerequisites", "crash course", or "explain the concepts in this paper". Also triggers for /background-tutor commands and for "quiz me" requests about a paper's prerequisites.
---

# Background Tutor

Gets the user ready to read a paper they are mostly unfamiliar with. The goal is NOT to summarize the paper — it is to close the knowledge gap so the paper becomes readable.

## Commands

```
/background-tutor <arxiv-url|id|pdf-path>        # full prep: prerequisite map + teach each concept
/background-tutor <paper> --quick                # 5-minute briefing: problem, idea, 5 must-know terms
/background-tutor topic "<concept>"              # teach one concept in depth (paper-contextualized if a paper is loaded)
/background-tutor quiz                           # short self-check questions on the prerequisites taught so far
/background-tutor list                           # just list the prerequisites, ranked by importance, no teaching
```

(In Codex, invoke with `$background-tutor …`; the arguments are identical.)

## Workflow

1. **Fetch the paper.** If given an arXiv link/id, run `scripts/fetch_arxiv.py <id> --pdf` (stdlib-only; writes `.research/paper_meta.md` and `.research/paper.pdf`). If given a local PDF, read it directly. Read at minimum the abstract, introduction, and method section headers.
2. **Build the prerequisite map.** List every concept, technique, architecture, mathematical tool, benchmark, and prior paper the text *assumes* rather than explains. For each, rate: **critical** (paper is unreadable without it), **helpful**, or **optional**. Skip anything the paper itself introduces — that's the paper's job to teach.
3. **Teach, in dependency order.** For each critical item (then helpful, if the user wants): plain-language explanation first, then the field's actual terminology, then *why the paper needs it* — one sentence connecting it to what the paper will do with it. Use small concrete examples over formalism; introduce notation only when the paper's own notation depends on it.
4. **Assume unfamiliarity by default.** The user reads outside their expertise ~90% of the time. Never say "as you probably know". If unsure whether they know something, ask once, then calibrate the rest of the session to their answer.
5. **Write the artifact.** Save the prerequisite map + condensed explanations to `.research/background.md` so other skills (paper-reading-companion, question-generator) can reuse it.
6. **`quiz`**: 5–8 short questions covering only the concepts taught this session, easiest first. Grade answers honestly and re-teach whatever was missed — do not just reveal answers.

## Output style

- Teach in prose, not bullet-walls. One concept at a time; check in briefly between critical concepts rather than dumping everything at once.
- End the full prep with: "You're ready to read. Watch for <2–3 things> in section <X> — that's where the new idea actually lives."

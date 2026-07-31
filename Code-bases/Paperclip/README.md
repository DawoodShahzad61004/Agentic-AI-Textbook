# 📎 Paperclip

*It looks like you're trying to understand a research paper. Want help?*

Everyone's favorite paperclip, except this one actually reads the paper, clones the repo, and tells you where the authors' claims quietly stopped matching their code.

Nine `SKILL.md` skills that take you from *"found this on arXiv"* to *"I understand the method, traced every claim to the code, and know what I'd try next."* Same files, no rewrites — works in **Claude Code**, **Codex CLI**, and **GitHub Copilot**.

---

## The bit

Research papers assume you already know the field. Research code assumes you already know the paper. Paperclip sits in both gaps: it teaches you what you're missing *before* you read, keeps you company *while* you read, then turns the paper into a checklist and audits the code against it — including the parts the authors would rather you didn't notice.

No more "explain the whole paper to me" walls of text. No more losing an afternoon inside someone's `train.py` with no map. Paperclip breaks the whole arc into nine small, sharp tools instead of one vague one.

## The nine clips

| # | Skill | Command | Does what it says | Writes |
|---|-------|---------|--------------------|--------|
| 1 | Background Tutor | `/background-tutor` | Teaches the prerequisites *before* you drown | `.research/background.md` |
| 2 | Paper Reading Companion | `/paper-reading-companion` | Decodes sentences, equations, figures *live*, as you paste them | `.research/reading_notes.md` |
| 3 | Paper Dissector | `/paper-dissector` | Extracts claims, assumptions, limitations, experiment setup | `.research/dissection.md` |
| 4 | Codebase Explorer | `/codebase-explorer` | Maps the repo — structure, entry points, execution flow | `.research/codebase_map.md` |
| 5 | Paper-to-Code Mapper | `/paper-to-code-mapper` | Traces every claim to code, flags what's missing or different | `.research/claim_map.md` |
| 6 | Reverse Engineering Assistant | `/reverse-engineering-assistant` | Explains *why* the code is built this way — decisions, trade-offs | `.research/design_analysis.md` |
| 7 | Question Generator | `/question-generator` | Writes the interrogation questions a sharp advisor would ask | `.research/questions.md` |
| 8 | Production Readiness Reviewer | `/production-readiness-reviewer` | Grades the distance from "it ran once" to "someone can ship it" | `.research/prod_review.md` |
| 9 | Improvement & Research Ideas | `/improvement-research-ideas` | Turns every gap it found into an experiment worth running | `.research/ideas.md` |

Each is its own skill — invoke one, invoke all nine, doesn't matter. They just get sharper together (see below).

## Install

Paperclip is plain `SKILL.md` folders — copy, don't build.

```bash
# Claude Code — personal (all projects)
cp -r paperclip/*/ ~/.claude/skills/

# Claude Code — this project only
cp -r paperclip/*/ .claude/skills/

# Codex CLI
cp -r paperclip/*/ ~/.codex/skills/        # keep clear of the .system/ folder — that's Codex's own

# GitHub Copilot
cp -r paperclip/*/ ~/.copilot/skills/
/skills reload                              # inside a Copilot session
```

One copy of the folders serves all three — the format is an open standard, no vendor-specific frontmatter. Restart (or start a fresh session in) whichever agent you installed into so it picks the skills up.

**Invoking:** `/skill-name args` in Claude Code and Copilot, `$skill-name args` in Codex — or just describe the task in plain English; every skill's description is written to auto-trigger on how you'd naturally ask ("what did they claim but not implement" wakes up the mapper on its own).

## How the clips hold together

Every skill writes into a `.research/` folder in your working directory, and later skills *read* what earlier ones wrote instead of redoing the work:

- the dissector's claim ids (`C1`, `C2`, …) are exactly what the mapper audits against the code
- the mapper's "claimed but absent" findings become question-generator questions *and* improvement-ideas experiments
- the explorer's map tells the reverse-engineer and prod-reviewer where to even look

Run any skill alone and it'll do a quick shallow pass to fill in what's missing — but run them in order and each one gets measurably sharper. `.research/` is per-project and disposable; add it to `.gitignore` if you don't want the trail committed.

## A session, start to finish

```bash
cd my-paper-folder    # .research/ lands here, not in ~/.claude

# get ready to read
/background-tutor https://arxiv.org/abs/2401.12345
/background-tutor https://arxiv.org/abs/2401.12345 --quick   # or the 5-minute version

# read it, paste what confuses you
/paper-reading-companion start https://arxiv.org/abs/2401.12345
"wait, doesn't Eq. 5 assume the posterior is tractable?"

# turn it into a checklist
/paper-dissector https://arxiv.org/abs/2401.12345

# clone the code, get the lay of the land
git clone https://github.com/authors/their-repo && cd their-repo
/codebase-explorer .

# catch them in the act
/paper-to-code-mapper .
/paper-to-code-mapper gaps

# ask why it's built this way
/reverse-engineering-assistant decisions src/model.py

# get quizzed
/question-generator --cross

# could this actually ship?
/production-readiness-reviewer . --plan

# what's worth trying next
/improvement-research-ideas --experiments
```

Full flag list for every command lives in each skill's own `SKILL.md` — they're short, just open them.

## Scripts

Two stdlib-only Python scripts do the parts that don't need judgment (no `pip install`):

- **`fetch_arxiv.py`** *(bundled in `background-tutor/` and `paper-dissector/`)* — pulls title, authors, abstract via the arXiv API; `--pdf` grabs the paper too.
- **`repo_map.py`** *(in `codebase-explorer/`)* — walks the repo, skips the junk (`.git`, `node_modules`, checkpoints…), reports line counts, language mix, and entry-point candidates (`__main__` guards, click/typer/hydra/argparse, Makefile targets, `console_scripts`).

The agent calls these itself when a skill triggers. Nothing stops you running them by hand either.

## Notes

- **Compatibility**: only `name` + `description` in the frontmatter — nothing Claude-, Codex-, or Copilot-specific — so nothing to port.
- **Personal vs. project**: install personally; the workflow's the same for every paper you'll ever read. State lives in `.research/`, not in the skills.
- **It's yours now**: plain Markdown, tune the tiers, the audit dimensions, the output paths. Just keep the descriptions specific — that's the only thing doing the auto-triggering.

---

📎 *Star cost zero. Fair trade.*

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project Context

This repository is the source material for a textbook, not a software product. Before doing anything else — answering a question, updating `Book_Index.md`, writing a chapter, or querying the graph — read `PROJECT_CONTEXT.md` in the repo root. It explains what this project is, the author's working methodology, and what "help" means in this repo.

## Writing Book Chapters

Any task that produces or edits a chapter of the *Self-Learning Agentic RAG
System* book — as a Word `.docx`, or as source that becomes one — MUST follow
`Chapter_Build_Instructions.md`. Read that file in full before writing,
formatting, or generating a chapter. It is the single source of truth; do not
infer formatting from memory or from other chapters.

Non-negotiables (the full detail lives in that file):

- **Output**: a Word `.docx` that renders identically to the reference
  Chapter 3. Font is Times New Roman for text, Courier New for code/paths/identifiers.
- **Margins**: top / left / right = 2.5 cm, bottom = 1.5 cm. US Letter, portrait.
- **Diagrams**: insert as SVG/image (never Word shapes). Every chapter needs
  conceptual diagrams AND procedural flowcharts. Figures 4.88" wide, centered,
  captioned "Figure X.Y — short title.", and referenced by number in the body.
- **Black-and-white printing**: diagram meaning must never depend on hue. Carry
  information on luminance, shape, position, and labels; grayscale-test every
  figure before shipping (see §7).
- **Exact values**: page/margin, font sizes, callout colors, and table palettes
  are exact, not approximate. Use the hex values as written.
- **Required elements per chapter**: illustrative examples, intuitive analogies,
  precise terminology, a Definition box at each term's first use, skeleton (not
  monolithic) code templates, conceptual diagrams, procedural flowcharts.
- **Cadence**: epigraph → 2–3 paragraph intro stating end-of-chapter goals →
  numbered N.M sections → one Analogy per non-trivial mechanism → Common pitfall
  boxes only for real observed traps → closing paragraph bridging to the next chapter.

When in doubt about any layout, color, spacing, or structural decision, defer to
`Chapter_Build_Instructions.md` rather than guessing. Work through its Section 10
checklist before considering a chapter done.
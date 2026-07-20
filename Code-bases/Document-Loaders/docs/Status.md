# Project Status

## Chronological Log

### July 2026 — Establishing a three-loader PDF comparison harness

- **Built parallel conversion paths:** Added Docling, Unstructured, and Marker scripts that convert a shared corpus into tool-specific Markdown result directories.
- **Standardized the runtimes:** Moved the toolchain from Python 3.14 to three isolated Python 3.12 environments after wheel and cross-loader dependency failures (ADR-002 and ADR-005; BUG-001, BUG-002, and BUG-005 through BUG-008).
- **Verified the initial comparison:** All three loaders produced Markdown for the original RAG chapter. The later expanded corpus was run through Docling and Marker only.
- **Added durable project records:** Created the five-file tracking system described by the project guide and indexed the documentation in Graphify.

---

#### 2026-07-14 — Implement and validate three PDF-to-Markdown loaders

* Updated `docling_test.py` to write Markdown files instead of printing converted content.
* Added `unstructured_test.py`, including a lightweight element-to-Markdown mapping, and added `marker_test.py` for Marker output.
* Surveyed open-source multi-format and complex-document loaders, distinguishing parsing engines from framework adapters and outlining a routed production ingestion design; see Research topic 3.
* Diagnosed missing Unstructured packages/extras, a missing result directory, Marker installation failure on Python 3.14, and misleading failures when invoking Windows Python from Git Bash (BUG-001 through BUG-004).
* Created a Python 3.12 environment, installed Docling, `unstructured[pdf]`, and `marker-pdf[full]`, then verified the initial scripts and generated Markdown files.
* Compared the loader APIs and operational behavior; see Research topics 1 through 3 and ADR-001 through ADR-003.
* Tracked in: the original root loader scripts and loader-specific result directories; new ADR-001–ADR-003, BUG-001–BUG-004, Research topics 1–3, and `Architecture.md`.

---

#### 2026-07-15 — Build and assess the expanded batch-comparison harness

* **11:12:** Created the repository and committed the initial three-loader comparison (`85b76b8`), including the Docling, Unstructured, and Marker scripts and Markdown output for the RAG chapter.
* **12:27:** Standardized output handling, added `.gitignore`, and created the architecture, decision, research, bug, and status records (`bd183ca`).
* **12:35:** Added the root `README.md` with the project overview, verified setup, loader behavior, usage, limitations, and documentation links (`dd50831`).
* **12:40–13:43:** Expanded the local, Git-ignored corpus with five procurement, legal, and engineering PDFs, bringing the corpus to six PDFs and 251 pages.
* **13:11:** Added a temporary `uv` project scaffold (`3e8876e`). Dependency resolution then exposed an obsolete Numba selection, incompatible Marker/Unstructured Pillow constraints, incomplete Torch metadata, and an unrelated `marker` distribution (BUG-005 through BUG-008).
* Replaced the broken shared environment with `.venv-docling`, `.venv-unstructured`, and `.venv-marker` on Python 3.12 (ADR-005). A CUDA-enabled Torch build was verified for Docling, but an unrestricted upgrade later replaced it with a CPU build; see Research topic 4.
* **13:43–17:49:** Moved all converters under `codes/`; added recursive `source/` discovery, source-relative result mirroring, converter reuse, automatic directory creation, per-file failure continuation, and correct nonzero batch status (ADR-004). Removed the temporary shared requirements/lock workflow and the committed source PDF.
* Investigated Docling `std::bad_alloc` preprocessing failures. The current runner can count a partially processed document as converted, so the expanded Docling output has not been established as page-complete (BUG-009).
* **14:46–15:08:** Ran all six PDFs through Docling and Marker. Both produced six Markdown files; no corresponding expanded-corpus Unstructured outputs are present.
* **17:49:** Committed and pushed the completed restructuring and tracked output updates (`c9f712a`).
* **18:08:** Added the detailed Marker assessment (`5599aa2`) covering six PDFs and 251 pages. It found strong ordinary-text recovery but material failures in complex tables, forms, page layout, merged cells, reading order, heading hierarchy, image delivery, and encoding (Research topic 5; BUG-010).
* **19:07:** Reformatted and cleaned the report (`13e8f44`). It was subsequently renamed from `Report.md` to `Marker-PDF Report.md` (`73d0f62`) as the final action associated with the July 15 work session.
* Tracked in: `README.md`, `Marker-PDF Report.md`, `codes/`, `docs/`, and the generated Docling/Marker result updates; new ADR-004–ADR-005, Research topics 4–5, and BUG-005 through BUG-010.

---

#### 2026-07-16 — Extend Marker validation and prototype Markdown chunking

* **01:51:** Renamed `Report.md` to `Marker-PDF Report.md` and pushed `73d0f62`.
* **11:48–12:44:** Added two large RFT continuation PDFs locally and converted them with Marker. Both source PDFs and generated Markdown remained Git-ignored.
* **14:15:** Expanded and pushed the Marker report (`1432ae7`) with page-level findings. Small and highlighted text was often accurate, but contact-table row associations were corrupted; repeated titles and TOC page numbers were omitted; running headers interrupted long lists; and a dense table around pages 61–62 caused reordered, duplicated, and missing content. The resulting conclusion is that aggregate word retention cannot prove structural completeness (Research topics 5–6; BUG-011).
* **15:49–16:32:** Began the Marker-Markdown chunking workflow and repeatedly refreshed Graphify while iterating.
* **16:09–16:36:** Generated the first three ignored chunk reports, containing 1,976, 1,263, and 1,290 chunks.
* **16:32:** Committed and pushed the initial chunking setup (`6e176b3`): added `chunking/ingest.py` and `chunking/logger_config.py`; recursively loaded only Marker Markdown; used a 1,600-character recursive splitter with 200-character overlap and Markdown-friendly boundaries; retained source paths and per-source sequence numbers; wrote timestamped human-readable reports under ignored `chunk-runs/`; removed the tracked RAG-chapter Marker output; and accidentally committed Python bytecode (ADR-006).
* **17:57–19:17, uncommitted:** Replaced the generic splitter with a custom Markdown hierarchy, iterating through heading-level descent, table detection and preservation, nested-list recursion, prose fallbacks, and table/token diagnostics. Added per-chunk `cl100k_base` token counts and average-token statistics, created the untracked `codes/count_table_tokens.py`, updated `.gitignore` for Python cache directories, generated five more run reports, and refreshed Graphify repeatedly.
* The eight run reports recorded 1,976, 1,263, 1,290, 4,662, 4,838, 2,271, 2,271, and 2,271 chunks. The final two also recorded an average of 109.59 tokens per chunk.
* **Outcome:** The custom heading/table/list implementation did not meet the intended section-by-section behavior and was rejected. It will be rewritten separately; overlap is not part of the intended replacement. The committed recursive splitter remains only a baseline, not the final chunking design (Research topic 7).
* Tracked in: `Marker-PDF Report.md` and the initial `chunking/` workflow. Uncommitted/local evidence remains in `.gitignore`, `chunking/`, `codes/count_table_tokens.py`, and ignored `chunk-runs/`; new ADR-006, Research topics 6–7, and BUG-011 document the work.

---

#### 2026-07-17 — Replace the rejected splitter with a hand-authored rule set

* **12:46:** Committed and pushed `50208bc`: replaced the tracked recursive splitter with the rejected July 16 custom heading/table/list splitter and its per-chunk `cl100k_base` token diagnostics, added `codes/count_table_tokens.py`, ignored Python cache directories, and pushed the July 16 documentation batch.
* **14:29:** Generated a chunk report against the newly committed heading/table/list splitter: 1,273 chunks, averaging 192.61 tokens.
* Diagnosed why two earlier attempts at section-by-section splitting had failed: a recursive splitter reused from a separate project, and a Codex-generated splitter built from many interacting helper functions. Neither reached the intended per-section behavior.
* Hand-typed a rule set covering as many observed structural situations as could be enumerated, then had the coding agent implement it as a new top-to-bottom `temp_split()` in `chunking/ingest.py`, replacing the committed `split_text()`.
* **18:13–19:24, uncommitted:** Rewrote the splitter as a top-to-bottom boundary-selection algorithm: detects headings outside fenced code blocks; locates whole Markdown-table spans and never splits them; detects list spans and indentation levels; keeps headings attached to following content, to immediately following tables, and to lead-in paragraphs before flat lists; moves trailing orphan headings into the next chunk; prefers paragraph and line boundaries over hard character cuts; removes the earlier 200-character overlap; and adds dedicated handling for oversized tables, nested lists, and individually oversized sections.
* Iterated in a loop — run `ingest.py`, manually inspect the report against the source RFT documents, add or adjust one rule — producing four more chunk reports: 2,065, 2,066, 1,915, and 1,913 chunks.
* While inspecting the reports, found that Marker's PDF-to-Markdown conversion itself flattens nested list pointers to a single indentation level, which limits how much list hierarchy the chunker can recover regardless of its own rules; a regex-based post-processing fix is planned but not yet implemented (BUG-012).
* Tracked in: uncommitted rewrite of `temp_split()` in `chunking/ingest.py`; five `chunk-runs/` reports; new Research topic 8 and BUG-012.

---

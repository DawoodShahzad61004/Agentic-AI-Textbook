# Architecture

## System Overview

Document Loaders is a batch comparison harness that recursively discovers files under `source/` and converts them to Markdown with Docling, Unstructured, and Marker. Each implementation is intentionally independent and writes into a dedicated result directory so outputs can be inspected side by side. Source subdirectories are mirrored in each result tree (ADR-004).

## High-Level Architecture

```text
source/**/* ──┬─> codes/docling_test.py ───────> docling_results/**/*.md
             ├─> codes/unstructured_test.py ──> unstructured_results/**/*.md
             │       └─> elements_to_markdown()
             └─> codes/marker_test.py ─────────> marker_results/**/*.md

docs/*.md <──── project history, architecture, decisions, research, and bugs
graphify-out/ <─ persistent graph of code, documents, sources, and relationships
```

## Module Breakdown

### `codes/docling_test.py`

Recursively discovers source files, creates one `docling.document_converter.DocumentConverter`, converts each file, calls `export_to_markdown()`, and writes UTF-8 Markdown into the matching path under `docling_results/`. Docling performs model-backed document analysis and may download OCR/layout assets on first use.

### `codes/unstructured_test.py`

Calls `unstructured.partition.auto.partition()` for every discovered file. Its local `elements_to_markdown()` adapter maps `Title`, `Header`, and `ListItem` categories to basic Markdown and emits other elements as plain paragraphs. Results are written into matching paths under `unstructured_results/`.

### `codes/marker_test.py`

Builds one `marker.converters.pdf.PdfConverter` with `create_model_dict()`, attempts every discovered source file, extracts Markdown using `text_from_rendered()`, and writes into matching paths under `marker_results/`. The current converter is PDF-oriented; unsupported source formats are reported as failures while the remaining files continue. The first run can spend significant time downloading or initializing model artifacts.

### `source/`

The shared recursive input tree. The scripts resolve it from their own file locations, so they behave consistently whether launched from the repository root or another current working directory.

### Result directories

`docling_results/`, `unstructured_results/`, and `marker_results/` isolate outputs by implementation. Each script creates its output directory and any mirrored subdirectories automatically. A source such as `source/manuals/guide.pdf` maps to `<loader>_results/manuals/guide.md`.

### `chunking/`

`chunking/ingest.py` recursively loads only Marker-generated `.md` and `.markdown` files, splits them into chunks, preserves each source-relative path, and assigns a zero-based per-source chunk sequence. The tracked implementation was `RecursiveCharacterTextSplitter` through `6e176b3`; `50208bc` (2026-07-17) replaced it with the committed custom heading/table/list splitter, dropping the `langchain-text-splitters` dependency entirely, and added per-chunk `cl100k_base` token counts, average-token statistics, and `codes/count_table_tokens.py`. `chunking/logger_config.py` writes one timestamped, human-readable report per run under `chunk-runs/`, including chunk content, source, sequence, character, and token counts (ADR-006).

An uncommitted 2026-07-17 rewrite replaces the committed heading/table/list splitter with a hand-authored, top-to-bottom boundary-selection algorithm (`temp_split()`), built from an explicit rule set rather than heading-level recursion. It walks the document once, deciding at each candidate chunk boundary whether to roll headings, tables, or list items into the next chunk, and drops the earlier overlap behavior entirely. This is the current in-progress design, refined iteratively against real Marker output; it is not yet committed or treated as settled architecture (Research topic 8).

A further uncommitted 2026-07-20 change adds a `preprocessing()` stage that runs inside `split_documents()` on each document's in-memory text before `temp_split()` (`temp_split(preprocessing(document.page_content))`); it does not rewrite the Marker Markdown on disk. It normalizes a specific Marker defect in RFT/contract-style sources — numbered clauses (`3.1`, `5.1`) emitted inconsistently as plain paragraphs, dash-prefixed items, or bold-labelled lines with bodies fragmented across blank lines — by detecting runs of consecutive same-family markers (numeric `x.y`, alphabetic `(a)`, roman `(i)`) and either normalizing their leading list syntax or promoting bold-labelled/already-headed runs to matching-level headings with fragmented bodies rejoined; it also promotes italic `*Label*:` sublabels under a heading to a deeper subheading and pulls leading `<span id="…">` anchors onto their own line. The pass is a best-effort heuristic scoped to observed patterns, validated against a full `marker_results/` ground-truth pair, and is bounded by Marker's own list-flattening defect (ADR-007; Research topic 9; BUG-012 through BUG-015).

### `chunk-runs/`

Stores local diagnostic reports from chunking runs. Reports are intentionally Git-ignored because they can be multi-megabyte derived artifacts. Eight July 16 reports document the progression from the initial recursive splitter to the abandoned structural prototype. Five July 17 reports document a run against the committed heading/table/list splitter (1,273 chunks) followed by four iterations of the rule-based rewrite (2,065; 2,066; 1,915; and 1,913 chunks).

### `docs/`

Contains the five cross-referenced tracking files: chronological status, current architecture, architectural decisions, research findings, and bug history.

### `graphify-out/`

Stores the generated knowledge graph, audit report, interactive HTML visualization, manifest, and extraction cache. Graphify links loader scripts, generated documents, RAG concepts, and project documentation.

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Runtime | Python 3.12.10 in three loader-specific environments | `.venv-docling`, `.venv-unstructured`, and `.venv-marker`; see ADR-002 and ADR-005 |
| Structured conversion | Docling 2.113.0 | Exports Markdown from Docling's document model |
| Element partitioning | Unstructured 0.24.1 | Installed with PDF extras; local code maps elements to Markdown |
| Model-backed conversion | Marker PDF 1.10.2 | Installed from `marker-pdf`; the unrelated `marker` distribution is incompatible |
| Environment/package tool | `uv` | Used to create the three Python 3.12 environments and install packages |
| Knowledge graph | Graphify | Maintains `graphify-out/graph.json`, report, and visualization |
| Markdown chunking | Hand-authored splitter (`chunking/ingest.py`) | `langchain-text-splitters` was dropped in `50208bc`; the committed heading/table/list splitter and its uncommitted rule-based replacement are both plain Python/`re`, and the final algorithm remains undecided |
| Token measurement | `tiktoken` (`cl100k_base`) | Used by the run logger and `codes/count_table_tokens.py` diagnostic utility |
| Dependency installation | Direct `uv pip install` commands | The temporary shared manifest and lockfile were removed because the selected Marker and Unstructured versions cannot resolve together |

## Operational Constraints

- Prefer PowerShell on Windows for the heavy native Python stack; Git Bash produced unreliable exit codes and a reported segmentation fault while PowerShell completed successfully (BUG-004).
- Initial runs may download OCR/layout models and can be slow on CPU.
- The scripts overwrite existing Markdown outputs that map to the same source path.
- Each loader has a dedicated environment because current Marker and Unstructured releases have incompatible Pillow requirements.
- Each batch continues after individual conversion errors and exits with status 1 if any source failed.
- Docling may return a document even when native preprocessing failed for individual pages, so a zero script-level failure count does not prove that every page converted completely (BUG-009).
- Marker currently writes only the Markdown returned by `text_from_rendered()`; it does not export or validate referenced image assets (BUG-010).
- Marker output can retain most words while corrupting row associations, dropping navigation data, and duplicating or omitting content near dense cross-page tables. Chunking must not be treated as a repair for these source-conversion defects (BUG-011).
- Marker flattens nested list pointers to one indentation level, which bounds how much list hierarchy any downstream Markdown splitter can recover (BUG-012).
- The uncommitted `preprocessing()` stage repairs Marker's clause/heading structure in memory only and never rewrites `marker_results/`; it is a best-effort heuristic scoped to observed RFT/contract patterns, not a general Markdown normalizer, and its correctness is guarded by a round-trip no-loss check rather than proven for arbitrary input (ADR-007; BUG-013 through BUG-015).
- `chunk-runs/` and the local source/result corpus are derived, Git-ignored artifacts. The committed chunking implementation no longer depends on `langchain-text-splitters`, but `tiktoken` (used by the run logger and `codes/count_table_tokens.py`) is still not represented by a tracked dependency manifest.

## Researched Production Direction (Not Implemented)

Research topic 3 recommends evolving beyond the current three-script comparison into routed ingestion. A production pipeline would inspect each document before parsing, choose a parser based on format and complexity, preserve page/section metadata, and quarantine low-confidence results rather than trusting one parser for every file.

```text
incoming document
       |
       v
format/layout/scan inspection
       |
       +--> ordinary digital PDF ------> PyMuPDF4LLM fast path
       +--> structured/complex file ---> Docling primary parser
       +--> scanned PDF/image ----------> PaddleOCR or OCRmyPDF
       +--> unsupported/legacy format --> Apache Tika fallback
       |
       v
normalized Document objects (for example, LangChain adapters)
       |
       +--> accepted with page/section metadata
       └--> quarantined when parsing confidence is low
```

This is research guidance only. None of the router, inspection, confidence scoring, quarantine, Tika, PyMuPDF4LLM, or OCR stages currently exists in the repository, and no ADR has adopted them.

## Changelog

### 2026-07-14 — Add parallel loaders and standardize Python 3.12

The project grew from a Docling experiment into three parallel PDF-to-Markdown implementations. Unstructured and Marker added their own APIs, model/dependency stacks, and result directories. The runtime moved from Python 3.14 to Python 3.12 to obtain compatible Windows wheels (ADR-002), and PowerShell became the verified execution shell (ADR-003).

### 2026-07-15 — Add tracking documents and graph integration

Added the five-file documentation system under `docs/` and indexed it in the existing Graphify knowledge graph. This changes the repository from code-and-output-only exploration into a project with durable, cross-referenced operational history.

The expanded source transcript also restored the broader loader survey and routed-ingestion recommendation. It is documented as a researched future direction, not as current system architecture or an accepted decision (Research topic 3).

The loader entry points were later moved under `codes/` and changed from one hard-coded input to recursive batch discovery under `source/`. Output trees are now created automatically and preserve source subdirectories (ADR-004; BUG-003).

The initial shared `uv` environment was abandoned after dependency resolution exposed incompatible Pillow constraints between Unstructured 0.24.1 and Marker 1.10.2. The project now uses three Python 3.12 environments, one per loader (ADR-005; BUG-005 through BUG-008).

The expanded six-PDF corpus was run through Docling and Marker. Both result trees contain six Markdown files, while Unstructured has no corresponding expanded-corpus outputs. The Marker assessment covers 251 source pages and is summarized in Research topic 5.

### 2026-07-16 — Extend Marker validation and begin Markdown chunking

Renamed the Marker report, then expanded it with page-level checks across two additional local RFT continuation volumes. The review confirmed accurate recovery of small and highlighted text but exposed corrupted contact-table row associations, omitted repeated titles and table-of-contents page numbers, running-header interruptions in long lists, and reordered, duplicated, and missing material around a dense table on pages 61–62 (Research topic 5; BUG-011).

Added the first committed chunking workflow (`6e176b3`). It recursively ingests Marker Markdown, uses a 1,600-character recursive splitter with 200-character overlap, retains source paths and per-source sequence numbers, and writes timestamped reports to the ignored `chunk-runs/` directory (ADR-006). The commit also removed the previously tracked RAG-chapter Marker output and accidentally included Python bytecode.

Later uncommitted experiments replaced the baseline with a custom Markdown hierarchy for headings, tables, and nested lists; added per-chunk `cl100k_base` token counts and average-token statistics; added `codes/count_table_tokens.py`; and ignored Python cache directories. After repeated runs, this custom splitter was rejected and will be rewritten separately, so its algorithm is documented as experimental rather than current architecture.

### 2026-07-17 — Commit the rejected splitter, then replace it with hand-authored rules

Committed and pushed the previously rejected custom heading/table/list splitter, its token diagnostics, and `codes/count_table_tokens.py` as the tracked `chunking/ingest.py` (`50208bc`), which also dropped the `langchain-text-splitters` dependency. A run against this committed splitter produced 1,273 chunks averaging 192.61 tokens.

After two earlier section-by-section approaches (a reused recursive splitter, a Codex-generated complex splitter) had failed to produce the intended behavior, hand-typed a rule set covering as many observed structural situations as could be enumerated and had the coding agent implement it as a new top-to-bottom, uncommitted `temp_split()`. Iterated in a loop of running `ingest.py`, inspecting the report against real RFT documents, and adding or adjusting one rule at a time, producing four more reports (2,065; 2,066; 1,915; and 1,913 chunks) as the rules stabilized (Research topic 8).

While inspecting these reports, found that Marker itself flattens nested list pointers to one indentation level, which bounds how much list hierarchy the chunker can recover independent of its own logic; a regex-based normalization fix is planned but not yet implemented (BUG-012).

### 2026-07-20 — Add an in-memory clause-normalization pass and harden splitter boundaries

Added an uncommitted `preprocessing()` stage that runs on each document's in-memory text before `temp_split()`, without rewriting the Marker Markdown on disk (ADR-007). It repairs Marker's inconsistent numbered-clause/heading formatting for RFT/contract-style sources — normalizing consecutive same-family markers (numeric, alphabetic, roman), promoting bold-labelled clause runs and italic sublabels to headings, rejoining clause bodies fragmented across blank lines, and pulling leading `<span id="…">` anchors onto their own line.

Validation escalated from two hand-authored before/after examples to a ~2,700-line real `marker_results/input.md` / `expected-output.md` ground-truth pair, which surfaced defects the toy examples hid: alphabetic/roman marker families chained across unrelated sections and overlapping nested edits (BUG-013), an unconditional forward-merge that concatenated unrelated glossary definitions (BUG-014), and a data-loss bug in the relaxed nested-list boundary helper (BUG-015). The same real document also drove two `temp_split()` boundary fixes — one-off deep subsections now close at the next shallower heading, lists stay attached to their heading/lead-in even when nested, a deferred subsection now carries its parent heading forward (`_enclosing_heading_start()`), and a resolved hierarchy no longer returns a raw mid-word character cut. Correctness is guarded by a full round-trip no-loss check across all four local documents (Research topic 9).

---

# Architecture

## System Overview

Document Loaders is a batch comparison harness that recursively discovers files under `source/` and converts them to Markdown with Docling, Unstructured, and Marker. Each implementation is intentionally independent and writes into a dedicated result directory so outputs can be inspected side by side. Source subdirectories are mirrored in each result tree (ADR-004).

## High-Level Architecture

```text
source/**/* ──┬─> codes/docling_test.py ───────> docling_results/**/*.md
             ├─> codes/unstructured_test.py ──> unstructured_results/**/*.md
             │       └─> elements_to_markdown()
             └─> codes/marker_test.py ─────────> marker_results/**/*.md
                     └─> in-process surya models (marker-pdf 1.10.2)
                         the 2.0.0 out-of-process VLM server was reverted; see ADR-012

marker_results/**/*.md ─> chunking/ingest.py ──> chunk-runs/chunks_<timestamp>.md
dataset/{input,expected-output}.md <─── chunking ground-truth pair (not a conversion output)

docs/*.md <──── project history, architecture, decisions, research, and bugs
graphify-out/ <─ persistent graph of code, documents, sources, and relationships
```

## Module Breakdown

### `codes/docling_test.py`

Recursively discovers source files, creates one `docling.document_converter.DocumentConverter`, converts each file, calls `export_to_markdown()`, and writes UTF-8 Markdown into the matching path under `docling_results/`. Docling performs model-backed document analysis and may download OCR/layout assets on first use.

### `codes/unstructured_test.py`

Calls `unstructured.partition.auto.partition()` for every discovered file. Its local `elements_to_markdown()` adapter maps `Title`, `Header`, and `ListItem` categories to basic Markdown and emits other elements as plain paragraphs. Results are written into matching paths under `unstructured_results/`.

### `codes/marker_test.py`

Builds one `marker.converters.pdf.PdfConverter` with `create_model_dict()` and no configuration, attempts every discovered source file, extracts Markdown using `text_from_rendered()`, and writes into matching paths under `marker_results/`. The current converter is PDF-oriented; unsupported source formats are reported as failures while the remaining files continue. The first run can spend significant time downloading or initializing model artifacts.

Conversion is deliberately sequential — one converter, one document at a time, whole documents rather than page ranges. Page batching and concurrent workers were implemented, measured, and rejected as slower and unstable on this hardware; see ADR-008 and BUG-016 before reintroducing either.

The module is a 51-line script with no environment preamble. It was restored to that state on 2026-07-23 by reverting Marker to `marker-pdf==1.10.2` on output-quality grounds (ADR-012), which removed three separate layers in one step: the 2.0.0 surya adaptation block (`SURYA_INFERENCE_BACKEND=llamacpp`, the `LLAMA_CPP_BINARY` fallback, `SURYA_GUIDED_LAYOUT=false`) added on 2026-07-21 for BUG-017 and BUG-018; the `config={"mode": "balanced"}` pin from ADR-008, which 1.10.2 has no concept of; and the same-day recursion and worker-pool instrumentation described in Research topic 12. Two consequences are load-bearing rather than cosmetic. Running headers and footers are no longer removed — `MarginaliaProcessor` does not exist in 1.10.2, so the position Research topic 6 describes governs again. And the two defects diagnosed on 2026-07-23 survive the revert while their fixes do not: `markdownify` over `html.parser` is the 1.10.2 Markdown renderer path too (BUG-024), and `pdftext 0.6.3` carries the identical `min(workers, pages // 10)` pool sizing with the same `pdftext_workers = 4` provider default, which Marker's own CLI and server front-ends override to 1 and this script does not (BUG-025).

### `source/`

The shared recursive input tree. The scripts resolve it from their own file locations, so they behave consistently whether launched from the repository root or another current working directory.

### Result directories

`docling_results/`, `unstructured_results/`, and `marker_results/` isolate outputs by implementation. Each script creates its output directory and any mirrored subdirectories automatically. A source such as `source/manuals/guide.pdf` maps to `<loader>_results/manuals/guide.md`.

`marker_results/` carries an additional provenance caveat after 2026-07-21: files may originate from Marker 1.10.2, 2.0.0 `fast`, or 2.0.0 `balanced`, which are three different extraction pipelines. The tree must be regenerated wholesale before it is treated as a comparison baseline (ADR-009; Research topic 10).

Since the 2026-07-23 revert that caveat is stronger still: **no file in the tree matches the installed Marker version.** All five current files are 2.0.0 `balanced` output — two 250-page RFT volumes from 2026-07-22 and `src1.md`/`src2.md`/`src3.md` from 2026-07-23 — while `.venv-marker` now holds 1.10.2 (ADR-012). Regenerating will also reintroduce the running headers that `MarginaliaProcessor` had been removing. One of those files, `src2.md`, is a structurally collapsed conversion that the batch summary counted as a success: 244 lines and 50 MB from a 154-page source, 83 of those lines a single 215-column table (BUG-026).

### `dataset/`

Holds the hand-produced ground-truth pair used to validate the chunking `preprocessing()` stage — `input.md` (a full ~2,700-line Marker-converted RFT plus its General Terms and Conditions contract body) and `expected-output.md` (its corrected form). Both previously sat inside `marker_results/`, where `chunking/ingest.py` picked them up as ordinary conversion output and inflated chunk counts. They were moved to a dedicated, Git-ignored `dataset/` directory on 2026-07-21 so the chunking corpus contains only real Marker output. `input.md` also serves as the retained pre-upgrade Marker 1.10.2 sample used for before/after comparison in Research topic 10.

### `chunking/`

`chunking/ingest.py` recursively loads only Marker-generated `.md` and `.markdown` files, splits them into chunks, preserves each source-relative path, and assigns a zero-based per-source chunk sequence. The tracked implementation was `RecursiveCharacterTextSplitter` through `6e176b3`; `50208bc` (2026-07-17) replaced it with the committed custom heading/table/list splitter, dropping the `langchain-text-splitters` dependency entirely, and added per-chunk `cl100k_base` token counts, average-token statistics, and `codes/count_table_tokens.py`. `chunking/logger_config.py` writes one timestamped, human-readable report per run under `chunk-runs/`, including chunk content, source, sequence, character, and token counts (ADR-006).

An uncommitted 2026-07-17 rewrite replaced the committed heading/table/list splitter with a hand-authored, top-to-bottom boundary-selection algorithm (`temp_split()`), built from an explicit rule set rather than heading-level recursion, and dropped the earlier overlap behavior entirely (Research topic 8). That rule set was itself replaced on 2026-07-22, after six rounds of extension against real Marker output left it producing chunks far below `CHUNK_SIZE` next to content that would have fitted, and sections torn at a subsection boundary (BUG-022).

`temp_split()` is now parse-then-pack (ADR-010). `_build_tree()` parses the document once into a tree of `_Node` structural units — sections nested by ATX heading level, and within each section its own tables, lists and paragraphs — and `_pack()` fills each chunk with whole sibling units until the next would not fit, moving that unit to the following chunk intact. `_split_node()` opens a unit up only when it cannot fit an empty chunk by itself, and then only one level at a time, so a section is never divided while a coarser boundary was available. `_extend_start()` attaches every heading to the first unit beneath it at every depth, making a stranded heading unrepresentable; `_lead_in_fits()` hands a short pending buffer into a unit that is about to be opened anyway rather than closing the chunk early. `CHUNK_SIZE` (1,600 characters) bounds every chunk; an oversized list splits on top-level pointers only, keeping nested children with their parent pointer.

Tables were exempt from that limit until 2026-07-22, when ADR-011 replaced the exemption with `_split_table()`. A table that does not fit is parsed into a header stack, an alignment row and data rows, then re-serialized across several chunks, each carrying the headers that apply to the cells it holds: by row when the table has column headers, both, or neither; by column when it has only row headers; descending to cell groups within a row or rows within a column, and finally to boundaries inside a single cell (paragraph, then list item, then sentence, then word) when a row, column or cell overruns on its own. Padding and alignment rows are normalized on output — neither is semantic, Marker pads to the widest cell, and normalization alone brings many tables back under the limit without splitting them at all. Any heading introducing the table repeats on every piece. Split tables are therefore not byte-identical to their source, so the strict round-trip check no longer applies to them; the standing invariants are that no chunk exceeds `CHUNK_SIZE`, that every source line still appears in some chunk once normalized to its rendered form, and that no chunk closes on a heading — nor on a heading followed by `<span id>` anchors — unless it is the last (BUG-023). All of this remains experimental and uncommitted: there is no test suite, and verification means re-running `ingest.py`, reading the report, and re-checking those invariants by hand.

A further uncommitted 2026-07-20 change adds a `preprocessing()` stage that runs inside `split_documents()` on each document's in-memory text before `temp_split()` (`temp_split(preprocessing(document.page_content))`); it does not rewrite the Marker Markdown on disk. It normalizes a specific Marker defect in RFT/contract-style sources — numbered clauses (`3.1`, `5.1`) emitted inconsistently as plain paragraphs, dash-prefixed items, or bold-labelled lines with bodies fragmented across blank lines — by detecting runs of consecutive same-family markers (numeric `x.y`, alphabetic `(a)`, roman `(i)`) and either normalizing their leading list syntax or promoting bold-labelled/already-headed runs to matching-level headings with fragmented bodies rejoined; it also promotes italic `*Label*:` sublabels under a heading to a deeper subheading and pulls leading `<span id="…">` anchors onto their own line. The pass is a best-effort heuristic scoped to observed patterns, validated against a full `marker_results/` ground-truth pair, and is bounded by Marker's own list-flattening defect (ADR-007; Research topic 9; BUG-012 through BUG-015).

### `chunk-runs/`

Stores local diagnostic reports from chunking runs. Reports are intentionally Git-ignored because they can be multi-megabyte derived artifacts. Eight July 16 reports document the progression from the initial recursive splitter to the abandoned structural prototype. Five July 17 reports document a run against the committed heading/table/list splitter (1,273 chunks) followed by four iterations of the rule-based rewrite (2,065; 2,066; 1,915; and 1,913 chunks). Ten July 20 reports cover the `preprocessing()` development and ground-truth validation cycle. One July 21 report (1,949 chunks, 128.14 average tokens) is the first run against Marker 2.0.0 output; it is not comparable to the July 20 totals, because the corpus simultaneously changed from four documents to two when the ground-truth pair moved to `dataset/`. Twenty-five July 22 reports track the parse-then-pack rewrite and the table work, and are only comparable to one another where `CHUNK_SIZE` matches — it was moved between 1,600, 2,000 and 2,400 during the day to compare fill. At 1,600 the sequence runs 1,949 (pre-rewrite) → 1,051 (parse-then-pack, ADR-010) → 1,069 (tables bounded, ADR-011) → 1,064 (trailing-heading rule, BUG-023), the last averaging 233.68 tokens against the 128.14 of the pre-rewrite run over the same corpus. Since 2026-07-22 each report also names the largest chunk by token count and gives its token and character totals.

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
| Model-backed conversion | Marker PDF 1.10.2 | Installed from `marker-pdf`; the unrelated `marker` distribution is incompatible. Upgraded to 2.0.0 on 2026-07-21 for `MarginaliaProcessor` (ADR-009), then reverted on 2026-07-23 on output-quality grounds (ADR-012) |
| Marker inference | surya-ocr 0.17.1, in-process | 1.10.2 runs its models inside the Python process. The 2.0.0 out-of-process VLM server — surya-ocr 0.22.1 plus a llama.cpp `llama-server` binary at `%LOCALAPPDATA%\llama.cpp` — was removed by the revert; no external binary is required. Related supporting packages rolled back with it: `pdftext 0.6.3`, `pypdfium2 4.30.0`, `transformers 4.57.6` |
| Marker GPU stack | `torch 2.13.0+cu130`, `torchvision 0.28.0+cu130` | Deliberately left untouched by the 2026-07-23 revert and re-verified with an actual matmul. The RTX 5050 Laptop is Blackwell (sm_120) and needs CUDA 12.8+; `cu130` is the only PyTorch index carrying `torch 2.13.0`. Any install that resolves Torch without an explicit `--index-url` silently reverts to CPU wheels. `torchaudio` must stay uninstalled (BUG-019) |
| Environment/package tool | `uv` | Used to create the three Python 3.12 environments and install packages |
| Knowledge graph | Graphify | Maintains `graphify-out/graph.json`, report, and visualization |
| Markdown chunking | Hand-authored splitter (`chunking/ingest.py`) | `langchain-text-splitters` was dropped in `50208bc`; the committed heading/table/list splitter, its uncommitted rule-based replacement, and the parse-then-pack rewrite that superseded that in turn are all plain Python/`re` (ADR-010, ADR-011). The algorithm is no longer boundary-selection but is still not settled |
| Token measurement | `tiktoken` (`cl100k_base`) | Used by the run logger and `codes/count_table_tokens.py` diagnostic utility |
| Dependency installation | Direct `uv pip install` commands | The temporary shared manifest and lockfile were removed because the selected Marker and Unstructured versions cannot resolve together |

## Operational Constraints

- Prefer PowerShell on Windows for the heavy native Python stack; Git Bash produced unreliable exit codes and a reported segmentation fault while PowerShell completed successfully (BUG-004).
- Initial runs may download OCR/layout models and can be slow on CPU.
- The scripts overwrite existing Markdown outputs that map to the same source path.
- Each loader has a dedicated environment because current Marker and Unstructured releases have incompatible Pillow requirements.
- Each batch continues after individual conversion errors and exits with status 1 if any source failed.
- Docling may return a document even when native preprocessing failed for individual pages, so a zero script-level failure count does not prove that every page converted completely (BUG-009).
- Marker currently writes only the Markdown returned by `text_from_rendered()`; it does not export or validate referenced image assets (BUG-010). The 2.0.0 upgrade did not change this — the regenerated two-volume corpus still contains 259 unresolved image references — although it did eliminate the separate mojibake symptom.
- Marker no longer requires an external `llama-server` binary or spawned inference servers; the 2026-07-23 revert to 1.10.2 returned it to in-process models (ADR-012). The out-of-process diagnostics that mattered under 2.0.0 — reading `~/.cache/datalab/surya/*.log` on a health-check timeout, killing orphaned `llama-server` processes still holding VRAM — do not apply to the installed version and are retained in ADR-009 and Research topic 10 as history.
- Running headers and footers are **not** removed by the installed version. `MarginaliaProcessor` is a 2.0.0 processor and does not exist in 1.10.2, so the classification-bound behaviour described in Research topic 6 governs again: `keep_pageheader_in_output=False` only suppresses blocks the layout model actually labelled `PageHeader`. Regenerating `marker_results/` will therefore return running headers to the chunking corpus (ADR-012).
- `codes/marker_test.py` constructs `PdfConverter` with no configuration, so it takes 1.10.2's defaults — including `pdftext_workers = 4`, which spawns a process pool for any document over ~40 pages and fails the whole conversion if one worker dies (BUG-025). Marker's own CLI, server and Streamlit entry points force this to 1; this script does not. The Markdown renderer path (`markdownify` over Python's `html.parser`) can also exhaust the recursion limit on deeply nested HTML, at roughly 480 levels under the default limit of 1000 (BUG-024). Both failures were diagnosed and fixed on 2026-07-23; both fixes were removed by the revert while the defects were not.
- Marker 1.10.2 has a dedicated table model, so the VLM-generated table pathologies of 2.0.0 do not apply to new conversions. They do apply to everything currently in `marker_results/`, all of which is 2.0.0 output (BUG-020, BUG-026).
- Marker output can retain most words while corrupting row associations, dropping navigation data, and duplicating or omitting content near dense cross-page tables. Chunking must not be treated as a repair for these source-conversion defects (BUG-011).
- Marker flattens nested list pointers to one indentation level, which bounds how much list hierarchy any downstream Markdown splitter can recover (BUG-012).
- The uncommitted `preprocessing()` stage repairs Marker's clause/heading structure in memory only and never rewrites `marker_results/`; it is a best-effort heuristic scoped to observed RFT/contract patterns, not a general Markdown normalizer, and its correctness is guarded by a round-trip no-loss check rather than proven for arbitrary input (ADR-007; BUG-013 through BUG-015).
- The splitter carries three invariants that nothing enforces automatically: no chunk exceeds `CHUNK_SIZE`, every source line survives in some chunk once normalized to its rendered form, and no chunk closes on a heading — nor on a heading followed by `<span id>` anchors — unless it is the document's last. Verifying a change to `chunking/ingest.py` means re-running it and re-checking all three by hand (ADR-010, ADR-011; BUG-023).
- A split table is deliberately not byte-identical to its source: padding is normalized, alignment rows are rewritten, and headers repeat on every piece. Do not compare `chunk-runs/` table text to `marker_results/` verbatim, and do not compare chunk counts across runs with different `CHUNK_SIZE` values (ADR-011).
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

### 2026-07-21 — Upgrade Marker to a VLM-server pipeline and reject page-level parallelism

Upgraded `.venv-marker` from `marker-pdf` 1.10.2 to 2.0.0 to obtain `MarginaliaProcessor`, which removes running headers and footers positionally rather than by layout classification — the defect the 1.10.2 configuration could not reach (ADR-009). Verified on the regenerated corpus at shipped defaults: the standalone running-header lines present in the retained 1.10.2 sample are gone, and mojibake disappeared, while broken image references remain (Research topic 10).

The upgrade replaced an in-process model pipeline with a hybrid one: surya-ocr 0.22.1 runs the VLM in a separate OpenAI-compatible inference server while the classical models stay torch-side. That forced a local `llama-server` install in place of the hardware-default vllm/Docker backend, disabling guided layout decoding, restoring a CUDA `cu130` Torch build, and removing an ABI-orphaned `torchaudio` (BUG-017 through BUG-019). `codes/marker_test.py` gained the environment preamble these require. A renderer recursion failure on a VLM-reconstructed table was also observed and left open (BUG-020).

`fast` mode was trialled as a cheaper pipeline and rejected on structural grounds; `balanced` is now pinned explicitly so output no longer depends on the active device. Parallel 20-page batching was then implemented to make `balanced` affordable, measured, and reverted — 32% slower serially and a reproducible native llama-server abort with two workers (ADR-008; BUG-016).

The chunking ground-truth pair moved out of `marker_results/` into a new Git-ignored `dataset/` directory so it stops entering the chunking corpus as if it were conversion output.

### 2026-07-22 — Replace boundary selection with structural packing and bound tables by size

`temp_split()` stopped being a boundary selector. The rule set extended through six rounds since 2026-07-17 was retired along with eleven of its helpers, and replaced by a two-phase parse-then-pack algorithm: the document is parsed once into a tree of structural units, then those units are packed greedily into chunks, with a unit opened up only when it cannot fit an empty chunk alone (ADR-010). The change was driven by two user-reported defects that the old rules could not express away — under-full chunks beside content that would have fitted, and sections torn at a subsection boundary (BUG-022) — and by a heading-level inversion in `preprocessing()` that made the old "deepest heading level" heuristic select a section and its own children as peers (BUG-021). `ingest.py` fell from 1,176 to 974 lines.

Tables stopped being exempt from `CHUNK_SIZE`. The exemption had been costing 38 over-limit chunks with a maximum of 10,071 characters, so `_split_table()` now re-serializes an oversized table across several chunks, each repeating the headers covering its own cells, splitting by row or by column according to which headers exist and descending to cell groups and then to content inside a cell when necessary (ADR-011). Because a split table is no longer byte-identical to its source, the strict round-trip invariant held since 2026-07-20 was narrowed to a per-line survival check, and two supporting parsing defects were corrected: pipe-splitting that ignored escapes and code spans, and table spans that began below a multi-level header stack.

A trailing-heading guard the rewrite had dropped was restored and then extended to cover a heading followed by `<span id>` anchors, so a chunk no longer closes on a heading whose content starts the next one (BUG-023). A broader form of that rule — never closing on any line that renders to nothing — was implemented, measured across the corpus, and rejected. `chunking/logger_config.py` now also reports the largest chunk of each run by token count, with its token and character totals.

### 2026-07-23 — Root-cause the Marker failures, then revert Marker to 1.10.2

Two conversion failures carried over from 2026-07-22 were located and measured. The `RecursionError` is `markdownify` walking the document DOM from Marker's Markdown renderer, which Python's `html.parser` nests one level deeper per unclosed inline tag, at ~1.99 frames per level — so the default limit of 1000 tops out near 480 levels, and the depth is bounded rather than infinite (BUG-024, re-filed from BUG-020, whose attribution to the table stage was wrong). The dead worker is `pdftext` sizing its pool as `min(pdftext_workers, pages // 10)` against a provider default of 4, so every document in the corpus spawned four workers and one dying took the conversion with it (BUG-025). Neither is fixable by splitting the input: nesting resets at each closed block-level tag, and a 50-page slice still yields four workers (Research topic 12).

Both fixes were committed (`b73c2e3`) — a spawned conversion thread with a raised recursion limit and a real stack behind it, `pdftext_workers=1`, a batching fallback on the exception path, resume-by-mtime, flushed output — and reverted eight minutes later (`aa1627f`). The revert is the architectural change: `.venv-marker` went back to `marker-pdf==1.10.2` and `codes/marker_test.py` back to its pre-upgrade form, removing the 2.0.0 surya adaptation layer and the `balanced` pin along with the new instrumentation (ADR-012). The Marker leg stops being an operated service — no external `llama-server`, no spawned inference servers, no GGUF downloads — and loses `MarginaliaProcessor`, so ADR-009's header-removal outcome is reversed and Research topic 6 governs again.

The decision was made on output quality, and the evidence is in the tree: `marker_results/src2.md` is 244 lines and 50 MB from a 154-page source, with 83 of those lines forming one 215-column table and 9 headings in the whole document, while the batch summary counted it as converted (BUG-026; Research topic 13). All five files in `marker_results/` are now 2.0.0 output against an installed 1.10.2, and the two defects diagnosed today are properties of `markdownify` and `pdftext` rather than of 2.0.0, so they survive the revert while their fixes do not.

---

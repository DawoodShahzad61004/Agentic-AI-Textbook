# Architecture Decisions

## ADR-001 · Keep one comparable script and result directory per loader

| Field | Detail |
|---|---|
| **Decision** | Maintain separate Docling, Unstructured, and Marker scripts that process the same chapter PDF and write to loader-specific directories. |
| **Date** | 2026-07-14 |
| **Context** | The project needed to explore multiple document loaders while preserving outputs for side-by-side inspection. |
| **Options Considered** | One configurable abstraction over all loaders (less duplication, but hides library-specific behavior) · Separate scripts with shared inputs (simple and transparent) · One-off CLI commands (fastest initially, but not repeatable) |
| **Chosen Solution** | Use `docling_test.py`, `unstructured_test.py`, and `marker_test.py`, with outputs under `docling_results/`, `unstructured_results/`, and `marker_results/`. |
| **Rationale** | Small independent scripts expose each library's native API and failure modes while keeping the corpus constant for comparison. |
| **Impact** | Establishes the current high-level architecture, creates some repeated source/path code, and enables Research topic 1. |

---

## ADR-002 · Standardize the Windows environment on Python 3.12

| Field | Detail |
|---|---|
| **Decision** | Use Python 3.12 instead of Python 3.14 for every loader environment. |
| **Date** | 2026-07-14 |
| **Context** | Marker required `regex==2024.11.6`, which had no compatible prebuilt Windows wheel for Python 3.14 and attempted a source build without MSVC Build Tools. Similar native dependencies made further 3.14 issues likely. |
| **Options Considered** | Stay on Python 3.14 and install build tools (large setup and continued compatibility risk) · Maintain separate runtimes per loader (works but fragments the project) · Move all loaders to Python 3.12 (mature wheel support and one environment) |
| **Chosen Solution** | Use Python 3.12.10 with `uv` and retire the Python 3.14 environment. ADR-005 later defines separate environments because the selected packages cannot coexist in one resolver solution. |
| **Rationale** | Python 3.12 provided compatible wheels for the native ML/OCR stack. Environment isolation is a separate dependency-compatibility decision recorded in ADR-005. |
| **Impact** | Resolved BUG-001 and BUG-002, defines the runtime in `Architecture.md`, and affects all three scripts. |

---

## ADR-003 · Use PowerShell as the verified Windows execution shell

| Field | Detail |
|---|---|
| **Decision** | Execute and validate the Windows virtual-environment scripts through PowerShell. |
| **Date** | 2026-07-14 |
| **Context** | Git Bash reported exit 139/127 and a segmentation fault around the Unstructured native dependency stack, while the same interpreter import and full conversion succeeded in PowerShell. |
| **Options Considered** | Debug Git Bash/MSYS process behavior · Use PowerShell, the native project shell · Run under WSL with a separate Linux environment |
| **Chosen Solution** | Use commands such as `& ".venv\Scripts\python.exe" unstructured_test.py` from PowerShell for Windows verification. |
| **Rationale** | PowerShell exercised the actual Windows interpreter and DLL environment reliably and produced successful output files. |
| **Impact** | Closes BUG-004 operationally and is documented as a runtime constraint in `Architecture.md`. |

---

## ADR-004 · Batch every source file and mirror relative output paths

| Field | Detail |
|---|---|
| **Decision** | Each loader recursively processes every file under `source/` and mirrors the source-relative path as Markdown under its own result directory. |
| **Date** | 2026-07-15 |
| **Context** | The three scripts had diverged into hard-coded filenames and working-directory-dependent paths, preventing repeatable batch comparisons. |
| **Options Considered** | Keep one hard-coded file per script (simple but manual) · Accept command-line paths (flexible but requires orchestration) · Use a shared recursive source directory (repeatable and zero-argument) |
| **Chosen Solution** | Resolve the project root from `__file__`, discover `source/**/*`, reuse one converter per batch where applicable, create mirrored output directories, continue after per-file errors, and return a nonzero status for partial failure. |
| **Rationale** | A shared zero-argument corpus keeps all three loader runs comparable while supporting nested source organization and execution from any working directory. |
| **Impact** | Changes all scripts under `codes/`, supersedes the directory-creation limitation in BUG-003, and makes unsupported-format failures visible without discarding successful conversions. |

---

## ADR-005 · Isolate each loader in its own Python environment

| Field | Detail |
|---|---|
| **Decision** | Run Docling, Unstructured, and Marker from `.venv-docling`, `.venv-unstructured`, and `.venv-marker` respectively. |
| **Date** | 2026-07-15 |
| **Context** | A combined installation was unsatisfiable: Unstructured 0.24.1's PDF stack requires `pi-heif`, whose available releases require Pillow 11.1 or newer, while Marker PDF 1.10.2 requires Pillow below 11. The shared environment also accumulated incomplete Torch metadata and an unrelated `marker` distribution. |
| **Options Considered** | Force one shared environment (resolver conflict) · Change loader versions until constraints overlap (would change the comparison baseline) · Use one Python 3.12 environment per loader (more setup, deterministic isolation) |
| **Chosen Solution** | Create three clean Python 3.12 environments with direct `uv pip install` commands and invoke each script with its matching interpreter. Install `marker-pdf`, not the unrelated `marker` package. |
| **Rationale** | Isolation preserves the selected comparison versions and prevents incompatible or damaged native dependency stacks from contaminating the other loaders. |
| **Impact** | Supersedes the shared-environment portion of ADR-002, removes the combined `requirements.txt`/`uv.lock` workflow, and resolves BUG-005 through BUG-008 operationally. |

---

## ADR-006 · Scope chunking to Marker Markdown and keep run reports untracked

| Field | Detail |
|---|---|
| **Decision** | The chunking workflow reads Markdown recursively from `marker_results/` only, preserves source identity and per-source sequence numbers, and writes timestamped diagnostic reports under the Git-ignored `chunk-runs/` directory. |
| **Date** | 2026-07-16 |
| **Context** | The project moved from loader comparison toward testing downstream ingestion. It needed repeatable chunks from the evaluated Marker output without mixing other loaders or committing multi-megabyte derived run logs. |
| **Options Considered** | Chunk every loader result together (broader but confounds parser comparisons) · Accept arbitrary input paths (flexible but less repeatable) · Limit the experiment to Marker Markdown and isolate run artifacts (narrow and auditable) |
| **Chosen Solution** | Add `chunking/ingest.py` and `chunking/logger_config.py`; discover `.md` and `.markdown` below `marker_results/`, attach source and sequence metadata, and emit one formatted report per execution below `chunk-runs/`. |
| **Rationale** | A fixed input family makes chunking runs comparable, while source metadata preserves traceability and ignored reports allow frequent experimentation without inflating repository history. |
| **Impact** | Establishes the ingestion boundary and report location. It does not adopt a final splitting algorithm: the committed recursive splitter is a baseline, and the later custom heading/table/list prototype was rejected for replacement. |

---

## ADR-007 · Normalize Marker clause structure in memory before chunking

| Field | Detail |
|---|---|
| **Decision** | Add a `preprocessing()` pass in `chunking/ingest.py` that repairs Marker's inconsistent numbered-clause and heading formatting per document, in memory, immediately before `temp_split()`, without rewriting the Marker Markdown on disk. |
| **Date** | 2026-07-20 |
| **Context** | Marker renders one logical numbered clause (for example `5.1`) inconsistently as a plain paragraph, a dash-prefixed list item, or a bold-labelled line, and wraps a single clause's body across stray blank lines from source pagination. `temp_split()` chooses chunk boundaries from heading and list structure, so this inconsistency degraded chunking. The font size/weight signal that marked these as headings in the PDF is already gone by the time Marker emits Markdown, and bold is overloaded for inline defined terms, so headings cannot be recovered by a naive "promote bold" rule. The project principle (CLAUDE.md) is that "chunking is not a repair mechanism for source-conversion defects." |
| **Options Considered** | Boundary-only soft-heading detection inside the splitter, feeding extra whole-line-anchored patterns to `_heading_matches()` without altering text (honors the principle strictly, but cannot rejoin fragmented clause bodies or supply missing list structure) · In-memory normalization before splitting that rewrites clause structure but never touches the `.md` files (repairs structure for the splitter while keeping the on-disk output authoritative) · Rewriting `marker_results/*.md` on disk (simplest downstream, but silently mutates the Marker output still under evaluation and destroys the audit trail) |
| **Chosen Solution** | Apply `preprocessing(document.page_content)` inside `split_documents()` before `temp_split()`. It runs `_normalize_marker_sequences()`, `_promote_italic_sublabels()`, and `_extract_leading_spans()` on the in-memory text only; the on-disk Marker Markdown is left unchanged. Scope is limited to the numbered-clause, bold-label, italic-sublabel, and leading `<span id="…">` anchor patterns observed in the RFT/contract document family. |
| **Rationale** | In-memory normalization gives the splitter reliable structure without mutating the Marker output the project is still assessing, preserving reproducibility and the "do not silently rewrite source" stance. Scoping to observed patterns keeps it a best-effort heuristic rather than a general Markdown normalizer. |
| **Impact** | Adds the `preprocessing()` stage to the chunking pipeline in `Architecture.md`; introduced and closed BUG-013 through BUG-015 during ground-truth validation; documented in Research topic 9. It refines rather than overrides ADR-006 and the "chunking is not a repair mechanism" principle: repair is limited to in-memory structural normalization that feeds boundary detection, not authoritative correction of Marker's output, and remains bounded by defects such as BUG-012. |

---

## ADR-008 · Run Marker in `balanced` mode, sequentially — page batching and parallelism rejected

| Field | Detail |
|---|---|
| **Decision** | Pin `codes/marker_test.py` to Marker's `balanced` mode and convert each PDF whole, in one `PdfConverter` call, one file at a time. Do **not** batch pages, and do not run converters concurrently. The parallel/batching implementation was written, measured, and reverted — this ADR exists so it is not attempted again. |
| **Date** | 2026-07-21 |
| **Context** | The driving goal was better chunk quality by removing running headers/footers from Marker's Markdown, not throughput. `balanced` mode on a 250-page RFT was slow enough to be abandoned mid-run, which prompted a switch to `fast` and then to page batching with concurrent workers as a way to make `balanced` affordable. |
| **Options Considered** | `fast` mode (rejected on **quality**: roughly as quick as the old pipeline and headers were gone, but it merged separate list points together, degrading chunking — a structural defect chunking cannot recover, cf. BUG-012) · Per-worker `create_model_dict()` as originally proposed (rejected on **design**: `SuryaInferenceManager` is documented "construct once per process" and every predictor is a thin client of a shared server, so a second dict races to spawn a second llama-server on the same GPU) · Shared model dict, two concurrent batch workers (rejected on **stability**: aborts the llama-server, BUG-016) · Shared model dict, batches serial (rejected on **speed**: 32% slower than not batching) · Whole-document `balanced`, sequential (**chosen**) |
| **Chosen Solution** | Whole-document `balanced` conversion. Measured on pages 0–59 of the RFT corpus, RTX 5050 Laptop (8 GB): whole document 90.1s; three 20-page batches serial 118.7s; three 20-page batches across two workers aborts the llama-server. All batching code was removed from `marker_test.py`; the script is back to one converter and a simple loop. |
| **Rationale** | Document-level threading duplicates parallelism that already exists one layer down: surya runs a single llama-server with `SURYA_INFERENCE_PARALLEL` (default 8) slots and coalesces pages across all in-flight requests. Splitting into 20-page calls shrinks the pool of pages available to coalesce and re-pays provider/converter setup per batch, so it is slower *even before* the crash — the batching code was pure overhead. Note `SURYA_INFERENCE_PARALLEL=8` is a no-op override: it equals the backend's existing `DEFAULT_PARALLEL`. |
| **Impact** | `marker_results/` output is not comparable to prior `fast`-mode runs (see the pipeline-mixing caveat in CLAUDE.md — regenerate the tree before using it as a baseline). Opens BUG-016. Leaves the original header/footer goal **unaddressed by this ADR**: the actual lever is `MarginaliaProcessor` config on the converter, which is independent of mode and of scheduling — see Research and the `ClassName_attr` config note in CLAUDE.md. Accept that a 500-page `balanced` run is simply slow on this hardware; there is no scheduling trick that avoids it. |

---

## ADR-009 · Upgrade Marker to 2.0.0 and run its VLM through a local llama.cpp server

| Field | Detail |
|---|---|
| **Decision** | Move `.venv-marker` from `marker-pdf==1.10.2` to `2.0.0` (surya-ocr 0.22.1) to obtain `MarginaliaProcessor`, and serve the VLM through a locally installed `llama-server` binary rather than the auto-selected vllm/Docker backend. Accept the resulting external runtime dependency and the three environment fixes it forced. |
| **Date** | 2026-07-21 |
| **Context** | The goal was chunk quality: running headers and footers were entering the reading stream in `marker_results/` and degrading chunk boundaries. Under 1.10.2 nothing could remove them, because `keep_pageheader_in_output=False` only suppresses blocks the layout model actually classified as `PageHeader`; anything labelled `Text` or `SectionHeader` survives regardless (Research topic 6). Marker 2.0.0 adds `MarginaliaProcessor` to the default PDF pipeline, which relabels running headers/footers positionally — by margin zone, page-extremality, block height, and text length — and is therefore not dependent on the layout model's classification. A local geometric processor was designed against 1.10.2 as an alternative and discarded once the upstream version was confirmed installed; the shipped implementation is better guarded. |
| **Options Considered** | Stay on 1.10.2 and register a custom geometric processor (rejected: duplicates upstream work with weaker guards, and Marker's `processor_list` path needs importable dotted paths, forcing a converter subclass) · Relabel low-confidence blocks with `BlockRelabelProcessor` (rejected: document-wide, positionally unaware, and its confidence comparison is inverted from the intuitive reading, so it demotes genuine mid-page section headers) · Tune `IgnoreTextProcessor`'s repetition thresholds (rejected as insufficient alone: it inspects only the first and last structured block per page, so a multi-block header is only ever partially caught) · Upgrade to 2.0.0 with the default vllm/Docker backend (rejected: a ~10 GB image, WSL2 GPU passthrough, and vllm defaults of 0.85 GPU-memory utilization against an 18,000-token model length on 8 GB of VRAM) · **Upgrade to 2.0.0 with the native llama.cpp backend (chosen)** |
| **Chosen Solution** | `marker-pdf==2.0.0`; `SURYA_INFERENCE_BACKEND=llamacpp`; `llama.cpp` b10068 (CUDA 13.3 build plus cudart) installed to `%LOCALAPPDATA%\llama.cpp` and added to the user `PATH`, with a `LLAMA_CPP_BINARY` fallback in `codes/marker_test.py` for shells that predate the `PATH` edit; `SURYA_GUIDED_LAYOUT=false`; Torch restored to `2.13.0+cu130` and the orphaned `torchaudio` removed. `MarginaliaProcessor` is left at its shipped defaults (`header_zone=0.08`, `footer_zone=0.13`, `max_height_frac=0.035`, `max_chars=150`) — no tuning proved necessary. |
| **Rationale** | The upgrade is the only route to positional marginalia removal, which was the actual objective. The backend choice follows from hardware: surya auto-selects vllm on any NVIDIA GPU (BUG-017), and vllm targets server-class cards. llama.cpp runs the quantized GGUF natively with no container. `cu130` is the only PyTorch index carrying `torch 2.13.0` for this Blackwell (sm_120) GPU — `cu128` stops at 2.9.1 — so the CUDA restore was a pure local-tag change with no dependency drift. Verified outcome: in the regenerated corpus the running-header line that previously opened the document is gone, and the only surviving `RFT Number:` occurrences are legitimate form fields inside tables. |
| **Impact** | Converts the Marker leg of this harness from "pip install and run" into "operate a local inference server": conversion now depends on an external binary, a spawned server process, model downloads (~1.5 GB of GGUF plus a 136 MB rf-detr checkpoint), and server lifecycle management including orphaned processes holding VRAM after an interrupted run. Forced BUG-017 through BUG-019 and surfaced BUG-020. Introduces the device-derived `mode` default that ADR-008 then pins. Invalidates every pre-upgrade file in `marker_results/`: the tree may hold output from 1.10.2, 2.0.0-`fast`, and 2.0.0-`balanced`, which are three different extraction pipelines and are not comparable (Research topic 10). Setup steps are recorded in `CLAUDE.md`; no tracked dependency manifest captures them. |

---

## ADR-010 · Chunk by packing a structural tree, not by selecting boundaries against a size limit

| Field | Detail |
|---|---|
| **Decision** | Rewrite `temp_split()` as a two-phase algorithm: parse the document once into a tree of structural units (sections nested by ATX heading level; within each section its own tables, lists and paragraphs), then pack those units greedily into chunks. Retire the rule-based boundary selector `_structural_cut()` and its supporting helpers entirely. |
| **Date** | 2026-07-22 |
| **Context** | The hand-authored rule set from 2026-07-17 had been extended six times against real Marker output and was still producing two classes of defect the user reported directly: chunks far below `CHUNK_SIZE` sitting next to content that would have fitted (a 64-character opening chunk), and sections torn in half at a subsection boundary (clause 5.4 split between `Technical Bids` and `Commercial Bids`). See BUG-022. |
| **Options Considered** | Add a minimum-fill rule to `_structural_cut()` (rejected: it would be the seventh patch to a rule set whose rules already contradict one another — `_list_section_after_heading()` deliberately emits an under-full chunk, so a global minimum-fill rule would need carve-outs for its own siblings) · Keep boundary selection but repair the deepest-ATX-level heuristic (rejected: the heuristic is a proxy for section ownership that only works when heading levels are well-formed, which Marker's are not — BUG-021 — so it would stay one malformed document away from the same failure) · **Parse-then-pack over a structural tree (chosen)** |
| **Chosen Solution** | `_build_tree()` produces `_Node` units; `_pack()` fills a chunk with whole sibling units until the next would not fit, then moves that unit forward intact; `_split_node()` opens a unit up only when it cannot fit an empty chunk by itself, and only one level at a time. A heading always travels with the first unit beneath it (`_extend_start()`), so no depth of splitting can strand one. A pending buffer holding only headings, or one sitting in front of a unit about to be opened anyway, is handed into that unit rather than published early (`_lead_in_fits()`). Oversized lists split on top-level pointers, keeping nested children with their parent pointer. |
| **Rationale** | The user's stated intent — "fill each chunk with as many characters as `CHUNK_SIZE` permits, but never separate a heading from its content or split a logical section; if the complete next section cannot fit, move the entire section to the next chunk" — is literally the definition of greedy packing over a containment tree. Expressing it that way makes both reported defects unrepresentable rather than patched: a chunk closes only when the next whole unit does not fit, and a unit is only ever divided along boundaries the document itself declares. It also removed 202 lines and eleven helpers whose interactions were the actual source of the bugs. |
| **Impact** | Chunk boundaries change document-wide; earlier `chunk-runs/` reports are not comparable. Chunk count on the two-document corpus fell from 1,949 to 1,051 at `CHUNK_SIZE=1600` as chunks became fuller. Verified lossless by whitespace-normalised round trip across `marker_results/`, `docling_results/` and `unstructured_results/` (nine files). The rewrite also dropped the predecessor's trailing-heading guard, which had to be restored as BUG-023. The splitter remains experimental — there is still no test suite, and verification means re-running `ingest.py` and reading the report. Supersedes the algorithm documented in Research topic 8; ADR-011 then removes the table-size exemption this ADR inherited. |

---

## ADR-011 · Bound tables by `CHUNK_SIZE` too, re-serializing them with repeated headers

| Field | Detail |
|---|---|
| **Decision** | Remove the standing exemption that let a Markdown table be emitted whole at any size. A table that does not fit is split into several chunks, each re-serialized with the headers that apply to the cells it carries. Splitting is by row when the table has column headers, both, or neither; by column when it has only row headers; and descends to cell groups and then to content inside a single cell when a row, column, or cell is itself too large. |
| **Date** | 2026-07-22 |
| **Context** | Every prior chunker in this project treated a table as one indivisible retrieval unit, on the grounds that a header row separated from its data is worse than an oversized chunk — the conflict Research topic 7 had already identified as unresolvable in the abstract. Measured against the real corpus that exemption cost 38 chunks above the limit, the largest 10,071 characters, well past the context budget any downstream retrieval step would allocate to a single chunk. The guarantee was protecting a unit that could not actually be used. The user supplied nine explicit rules covering how a table should be divided. |
| **Options Considered** | Keep the exemption (rejected: an unusable chunk is not a preserved one) · Split tables by row without repeating headers (rejected: every piece after the first loses the column names, which is exactly the failure the exemption existed to prevent) · Slice table pieces out of the source verbatim (rejected: a verbatim slice cannot carry a repeated header, and Marker pads columns to the widest cell — alignment rows of up to 897 characters occur here — so most of a slice's budget is padding) · **Re-serialize with normalized padding and repeated headers (chosen)** |
| **Chosen Solution** | `_split_table()` parses the table into a header stack, an alignment row and data rows, then dispatches on which headers exist. Padding and the alignment row are normalized on output; the size limit is measured on the emitted chunk, not on the source it came from. Orientation is decided by `_has_column_headers()` and `_has_row_headers()`, the latter a documented heuristic since Markdown has no row-header syntax. Fallbacks descend one level at a time: whole rows → cell groups within a row (`_split_across_columns`) or rows within a column (`_split_across_rows`) → content within one cell (`_split_cell`, preferring paragraph, then list-item, then sentence, then word boundaries). Any heading introducing the table repeats on every piece, since each piece is meant to stand alone. No fragment index, table identity, or generated positional label is added — only real headers are repeated. |
| **Rationale** | Repeating the headers is what makes splitting safe: the reason tables were exempt is that a bare row block is uninterpretable, and a repeated header removes that objection for a few dozen characters per chunk. Normalizing padding is not cosmetic — the RFT summary table is 5,922 source characters carrying 1,823 characters of content — so normalization alone brings many tables back under the limit and satisfies rule 1 with no split at all. `_has_row_headers()` only chooses between splitting axes and whether a row label repeats, so a wrong guess degrades a chunk rather than corrupting one. |
| **Impact** | No chunk in the corpus now exceeds `CHUNK_SIZE`, down from 38. Chunk count rose from 1,051 to 1,069 at `CHUNK_SIZE=1600`. Split tables are no longer byte-identical to their source — padding is normalized, alignment rows are rewritten to `---`, and headers appear more than once — so the strict round-trip check used since 2026-07-20 no longer applies to them and was replaced by a per-line survival check: every source line, normalized to its rendered form, must appear in some chunk. Content can now be lost only inside a single cell that exceeds the limit on its own, which no table in the current corpus does. Supporting changes: `_table_cells()` now honours escaped and code-span pipes so column indices are correct, and `_table_spans()` extends backwards over rows above the alignment row so multi-level header stacks are captured and repeated in full. Removes the exemption ADR-010 inherited; closes the oversized-table policy gap left open by Research topic 7. |

---

## ADR-012 · Revert Marker to 1.10.2 and abandon the 2.0.0 VLM-server pipeline

| Field | Detail |
|---|---|
| **Decision** | Return `.venv-marker` to `marker-pdf==1.10.2` and restore `codes/marker_test.py` to its pre-upgrade form (`c9f712a`) — a bare `PdfConverter(artifact_dict=create_model_dict())`. This reverses ADR-009, moots ADR-008's `balanced` pin, and discards the same-day recursion and worker-pool instrumentation along with it. |
| **Date** | 2026-07-23 |
| **Context** | 2.0.0 was adopted for one reason: `MarginaliaProcessor`, which removes running headers and footers positionally and which 1.10.2 cannot do at any configuration (ADR-009; Research topic 6, topic 10). That objective was met. What followed was two days of failures the pipeline change had introduced — Docker/vllm backend selection, a GBNF grammar rejection, an ABI-orphaned `torchaudio`, a renderer recursion crash, a dead `pdftext` worker (BUG-017 through BUG-020, BUG-024, BUG-025) — and then output that was worse than what the upgrade replaced. The deciding evidence is `marker_results/src2.md`: a 154-page source rendered as 244 lines, 50 MB, with 83 of them a single 215-column table and 9 headings in the whole document (BUG-026). The user's stated ground for reverting was output quality, and the tree corroborates it. |
| **Options Considered** | Stay on 2.0.0 and quarantine the bad document (rejected: the harness exists to compare loaders, and a pipeline that can silently turn a 154-page contract into one table is not a baseline — the failure is not detectable from the batch summary, which counted it as converted) · Stay on 2.0.0 and keep the recursion/worker instrumentation as permanent guards (rejected: both are workarounds for defects the older pipeline does not have, and each adds machinery — a spawned thread with a 128 MB stack, a page-batching fallback — to a script whose value is being small enough to read) · Pin 2.0.0 to `fast` mode (rejected earlier on structural grounds in ADR-008: it merges separate list points, which chunking cannot recover) · **Revert to 1.10.2 and accept losing `MarginaliaProcessor` (chosen)** |
| **Chosen Solution** | `uv pip install --python .venv-marker\Scripts\python.exe "marker-pdf==1.10.2"`, which rolled back the transitive stack with it (surya-ocr 0.22.1 → 0.17.1, pdftext 0.7.1 → 0.6.3, pypdfium2 5.10.1 → 4.30.0, transformers 5.14.1 → 4.57.6, plus the anthropic/openai/google-genai/huggingface-hub clients). `git checkout c9f712a -- codes/marker_test.py`, committed as `aa1627f`. Torch was deliberately left untouched at `2.13.0+cu130` and re-verified with an actual matmul; `tiktoken` survived, so `chunking/` is unaffected. |
| **Rationale** | The upgrade traded one known, bounded defect (running headers entering the reading stream, which `preprocessing()` and the packer already cope with) for an unbounded one (arbitrary structural collapse with no signal at the batch level). Between a defect you can see in every document and a defect that appears in one document out of three and is invisible until you open the file, the first is the better position for a comparison harness. `codes/marker_test.py` reverting past the 2.0.0 adaptation layer is not incidental damage — `SURYA_INFERENCE_BACKEND`, the `LLAMA_CPP_BINARY` fallback and `SURYA_GUIDED_LAYOUT=false` exist only to make surya 0.22.1 run, and are inert or harmful once 0.17.1 is installed. |
| **Impact** | **Header/footer removal is lost.** `MarginaliaProcessor` does not exist in the installed 1.10.2 tree (verified), so ADR-009's delivered outcome is reversed and Research topic 6's conclusion — that 1.10.2 cannot reach a running header the layout model labelled `Text` — governs again the moment the corpus is regenerated. The Marker leg also stops being an operated service: no `llama-server` binary, no spawned inference servers, no GGUF downloads, no orphaned VRAM. **Two defects survive the revert while their fixes do not.** `markdownify` over `html.parser` is the renderer path in 1.10.2 as well (BUG-024), and `pdftext 0.6.3` has the identical `min(workers, pages // 10)` pool sizing with the same `pdftext_workers = 4` provider default (BUG-025) — Marker's own CLI and server front-ends force it to 1, and `codes/marker_test.py` now does not. **`marker_results/` no longer matches the installed version at all**: all five files were produced by 2.0.0 (two `balanced` on 2026-07-22, three on 2026-07-23), so the whole tree must be regenerated before it is a baseline for anything, and regenerating it will reintroduce running headers into the chunking corpus. `docs/`, `CLAUDE.md` and `README.md` all documented the 2.0.0 setup as current until this entry. Supersedes ADR-009; ADR-008's mode pin is moot, since 1.10.2 has no `mode` concept, though its rejection of page batching and concurrent converters stands on independent grounds. |

---

# Research Notes

## 1. Docling, Unstructured, and Marker conversion approaches

| Field | Detail |
|---|---|
| **Topic** | Compare how three Python document loaders convert the same chapter PDF to Markdown and what each implementation requires. |
| **Date** | 2026-07-14 |
| **Findings** | Docling converts into an internal document model and directly exports Markdown. Unstructured partitions a PDF into typed elements and requires local formatting logic; the current adapter only gives special treatment to titles, headers, and list items. Marker renders through a model-backed `PdfConverter` and returns Markdown via `text_from_rendered()`. All three successfully produced Markdown for `Chapter_1_Why_RAG.pdf` under Python 3.12. Output sizes differ: the current files are approximately 17.2 KB (Docling), 25.2 KB (Unstructured), and 25.4 KB (Marker); size alone is not a quality score. |
| **Conclusion** | Keep all three implementations for transparent output comparison (ADR-001). A future evaluation should score heading fidelity, tables, reading order, equations, images, and runtime rather than choosing from file size. |
| **Relevance to Project** | Applies to all three scripts and result directories; it motivates the comparison-oriented architecture and future benchmark work. |

---

## 2. Windows Python compatibility for document-AI dependencies

| Field | Detail |
|---|---|
| **Topic** | Determine why loader installations and executions failed under the initial Windows environment. |
| **Date** | 2026-07-14 |
| **Findings** | Python 3.14 lacked a prebuilt Windows wheel for Marker’s pinned `regex==2024.11.6`, forcing a source build that required unavailable MSVC Build Tools. A Python 3.12.10 environment installed Marker 1.10.2, Docling, and Unstructured PDF extras successfully. Installing plain Unstructured was insufficient for PDFs because `unstructured_inference` was absent; `unstructured[pdf]` supplied the required inference/OCR dependencies. Git Bash also produced unreliable native-process results, whereas PowerShell imported Unstructured and completed conversion with exit code 0. |
| **Conclusion** | Use a shared Python 3.12 Windows environment and PowerShell (ADR-002 and ADR-003). Install loader extras, not only top-level packages. |
| **Relevance to Project** | Defines environment setup for every script and explains BUG-001 through BUG-004. The empty `requirements.txt` remains a reproducibility gap. |

---

## 3. Open-source loaders and routed production ingestion

| Field | Detail |
|---|---|
| **Topic** | Survey open-source loaders for mixed and complex files and identify a production-grade ingestion strategy beyond the current comparison scripts. |
| **Date** | 2026-07-14 |
| **Findings** | Docling is a strong primary multi-format parser because it preserves layout, hierarchy, reading order, tables, formulas, code blocks, images, captions, and metadata in a unified document model. Unstructured offers mature automatic type detection, typed elements, metadata, chunking, and configurable PDF strategies, but has a heavy dependency stack and materially different `fast`, `hi_res`, and OCR behavior. Apache Tika offers exceptionally broad format and metadata coverage but tends to flatten complex layouts, making it better as a fallback. Marker and MinerU specialize in high-fidelity, layout-heavy PDFs and can be computationally expensive. PyMuPDF4LLM is a faster path for ordinary digital PDFs. PaddleOCR or OCRmyPDF addresses scanned input. LlamaIndex Readers and LangChain Document Loaders are orchestration adapters whose parsing quality depends on their underlying engine; they do not independently guarantee table or layout fidelity. Haystack Converters provide another framework-integrated option. |
| **Conclusion** | No production router was implemented or formally adopted. The research recommendation is to avoid a single universal parser: inspect each file, route ordinary PDFs to a fast parser, use Docling for structured multi-format content, apply OCR to scans, retain Tika as a broad fallback, normalize results through framework adapters where useful, preserve page/section metadata, and quarantine low-confidence parses. File extension alone is insufficient because PDFs may be scanned, encrypted, malformed, multi-column, or table-heavy. |
| **Relevance to Project** | Explains why ADR-001 retains comparable native implementations and defines a possible evolution from the current scripts. The proposed router, confidence model, metadata contract, and quarantine path are future work documented in `Architecture.md`, not present capabilities. |

---

## 4. Dependency isolation and Docling acceleration behavior

| Field | Detail |
|---|---|
| **Topic** | Determine a workable installation layout for the expanded batch harness and investigate why Docling was not using the available NVIDIA GPU. |
| **Date** | 2026-07-15 |
| **Findings** | A combined environment is not resolvable at the selected versions because Unstructured 0.24.1's `pi-heif` path requires Pillow 11.1 or newer while Marker PDF 1.10.2 requires Pillow below 11. The experimental environment also exposed an obsolete Numba selection, incomplete Torch metadata, and an unrelated `marker` package. Three clean Python 3.12 environments avoided those conflicts. Docling initially used `torch 2.13.0+cpu`, so automatic acceleration resolved to CPU even though the NVIDIA RTX 5050 Laptop GPU and driver were visible. Installing `torch 2.11.0+cu128` enabled CUDA, but an unrestricted package upgrade replaced it with `torch 2.13.0+cpu`, demonstrating that the CUDA build must be pinned and verified after upgrades. Native `std::bad_alloc` page-preprocessing failures were system-memory failures rather than CUDA out-of-memory errors, and Docling could still return partial documents. |
| **Conclusion** | Keep loader dependencies isolated (ADR-005). Treat the CUDA Torch build as an explicit environment constraint, verify `torch.cuda.is_available()` after dependency changes, and do not equate a returned Docling document with page-complete conversion (BUG-009). |
| **Relevance to Project** | Defines the current three-environment setup and identifies a validation gap in `codes/docling_test.py`. No CUDA pin or low-memory pipeline configuration is currently tracked in the repository. |

---

## 5. Marker quality across the expanded six-PDF corpus

| Field | Detail |
|---|---|
| **Topic** | Assess the end-to-end Marker workflow on six procurement, legal, engineering, and RAG PDFs totaling 251 pages. |
| **Date** | 2026-07-15 |
| **Findings** | Marker recovered ordinary prose well: the 91-page legal document yielded about 44,443 Markdown words from roughly 45,450 PDF words, and the RAG chapter yielded about 4,032 from roughly 4,023. It often retained emphasis, footnotes, colored text as plain text, simple tables, and much surrounding prose. Structural fidelity was substantially weaker: complex forms and merged tables were flattened, narrow headers fragmented into letters or syllables, heading levels were inconsistent, repeated page furniture entered the reading stream, page breaks and layout semantics were lost, and nested lists degraded. The Markdown contains 131 image references with no delivered assets, and the RAG output contains at least 26 mojibake sequences. |
| **Conclusion** | Marker is useful as a text-centric first-stage extractor for search and RAG after validation and cleanup, but its raw Markdown is not an authoritative representation of contracts, forms, engineering documents, or visually rich publications. July 16 page checks sharpened this conclusion: very small and highlighted text could be correct while contact-table associations were wrong; repeated titles and TOC page numbers were omitted; running headers interrupted cross-page lists; and a dense table around pages 61–62 caused reordering, a duplicated section number, and subsequent omissions. High aggregate word retention therefore cannot establish structural completeness. Asset export, encoding checks, page-aware cleanup, heading normalization, table-quality checks, and targeted source comparison at page/table boundaries are required. |
| **Relevance to Project** | Documents the Marker output assessed on July 15–16, supports BUG-010 and BUG-011, and provides the evidence behind `Marker-PDF Report.md`. No equivalent expanded-corpus assessment exists yet for Docling or Unstructured. |

---

## 6. Marker header/footer configuration for RAG

| Field | Detail |
|---|---|
| **Topic** | Determine how Marker classifies, removes, preserves, and debugs page headers and footers. |
| **Date** | 2026-07-16 |
| **Findings** | Marker classifies page regions as `PageHeader` and `PageFooter`; the renderer excludes those types by default through `keep_pageheader_in_output=False` and `keep_pagefooter_in_output=False`. This is layout classification rather than repeated-text matching, so a real heading misclassified as a page header can disappear, while a running header classified as ordinary text remains. `paginate_output`, JSON/chunks output, block IDs, and debug layout/JSON artifacts can expose page and block structure. Low-confidence blocks can be relabeled, and headers/footers can be retained for downstream policy. Footnotes are a separate block type and should not be treated as page footers. |
| **Conclusion** | For RAG evaluation, preserve headers and footers initially, retain page/block metadata, and decide downstream whether each item should be content, metadata, or boilerplate. Repetition and geometry rules require validation for first pages, alternating headers, section-specific identifiers, scans, and technical document frames. Do not assume the default exclusion policy is lossless. |
| **Relevance to Project** | Explains both omitted repeated titles and intrusive running headers in the Marker report. The current `codes/marker_test.py` does not pass these diagnostic settings or retain structured page/block output; no production policy has been adopted. |

---

## 7. Markdown chunking experiments on Marker output

| Field | Detail |
|---|---|
| **Topic** | Explore how Marker-generated official-document Markdown should be divided without destroying heading, table, or nested-list structure. |
| **Date** | 2026-07-16 |
| **Findings** | The committed baseline used `RecursiveCharacterTextSplitter` with a 1,600-character target, 200-character overlap, and Markdown-oriented boundaries. Eight local runs then tested increasingly structural algorithms: heading-level descent, whole-table preservation, recursive splitting at shallow list indentation, prose fallback, table token diagnostics, and per-chunk `cl100k_base` counts. Run totals varied substantially (1,263–4,838 chunks before settling at 2,271 in the last three reports), showing that small policy changes materially alter the retrieval unit population. The custom implementation also exposed a core conflict: a hard size limit and an indivisible oversized table cannot both be guaranteed. The user rejected this implementation path and plans a separate rewrite; overlap was also removed from the intended design. |
| **Conclusion** | Heading hierarchy, list nesting, and table boundaries need explicit tests against real Marker irregularities before a splitter is adopted. Table completeness must have a defined oversized-table policy, token limits should use the target model tokenizer, and run reports should retain source, sequence, character, and token metrics. Chunking cannot restore content or relationships already lost during PDF conversion. |
| **Relevance to Project** | Frames `6e176b3` as a baseline rather than the final design, explains the ignored `chunk-runs/` evidence and `codes/count_table_tokens.py`, and prevents the abandoned custom splitter from being documented as accepted architecture. |

---

## 8. Iteratively authoring rule-based Markdown chunking boundaries

| Field | Detail |
|---|---|
| **Topic** | Determine why algorithmic approaches to section-by-section Markdown chunking (a reused recursive splitter, an LLM-generated complex splitter) failed, and evaluate a hand-authored rule set as a replacement. |
| **Date** | 2026-07-17 |
| **Findings** | Two earlier approaches to per-section chunking did not reach the intended behavior: reusing a recursive splitter from a separate project, and a Codex-generated splitter built from many interacting helper functions. Both were abandoned. Hand-typing rules for as many observed structural situations as could be enumerated — heading hierarchy and incomplete-subsection rollover, flat/nested list splitting by indentation, paragraph fallback boundaries, partial/oversized table handling, fenced-code exclusion, no overlap — and having the coding agent implement them as a single top-to-bottom `temp_split()` produced a workable draft on the first pass. A run against the then-committed heading/table/list splitter (`50208bc`) gave a comparison baseline of 1,273 chunks averaging 192.61 tokens. Four rounds of manually inspecting chunk reports against real RFT documents each surfaced one concrete misbehavior — a heading left dangling at the end of a chunk, a lead-in paragraph separated from the list it introduced, a table rule that dropped an intervening heading, a chunk ending on a heading when a table/list/paragraph followed — and each was fixed as one targeted rule addition rather than a rewrite. Chunk counts across the four iterations were 2,065; 2,066; 1,915; and 1,913, converging as the rules stabilized. This process also surfaced a Marker source defect: nested list sub-points are flattened to the same indentation as their parent pointer, which bounds how much list hierarchy the chunker can ever recover from Marker's output (BUG-012). |
| **Conclusion** | For this splitting problem, an explicit, example-driven rule set authored against real documents converged faster than either a reused generic algorithm or an LLM-generated complex implementation. Manually inspecting real chunk output and fixing one concrete failure at a time is the effective feedback loop; the design is still being refined and is not adopted as final. Chunk quality is bounded by Marker's own list-flattening defect, independent of the splitter's own logic. |
| **Relevance to Project** | Extends Research topic 7 from the rejected heading/table/list prototype to its rule-based replacement, explains the four uncommitted 2026-07-17 `chunk-runs/` reports, and links the chunking work back to Marker's source-conversion fidelity (BUG-010, BUG-011, BUG-012). |

---

## 9. Repairing Marker clause structure and validating against full-document ground truth

| Field | Detail |
|---|---|
| **Topic** | Determine how to give the Markdown splitter reliable heading and list structure when Marker renders numbered clauses inconsistently, and validate the repair against a full real RFT/contract document rather than small examples. |
| **Date** | 2026-07-20 |
| **Findings** | In RFT-style sources the only reliable "this is a heading" signal — PDF font size and weight — is already gone once Marker emits Markdown, so second-level numbered clauses (`5.1`, `5.3`, italic `*Technical Bids*:`) survive as bold-run paragraphs, and because bold is overloaded for inline defined terms ("**Company**", "**RFT**"), a blind "promote bold to heading" rule would create many false headings; whole-line anchoring is the safeguard. Two designs were weighed — boundary-only soft-heading detection inside the splitter versus an in-memory `preprocessing()` normalization pass — and the latter was adopted (ADR-007) because it can also rejoin clause bodies fragmented across blank lines and supply missing list structure, while never rewriting the on-disk `.md`. Validation moved from two hand-authored before/after examples to a ~2,700-line `marker_results/input.md` / `expected-output.md` ground-truth pair (a full RFT plus its General Terms and Conditions contract body), which exposed defects the toy examples could not: alphabetic/roman marker families chained across unrelated sections (BUG-013), fully-nested marker edits overlapping and scrambling output (fixed with BUG-013), an unconditional forward-merge that concatenated unrelated glossary definitions (BUG-014), and inline `<span id="…">` anchors glued to line starts breaking detection (addressed by adding `_extract_leading_spans()`). Diffing output against ground truth fell from 1,596 to ~830 changed lines. Inspecting real chunk output separately surfaced two `temp_split()` boundary failures driven by user feedback — one-off deep subsections (a single `#####` level inside one `####` clause) whose run "never closed" under a same-level-only search, and lists with any nesting being invisible to the keep-list-with-lead-in helpers — plus a parent-heading that stayed stranded when its subsections were deferred (fixed with `_enclosing_heading_start()`), a data-loss bug in the new top-level-item boundary helper (BUG-015), and a mid-word cut when a hierarchy resolved before the size limit and the rule returned the raw, unsnapped character limit. Each was fixed as a targeted rule change and re-verified with a full round-trip check (every emitted chunk reappears in the preprocessed text with nothing left over) across all four local documents. |
| **Conclusion** | Font-derived heading signal cannot be recovered from Marker Markdown, so structure must be reconstructed heuristically; a whole-line-anchored, in-memory normalization pass is a workable best-effort repair, but must be validated against full real documents, since small examples hide global-scoping, unconditional-merge, and edit-overlap failures. A round-trip no-loss invariant is the effective guard against silent data loss and corruption during both preprocessing and splitting. One ambiguity is unresolved: "RFT Number: [...]" page-footer boilerplate merges inconsistently in the ground truth itself, with no punctuation or structural signal distinguishing the cases, so it was flagged to the user rather than special-cased by guesswork. Repair remains bounded by Marker's own list-flattening defect (BUG-012). |
| **Relevance to Project** | Extends Research topic 8 from splitter rule authoring to source-structure normalization; motivates ADR-007 and the `preprocessing()` stage documented in `Architecture.md`; and records BUG-013 through BUG-015. The transforms are scoped to the observed RFT/contract patterns and remain experimental, not a general Markdown normalizer. |

---

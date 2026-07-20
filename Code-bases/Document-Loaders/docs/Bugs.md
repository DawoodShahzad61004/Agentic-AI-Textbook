# Bug Records

### BUG-012 · Marker flattens nested Markdown list pointers to one indentation level

| Field | Detail |
|---|---|
| **Issue** | Marker's Markdown output represents multi-level list pointers (bullet-symbol sub-points, parenthetical roman-numeral sub-points) as flat `-` items at the same indentation as their parent pointer, discarding the original nesting depth. |
| **Found Date** | 2026-07-17 |
| **Status** | Open |
| **Severity** | MEDIUM |
| **File** | `codes/marker_test.py`; `marker_results/`; surfaced while inspecting `chunking/ingest.py` reports |
| **Description** | Found by manually comparing chunk reports against the source RFT documents while iterating on the Markdown splitter: sub-points such as "• the requirements..." and "(i) the requirements..." are emitted as top-level `- ` list items, so no indentation signal distinguishes a pointer from its sub-pointers. |
| **Root Cause** | Not isolated. Marker's list-block serialization does not appear to preserve original nesting depth for bullet- and roman-numeral-style sub-points. |
| **Solution** | Not yet implemented. A regex-based normalization pass over Marker's Markdown output is planned, to reconstruct indentation from marker glyphs (for example `•`, parenthetical numerals) before chunking. |
| **Date Resolved** | — |

---

### BUG-011 · Marker can silently corrupt structural completeness despite high word retention

| Field | Detail |
|---|---|
| **Issue** | Page-level comparison found incorrect table row associations, missing navigation data, interrupted lists, and reordered, duplicated, or omitted content even though aggregate word recovery remained high. |
| **Found Date** | 2026-07-16 |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `codes/marker_test.py`; local `marker_results/`; `Marker-PDF Report.md` |
| **Description** | In the first RFT continuation volume, the page 5 contact table split and merged organizations into the wrong rows, the repeated RFT title was omitted, page 204 table-of-contents numbers disappeared, and running headers interrupted lists from about page 220. In the second continuation volume, a dense table around pages 61–62 was reordered, section `2.1.2` was duplicated, and later content was missing. |
| **Root Cause** | Marker’s layout classification and Markdown serialization do not reliably preserve two-dimensional row relationships, page furniture, pagination, or cross-page sequence. The exact trigger for the pages 61–62 loss has not been isolated. |
| **Solution** | Not yet implemented. Preserve page/block metadata, enable targeted source-to-output validation at table and page boundaries, detect duplicate section labels and missing TOC pagination, and quarantine structurally complex pages before chunking or retrieval. |
| **Date Resolved** | — |

---

### BUG-001 · Unstructured PDF conversion failed because PDF extras were missing

| Field | Detail |
|---|---|
| **Issue** | `unstructured_test.py` could not load the PDF partitioner and raised `ModuleNotFoundError: No module named 'unstructured_inference'`. |
| **Found Date** | 2026-07-14 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `unstructured_test.py`; Python environment |
| **Description** | The base package/import was initially absent, and a later run with incomplete dependencies reached `unstructured.partition.pdf_image.pdfminer_processing` before failing to import `unstructured_inference`. |
| **Root Cause** | PDF support depends on optional inference/OCR packages not supplied by a minimal Unstructured installation. |
| **Solution** | Install `unstructured[pdf]` in the Python 3.12 environment and verify the target PDF through PowerShell; see ADR-002 and Research topic 2. |
| **Date Resolved** | 2026-07-14 |

---

### BUG-005 · Shared installation selected a Python-incompatible Numba release

| Field | Detail |
|---|---|
| **Issue** | Installing the unpinned combined `requirements.txt` selected `numba==0.53.1`, which refuses Python 3.12. |
| **Found Date** | 2026-07-15 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Temporary `requirements.txt`; shared Python environment |
| **Description** | `uv pip install -r requirements.txt` failed while building Numba because that release supports Python 3.6 through 3.9. |
| **Root Cause** | The unconstrained dependency resolution selected an obsolete transitive Numba version for Unstructured. |
| **Solution** | Abandon the combined environment and install each pinned loader in its own Python 3.12 environment under ADR-005. |
| **Date Resolved** | 2026-07-15 |

---

### BUG-006 · Marker and Unstructured have incompatible Pillow constraints

| Field | Detail |
|---|---|
| **Issue** | Marker PDF 1.10.2 and `unstructured[pdf]` 0.24.1 could not be resolved in one environment. |
| **Found Date** | 2026-07-15 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Temporary `requirements.txt`; shared Python environment |
| **Description** | Unstructured's `pi-heif` dependency required Pillow 11.1 or newer, while Marker required Pillow below 11. |
| **Root Cause** | The selected upstream releases declare mutually exclusive version ranges for Pillow. |
| **Solution** | Use the three loader-specific environments defined by ADR-005; remove the unsatisfiable shared requirements and lockfile. |
| **Date Resolved** | 2026-07-15 |

---

### BUG-007 · Shared environment contained incomplete Torch metadata

| Field | Detail |
|---|---|
| **Issue** | `uv` could not read the installed Torch distribution because its `METADATA` file was missing. |
| **Found Date** | 2026-07-15 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Temporary `.venv`; Torch installation |
| **Description** | Repeated installs failed while reading `torch-2.13.0.dist-info/METADATA`, indicating a corrupted or incomplete package state. |
| **Root Cause** | The experimental shared environment accumulated a partial Torch installation while dependencies were repeatedly added and re-resolved. |
| **Solution** | Delete the shared environment and recreate isolated environments from scratch (ADR-005). |
| **Date Resolved** | 2026-07-15 |

---

### BUG-008 · Unrelated `marker` package shadowed Marker PDF

| Field | Detail |
|---|---|
| **Issue** | `marker_test.py` imported an unrelated distribution and failed with `ImportError: cannot import name 'CONFIG_DIR' from 'marker.utils'`. |
| **Found Date** | 2026-07-15 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Python environment; `codes/marker_test.py` blocked |
| **Description** | The installed package exposed `marker.lms.Markus`, not Datalab's `marker.converters.pdf.PdfConverter` implementation expected by the script. |
| **Root Cause** | The distribution named `marker` was installed instead of `marker-pdf`, creating a namespace collision. |
| **Solution** | Create `.venv-marker` and install `marker-pdf==1.10.2`; do not install the unrelated `marker` distribution. |
| **Date Resolved** | 2026-07-15 |

---

### BUG-009 · Docling can report batch success after page preprocessing failures

| Field | Detail |
|---|---|
| **Issue** | Docling emitted `Stage preprocess failed ... std::bad_alloc` for individual pages, but the runner still counted the containing document as converted. |
| **Found Date** | 2026-07-15 |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `codes/docling_test.py`; Docling preprocessing pipeline |
| **Description** | Native page preprocessing ran on a CPU-only Torch build and repeatedly failed to allocate memory, often after the first ten zero-based page indexes. Docling returned partial document objects, so the script wrote Markdown and printed `6 converted, 0 failed`. |
| **Root Cause** | The native preprocessing stage can fail below the document-level exception boundary; the runner validates only whether `converter.convert()` returns, not page completeness. CPU buffering, a native allocation leak, or OCR pressure remained suspected rather than proven. |
| **Solution** | Not yet implemented. Candidate diagnostics are to disable OCR for text PDFs, reduce OCR/layout/table batch sizes and queue depth, preserve a verified CUDA Torch pin, and add page-level completeness checks. |
| **Date Resolved** | — |

---

### BUG-010 · Marker Markdown contains broken image links and mojibake

| Field | Detail |
|---|---|
| **Issue** | The six-file Marker run produced Markdown with 131 image references but no corresponding image assets; the RAG chapter also contains at least 26 mojibake sequences. |
| **Found Date** | 2026-07-15 |
| **Status** | Open |
| **Severity** | HIGH |
| **File** | `codes/marker_test.py`; `marker_results/`; `Marker-PDF Report.md` |
| **Description** | Every referenced logo, diagram, map, engineering graphic, and page image is broken in the delivered result tree. Corrupted punctuation and symbols remain in the RAG output despite UTF-8 writes. |
| **Root Cause** | The runner writes only Markdown from `text_from_rendered()` and does not export or validate image assets. The exact layer introducing mojibake has not been isolated. |
| **Solution** | Not yet implemented. Export assets to stable relative paths, validate links, and scan/normalize text encoding before accepting a conversion. |
| **Date Resolved** | — |

---

### BUG-002 · Marker installation failed on Python 3.14 at the regex dependency

| Field | Detail |
|---|---|
| **Issue** | Installing `marker-pdf[full]` failed while building `regex==2024.11.6`. |
| **Found Date** | 2026-07-14 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Python environment; `marker_test.py` blocked |
| **Description** | The installer could not find a compatible wheel and attempted a native source build that required unavailable Microsoft C++ build tooling. |
| **Root Cause** | Python 3.14 was newer than the supported Windows wheel set for the pinned dependency. |
| **Solution** | Create a Python 3.12 environment and install `marker-pdf[full]`, which resolved compatible wheels; standardized in ADR-002. |
| **Date Resolved** | 2026-07-14 |

---

### BUG-003 · Unstructured output directory was absent before the first write

| Field | Detail |
|---|---|
| **Issue** | `unstructured_test.py` targeted `unstructured_results/*.md` while the directory did not exist. |
| **Found Date** | 2026-07-14 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `unstructured_test.py`; `unstructured_results/` |
| **Description** | Python's `open()` creates a file but not its missing parent directory, so the planned write would fail with `FileNotFoundError`. |
| **Root Cause** | The script assumes result directories are provisioned externally. |
| **Solution** | Initially create `unstructured_results/` manually. ADR-004 later removed the underlying assumption: all three scripts now create their output directories and mirrored subdirectories automatically. |
| **Date Resolved** | 2026-07-14 |

---

### BUG-004 · Git Bash reported false native-process failures for Unstructured

| Field | Detail |
|---|---|
| **Issue** | Invoking the Windows Python 3.12 interpreter through Git Bash produced exit 139/127 and a reported segmentation fault with no useful log. |
| **Found Date** | 2026-07-14 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | Execution environment; `unstructured_test.py` |
| **Description** | Basic Python worked, but heavy Unstructured/native DLL imports behaved inconsistently through Git Bash. The same import and full script worked through PowerShell and generated both outputs. |
| **Root Cause** | Shell/process interoperability around the Windows native Python and its heavy DLL stack, not a reproducible application-code crash. |
| **Solution** | Use PowerShell for Windows execution and verification; see ADR-003. |
| **Date Resolved** | 2026-07-14 |

---

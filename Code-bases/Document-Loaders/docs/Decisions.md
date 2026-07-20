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

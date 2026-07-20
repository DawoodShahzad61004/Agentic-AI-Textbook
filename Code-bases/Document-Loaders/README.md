# Document Loaders

A small batch-comparison project that converts every file under `source/` to Markdown with three open-source document-processing libraries:

- [Docling](https://github.com/docling-project/docling)
- [Unstructured](https://github.com/Unstructured-IO/unstructured)
- [Marker](https://github.com/datalab-to/marker)

Each loader runs through an independent Python script and writes its output to a dedicated directory. This keeps library-specific behavior visible and makes the generated Markdown easy to compare side by side. The project also contains an experimental workflow for chunking Marker-generated Markdown and recording human-readable run reports.

## Source Corpus

All three scripts recursively discover files under:

```text
source/
```

Nested source directories are mirrored under each loader's result directory.

Source PDFs and Marker-generated Markdown are ignored by Git and remain local. The six-PDF, 251-page corpus used for the main Marker assessment contained the original RAG chapter plus five procurement, legal, and engineering documents. Two large RFT continuation PDFs and their Marker outputs were later used for supplemental page-level checks and the chunking experiments. Because these inputs and outputs are local artifacts, their current directory counts are not part of the reproducible repository state. The tracked Docling and Unstructured result trees each retain the original RAG-chapter output.

## How It Works

```text
source/**/*
    |
    +--> codes/docling_test.py -------> docling_results/**/*.md
    |
    +--> codes/unstructured_test.py --> unstructured_results/**/*.md
    |       `--> elements_to_markdown()
    |
    `--> codes/marker_test.py --------> marker_results/**/*.md

marker_results/**/*.md
    `--> chunking/ingest.py ----------> chunk-runs/chunks_<timestamp>.md
```

| Loader | Approach | Current package version |
|---|---|---:|
| Docling | Converts into a structured document model and exports Markdown | 2.113.0 |
| Unstructured | Partitions the PDF into typed elements; local code maps them to Markdown | 0.24.1 |
| Marker | Uses a model-backed PDF converter optimized for structured Markdown | 1.10.2 |

## Requirements

- Windows with PowerShell
- Python 3.12 (the verified environment uses Python 3.12.10)
- [`uv`](https://docs.astral.sh/uv/)
- `tiktoken` for chunk and Markdown-table token counts
- Sufficient disk space for document-analysis and OCR model downloads

Python 3.12 is intentional. The project previously encountered missing Windows wheels for parts of the document-AI stack on Python 3.14.

## Setup

Current Marker and Unstructured releases have incompatible Pillow constraints, so use a separate environment for each loader. From the project root in PowerShell:

```powershell
uv venv .venv-docling --python 3.12
uv pip install --python .venv-docling\Scripts\python.exe "docling==2.113.0"

uv venv .venv-unstructured --python 3.12
uv pip install --python .venv-unstructured\Scripts\python.exe "unstructured[pdf]==0.24.1"

uv venv .venv-marker --python 3.12
uv pip install --python .venv-marker\Scripts\python.exe "marker-pdf==1.10.2"
uv pip install --python .venv-marker\Scripts\python.exe tiktoken
```

The scripts create their result directories automatically. Marker uses `marker-pdf` rather than the unrelated package named `marker`; the `[full]` extra is unnecessary for the current PDF corpus.

## Usage

Run any loader independently from the repository root:

```powershell
& .\.venv-docling\Scripts\python.exe .\codes\docling_test.py
& .\.venv-unstructured\Scripts\python.exe .\codes\unstructured_test.py
& .\.venv-marker\Scripts\python.exe .\codes\marker_test.py
```

Each batch continues after individual conversion errors, prints a summary, and exits with status 1 if any source failed. Existing Markdown outputs for the same source-relative paths are overwritten.

First runs can be slow because Docling, Unstructured, and Marker may download or initialize OCR and layout models. CPU-only conversion is supported but can take several minutes for complex documents.

To chunk every Markdown file currently under `marker_results/` and write a timestamped report under the ignored `chunk-runs/` directory:

```powershell
& .\.venv-marker\Scripts\python.exe .\chunking\ingest.py
```

Each report records the source path, zero-based per-source chunk sequence, character count, `cl100k_base` token count, and average tokens across the run. The splitter remains experimental: the committed implementation is a custom heading/table/list splitter that replaced the earlier recursive-splitter baseline and dropped the `langchain-text-splitters` dependency, and an uncommitted, hand-authored rule-based rewrite is actively replacing it in turn. That uncommitted rewrite also adds an in-memory preprocessing pass that normalizes Marker's inconsistent numbered-clause and heading formatting before splitting; it operates on the loaded text only and never rewrites the Markdown under `marker_results/`.

To inspect the `cl100k_base` token size of every pipe-style Markdown table in `marker_results/`:

```powershell
& .\.venv-marker\Scripts\python.exe .\codes\count_table_tokens.py
```

The utility also accepts a custom input directory and `--encoding` value.

## Project Structure

```text
Document-Loaders/
|-- source/                        # Shared recursive source corpus
|-- codes/
|   |-- count_table_tokens.py      # Markdown-table token diagnostic
|   |-- docling_test.py            # Docling batch entry point
|   |-- marker_test.py             # Marker batch entry point
|   `-- unstructured_test.py       # Unstructured batch entry point
|-- chunking/
|   |-- ingest.py                  # Experimental Marker-Markdown chunker
|   `-- logger_config.py           # Timestamped chunk-run report writer
|-- chunk-runs/                    # Generated chunk reports (gitignored)
|-- docling_results/               # Docling Markdown output
|-- marker_results/                # Marker Markdown output
|-- unstructured_results/          # Unstructured Markdown output
|-- docs/                          # Status, architecture, ADRs, research, and bugs
|-- graphify-out/                  # Generated knowledge graph (gitignored)
|-- Marker-PDF Report.md           # Detailed six-PDF Marker quality assessment
`-- main.py                        # Temporary uv scaffold; not part of the loader workflow
```

## Loader Notes

### Docling

`codes/docling_test.py` creates one `DocumentConverter`, converts every discovered file, and calls `export_to_markdown()` on each Docling document model.

### Unstructured

`codes/unstructured_test.py` calls `partition()` for each discovered file and then applies a small local adapter:

- `Title` becomes a level-one heading.
- `Header` becomes a level-two heading.
- `ListItem` becomes a Markdown list item.
- Other elements become plain paragraphs.

This is deliberately lightweight and does not preserve every metadata or layout feature available from Unstructured.

### Marker

`codes/marker_test.py` creates one `PdfConverter`, attempts every discovered file, and obtains Markdown with `text_from_rendered()`. The converter is PDF-oriented, so unsupported formats are reported as per-file failures. Marker can be computationally heavier and benefits more from acceleration on complex documents.

### Marker Markdown chunking

`chunking/ingest.py` recursively reads only `.md` and `.markdown` files under `marker_results/`, retains each source-relative path, and assigns per-source chunk sequence numbers. In the current uncommitted revision it first runs an in-memory preprocessing pass that repairs Marker's inconsistent numbered-clause and heading formatting (best-effort, scoped to the observed RFT/contract patterns) before splitting, without modifying the source Markdown. `chunking/logger_config.py` writes the resulting chunks and token statistics to `chunk-runs/`. These files support experimentation; they do not yet define a production-ready or final section-splitting policy.

## Comparing Results

The generated files should be evaluated on more than file size. Useful comparison dimensions include:

- Heading hierarchy
- Reading order
- Tables
- Equations
- Lists and code blocks
- Image and caption handling
- Metadata preservation
- Runtime and resource usage

No automated quality benchmark is implemented yet.

The six-PDF Marker assessment and supplemental page-level findings are documented in [`Marker-PDF Report.md`](Marker-PDF%20Report.md). Marker generally recovers ordinary prose well, including some unusually small and highlighted text, but its raw output is not reliable for complex forms, row associations, merged or cross-page tables, page navigation, heading hierarchy, or other documents where structural relationships carry meaning. High aggregate word retention does not prove structural completeness.

## Known Limitations

- Marker currently uses its PDF-oriented converter and may reject non-PDF sources.
- The Marker runner writes Markdown but does not export or validate referenced image assets. The assessed outputs contain 131 broken image references, and the RAG chapter contains at least 26 mojibake sequences.
- Marker flattens nested Markdown list pointers (bullet- and roman-numeral-style sub-points) to a single indentation level, discarding the original list hierarchy that downstream chunking would otherwise use.
- Docling can return and write a document even after page-level preprocessing failures, so a successful batch summary does not currently prove that every page converted completely.
- The expanded six-PDF corpus has not yet been run through Unstructured.
- The chunking workflow is experimental. The committed splitter is a custom heading/table/list implementation that replaced the earlier recursive-splitter baseline; an uncommitted, hand-authored rule-based rewrite is now iterating toward a section-oriented algorithm and is not yet final.
- Chunking cannot recover content, row relationships, or page structure already lost during PDF conversion.
- Generated chunk reports can be several megabytes and are intentionally ignored by Git.
- There is no shared CLI, configuration file, batch runner, or automated test suite.
- The three loaders require separate environments with the currently selected versions.
- The scripts are comparison experiments, not a production ingestion pipeline.
- A routed architecture using fast PDF parsing, OCR, broad-format fallback, confidence scoring, and quarantine has been researched but is not implemented.

## Documentation

Detailed project records are maintained in:

- [`docs/Architecture.md`](docs/Architecture.md) — current structure and researched future direction
- [`docs/Decisions.md`](docs/Decisions.md) — architecture decision records
- [`docs/Research.md`](docs/Research.md) — loader and environment research
- [`docs/Bugs.md`](docs/Bugs.md) — historical failures and fixes
- [`docs/Status.md`](docs/Status.md) — chronological project log

## Knowledge Graph

The project uses Graphify to maintain a local knowledge graph under `graphify-out/`. That directory is generated and gitignored. When available, its primary artifacts are:

- `graphify-out/graph.html` — interactive visualization
- `graphify-out/GRAPH_REPORT.md` — graph audit and summary
- `graphify-out/graph.json` — machine-readable graph data

## License

No project license has been added yet. The three loader libraries retain their respective upstream licenses.

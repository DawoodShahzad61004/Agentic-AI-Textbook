"""Convert PDF files to Markdown by calling the isolated Marker microservice.

Marker (marker-pdf 1.10.2 + surya-ocr 0.17.1 + CUDA torch) cannot be installed
into app_workflow's Python 3.14 environment without forcing transformers down to
4.x and breaking sentence-transformers, so it runs in its own GPU container (see
``marker_service/``). This module POSTs each PDF to that service and wraps the
returned Markdown in a :class:`~langchain_core.documents.Document` whose
``metadata['source']`` is the PDF's path. Non-PDF paths are ignored, so the
discovered file list can be passed in wholesale.

The public ``load_documents`` signature is unchanged from the earlier in-process
version, so ``ingestion_requests.run_ingestion`` needs no changes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from langchain_core.documents import Document

from app_workflow.config import (
    DATA_FILES_DIR,
    MARKER_SERVICE_TIMEOUT,
    MARKER_SERVICE_URL,
)

logger = logging.getLogger(__name__)

_PDF_EXT = {".pdf"}


def _source_label(path: Path) -> str:
    """Represent the PDF path relative to the data-files root when possible."""
    try:
        return str(path.relative_to(DATA_FILES_DIR))
    except ValueError:
        return str(path)


def load_documents(file_paths: list[str]) -> list[Document]:
    """Render every PDF in ``file_paths`` to a Markdown ``Document``.

    Each PDF is streamed to the Marker service's ``/convert`` endpoint. A failure
    on one file is logged and skipped so the rest of the batch still ingests,
    matching the previous in-process behaviour.
    """
    pdf_paths = [Path(fp) for fp in file_paths if Path(fp).suffix.lower() in _PDF_EXT]
    if not pdf_paths:
        logger.warning("Marker loader: no PDF files found among %d paths", len(file_paths))
        return []

    convert_url = MARKER_SERVICE_URL.rstrip("/") + "/convert"
    logger.info("Marker service at %s. Converting %d PDF(s).", convert_url, len(pdf_paths))

    documents: list[Document] = []
    for pdf_path in pdf_paths:
        source = _source_label(pdf_path)
        try:
            with pdf_path.open("rb") as fh:
                response = requests.post(
                    convert_url,
                    files={"file": (pdf_path.name, fh, "application/pdf")},
                    timeout=MARKER_SERVICE_TIMEOUT,
                )
            response.raise_for_status()
            markdown_output = response.json()["markdown"]
        except Exception:
            logger.warning("Marker service failed to convert %s", source, exc_info=True)
            continue

        if not markdown_output.strip():
            logger.warning("Marker produced empty Markdown for %s", source)
            continue

        documents.append(
            Document(page_content=markdown_output, metadata={"source": source})
        )
        logger.info("Marker converted %s (%d chars)", source, len(markdown_output))

    logger.info("Marker loaded %d of %d PDF(s)", len(documents), len(pdf_paths))
    return documents

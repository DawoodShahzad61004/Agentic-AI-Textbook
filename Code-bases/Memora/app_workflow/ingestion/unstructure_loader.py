"""Load raw source files into LangChain ``Document`` objects.

This is the default (non-Marker) loader. It handles three families of input:

* Unstructured-supported documents (PDF, text, Word, HTML) via
  :class:`~langchain_unstructured.UnstructuredLoader`.
* Tabular files (CSV / Excel), which are converted to JSON records **in memory**
  and turned directly into documents — nothing is written to disk. The produced
  documents mirror the shape :class:`~langchain_community.document_loaders.JSONLoader`
  emits for ``jq_schema=".[]"`` with ``text_content=False`` (one document per
  record, ``page_content`` a JSON string, ``metadata`` carrying ``source`` and a
  1-based ``seq_num``).
* JSON files already on disk, loaded with ``JSONLoader`` as-is.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from langchain_community.document_loaders import JSONLoader
from langchain_core.documents import Document
from langchain_unstructured import UnstructuredLoader

from app_workflow.config import TABULAR_EXT, UNSTRUCTURED_EXT

logger = logging.getLogger(__name__)


def _tabular_to_documents(path: Path) -> list[Document]:
    """Convert a CSV/Excel file to JSON-record documents without persisting.

    Reproduces what ``JSONLoader(jq_schema=".[]", text_content=False)`` would
    yield if the records had first been written to a ``.json`` file, but keeps
    everything in memory.
    """
    try:
        ext = path.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path, sheet_name=0)
        df = df.fillna("")
        records = df.to_dict(orient="records")
    except Exception:
        logger.warning("Failed to convert %s", path.name, exc_info=True)
        return []

    documents = [
        Document(
            page_content=json.dumps(record, ensure_ascii=False),
            metadata={"source": str(path), "seq_num": index},
        )
        for index, record in enumerate(records, start=1)
    ]
    logger.info("Converted %s -> %d in-memory JSON records", path.name, len(documents))
    return documents


def load_documents(file_paths: list[str]) -> list[Document]:
    """Create LangChain ``Document`` objects from ``file_paths``.

    Tabular files are converted to JSON documents in memory; JSON files are
    loaded from disk; everything else supported goes through UnstructuredLoader.
    """
    logger.info("Found %d supported files", len(file_paths))
    all_docs: list[Document] = []
    unstructured_paths: list[str] = []
    json_paths: list[str] = []

    for fp in file_paths:
        p = Path(fp)
        ext = p.suffix.lower()
        if ext in TABULAR_EXT:
            all_docs.extend(_tabular_to_documents(p))
        elif ext == ".json":
            json_paths.append(fp)
        elif ext in UNSTRUCTURED_EXT:
            unstructured_paths.append(fp)

    if unstructured_paths:
        try:
            docs = UnstructuredLoader(unstructured_paths).load()
            all_docs.extend(docs)
            logger.info(
                "UnstructuredLoader: %d sections from %d files",
                len(docs),
                len(unstructured_paths),
            )
        except Exception:
            logger.warning("UnstructuredLoader failed", exc_info=True)

    for fp in json_paths:
        try:
            docs = JSONLoader(file_path=fp, jq_schema=".[]", text_content=False).load()
            all_docs.extend(docs)
            logger.info("JSONLoader: %d records from %s", len(docs), Path(fp).name)
        except Exception:
            logger.warning("Failed to load %s", Path(fp).name, exc_info=True)

    logger.info("Loaded %d document pages/sections total", len(all_docs))
    return all_docs

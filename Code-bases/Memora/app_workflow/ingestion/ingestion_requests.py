"""Entry point that drives one ingestion run.

Responsibilities:

* Resolve the ``ENABLE_MARKER_LOADER`` / ``ENABLE_CUSTOM_SPLITTER`` switches:
  an explicit boolean passed in overrides the ``config.py`` default; ``None``
  keeps the default.
* Discover every supported source file under ``data_files/`` (recursively).
* Pick the loader (Marker vs. Unstructured) and the splitter (custom vs.
  recursive) according to the resolved switches, produce chunks, embed them,
  and add them to the vector store.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

from app_workflow import config
from app_workflow.config import (
    BATCH_SIZE,
    COLLECTION_NAME,
    DATA_FILES_DIR,
    SUPPORTED_EXT,
    VECTOR_STORE_PATH,
)
from app_workflow.services.embedding_manager import EmbeddingManager
from app_workflow.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


def discover_files() -> list[str]:
    """Return every supported file under ``data_files/``, searched recursively.

    ``data_files/`` may contain arbitrarily nested subfolders; ``rglob`` walks
    all of them. Paths are de-duplicated while preserving discovery order.
    """
    file_paths: list[str] = []
    if DATA_FILES_DIR.exists():
        for path in DATA_FILES_DIR.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXT:
                file_paths.append(str(path))
    return list(dict.fromkeys(file_paths))  # deduplicate, preserve order


def _resolve(override: Optional[bool], default: bool) -> bool:
    """An explicit boolean override wins; ``None`` falls back to the config default."""
    return default if override is None else bool(override)


def run_ingestion(
    enable_marker_loader: Optional[bool] = None,
    enable_custom_splitter: Optional[bool] = None,
) -> dict:
    """Run the full ingestion pipeline and return a summary of what happened.

    ``enable_marker_loader`` / ``enable_custom_splitter`` override the matching
    ``config.py`` toggles when provided (not ``None``).
    """
    use_marker = _resolve(enable_marker_loader, config.ENABLE_MARKER_LOADER)
    use_custom = _resolve(enable_custom_splitter, config.ENABLE_CUSTOM_SPLITTER)
    logger.info(
        "Ingestion run: marker_loader=%s, custom_splitter=%s", use_marker, use_custom
    )

    file_paths = discover_files()
    if not file_paths:
        logger.warning("No supported files found under %s", DATA_FILES_DIR)
        return {
            "files_discovered": 0,
            "documents_loaded": 0,
            "chunks_created": 0,
            "documents_in_store": None,
            "marker_loader": use_marker,
            "custom_splitter": use_custom,
        }

    # --- load -------------------------------------------------------------
    if use_marker:
        from app_workflow.ingestion import marker_loader

        documents: list[Document] = marker_loader.load_documents(file_paths)
    else:
        from app_workflow.ingestion import unstructure_loader

        documents = unstructure_loader.load_documents(file_paths)

    # --- split ------------------------------------------------------------
    if use_custom:
        from app_workflow.ingestion import custom_splitter

        chunks = custom_splitter.split_documents(documents)
    else:
        from app_workflow.ingestion import recursive_splitter

        chunks = recursive_splitter.split_documents(documents)

    if not chunks:
        logger.warning("No chunks produced from %d documents", len(documents))
        return {
            "files_discovered": len(file_paths),
            "documents_loaded": len(documents),
            "chunks_created": 0,
            "documents_in_store": None,
            "marker_loader": use_marker,
            "custom_splitter": use_custom,
        }

    # --- embed + store ----------------------------------------------------
    embedding_manager = EmbeddingManager()
    vector_store = VectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=VECTOR_STORE_PATH,
    )
    vector_store.add_documents_in_batches(chunks, embedding_manager, batch_size=BATCH_SIZE)

    total_in_store = vector_store.collection.count()
    logger.info("Ingestion complete. Total documents in store: %d", total_in_store)

    return {
        "files_discovered": len(file_paths),
        "documents_loaded": len(documents),
        "chunks_created": len(chunks),
        "documents_in_store": total_in_store,
        "marker_loader": use_marker,
        "custom_splitter": use_custom,
    }


def main() -> None:
    from app_workflow.services.logger_config import setup_logging

    setup_logging(app_name="ingestion")
    summary = run_ingestion()
    logger.info("Ingestion summary: %s", summary)


if __name__ == "__main__":
    main()

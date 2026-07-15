import logging
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_unstructured import UnstructuredLoader
from langchain_community.document_loaders import JSONLoader

from embedding_manager import EmbeddingManager
from vector_store import VectorStore
import json
import pandas as pd

from logger_config import setup_logging

logger = logging.getLogger(__name__)

from config import (
    UNSTRUCTURED_EXT,
    TABULAR_EXT,
    SUPPORTED_EXT,
    SEARCH_ROOTS,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    BATCH_SIZE,
    VECTOR_STORE_PATH,
    COLLECTION_NAME,
    MIN_CHUNK_CHARS,
    JSON_DIR,
)

def discover_files() -> list[str]:
    file_paths = []
    for root in SEARCH_ROOTS:
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
                    file_paths.append(str(p))
    return list(dict.fromkeys(file_paths))  # deduplicate, preserve order

def _convert_tabular_to_json(p: Path) -> Path | None:
    try:
        ext = p.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(p)
        else:
            df = pd.read_excel(p, sheet_name=0)
        df = df.fillna("")
        records = df.to_dict(orient="records")
        json_path = JSON_DIR / p.with_suffix(".json").name
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Converted {p.name} -> {json_path.name} ({len(records)} rows)")
        return json_path
    except Exception:
        logger.warning(f"Failed to convert {p.name}", exc_info=True)
        return None

def load_documents(file_paths: list[str]) -> list[Document]:
    logger.info(f"Found {len(file_paths)} supported files")
    all_docs: list[Document] = []
    unstructured_paths: list[str] = []
    json_paths: list[str] = []

    for fp in file_paths:
        p = Path(fp)
        ext = p.suffix.lower()
        if ext in TABULAR_EXT:
            converted = _convert_tabular_to_json(p)
            if converted:
                json_paths.append(str(converted))
        elif ext == ".json":
            json_paths.append(fp)
        elif ext in UNSTRUCTURED_EXT:
            unstructured_paths.append(fp)

    if unstructured_paths:
        try:
            docs = UnstructuredLoader(unstructured_paths).load()
            all_docs.extend(docs)
            logger.info(f"UnstructuredLoader: {len(docs)} sections from {len(unstructured_paths)} files")
        except Exception:
            logger.warning("UnstructuredLoader failed", exc_info=True)

    for fp in json_paths:
        try:
            docs = JSONLoader(file_path=fp, jq_schema=".[]", text_content=False).load()
            all_docs.extend(docs)
            logger.info(f"JSONLoader: {len(docs)} records from {Path(fp).name}")
        except Exception:
            logger.warning(f"Failed to load {Path(fp).name}", exc_info=True)

    logger.info(f"Loaded {len(all_docs)} document pages/sections total")
    return all_docs

def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks")

    # ── NAC: stamp chunk_seq per source ──────────────────────────────────────
    # Group by source path so sequence resets for each file.
    from collections import defaultdict
    seq_counter: dict[str, int] = defaultdict(int)
    for chunk in chunks:
        src = chunk.metadata.get("source", "__unknown__")
        chunk.metadata["chunk_seq"] = seq_counter[src]
        seq_counter[src] += 1
    # ─────────────────────────────────────────────────────────────────────────

    before = len(chunks)
    chunks = [c for c in chunks if len(c.page_content.strip()) >= MIN_CHUNK_CHARS]
    logger.info(f"Filtered {before - len(chunks)} stub chunks. {len(chunks)} remain.")
    if chunks:
        logger.debug(f"\nExample chunk preview:\n{chunks[0].page_content[:200]}...\n")
    return chunks

def main():
    setup_logging()
    logger.debug("=" * 60)
    logger.debug("RAG Pipeline — Document Ingestion")
    logger.debug("=" * 60)

    file_paths = discover_files()
    if not file_paths:
        logger.warning("No supported files found. Check your data directories.")
        return

    documents = load_documents(file_paths)
    chunks = split_documents(documents)

    embedding_manager = EmbeddingManager()
    vector_store = VectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=VECTOR_STORE_PATH,
    )

    vector_store.add_documents_in_batches(chunks, embedding_manager, batch_size=BATCH_SIZE)

    logger.info("Ingestion complete")
    logger.info(f"Total documents in store: {vector_store.collection.count()}")


if __name__ == "__main__":
    main()

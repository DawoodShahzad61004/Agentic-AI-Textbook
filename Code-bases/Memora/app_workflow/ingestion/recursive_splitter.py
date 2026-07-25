"""Split LangChain ``Document`` objects into chunks with a recursive splitter.

This is the default (non-custom) splitter: a plain
:class:`~langchain_text_splitters.RecursiveCharacterTextSplitter` sized by the
``CHUNK_SIZE`` / ``CHUNK_OVERLAP`` config values, followed by a per-source
``chunk_seq`` stamp and a minimum-length filter.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app_workflow.config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_CHARS

logger = logging.getLogger(__name__)


def split_documents(documents: list[Document]) -> list[Document]:
    """Split ``documents`` into chunks and return them."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    logger.info("Split %d documents into %d chunks", len(documents), len(chunks))

    # ── stamp chunk_seq per source ───────────────────────────────────────────
    # Group by source path so the sequence resets for each file.
    seq_counter: dict[str, int] = defaultdict(int)
    for chunk in chunks:
        src = chunk.metadata.get("source", "__unknown__")
        chunk.metadata["chunk_seq"] = seq_counter[src]
        seq_counter[src] += 1
    # ─────────────────────────────────────────────────────────────────────────

    before = len(chunks)
    chunks = [c for c in chunks if len(c.page_content.strip()) >= MIN_CHUNK_CHARS]
    logger.info("Filtered %d stub chunks. %d remain.", before - len(chunks), len(chunks))
    if chunks:
        logger.debug("\nExample chunk preview:\n%s...\n", chunks[0].page_content[:200])
    return chunks

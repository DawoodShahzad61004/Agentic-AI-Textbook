"""Logging and chunk-run output for the Markdown chunking workflow."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

import tiktoken


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN_DIR = PROJECT_ROOT / "chunk-runs"
_CONFIGURED_ATTR = "_chunking_logging_configured"
TOKEN_ENCODING = "cl100k_base"
_TOKEN_ENCODER = tiktoken.get_encoding(TOKEN_ENCODING)


class Chunk(Protocol):
    """The subset of a LangChain Document needed by the run writer."""

    page_content: str
    metadata: dict


def setup_logging(console_level: int = logging.INFO) -> None:
    """Configure concise console logging once for the current process."""
    root_logger = logging.getLogger()
    if getattr(root_logger, _CONFIGURED_ATTR, False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(console_level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    setattr(root_logger, _CONFIGURED_ATTR, True)


def write_chunk_run(
    chunks: Iterable[Chunk],
    run_dir: str | Path = DEFAULT_RUN_DIR,
) -> Path:
    """Write one human-readable file containing all chunks from this run."""
    chunk_list = list(chunks)
    output_dir = Path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"chunks_{timestamp}.md"

    prepared_chunks = [
        (
            chunk,
            chunk.page_content.strip(),
            len(_TOKEN_ENCODER.encode(chunk.page_content.strip())),
        )
        for chunk in chunk_list
    ]
    average_tokens = (
        sum(token_count for _, _, token_count in prepared_chunks) / len(prepared_chunks)
        if prepared_chunks
        else 0.0
    )

    sections = [
        "# Chunking Run",
        "",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Total chunks: {len(chunk_list)}",
        f"- Average chunk tokens: {average_tokens:.2f}",
    ]

    for index, (chunk, content, token_count) in enumerate(prepared_chunks, start=1):
        source = chunk.metadata.get("source", "unknown")
        sequence = chunk.metadata.get("chunk_seq", index - 1)
        backtick_runs = re.findall(r"`+", content)
        fence = "`" * max(3, 1 + max((len(run) for run in backtick_runs), default=0))
        sections.extend(
            [
                "",
                "---",
                "",
                f"## Chunk {index}",
                "",
                f"- Source: `{source}`",
                f"- Source chunk: {sequence}",
                f"- Characters: {len(content)}",
                f"- Tokens: {token_count}",
                "",
                f"{fence}text",
                content,
                fence,
            ]
        )

    output_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return output_path

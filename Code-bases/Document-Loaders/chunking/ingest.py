"""Split Marker-generated Markdown files into text chunks."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

if __package__:
    from .logger_config import setup_logging, write_chunk_run
else:
    from logger_config import setup_logging, write_chunk_run


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MARKER_RESULTS_DIR = PROJECT_ROOT / "marker_results"
CHUNK_SIZE = 1600
MIN_CHUNK_CHARS = 50

logger = logging.getLogger(__name__)

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+\S")
LIST_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:[-*+]|\d+[.)])[ \t]+\S", re.MULTILINE
)
TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


@dataclass
class Document:
    """A text payload and the metadata carried into each derived chunk."""

    page_content: str
    metadata: dict[str, object] = field(default_factory=dict)


def discover_files() -> list[Path]:
    """Return every Markdown file below ``marker_results/`` in stable order."""
    if not MARKER_RESULTS_DIR.is_dir():
        return []

    return sorted(
        path
        for path in MARKER_RESULTS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
    )


def load_documents(file_paths: list[Path]) -> list[Document]:
    """Load each Markdown file as one document while retaining its source path."""
    documents: list[Document] = []

    for path in file_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            logger.exception("Could not read %s", path.relative_to(PROJECT_ROOT))
            continue

        if not content.strip():
            logger.warning("Skipping empty file: %s", path.relative_to(PROJECT_ROOT))
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={"source": str(path.relative_to(PROJECT_ROOT))},
            )
        )

    logger.info("Loaded %d of %d Markdown files", len(documents), len(file_paths))
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Split documents and assign a zero-based chunk sequence per source file."""
    chunks: list[Document] = []
    for document in documents:
        for text in temp_split(document.page_content):
            if len(text) >= MIN_CHUNK_CHARS:
                chunks.append(Document(page_content=text, metadata=document.metadata.copy()))

    sequence_by_source: dict[str, int] = defaultdict(int)
    for chunk in chunks:
        source = str(chunk.metadata.get("source", "unknown"))
        chunk.metadata["chunk_seq"] = sequence_by_source[source]
        sequence_by_source[source] += 1

    logger.info("Split %d documents into %d chunks", len(documents), len(chunks))
    return chunks


def temp_split(text: str) -> list[str]:
    """Split Markdown from top to bottom without cutting structural blocks.

    ``CHUNK_SIZE`` is a hard limit for ordinary prose.  Markdown tables are the
    deliberate exception: a table that starts a chunk is emitted whole so that
    its header and rows never become separate retrieval units.
    """
    text = text.strip()
    if not text:
        return []

    table_spans = _table_spans(text)
    list_spans = _list_spans(text)
    headings = _heading_matches(text)
    chunks: list[str] = []
    cursor = 0

    while cursor < len(text):
        cursor = _skip_blank_lines(text, cursor)
        if cursor >= len(text):
            break

        # A consecutive heading group directly before a table belongs to the
        # table.  This also prevents a heading-only chunk before an oversized
        # table.
        heading_table = _table_section_after_heading(
            text,
            cursor,
            headings=headings,
            table_spans=table_spans,
        )
        if heading_table is not None:
            _append_chunk(chunks, text[cursor:heading_table[1]])
            cursor = heading_table[1]
            continue

        # Rule 6: once a table reaches the front, keep all of it together.
        table = _span_starting_at(table_spans, cursor)
        if table is not None:
            _append_chunk(chunks, text[cursor : table[1]])
            cursor = table[1]
            continue

        # When a list was moved forward, retain its immediately preceding
        # lead-in paragraph (for example, "To be submitted in accordance
        # with:") in the same chunk as the list.
        paragraph_list = _flat_list_section_after_paragraph(
            text,
            cursor,
            list_spans=list_spans,
        )
        if paragraph_list is not None:
            list_start, list_end = paragraph_list
            if list_end - cursor <= CHUNK_SIZE:
                _append_chunk(chunks, text[cursor:list_end])
            else:
                items = _list_items(text, list_start, list_end)
                boundaries = [start for start, _ in items] + [list_end]
                first_end = boundaries[1]
                _append_limited(chunks, text[cursor:first_end])
                for item_start, item_end in zip(
                    boundaries[1:], boundaries[2:]
                ):
                    _append_limited(chunks, text[item_start:item_end])
            cursor = list_end
            continue

        # A section containing one heading followed only by a flat list stays
        # together when it fits.  If it is oversized, each pointer remains an
        # indivisible unit and the heading is attached to the first pointer.
        heading_list = _flat_list_section_after_heading(
            text,
            cursor,
            headings=headings,
            list_spans=list_spans,
        )
        if heading_list is not None:
            list_start, list_end, section_end = heading_list
            if list_end - cursor <= CHUNK_SIZE:
                _append_chunk(chunks, text[cursor:section_end])
            else:
                items = _list_items(text, list_start, list_end)
                boundaries = [start for start, _ in items] + [list_end]
                first_end = boundaries[1]
                _append_limited(chunks, text[cursor:first_end])
                for start, end in zip(boundaries[1:], boundaries[2:]):
                    _append_limited(chunks, text[start:end])
            cursor = section_end
            continue

        # A flat list that was moved to the next chunk is split one pointer at
        # a time.  Continuation lines stay attached to their pointer.
        list_block = _list_block_starting_at(text, list_spans, cursor)
        if list_block is not None:
            items = _list_items(text, cursor, list_block[1])
            if items and len({indent for _, indent in items}) == 1:
                boundaries = [start for start, _ in items] + [list_block[1]]
                for start, end in zip(boundaries, boundaries[1:]):
                    _append_limited(chunks, text[start:end])
                cursor = list_block[1]
                continue

        limit = min(cursor + CHUNK_SIZE, len(text))
        if limit == len(text):
            _append_chunk(chunks, text[cursor:])
            break

        cut = _structural_cut(
            text,
            cursor,
            limit,
            headings=headings,
            table_spans=table_spans,
            list_spans=list_spans,
        )
        trailing_heading = _trailing_heading_start(
            text,
            cursor,
            cut,
            headings,
        )
        if trailing_heading is not None:
            cut = trailing_heading
        if cut <= cursor or _contains_only_headings(text, cursor, cut):
            cut = _cut_with_heading_content(text, cursor, limit)

        # The heading-aware fallback can itself land immediately after a later
        # heading.  Run the rollover check once more on the final candidate so
        # no completed chunk ends with a heading before body content.
        trailing_heading = _trailing_heading_start(
            text,
            cursor,
            cut,
            headings,
        )
        if trailing_heading is not None:
            cut = trailing_heading

        _append_chunk(chunks, text[cursor:cut])
        cursor = cut

    return chunks


def _structural_cut(
    text: str,
    start: int,
    limit: int,
    *,
    headings: list[tuple[int, int]],
    table_spans: list[tuple[int, int]],
    list_spans: list[tuple[int, int]],
) -> int:
    """Choose the boundary for one size-limited candidate chunk."""
    candidate_headings = [
        heading for heading in headings if start <= heading[0] < limit
    ]

    # Rules 4 and 5: move a partial table, plus the appropriate heading when
    # the chunk began in unheaded prose, into the following chunk.
    partial_table = next(
        (span for span in table_spans if span[0] < limit < span[1]), None
    )
    if partial_table is not None:
        table_start = partial_table[0]
        starts_with_heading = bool(
            candidate_headings and candidate_headings[0][0] == start
        )
        if starts_with_heading:
            headings_between = [
                position
                for position, _ in candidate_headings
                if start < position < table_start
            ]
            if not headings_between:
                return table_start
            return _heading_group_start_before_table(
                text,
                headings_between,
                table_start,
            )

        headings_before_table = [
            position
            for position, _ in candidate_headings
            if position < table_start
        ]
        if headings_before_table:
            return headings_before_table[-1]
        return table_start

    # Rule 2 applies when the candidate contains a heading hierarchy rather
    # than a lone heading.  The numerically largest ATX level is the smallest
    # (deepest) level in that hierarchy.
    if len(candidate_headings) > 1:
        deepest_level = max(level for _, level in candidate_headings)
        deepest = [
            position
            for position, level in candidate_headings
            if level == deepest_level
        ]
        last_deepest = deepest[-1]
        next_peer = next(
            (
                position
                for position, level in headings
                if position > last_deepest and level == deepest_level
            ),
            len(text),
        )
        if text[limit:next_peer].strip():
            # Drop every deepest-level subsection in the candidate.  If that
            # would make an empty chunk, retain completed peer sections and
            # move only the final incomplete peer.
            return deepest[0] if deepest[0] > start else deepest[-1]

        return limit

    # Rule 3(i): a heading immediately after this candidate is already a safe
    # boundary, so the candidate can be kept as recorded.
    if re.match(r"[\r\n\t ]*#{1,6}[ \t]+\S", text[limit:]):
        return limit

    # Rule 3(ii), lists: if the limit lands in a list, move its deepest pointer
    # level.  A flat list is moved in full and split per pointer on the next
    # loop iteration.
    list_block = next(
        (span for span in list_spans if span[0] < limit < span[1]), None
    )
    if list_block is not None:
        effective_start = max(start, list_block[0])
        block_items = _list_items(text, effective_start, list_block[1])
        if block_items and len({indent for _, indent in block_items}) == 1:
            paragraph_start = _paragraph_before_list(
                text,
                start,
                effective_start,
            )
            return (
                paragraph_start
                if paragraph_start is not None
                else effective_start
            )

        items = _list_items(text, effective_start, limit)
        if items:
            deepest_indent = max(indent for _, indent in items)
            deepest_items = [
                position for position, indent in items if indent == deepest_indent
            ]
            return deepest_items[0]

    # Rule 3(ii), prose: move the last paragraph into the next chunk.  When a
    # single paragraph is itself oversized, fall back to a hard word boundary
    # so the loop always advances and the size limit remains meaningful.
    paragraph_starts = _paragraph_starts(text, start, limit)
    if paragraph_starts and paragraph_starts[-1] > start:
        return paragraph_starts[-1]
    return _hard_cut(text, start, limit)


def _heading_matches(text: str) -> list[tuple[int, int]]:
    """Return ``(character offset, ATX level)`` outside fenced code blocks."""
    fences = _fenced_code_spans(text)
    matches: list[tuple[int, int]] = []
    for match in re.finditer(r"^(#{1,6})[ \t]+\S", text, re.MULTILINE):
        if not _inside_spans(match.start(), fences):
            matches.append((match.start(), len(match.group(1))))
    return matches


def _fenced_code_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    opening: tuple[str, int] | None = None
    for match in re.finditer(r"^(?P<fence>`{3,}|~{3,}).*$", text, re.MULTILINE):
        marker = match.group("fence")[0]
        if opening is None:
            opening = (marker, match.start())
        elif opening[0] == marker:
            spans.append((opening[1], match.end()))
            opening = None
    if opening is not None:
        spans.append((opening[1], len(text)))
    return spans


def _inside_spans(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _table_spans(text: str) -> list[tuple[int, int]]:
    """Locate complete GitHub-style pipe tables outside fenced code blocks."""
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    fences = _fenced_code_spans(text)
    spans: list[tuple[int, int]] = []
    index = 0
    while index + 1 < len(lines):
        if (
            not _inside_spans(offsets[index], fences)
            and _is_table_row(lines[index].rstrip("\r\n"))
            and _is_table_separator(lines[index + 1].rstrip("\r\n"))
        ):
            start = offsets[index]
            index += 2
            while index < len(lines) and _is_table_row(
                lines[index].rstrip("\r\n")
            ):
                index += 1
            end = offsets[index] if index < len(lines) else len(text)
            spans.append((start, end))
        else:
            index += 1
    return spans


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_table_row(line: str) -> bool:
    return bool(_table_cells(line))


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(
        cells
        and all(
            TABLE_SEPARATOR_CELL_RE.fullmatch(cell.replace(" ", ""))
            for cell in cells
        )
    )


def _list_spans(text: str) -> list[tuple[int, int]]:
    """Return paragraph-like blocks whose first structural item is a list."""
    fences = _fenced_code_spans(text)
    spans: list[tuple[int, int]] = []
    block_start = 0
    separators = list(re.finditer(r"\n[ \t]*\n+", text))
    for separator in [*separators, None]:
        block_end = separator.start() if separator else len(text)
        items = [
            match
            for match in LIST_ITEM_RE.finditer(text, block_start, block_end)
            if not _inside_spans(match.start(), fences)
        ]
        if items:
            spans.append((items[0].start(), block_end))
        if separator is None:
            break
        block_start = separator.end()
    return spans


def _list_items(text: str, start: int, end: int) -> list[tuple[int, int]]:
    return [
        (match.start(), len(match.group("indent").expandtabs(4)))
        for match in LIST_ITEM_RE.finditer(text, start, end)
    ]


def _list_block_starting_at(
    text: str, spans: list[tuple[int, int]], cursor: int
) -> tuple[int, int] | None:
    if not LIST_ITEM_RE.match(text, cursor):
        return None
    return next(
        (span for span in spans if span[0] <= cursor < span[1]),
        None,
    )


def _flat_list_section_after_heading(
    text: str,
    cursor: int,
    *,
    headings: list[tuple[int, int]],
    list_spans: list[tuple[int, int]],
) -> tuple[int, int, int] | None:
    """Return a section made only of one heading and one flat list."""
    current_heading = next(
        (heading for heading in headings if heading[0] == cursor),
        None,
    )
    if current_heading is None:
        return None

    next_heading = next(
        (position for position, _ in headings if position > cursor),
        len(text),
    )
    heading_line_end = text.find("\n", cursor, next_heading)
    if heading_line_end < 0:
        return None

    list_block = next(
        (
            span
            for span in list_spans
            if heading_line_end <= span[0] < span[1] <= next_heading
        ),
        None,
    )
    if list_block is None:
        return None

    list_start, list_end = list_block
    if text[heading_line_end:list_start].strip():
        return None
    if text[list_end:next_heading].strip():
        return None

    items = _list_items(text, list_start, list_end)
    if not items or len({indent for _, indent in items}) != 1:
        return None
    return list_start, list_end, next_heading


def _flat_list_section_after_paragraph(
    text: str,
    cursor: int,
    *,
    list_spans: list[tuple[int, int]],
) -> tuple[int, int] | None:
    """Return one lead-in paragraph followed immediately by one flat list."""
    list_block = next(
        (span for span in list_spans if span[0] > cursor),
        None,
    )
    if list_block is None:
        return None

    list_start, list_end = list_block
    lead_in = text[cursor:list_start].rstrip()
    if not lead_in or re.search(r"\n[ \t]*\n", lead_in):
        return None
    if HEADING_RE.match(lead_in):
        return None

    items = _list_items(text, list_start, list_end)
    if not items or len({indent for _, indent in items}) != 1:
        return None
    return list_start, list_end


def _paragraph_before_list(text: str, start: int, list_start: int) -> int | None:
    """Find the paragraph immediately before a list being moved forward."""
    paragraph_starts = _paragraph_starts(text, start, list_start)
    if not paragraph_starts:
        return None

    paragraph_start = paragraph_starts[-1]
    if paragraph_start >= list_start:
        return None
    return paragraph_start if text[paragraph_start:list_start].strip() else None


def _trailing_heading_start(
    text: str,
    start: int,
    end: int,
    headings: list[tuple[int, int]],
) -> int | None:
    """Move a heading that is the candidate's final nonblank line forward."""
    trailing = [position for position, _ in headings if start < position < end]
    if not trailing:
        return None

    position = trailing[-1]
    line_end = text.find("\n", position, end)
    if line_end < 0:
        line_end = end
    return position if not text[line_end:end].strip() else None


def _heading_group_start_before_table(
    text: str,
    headings: list[int],
    table_start: int,
) -> int:
    """Return the first consecutive heading immediately before a table."""
    group_start = headings[-1]
    following_start = table_start

    for position in reversed(headings):
        line_end = text.find("\n", position, following_start)
        if line_end < 0:
            line_end = following_start
        if text[line_end:following_start].strip():
            break
        group_start = position
        following_start = position

    return group_start


def _table_section_after_heading(
    text: str,
    cursor: int,
    *,
    headings: list[tuple[int, int]],
    table_spans: list[tuple[int, int]],
) -> tuple[int, int] | None:
    """Return a heading group followed only by whitespace and a table."""
    if not any(position == cursor for position, _ in headings):
        return None

    table = next((span for span in table_spans if span[0] > cursor), None)
    if table is None:
        return None

    prefix = text[cursor : table[0]]
    if not all(not line.strip() or HEADING_RE.match(line) for line in prefix.splitlines()):
        return None
    return table


def _contains_only_headings(text: str, start: int, end: int) -> bool:
    """Return whether a nonempty candidate has headings but no body content."""
    lines = text[start:end].splitlines()
    has_heading = any(HEADING_RE.match(line) for line in lines)
    return has_heading and all(
        not line.strip() or HEADING_RE.match(line) for line in lines
    )


def _cut_with_heading_content(text: str, start: int, limit: int) -> int:
    """Cut only after including content that follows an initial heading group."""
    body_start: int | None = None
    position = start
    for line in text[start:].splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not HEADING_RE.match(line.rstrip("\r\n")):
            body_start = position
            break
        position += len(line)

    if body_start is None:
        return min(limit, len(text))
    if body_start >= limit:
        return min(max(limit, body_start + 1), len(text))

    newline = text.rfind("\n", body_start + 1, limit + 1)
    if newline > body_start:
        return newline
    space = max(
        text.rfind(" ", body_start + 1, limit + 1),
        text.rfind("\t", body_start + 1, limit + 1),
    )
    return space if space > body_start else limit


def _paragraph_starts(text: str, start: int, limit: int) -> list[int]:
    starts = [start]
    starts.extend(
        match.end()
        for match in re.compile(r"\n[ \t]*\n+").finditer(text, start, limit)
        if match.end() < limit
    )
    return starts


def _span_starting_at(
    spans: list[tuple[int, int]], cursor: int
) -> tuple[int, int] | None:
    return next((span for span in spans if span[0] == cursor), None)


def _skip_blank_lines(text: str, cursor: int) -> int:
    match = re.match(r"(?:[ \t]*\r?\n)+", text[cursor:])
    return cursor + match.end() if match else cursor


def _hard_cut(text: str, start: int, limit: int) -> int:
    newline = text.rfind("\n", start + 1, limit + 1)
    first_newline = text.find("\n", start, limit + 1)
    if HEADING_RE.match(text[start:]) and newline == first_newline:
        newline = -1
    if newline > start:
        return newline
    space = max(
        text.rfind(" ", start + 1, limit + 1),
        text.rfind("\t", start + 1, limit + 1),
    )
    return space if space > start else limit


def _append_chunk(chunks: list[str], value: str) -> None:
    cleaned = value.strip("\r\n")
    if cleaned.strip():
        chunks.append(cleaned)


def _append_limited(chunks: list[str], value: str) -> None:
    """Append one pointer, hard-splitting only an individually oversized one."""
    value = value.strip("\r\n")
    while len(value) > CHUNK_SIZE:
        cut = _hard_cut(value, 0, CHUNK_SIZE)
        _append_chunk(chunks, value[:cut])
        value = value[cut:].strip("\r\n")
    _append_chunk(chunks, value)


def main() -> None:
    setup_logging()

    file_paths = discover_files()
    if not file_paths:
        logger.warning("No Markdown files found in %s", MARKER_RESULTS_DIR)
        return

    chunks = split_documents(load_documents(file_paths))
    run_path = write_chunk_run(chunks)
    logger.info("Wrote %d chunks to %s", len(chunks), run_path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()

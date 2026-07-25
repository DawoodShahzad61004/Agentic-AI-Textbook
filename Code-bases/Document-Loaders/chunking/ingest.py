"""Split Marker-generated Markdown files into text chunks."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
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
HTML_TAG_RE = re.compile(r"<[^>]*>")
LIST_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:[-*+]|\d+[.)])[ \t]+\S", re.MULTILINE
)
TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")

# --- preprocessing() support -------------------------------------------------
#
# Marker-clause normalization for source documents (e.g. Marker-converted
# legal/tender PDFs) that fragment numbered clauses across stray blank lines
# and mix "3.1 text" / "- 3.1 text" / "3.1 **Label** text" styles for what is
# structurally the same numbered sequence. This is a best-effort heuristic,
# not a full Markdown parser: it operates on blank-line-delimited blocks and
# only acts on sequences of 2+ consecutive markers of the same family.

ROMAN_VALUES = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}

BLOCK_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
MARKER_BLOCK_RE = re.compile(
    r"^(?P<prefix>#{1,6}[ \t]+|[-*+][ \t]+)?"
    r"(?P<marker>\d+(?:\.\d+)+|\([a-hj-uwyz]\)|\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\))"
    r"(?P<gap>[ \t]+)"
)
BOLD_LABEL_RE = re.compile(r"^\*\*(?P<label>[^*\n]+?)\*\*")
ITALIC_SUBLABEL_RE = re.compile(r"\*(?P<label>[^*\n]+?)(?:\*:|:\*)\s*")
LIST_BLOCK_LEAD_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
TABLE_ROW_LEAD_RE = re.compile(r"^\s*\|.*\|\s*$")
SPAN_TAG_RE = re.compile(r'<span id="[^"]*"></span>')
LEADING_SPAN_RE = re.compile(
    r'^(?P<prefix>#{1,6}[ \t]+|[-*+][ \t]+)?(?P<spans>(?:<span id="[^"]*"></span>)+)(?P<rest>.*)$',
    re.MULTILINE,
)


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


def preprocessing(text: str) -> str:
    """Normalize fragmented numbered-clause sequences before splitting.

    Best-effort heuristic for source documents (Marker-converted legal /
    tender PDFs) that render one logical numbered clause as an inconsistent
    mix of "3.1 text", "- 3.1 text", or "3.1 **Label** text", with the
    clause's own body wrapped across stray blank lines. See the docstrings
    on the helper functions below for the two supported transforms.
    """
    text = _normalize_marker_sequences(text)
    text = _promote_italic_sublabels(text)
    text = _extract_leading_spans(text)
    return text


def _marker_family_value(marker: str) -> tuple[str, int]:
    """Classify a marker into a family key and its position within it."""
    if marker[0] == "(":
        inner = marker[1:-1]
        if inner in ROMAN_VALUES:
            return "roman", ROMAN_VALUES[inner]
        return "alpha", ord(inner) - ord("a") + 1
    base, _, last = marker.rpartition(".")
    return f"num:{base}", int(last)


def _classify_block(block_text: str) -> dict:
    """Identify the structural role of one blank-line-delimited block."""
    first_line_end = block_text.find("\n")
    first_line = block_text if first_line_end < 0 else block_text[:first_line_end]

    match = MARKER_BLOCK_RE.match(block_text)
    if match:
        prefix = match.group("prefix")
        rest = block_text[match.end():]
        bold = BOLD_LABEL_RE.match(rest)
        return {
            "kind": "marker",
            "prefix": prefix,
            "marker": match.group("marker"),
            "is_heading_prefix": bool(prefix and prefix.lstrip().startswith("#")),
            "bold_label": bold.group("label") if bold else None,
            "after_marker_offset": match.end(),
            "after_label_offset": match.end() + bold.end() if bold else None,
        }
    if HEADING_RE.match(first_line):
        return {"kind": "heading"}
    if LIST_BLOCK_LEAD_RE.match(first_line):
        return {"kind": "list"}
    if TABLE_ROW_LEAD_RE.match(first_line):
        return {"kind": "table"}
    if ITALIC_SUBLABEL_RE.fullmatch(first_line.strip()):
        return {"kind": "italic_label"}
    return {"kind": "paragraph"}


def _split_blocks(text: str) -> list[dict]:
    """Split text on blank lines into classified blocks with their offsets."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in BLOCK_SPLIT_RE.finditer(text):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))

    blocks = []
    for start, end in spans:
        block_text = text[start:end]
        info = _classify_block(block_text)
        info.update(start=start, end=end, text=block_text)
        blocks.append(info)
    return blocks


def _marker_sequences(blocks: list[dict]) -> list[list[int]]:
    """Group block indices into runs of consecutive same-family markers.

    Numeric markers (``3.1``, ``5.1``, ...) are naturally scoped by their
    leading digits, so two unrelated numeric families never collide. Alpha
    (``(a)``) and roman (``(i)``) markers have no such natural scope and are
    reused constantly for unrelated enumerations throughout a document, so a
    heading or a numeric marker — both reliable signs of a new clause —
    flushes any in-progress alpha/roman run rather than letting it silently
    chain across unrelated sections.
    """
    sequences: list[list[int]] = []
    active: dict[str, list[int]] = {}

    def flush_unscoped() -> None:
        for key in ("alpha", "roman"):
            running = active.pop(key, None)
            if running is not None and len(running) >= 2:
                sequences.append(running)

    for idx, info in enumerate(blocks):
        if info["kind"] == "heading":
            flush_unscoped()
            continue
        if info["kind"] != "marker":
            continue
        family, value = _marker_family_value(info["marker"])
        info["family"], info["value"] = family, value

        if family.startswith("num:"):
            flush_unscoped()

        running = active.get(family)
        if running is not None and blocks[running[-1]]["value"] == value - 1:
            running.append(idx)
        else:
            if running is not None and len(running) >= 2:
                sequences.append(running)
            active[family] = [idx]

    for running in active.values():
        if len(running) >= 2:
            sequences.append(running)
    return sequences


SENTENCE_END_RE = re.compile(r"[.!?][\"'”)\]]*\s*$")


def _ends_sentence(text: str) -> bool:
    """Whether ``text`` looks like it ends a sentence rather than being cut mid-clause."""
    return bool(SENTENCE_END_RE.search(text))


def _merge_forward(
    blocks: list[dict], n: int, i: int, stop: int | None, lead_text: str
) -> tuple[list[str], int]:
    """Collect immediately-following plain-paragraph blocks for one marker.

    A marker's body absorbs an immediately-following plain-paragraph block
    (rejoining text that source pagination split across blank lines) only
    while the text accumulated so far does not already look like a complete
    sentence — this is what stops the merge from running past a genuine
    paragraph break into unrelated following content. It still stops at the
    next marker in the sequence (``stop``), a structurally different block
    (list/heading/table/italic label), or the end of the document, whichever
    comes first. Returns the merged fragments and the index of the last
    block consumed (``i`` itself if none were absorbed).
    """
    fragments: list[str] = []
    tail = lead_text
    j = i + 1
    while (
        j < n
        and (stop is None or blocks[j]["start"] < stop)
        and blocks[j]["kind"] == "paragraph"
        and not _ends_sentence(tail)
    ):
        tail = blocks[j]["text"]
        fragments.append(tail)
        j += 1
    consumed_until = j - 1 if j > i else i
    return fragments, consumed_until


def _apply_plain_branch(
    text: str, blocks: list[dict], seq: list[int]
) -> tuple[int, int, str] | None:
    """Give every marker in the sequence the same leading list-syntax char.

    Also merges each marker's immediately-following paragraph fragments back
    into it (see ``_merge_forward``) — the same page-break defragmentation
    the heading branch performs, just without a heading promotion.
    """
    prefixes = [blocks[i]["prefix"] for i in seq if blocks[i]["prefix"]]
    target_prefix = prefixes[0] if prefixes else "- "
    n = len(blocks)

    start = blocks[seq[0]]["start"]
    pieces: list[str] = []
    cursor = start
    changed = False
    for pos, i in enumerate(seq):
        b = blocks[i]
        if cursor < b["start"]:
            pieces.append(text[cursor:b["start"]])

        marker_text = (target_prefix + b["text"]) if b["prefix"] is None else b["text"]
        changed = changed or b["prefix"] is None

        stop = blocks[seq[pos + 1]]["start"] if pos + 1 < len(seq) else None
        fragments, consumed_until = _merge_forward(blocks, n, i, stop, b["text"])
        if fragments:
            changed = True
            extra = " ".join(
                re.sub(r"\s+", " ", fragment).strip()
                for fragment in fragments
                if fragment.strip()
            )
            marker_text = marker_text.rstrip() + (f" {extra}" if extra else "")

        pieces.append(marker_text)
        cursor = blocks[consumed_until]["end"]

    if not changed:
        return None
    return start, cursor, "".join(pieces)


def _enclosing_heading_level(headings: list[tuple[int, int]], position: int) -> int | None:
    """ATX level of the nearest heading preceding ``position``."""
    preceding = [level for start, level in headings if start < position]
    return preceding[-1] if preceding else None


def _apply_heading_branch(
    text: str,
    blocks: list[dict],
    seq: list[int],
    *,
    bold: bool,
    headings: list[tuple[int, int]],
) -> tuple[int, int, str]:
    """Promote every marker in the sequence to a heading, merging its body.

    Content between two markers that no body absorbs (e.g. a sub-list under
    one clause) is copied through verbatim rather than dropped.

    The promoted level may never be *shallower* than the section heading the
    clauses live under, or the sequence reads as a sibling of its own parent
    and every consumer that groups by ATX level nests the document wrongly.
    Marker emits exactly that inversion — a "#### 5. INSTRUCTIONS TO BIDDERS"
    section whose clauses it already wrote as "### 5.6" — so a heading prefix
    found in the sequence is a floor, not the answer. Level-with-the-parent
    rather than one below it is what `dataset/expected-output.md` specifies;
    it is enough to make the section tree well-formed, because a section
    heading left owning nothing still travels with the clause that follows it.
    """
    level = 5
    for i in seq:
        if blocks[i]["is_heading_prefix"]:
            level = len(blocks[i]["prefix"].strip())
            break
    enclosing = _enclosing_heading_level(headings, blocks[seq[0]]["start"])
    if enclosing is not None:
        level = max(level, enclosing)
    hashes = "#" * min(level, 6)
    n = len(blocks)

    start = blocks[seq[0]]["start"]
    pieces: list[str] = []
    cursor = start
    for pos, i in enumerate(seq):
        b = blocks[i]
        if cursor < b["start"]:
            pieces.append(text[cursor:b["start"]])

        label = b["bold_label"] if bold else None
        if bold and label is not None:
            heading_line = f"{hashes} {b['marker']} **{label}**"
            body_offset = b["after_label_offset"]
        else:
            heading_line = f"{hashes} {b['marker']}"
            body_offset = b["after_marker_offset"]

        # Keep whatever whitespace originally separated the label from its
        # body text attached to the heading line, rather than the synthetic
        # blank line we insert below when there is a body to show.
        raw_tail = b["text"][body_offset:]
        trailing_ws = raw_tail[: len(raw_tail) - len(raw_tail.lstrip(" \t"))]
        heading_line += trailing_ws

        lead_text = raw_tail.lstrip(" \t")
        stop = blocks[seq[pos + 1]]["start"] if pos + 1 < len(seq) else None
        fragments, consumed_until = _merge_forward(blocks, n, i, stop, lead_text)
        fragments.insert(0, lead_text)

        body = " ".join(
            re.sub(r"\s+", " ", fragment).strip()
            for fragment in fragments
            if fragment.strip()
        )
        pieces.append(heading_line if not body else f"{heading_line}\n\n{body}")
        cursor = blocks[consumed_until]["end"]

    return start, cursor, "".join(pieces)


def _normalize_marker_sequences(text: str) -> str:
    """Apply rule 1: normalize numbered-clause sequences (see preprocessing)."""
    blocks = _split_blocks(text)
    sequences = _marker_sequences(blocks)
    headings = _heading_matches(text)

    edits: list[tuple[int, int, str]] = []
    for seq in sequences:
        has_bold = any(blocks[i]["bold_label"] for i in seq)
        has_heading_prefix = any(blocks[i]["is_heading_prefix"] for i in seq)
        if has_bold or has_heading_prefix:
            edits.append(
                _apply_heading_branch(
                    text, blocks, seq, bold=has_bold, headings=headings
                )
            )
        else:
            edit = _apply_plain_branch(text, blocks, seq)
            if edit is not None:
                edits.append(edit)

    if not edits:
        return text

    # A short marker sequence nested entirely inside a larger one (e.g. a
    # roman-numeral sub-list inside one clause of a heading-branch run
    # spanning many clauses) produces an edit whose span sits inside the
    # outer edit's span. Applying both would double-process that stretch of
    # text and scramble the output, so keep only the outermost edit for any
    # overlapping span — the inner content still passes through unchanged
    # as part of the outer edit's verbatim gap-copying.
    edits.sort(key=lambda edit: (edit[0], -edit[1]))
    non_overlapping: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, replacement in edits:
        if start < last_end:
            continue
        non_overlapping.append((start, end, replacement))
        last_end = end
    edits = non_overlapping

    pieces = []
    cursor = 0
    for start, end, replacement in edits:
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _promote_italic_sublabels(text: str) -> str:
    """Apply rule 2: promote "*Label*:" lines under a heading to a subheading."""
    lines = text.split("\n")
    last_level: int | None = None
    out_lines = []
    for line in lines:
        heading_match = HEADING_RE.match(line)
        if heading_match:
            last_level = len(heading_match.group(1))
            out_lines.append(line)
            continue

        match = ITALIC_SUBLABEL_RE.fullmatch(line.strip())
        if match is not None and last_level is not None:
            label = match.group("label").strip().rstrip(":").strip()
            level = min(last_level + 1, 6)
            out_lines.append(f"{'#' * level} {label}:")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _extract_leading_spans(text: str) -> str:
    """Apply rule 3: pull `<span id="...">` anchors onto their own line(s).

    Marker's PDF-to-Markdown conversion glues internal cross-reference
    anchors to the front of whatever line they annotate (a heading, a list
    item, or a plain paragraph), e.g. `#### <span id="x"></span>**Title**`.
    Left in place they break heading/list detection for that line; moved
    onto their own preceding line(s) they stay inert, cross-reference links
    elsewhere in the document keep resolving, and the annotated line reads
    normally again.
    """

    def replace(match: re.Match) -> str:
        prefix = match.group("prefix") or ""
        span_lines = "\n".join(SPAN_TAG_RE.findall(match.group("spans")))
        rest = match.group("rest")
        if prefix:
            return f"{span_lines}\n{prefix}{rest}"
        if rest.strip():
            return f"{span_lines}\n\n{rest}"
        return span_lines

    return LEADING_SPAN_RE.sub(replace, text)


def split_documents(documents: list[Document]) -> list[Document]:
    """Split documents and assign a zero-based chunk sequence per source file."""
    chunks: list[Document] = []
    for document in documents:
        for text in temp_split(preprocessing(document.page_content)):
            if len(text) >= MIN_CHUNK_CHARS:
                chunks.append(Document(page_content=text, metadata=document.metadata.copy()))

    sequence_by_source: dict[str, int] = defaultdict(int)
    for chunk in chunks:
        source = str(chunk.metadata.get("source", "unknown"))
        chunk.metadata["chunk_seq"] = sequence_by_source[source]
        sequence_by_source[source] += 1

    logger.info("Split %d documents into %d chunks", len(documents), len(chunks))
    return chunks


@dataclass
class _Node:
    """One structural unit of the document: a section, table, list or paragraph.

    ``start``/``end`` are character offsets into the whole document. A node's
    span always covers every heading line enclosing it that no earlier sibling
    already carries, so emitting ``text[node.start:node.end]`` never loses a
    heading. ``content_start`` records where the unit's own content began
    before any such heading was attached, which is what a table needs in order
    to tell its headings apart from its first row.
    """

    start: int
    end: int
    kind: str
    children: list["_Node"]
    content_start: int | None = None


def temp_split(text: str) -> list[str]:
    """Split Markdown into chunks that are as full as ``CHUNK_SIZE`` allows.

    The document is parsed into a tree of structural units — sections nested
    by ATX heading level, and within each section the tables, lists and
    paragraphs of its own body — and those units are then packed greedily:
    a chunk takes whole sibling units until the next one would not fit, and
    that next unit moves to the following chunk intact. A unit is only ever
    opened up when it does not fit in an empty chunk by itself, and then only
    one level at a time, so a heading is never separated from its content and
    a section is never torn in half while a coarser boundary was available.

    ``CHUNK_SIZE`` bounds every chunk, tables included. A table that does not
    fit is re-serialized into several chunks, each repeating the headers that
    apply to the cells it carries, so that a piece still reads as a table
    rather than as loose rows — see `_split_table`.
    """
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    _pack(text, _build_tree(text), chunks)
    return chunks


def _build_tree(text: str) -> list[_Node]:
    """Parse the whole document into top-level structural units."""
    return _sections(
        text,
        0,
        len(text),
        headings=_heading_matches(text),
        table_spans=_table_spans(text),
        list_spans=_list_spans(text),
    )


def _sections(
    text: str,
    start: int,
    end: int,
    *,
    headings: list[tuple[int, int]],
    table_spans: list[tuple[int, int]],
    list_spans: list[tuple[int, int]],
) -> list[_Node]:
    """Group ``[start, end)`` into sections at its shallowest heading level.

    Levels are read from the document as written rather than assumed to be
    well-formed: the shallowest level *present in this range* opens the
    sections, so a document that starts at ``###`` or skips a level still
    nests sensibly.
    """
    inner = [(position, level) for position, level in headings if start <= position < end]
    if not inner:
        return _content_units(text, start, end, table_spans, list_spans)

    top_level = min(level for _, level in inner)
    starts = [position for position, level in inner if level == top_level]

    nodes: list[_Node] = []
    if starts[0] > start:
        nodes.extend(_content_units(text, start, starts[0], table_spans, list_spans))
    for index, position in enumerate(starts):
        section_end = starts[index + 1] if index + 1 < len(starts) else end
        nodes.append(
            _section_node(
                text,
                position,
                section_end,
                headings=headings,
                table_spans=table_spans,
                list_spans=list_spans,
            )
        )
    return nodes


def _section_node(
    text: str,
    start: int,
    end: int,
    *,
    headings: list[tuple[int, int]],
    table_spans: list[tuple[int, int]],
    list_spans: list[tuple[int, int]],
) -> _Node:
    """Build one section: its heading line plus everything it owns."""
    line_end = text.find("\n", start, end)
    body_start = end if line_end < 0 else line_end + 1

    children = _sections(
        text,
        body_start,
        end,
        headings=headings,
        table_spans=table_spans,
        list_spans=list_spans,
    )
    if children:
        _extend_start(children[0], start)
    return _Node(start, end, "section", children)


def _extend_start(node: _Node, start: int) -> None:
    """Attach a heading line to the first unit that follows it, recursively.

    The heading has to travel with whichever chunk its content lands in, at
    every depth — otherwise splitting a section strands its heading and
    splitting that section's first subsection strands the heading again.
    """
    node.start = start
    if node.children:
        _extend_start(node.children[0], start)


def _content_units(
    text: str,
    start: int,
    end: int,
    table_spans: list[tuple[int, int]],
    list_spans: list[tuple[int, int]],
) -> list[_Node]:
    """Split a heading-free region into blocks, keeping tables and lists whole."""
    units: list[_Node] = []
    cursor = _skip_blank_lines(text, start)

    while cursor < end:
        separator = BLOCK_SPLIT_RE.search(text, cursor, end)
        block_end = separator.start() if separator else end
        if block_end <= cursor:
            break

        table = next((span for span in table_spans if cursor <= span[0] < block_end), None)
        listing = next((span for span in list_spans if cursor <= span[0] < block_end), None)
        if table is not None and listing is not None:
            kind, span = (
                ("table", table) if table[0] <= listing[0] else ("list", listing)
            )
        elif table is not None:
            kind, span = "table", table
        elif listing is not None:
            kind, span = "list", listing
        else:
            units.append(_Node(cursor, block_end, "paragraph", []))
            cursor = _skip_blank_lines(text, block_end)
            continue

        if span[0] > cursor:
            units.append(_Node(cursor, span[0], "paragraph", []))
        unit_end = min(span[1], block_end)
        if unit_end <= span[0]:
            unit_end = block_end
        units.append(_Node(span[0], unit_end, kind, [], content_start=span[0]))
        cursor = _skip_blank_lines(text, unit_end)

    return _group_list_lead_ins(units)


def _group_list_lead_ins(units: list[_Node]) -> list[_Node]:
    """Absorb a list's lead-in paragraph ("To be submitted ... with:") into it."""
    grouped: list[_Node] = []
    for unit in units:
        if unit.kind == "list" and grouped and grouped[-1].kind == "paragraph":
            lead_in = grouped.pop()
            grouped.append(_Node(lead_in.start, unit.end, "list", []))
        else:
            grouped.append(unit)
    return grouped


def _pack(
    text: str, nodes: list[_Node], chunks: list[str], *, tail_open: bool = False
) -> int | None:
    """Emit chunks for ``nodes``, filling each one as far as ``CHUNK_SIZE`` allows.

    ``tail_open`` says whether the caller still has text after these nodes. If
    it does, and packing ends on a heading run with nothing under it, that run
    is returned rather than emitted so the caller can put it in front of what
    it introduces. Returns ``None`` whenever there is nothing to hand back.
    """
    buffer_start: int | None = None
    buffer_end = 0

    for index, node in enumerate(nodes):
        more_follows = tail_open or index + 1 < len(nodes)
        start = node.start
        if buffer_start is not None:
            if _fits(text, buffer_start, node.end):
                buffer_end = node.end
                continue
            # The pending chunk is closed here — unless it should instead be
            # handed to this node as a lead-in. Two reasons to hand it over: a
            # buffer holding nothing but heading lines would otherwise be
            # published as a body-less chunk, and a buffer well short of
            # ``CHUNK_SIZE`` sitting in front of a node that is about to be
            # opened up anyway can keep filling from that node's first piece
            # rather than closing early.
            carry = _contains_only_headings(text, buffer_start, buffer_end)
            if not carry and not _fits(text, node.start, node.end):
                carry = _lead_in_fits(text, node, buffer_start)
            if carry:
                start = buffer_start
            else:
                # A chunk must not end on a heading while text it introduces
                # is still to come: a trailing heading describes what follows
                # it, so publishing it here labels the wrong content and
                # leaves the real content unlabelled. Hand the trailing run
                # forward and close the chunk on the last body line instead.
                trailing = _trailing_heading_start(text, buffer_start, buffer_end)
                _append_chunk(chunks, text[buffer_start : trailing or buffer_end])
                if trailing is not None:
                    start = trailing
            buffer_start = None

        if _fits(text, start, node.end):
            buffer_start, buffer_end = start, node.end
        else:
            leftover = _split_node(
                text, node, start, chunks, tail_open=more_follows
            )
            if leftover is not None:
                # Headings this node ended on: hold them as the pending chunk
                # so the next node picks them up the same way it would any
                # heading-only buffer.
                buffer_start, buffer_end = leftover, node.end

    if buffer_start is None:
        return None

    if tail_open:
        if _contains_only_headings(text, buffer_start, buffer_end):
            return buffer_start
        trailing = _trailing_heading_start(text, buffer_start, buffer_end)
        if trailing is not None:
            _append_chunk(chunks, text[buffer_start:trailing])
            return trailing

    _append_chunk(chunks, text[buffer_start:buffer_end])
    return None


def _open_node(text: str, node: _Node, start: int) -> list[_Node] | None:
    """Return the sub-units a too-large node splits into, or ``None`` if atomic.

    ``start`` may sit before ``node.start`` when the caller handed over a
    lead-in; the sub-unit that opens the node takes it over, so no text is
    lost and no heading is stranded.
    """
    if node.kind == "table":
        # A table has no sub-units expressible as source spans: every piece
        # has to be re-serialized with its own copy of the headers, so
        # `_split_table` emits it directly instead.
        return None

    if node.kind == "list":
        # Split on top-level pointers only, so a nested sub-item never gets
        # separated from its parent pointer. Anything the span picked up
        # ahead of the first pointer — a heading, a lead-in paragraph — rides
        # along with it.
        if not _list_items(text, start, node.end):
            return None
        boundaries = _top_level_item_boundaries(text, start, node.end)
        items = [
            _Node(item_start, item_end, "list-item", [])
            for item_start, item_end in zip(boundaries, boundaries[1:])
        ]
        return items if len(items) > 1 else None

    if not node.children:
        return None

    children = list(node.children)
    if start < children[0].start:
        children[0] = replace(children[0], start=start)
    return children


def _split_node(
    text: str,
    node: _Node,
    start: int,
    chunks: list[str],
    *,
    tail_open: bool = False,
) -> int | None:
    """Emit chunks for one unit that cannot fit in a chunk of its own.

    Returns any trailing heading run the caller should carry forward; see
    `_pack`. Tables and leaves never end on a heading, so only the recursive
    case can hand anything back.
    """
    children = _open_node(text, node, start)
    if children is not None:
        return _pack(text, children, chunks, tail_open=tail_open)
    if node.kind == "table":
        _split_table(text, node, start, chunks)
    else:
        _append_limited(chunks, text[start:node.end])
    return None


def _lead_in_fits(text: str, node: _Node, lead_start: int) -> bool:
    """Whether ``lead_start`` can be handed to the first piece ``node`` splits into."""
    children = _open_node(text, node, lead_start)
    return children is not None and _fits(text, lead_start, children[0].end)


def _fits(text: str, start: int, end: int) -> bool:
    """Whether ``text[start:end]`` fits a chunk once trimmed as one would be."""
    return len(text[start:end].strip()) <= CHUNK_SIZE


# --- table splitting ---------------------------------------------------------
#
# A table too large for one chunk is re-serialized rather than sliced out of the
# source, because each piece has to carry its own copy of the headers. Cell
# padding and the alignment row are normalized on the way out: neither is
# semantic in Markdown, Marker pads columns to the width of the widest cell
# (alignment rows of 800+ characters occur in this corpus), and the size limit
# is defined on the emitted chunk rather than on the source it came from.
#
# The only content this can lose is at a boundary chosen *inside* a cell, which
# happens solely when one cell plus its headers exceeds CHUNK_SIZE on its own.


ALIGNMENT_CELL_RE = re.compile(r"^(?P<left>:?)-+(?P<right>:?)$")
CELL_PARAGRAPH_RE = re.compile(r"(?:<br\s*/?>[ \t]*){2,}|\n[ \t]*\n[ \t\n]*")
CELL_LIST_ITEM_RE = re.compile(r"(?:<br\s*/?>|\n)(?=[ \t]*(?:[-*+•➢]|\d+[.)])[ \t])")
CELL_SENTENCE_RE = re.compile(r"(?<=[.!?])(?:[ \t]|<br\s*/?>|\n)+")
CELL_WORD_RE = re.compile(r"(?:[ \t]|<br\s*/?>|\n)+")


@dataclass
class _Table:
    """A parsed pipe table: its header stack, alignment row, and data rows."""

    header_rows: list[list[str]]
    alignment: list[str]
    body_rows: list[list[str]]
    width: int


def _parse_table(block: str) -> _Table | None:
    """Parse one pipe table. Rows after the first alignment row are all data."""
    lines = [line for line in block.splitlines() if line.strip()]
    rows = [(line, _table_cells(line)) for line in lines]
    if any(cells is None for _, cells in rows):
        return None

    alignment_index = next(
        (index for index, (line, _) in enumerate(rows) if _is_table_separator(line)),
        None,
    )
    if alignment_index is None:
        return None

    header_rows = [cells for _, cells in rows[:alignment_index]]
    alignment = rows[alignment_index][1]
    # Any further alignment row is a converter artefact rather than a second
    # header stack — keep it as data so nothing is silently dropped.
    body_rows = [cells for _, cells in rows[alignment_index + 1 :]]

    width = max((len(cells) for cells in [*header_rows, alignment, *body_rows]), default=0)
    if width == 0:
        return None
    return _Table(header_rows, alignment, body_rows, width)


def _cell(row: list[str], column: int) -> str:
    """Read one cell, tolerating the ragged rows Marker's OCR produces."""
    return row[column] if column < len(row) else ""


def _render_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _alignment_cell(spec: str) -> str:
    match = ALIGNMENT_CELL_RE.fullmatch(spec.replace(" ", ""))
    if match is None:
        return "---"
    return f"{match.group('left')}---{match.group('right')}"


def _row_line(row: list[str], columns: list[int]) -> str:
    return _render_row([_cell(row, column) for column in columns])


def _render_table(
    prefix: str, table: _Table, rows: list[list[str]], columns: list[int]
) -> str:
    """Serialize a header stack plus ``rows``, restricted to ``columns``."""
    lines = [_row_line(header, columns) for header in table.header_rows]
    lines.append(
        _render_row([_alignment_cell(_cell(table.alignment, c)) for c in columns])
    )
    lines.extend(_row_line(row, columns) for row in rows)
    body = "\n".join(lines)
    return f"{prefix}\n\n{body}" if prefix else body


def _has_column_headers(table: _Table) -> bool:
    """Whether the row above the alignment row carries any label."""
    return any(cell.strip() for header in table.header_rows for cell in header)


def _has_row_headers(table: _Table) -> bool:
    """Whether the first column labels its rows, rather than holding data.

    Markdown has no row-header syntax, so this is a heuristic: the column has
    to be populated on nearly every row and be substantially shorter than the
    data beside it. It only decides two things — whether an unheaded table is
    split by column instead of by row, and whether a label is repeated onto
    the pieces of an oversized row — so a wrong guess degrades a chunk rather
    than corrupting one.
    """
    if table.width < 2 or not table.body_rows:
        return False

    labels = [_cell(row, 0).strip() for row in table.body_rows]
    if sum(1 for label in labels if label) < 0.6 * len(labels):
        return False

    label_size = sum(len(label) for label in labels)
    data_size = sum(
        len(_cell(row, column))
        for row in table.body_rows
        for column in range(1, table.width)
    )
    return data_size > 0 and label_size * 2 <= data_size


def _split_table(text: str, node: _Node, start: int, chunks: list[str]) -> None:
    """Emit one table as chunks, repeating its headers onto every piece.

    ``start`` may sit before the table so that the headings introducing it
    ride along; those repeat on every piece too, since each piece is meant to
    stand on its own as a retrieval unit.
    """
    table_start = node.content_start if node.content_start is not None else node.start
    prefix = text[start:table_start].strip()
    table = _parse_table(text[table_start : node.end])
    if table is None:
        _append_limited(chunks, text[start : node.end])
        return

    # Rule 1: normalizing the padding away can bring a table that overran the
    # limit in its source form back under it, and then it stays one chunk.
    whole = _render_table(prefix, table, table.body_rows, list(range(table.width)))
    if len(whole) <= CHUNK_SIZE:
        _append_chunk(chunks, whole)
        return

    if not table.body_rows:
        _split_across_columns(prefix, table, [], [], chunks)
    elif _has_row_headers(table) and not _has_column_headers(table):
        # Rule 4: row headers only — the table reads across, so split by column
        # and repeat the row labels.
        _split_by_columns(prefix, table, chunks)
    else:
        # Rules 3, 5 and 6: with column headers, with both, or with neither,
        # the split is by row.
        _split_by_rows(prefix, table, chunks)


def _split_by_rows(prefix: str, table: _Table, chunks: list[str]) -> None:
    """Rules 3, 5, 6 — repeat the column headers, then fill with whole rows."""
    columns = list(range(table.width))
    label_columns = [0] if _has_row_headers(table) else []
    base = len(_render_table(prefix, table, [], columns))

    group: list[list[str]] = []
    size = base
    for row in table.body_rows:
        cost = 1 + len(_row_line(row, columns))
        if group and size + cost > CHUNK_SIZE:
            _append_chunk(chunks, _render_table(prefix, table, group, columns))
            group, size = [], base
        if not group and base + cost > CHUNK_SIZE:
            # Rule 7: this row does not fit even alone, so break it up by
            # column instead of emitting it oversized.
            _split_across_columns(prefix, table, [row], label_columns, chunks)
            continue
        group.append(row)
        size += cost

    if group:
        _append_chunk(chunks, _render_table(prefix, table, group, columns))


def _split_by_columns(prefix: str, table: _Table, chunks: list[str]) -> None:
    """Rule 4 — repeat the row headers, then fill with whole columns."""
    label_columns = [0]
    rows = table.body_rows

    group: list[int] = []
    for column in range(1, table.width):
        if group and len(
            _render_table(prefix, table, rows, [*label_columns, *group, column])
        ) > CHUNK_SIZE:
            _append_chunk(
                chunks, _render_table(prefix, table, rows, [*label_columns, *group])
            )
            group = []
        if not group and len(
            _render_table(prefix, table, rows, [*label_columns, column])
        ) > CHUNK_SIZE:
            # Rule 8: this column does not fit even alone, so break it up by row.
            _split_across_rows(prefix, table, column, label_columns, chunks)
            continue
        group.append(column)

    if group:
        _append_chunk(
            chunks, _render_table(prefix, table, rows, [*label_columns, *group])
        )


def _split_across_columns(
    prefix: str,
    table: _Table,
    rows: list[list[str]],
    label_columns: list[int],
    chunks: list[str],
) -> None:
    """Rule 7 — place as many whole cells of one row per chunk as will fit."""
    data_columns = [c for c in range(table.width) if c not in label_columns]

    group: list[int] = []
    for column in data_columns:
        if group and len(
            _render_table(prefix, table, rows, [*label_columns, *group, column])
        ) > CHUNK_SIZE:
            _append_chunk(
                chunks, _render_table(prefix, table, rows, [*label_columns, *group])
            )
            group = []
        if not group and len(
            _render_table(prefix, table, rows, [*label_columns, column])
        ) > CHUNK_SIZE:
            if rows:
                _split_cell(prefix, table, rows[0], column, label_columns, chunks)
                continue
            # A header stack with no data behind it that still overruns: there
            # is no finer boundary left to take, so let it overrun.
            _append_chunk(
                chunks, _render_table(prefix, table, rows, [*label_columns, column])
            )
            continue
        group.append(column)

    if group:
        _append_chunk(
            chunks, _render_table(prefix, table, rows, [*label_columns, *group])
        )


def _split_across_rows(
    prefix: str,
    table: _Table,
    column: int,
    label_columns: list[int],
    chunks: list[str],
) -> None:
    """Rule 8 — place as many whole cells of one column per chunk as will fit."""
    columns = [*label_columns, column]

    group: list[list[str]] = []
    for row in table.body_rows:
        if group and len(_render_table(prefix, table, [*group, row], columns)) > CHUNK_SIZE:
            _append_chunk(chunks, _render_table(prefix, table, group, columns))
            group = []
        if not group and len(_render_table(prefix, table, [row], columns)) > CHUNK_SIZE:
            _split_cell(prefix, table, row, column, label_columns, chunks)
            continue
        group.append(row)

    if group:
        _append_chunk(chunks, _render_table(prefix, table, group, columns))


def _split_cell(
    prefix: str,
    table: _Table,
    row: list[str],
    column: int,
    label_columns: list[int],
    chunks: list[str],
) -> None:
    """Rule 9 — split one cell's own content, repeating its headers on each piece."""
    columns = [*label_columns, column]
    blank = list(row) + [""] * max(0, table.width - len(row))
    blank[column] = ""
    overhead = len(_render_table(prefix, table, [blank], columns))

    for piece in _cell_pieces(_cell(row, column), CHUNK_SIZE - overhead):
        fragment = list(blank)
        fragment[column] = piece
        _append_chunk(chunks, _render_table(prefix, table, [fragment], columns))


def _cell_pieces(value: str, budget: int) -> list[str]:
    """Break cell content at the coarsest boundary whose pieces all fit.

    Paragraphs first, then list items, then sentences, then words — and if a
    single word still overruns, fixed-width slices, because at that point
    there is no boundary in the text left to respect.
    """
    if budget <= 0 or len(value) <= budget:
        return [value]

    for pattern in (
        CELL_PARAGRAPH_RE,
        CELL_LIST_ITEM_RE,
        CELL_SENTENCE_RE,
        CELL_WORD_RE,
    ):
        groups = _merge_segments(_segments(value, pattern), budget)
        if all(len(group) <= budget for group in groups):
            return [group.strip() for group in groups if group.strip()]

    return [value[index : index + budget] for index in range(0, len(value), budget)]


def _segments(value: str, pattern: re.Pattern[str]) -> list[str]:
    """Cut ``value`` at each match, keeping the separator on the piece before it."""
    pieces: list[str] = []
    cursor = 0
    for match in pattern.finditer(value):
        if match.end() <= cursor:
            continue
        pieces.append(value[cursor : match.end()])
        cursor = match.end()
    if cursor < len(value):
        pieces.append(value[cursor:])
    return pieces


def _merge_segments(segments: list[str], budget: int) -> list[str]:
    """Greedily concatenate consecutive segments up to ``budget``."""
    groups: list[str] = []
    current = ""
    for segment in segments:
        if current and len(current) + len(segment) > budget:
            groups.append(current)
            current = segment
        else:
            current += segment
    if current:
        groups.append(current)
    return groups


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
    consumed = 0
    index = 0
    while index + 1 < len(lines):
        if (
            not _inside_spans(offsets[index], fences)
            and _is_table_row(lines[index].rstrip("\r\n"))
            and _is_table_separator(lines[index + 1].rstrip("\r\n"))
        ):
            # A GitHub table declares one header row, but a converter
            # reconstructing a multi-level header emits the upper levels as
            # further rows above it. Walk back over them so the whole header
            # stack belongs to the table and can be repeated on every piece
            # when the table is split.
            first = index
            while (
                first > consumed
                and _is_table_row(lines[first - 1].rstrip("\r\n"))
                and not _is_table_separator(lines[first - 1].rstrip("\r\n"))
                and not _inside_spans(offsets[first - 1], fences)
            ):
                first -= 1
            start = offsets[first]
            index += 2
            while index < len(lines) and _is_table_row(
                lines[index].rstrip("\r\n")
            ):
                index += 1
            end = offsets[index] if index < len(lines) else len(text)
            spans.append((start, end))
            consumed = index
        else:
            index += 1
    return spans


def _table_cells(line: str) -> list[str] | None:
    """Split a pipe row into stripped cells, or ``None`` if it is not a row.

    Pipes that are backslash-escaped or inside an inline code span are cell
    content, not delimiters — splitting on them naively miscounts the row's
    width, which matters now that cells are addressed by index when a table
    is split by column.
    """
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None

    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    code_span = False

    for character in stripped[1:-1]:
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "`":
            code_span = not code_span
        elif character == "|" and not code_span:
            cells.append("".join(cell).strip())
            cell = []
            continue
        cell.append(character)

    cells.append("".join(cell).strip())
    return cells


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


def _top_level_item_boundaries(text: str, start: int, end: int) -> list[int]:
    """Return pointer-start offsets for a list's shallowest indent level.

    Used to split an oversized list one pointer at a time without ever
    separating a nested sub-item from its parent pointer: a "top-level"
    pointer's span runs up to the *next* top-level pointer, so anything
    nested underneath it (deeper indent) rides along inside that span.

    ``start`` is always the first boundary, even when the item sitting there
    is itself nested (deeper than the shallowest indent found) — that
    happens when a previous cut already landed mid-list, inside a nested
    run. Without forcing ``start`` in, that leading nested content would
    fall between it and the first true top-level pointer and be dropped.
    """
    items = _list_items(text, start, end)
    min_indent = min(indent for _, indent in items)
    boundaries = [pos for pos, indent in items if indent == min_indent]
    if not boundaries or boundaries[0] != start:
        boundaries.insert(0, start)
    return boundaries + [end]


def _is_markup_line(line: str) -> bool:
    """Whether a line renders to nothing — only tags, no text of its own.

    Marker emits `<span id="…"></span>` cross-reference anchors, which
    `_extract_leading_spans` moves onto their own line. Such a line is not
    content, but it is not a reason to move a chunk boundary either: it is
    only ever relocated when it trails a heading that is moving anyway.
    """
    stripped = line.strip()
    return bool(stripped) and "<" in stripped and not HTML_TAG_RE.sub("", stripped).strip()


def _has_body(text: str, start: int, end: int) -> bool:
    """Whether the region holds anything that is not a heading or bare markup."""
    return any(
        line.strip() and not HEADING_RE.match(line) and not _is_markup_line(line)
        for line in text[start:end].splitlines()
    )


def _trailing_heading_start(text: str, start: int, end: int) -> int | None:
    """Offset where a heading that introduces nothing closes the region.

    The run being measured is a heading plus any markup-only lines it carries
    — an anchor sitting *after* a trailing heading annotates what comes next
    and travels with it. An anchor *before* the heading belongs to the body
    already recorded, so it stays; a tail of markup with no heading in it is
    not a trailing heading at all and is left alone.

    Returns ``None`` when the region ends in body content, and also when
    moving the run would leave no body behind — that case is a body-less
    chunk, which `_contains_only_headings` handles by moving the whole buffer
    rather than part of it.
    """
    offsets: list[tuple[int, str]] = []
    cursor = start
    for line in text[start:end].splitlines(keepends=True):
        offsets.append((cursor, line))
        cursor += len(line)

    boundary: int | None = None
    for offset, line in reversed(offsets):
        if not line.strip():
            continue
        if HEADING_RE.match(line):
            boundary = offset
            continue
        if _is_markup_line(line):
            continue
        break

    if boundary is None or not _has_body(text, start, boundary):
        return None
    return boundary


def _contains_only_headings(text: str, start: int, end: int) -> bool:
    """Return whether a nonempty candidate has headings but no body content."""
    lines = text[start:end].splitlines()
    has_heading = any(HEADING_RE.match(line) for line in lines)
    return has_heading and not _has_body(text, start, end)


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

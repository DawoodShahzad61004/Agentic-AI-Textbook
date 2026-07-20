"""Print token counts for Markdown tables produced by Marker."""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "marker_results"
DEFAULT_ENCODING = "cl100k_base"

SEPARATOR_CELL = re.compile(r"^:?-+:?$")


def split_row(line: str) -> list[str] | None:
    """Split a pipe-style Markdown row, ignoring escaped and code-span pipes."""
    stripped = line.strip()
    if "|" not in stripped:
        return None

    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    code_span = False

    for character in stripped:
        if escaped:
            cell.append(character)
            escaped = False
        elif character == "\\":
            cell.append(character)
            escaped = True
        elif character == "`":
            cell.append(character)
            code_span = not code_span
        elif character == "|" and not code_span:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(character)

    cells.append("".join(cell).strip())
    if stripped.startswith("|"):
        cells.pop(0)
    if stripped.endswith("|"):
        cells.pop()
    # Marker can produce legitimate one-column tables. Require outer pipes for
    # those so an ordinary sentence containing one pipe is not treated as a row.
    if len(cells) >= 2 or (len(cells) == 1 and stripped.startswith("|") and stripped.endswith("|")):
        return cells
    return None


def is_separator_row(line: str) -> bool:
    cells = split_row(line)
    return bool(
        cells
        and all(SEPARATOR_CELL.fullmatch(cell.replace(" ", "")) for cell in cells)
    )


def iter_tables(markdown: str) -> Iterator[tuple[int, str]]:
    """Yield ``(starting line number, source text)`` for each Markdown table."""
    lines = markdown.splitlines()
    index = 0

    while index + 1 < len(lines):
        header_cells = split_row(lines[index])
        if not header_cells or not is_separator_row(lines[index + 1]):
            index += 1
            continue

        start = index
        index += 2
        while index < len(lines):
            row_cells = split_row(lines[index])
            # Marker output is generated from OCR and occasionally changes the
            # apparent column count within one table. A blank/non-row line is a
            # more reliable table boundary than strict column equality.
            if not row_cells or is_separator_row(lines[index]):
                break
            index += 1

        yield start + 1, "\n".join(lines[start:index])


def discover_markdown_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count tokens in every Markdown table under a directory."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="directory to scan recursively (default: marker_results)",
    )
    parser.add_argument(
        "--encoding",
        default=DEFAULT_ENCODING,
        help=f"tiktoken encoding name (default: {DEFAULT_ENCODING})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    try:
        import tiktoken
    except ImportError as error:
        raise SystemExit(
            "Missing dependency 'tiktoken'. Install it with: python -m pip install tiktoken"
        ) from error

    try:
        encoding = tiktoken.get_encoding(args.encoding)
    except ValueError as error:
        raise SystemExit(f"Unknown tiktoken encoding: {args.encoding}") from error

    files = discover_markdown_files(input_dir)
    total_tables = 0
    total_tokens = 0

    for path in files:
        try:
            markdown = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"SKIP {path}: {error}")
            continue

        display_path = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        file_tables = 0
        for file_tables, (line_number, table) in enumerate(iter_tables(markdown), start=1):
            token_count = len(encoding.encode(table))
            total_tables += 1
            total_tokens += token_count
            print(
                f"{display_path} | table {file_tables} | "
                f"line {line_number} | {token_count} tokens"
            )

        if file_tables == 0:
            print(f"{display_path} | no tables")

    print(
        f"Done: {len(files)} file(s), {total_tables} table(s), "
        f"{total_tokens} table token(s)."
    )


if __name__ == "__main__":
    main()

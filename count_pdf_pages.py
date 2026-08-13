from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pypdf import PdfReader


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def iter_pdf_files(root: Path, *, include_hidden: bool) -> list[Path]:
    pdfs: list[Path] = []

    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        if not include_hidden:
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]

        for filename in filenames:
            path = current_path / filename
            if path.suffix.lower() != ".pdf":
                continue
            if not include_hidden and is_hidden(path.relative_to(root)):
                continue
            pdfs.append(path)

    return sorted(pdfs, key=lambda path: str(path).lower())


def count_pages(path: Path) -> int:
    with path.open("rb") as stream:
        return len(PdfReader(stream).pages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count the total pages across PDF files only."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory to scan recursively, or a single PDF file. Defaults to the current directory.",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden directories such as .git or .docx-tools.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print each PDF's page count before the total.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.path).resolve()

    if root.is_file():
        if root.suffix.lower() != ".pdf":
            print(f"Not a PDF file: {root}", file=sys.stderr)
            return 2
        pdfs = [root]
    elif root.is_dir():
        pdfs = iter_pdf_files(root, include_hidden=args.include_hidden)
    else:
        print(f"Path does not exist: {root}", file=sys.stderr)
        return 2

    total_pages = 0
    failures: list[str] = []

    for pdf in pdfs:
        try:
            pages = count_pages(pdf)
        except Exception as exc:
            failures.append(f"{pdf}: {exc}")
            continue

        total_pages += pages
        if args.details:
            print(f"{pages:>5}  {pdf}")

    if failures:
        print("Failed to read one or more PDF files:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(total_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

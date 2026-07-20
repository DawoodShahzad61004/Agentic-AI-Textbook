from pathlib import Path

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "source"
OUTPUT_DIR = PROJECT_ROOT / "docling_results"


def output_path_for(source_path: Path) -> Path:
    relative_path = source_path.relative_to(SOURCE_DIR)
    return (OUTPUT_DIR / relative_path).with_suffix(".md")


def main() -> None:
    source_files = sorted(
        path for path in SOURCE_DIR.rglob("*") if path.is_file()
    )

    if not source_files:
        raise SystemExit(f"No source files found in: {SOURCE_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                backend=PyPdfiumDocumentBackend
            )
        }
    )

    print(f"Found {len(source_files)} source file(s).")

    converted = 0
    failures = []

    for source_path in source_files:
        output_path = output_path_for(source_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Converting: {source_path.relative_to(PROJECT_ROOT)}")

        try:
            result = converter.convert(source_path)

            markdown = result.document.export_to_markdown()
            output_path.write_text(markdown, encoding="utf-8")

            converted += 1
            print(f"Markdown written to: {output_path.relative_to(PROJECT_ROOT)}")

        except Exception as error:
            failures.append((source_path, error))
            print(f"FAILED: {source_path.name}: {error}")

    print(f"Docling complete: {converted} converted, {len(failures)} failed.")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
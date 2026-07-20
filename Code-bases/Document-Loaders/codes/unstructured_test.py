from pathlib import Path

from unstructured.partition.auto import partition


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "source"
OUTPUT_DIR = PROJECT_ROOT / "unstructured_results"


def elements_to_markdown(elements) -> str:
    lines = []
    for element in elements:
        category = element.category
        text = str(element)
        if category == "Title":
            lines.append(f"# {text}")
        elif category == "Header":
            lines.append(f"## {text}")
        elif category == "ListItem":
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


def output_path_for(source_path: Path) -> Path:
    relative_path = source_path.relative_to(SOURCE_DIR)
    return (OUTPUT_DIR / relative_path).with_suffix(".md")


def main() -> None:
    source_files = sorted(path for path in SOURCE_DIR.rglob("*") if path.is_file())
    if not source_files:
        raise SystemExit(f"No source files found in: {SOURCE_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(source_files)} source file(s) for Unstructured.")

    converted = 0
    failures: list[tuple[Path, Exception]] = []

    for source_path in source_files:
        output_path = output_path_for(source_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Converting: {source_path.relative_to(PROJECT_ROOT)}")

        try:
            elements = partition(filename=str(source_path))
            output_path.write_text(elements_to_markdown(elements), encoding="utf-8")
            converted += 1
            print(f"Markdown written to: {output_path.relative_to(PROJECT_ROOT)}")
        except Exception as error:
            failures.append((source_path, error))
            print(f"FAILED: {source_path.name}: {error}")

    print(f"Unstructured complete: {converted} converted, {len(failures)} failed.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Deterministic repository map: tree, sizes, languages, and entry-point candidates.

Usage:
    python repo_map.py <repo-root> [--out FILE] [--max-depth N]

Writes a markdown report (default: .research/repo_map_raw.md) containing:
  - directory tree (junk dirs skipped) with per-file line counts
  - language/extension breakdown
  - entry-point candidates found by static heuristics
  - config/build/dependency files found

Stdlib only — no pip installs required. This produces the *raw facts*;
the codebase-explorer skill turns them into an annotated tour.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

SKIP_DIRS = {".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", "env",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
             ".idea", ".vscode", ".tox", "site-packages", ".eggs", "wandb",
             "checkpoints", "outputs", ".research"}
SKIP_EXTS = {".pyc", ".so", ".o", ".a", ".bin", ".pt", ".pth", ".ckpt", ".onnx",
             ".npy", ".npz", ".pkl", ".h5", ".safetensors", ".png", ".jpg",
             ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz", ".whl", ".ico",
             ".woff", ".woff2", ".ttf", ".mp4", ".wav"}
CODE_EXTS = {".py", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".c",
             ".cc", ".cpp", ".h", ".hpp", ".cu", ".java", ".rb", ".sh", ".jl",
             ".lua", ".m", ".r", ".scala"}
CONFIG_NAMES = {"setup.py", "setup.cfg", "pyproject.toml", "requirements.txt",
                "environment.yml", "environment.yaml", "Makefile", "makefile",
                "package.json", "Cargo.toml", "go.mod", "CMakeLists.txt",
                "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                "conda.yml", "tox.ini", "noxfile.py"}

ENTRY_PATTERNS = [
    (re.compile(r'if\s+__name__\s*==\s*["\']__main__["\']'), "python __main__ guard"),
    (re.compile(r"^\s*@(click\.command|app\.command|hydra\.main)", re.M), "CLI decorator (click/typer/hydra)"),
    (re.compile(r"argparse\.ArgumentParser\("), "argparse CLI"),
    (re.compile(r"^\s*def\s+main\s*\(", re.M), "main() function"),
    (re.compile(r"(fire\.Fire|absl\.app\.run|app\.run\()"), "fire/absl/app runner"),
]


def count_lines(p: Path) -> int:
    try:
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default=".research/repo_map_raw.md")
    ap.add_argument("--max-depth", type=int, default=6)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    files, tree_lines = [], []
    ext_counter, loc_counter = Counter(), Counter()

    def walk(d: Path, depth: int) -> None:
        if depth > args.max_depth:
            tree_lines.append("  " * depth + "…")
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if p.name.startswith(".") and p.name not in {".github"}:
                continue
            if p.is_dir():
                if p.name in SKIP_DIRS:
                    continue
                tree_lines.append("  " * depth + f"{p.name}/")
                walk(p, depth + 1)
            else:
                if p.suffix.lower() in SKIP_EXTS:
                    continue
                loc = count_lines(p)
                files.append((p, loc))
                ext = p.suffix.lower() or p.name
                ext_counter[ext] += 1
                loc_counter[ext] += loc
                tree_lines.append("  " * depth + f"{p.name}  ({loc} lines)")

    walk(root, 0)

    entry_hits, configs = [], []
    for p, _loc in files:
        if p.name in CONFIG_NAMES:
            configs.append(p)
        if p.suffix.lower() in CODE_EXTS and p.suffix.lower() != ".ipynb":
            try:
                src = p.read_text(errors="ignore")
            except OSError:
                continue
            hits = [label for rx, label in ENTRY_PATTERNS if rx.search(src)]
            if hits:
                entry_hits.append((p, hits))
    # console_scripts / package.json scripts
    for c in configs:
        try:
            src = c.read_text(errors="ignore")
        except OSError:
            continue
        if c.name in {"setup.py", "setup.cfg", "pyproject.toml"} and "console_scripts" in src:
            entry_hits.append((c, ["declares console_scripts"]))
        if c.name == "package.json" and '"scripts"' in src:
            entry_hits.append((c, ["declares npm scripts"]))
        if c.name.lower() == "makefile":
            targets = re.findall(r"^([A-Za-z0-9_\-]+):", src, re.M)
            if targets:
                entry_hits.append((c, [f"make targets: {', '.join(targets[:12])}"]))

    biggest = sorted(files, key=lambda t: -t[1])[:15]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Raw repo map: {root.name}\n\n")
        f.write(f"Total files scanned: {len(files)}\n\n")
        f.write("## Language breakdown (files / lines)\n\n")
        for ext, n in ext_counter.most_common(15):
            f.write(f"- `{ext}`: {n} files, {loc_counter[ext]} lines\n")
        f.write("\n## Entry-point candidates\n\n")
        if not entry_hits:
            f.write("_None detected by heuristics — check README / notebooks._\n")
        for p, hits in sorted(entry_hits, key=lambda t: str(t[0])):
            f.write(f"- `{p.relative_to(root)}` — {'; '.join(hits)}\n")
        f.write("\n## Config / build / dependency files\n\n")
        for c in configs:
            f.write(f"- `{c.relative_to(root)}`\n")
        f.write("\n## Largest files\n\n")
        for p, loc in biggest:
            f.write(f"- `{p.relative_to(root)}` — {loc} lines\n")
        f.write("\n## Tree\n\n```\n")
        f.write("\n".join(tree_lines))
        f.write("\n```\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fetch arXiv paper metadata (and optionally the PDF) into .research/.

Usage:
    python fetch_arxiv.py <arxiv-url-or-id> [--pdf] [--out DIR]

Examples:
    python fetch_arxiv.py https://arxiv.org/abs/1706.03762
    python fetch_arxiv.py 1706.03762 --pdf
Writes:
    <out>/paper_meta.md   (title, authors, abstract, categories, links)
    <out>/paper.pdf       (only with --pdf)

Stdlib only — no pip installs required.
"""
import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ATOM = "{http://www.w3.org/2005/Atom}"


def extract_id(s: str) -> str:
    """Accept a bare id, abs/ url, pdf/ url, or versioned id."""
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s)
    if m:
        return m.group(1) + (m.group(2) or "")
    # old-style ids like cs/9901002
    m = re.search(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})", s)
    if m:
        return m.group(1)
    sys.exit(f"error: could not parse an arXiv id from: {s}")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "research-skills/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paper", help="arXiv URL or id")
    ap.add_argument("--pdf", action="store_true", help="also download the PDF")
    ap.add_argument("--out", default=".research", help="output directory (default: .research)")
    args = ap.parse_args()

    pid = extract_id(args.paper)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    api = f"https://export.arxiv.org/api/query?id_list={pid}"
    root = ET.fromstring(fetch(api))
    entry = root.find(ATOM + "entry")
    if entry is None or entry.find(ATOM + "title") is None:
        sys.exit(f"error: arXiv API returned no entry for id {pid}")

    def text(tag: str) -> str:
        el = entry.find(ATOM + tag)
        return re.sub(r"\s+", " ", el.text or "").strip() if el is not None else ""

    title = text("title")
    abstract = text("summary")
    published = text("published")[:10]
    authors = [a.find(ATOM + "name").text for a in entry.findall(ATOM + "author")]
    cats = [c.attrib.get("term", "") for c in entry.findall(ATOM + "category")]
    links = {l.attrib.get("title", l.attrib.get("rel", "")): l.attrib.get("href", "")
             for l in entry.findall(ATOM + "link")}
    pdf_url = links.get("pdf") or f"https://arxiv.org/pdf/{pid}"

    meta = out / "paper_meta.md"
    meta.write_text(
        f"# {title}\n\n"
        f"- **arXiv id:** {pid}\n"
        f"- **Published:** {published}\n"
        f"- **Authors:** {', '.join(authors)}\n"
        f"- **Categories:** {', '.join(cats)}\n"
        f"- **Abs:** https://arxiv.org/abs/{pid}\n"
        f"- **PDF:** {pdf_url}\n\n"
        f"## Abstract\n\n{abstract}\n",
        encoding="utf-8",
    )
    print(f"wrote {meta}")

    if args.pdf:
        pdf_path = out / "paper.pdf"
        pdf_path.write_bytes(fetch(pdf_url))
        print(f"wrote {pdf_path} ({pdf_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

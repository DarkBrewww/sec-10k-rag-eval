"""Search the extracted filing sections as plain text.

This exists to write golden-dataset questions *without* consulting the RAG
system's own retriever, which matters more than it looks.

If questions were sourced by asking the retriever what it can find, the eval
would be scored on questions selected for being easy to retrieve — the dataset
would silently inherit the blind spots of the system it is supposed to audit,
and retrieval recall would look far better than it is. Grepping the raw section
text keeps question selection independent of the system under test.

Usage:
    python -m scripts.corpus_search "dividend"
    python -m scripts.corpus_search --company GOOGL --section mdna "capital return"
    python -m scripts.corpus_search --regex "revenue (increased|decreased)"
    python -m scripts.corpus_search --context 600 "AI competition"
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from src import config


def load_sections(company: str | None, year: int | None, section: str | None) -> list[dict]:
    """Load extracted section records, optionally filtered."""
    records = []
    for path in sorted(config.EXTRACTED_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            rec = json.load(f)
        if company and rec["company"] != company.upper():
            continue
        if year and rec["fiscal_year"] != year:
            continue
        if section and rec["section"] != section:
            continue
        records.append(rec)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Search extracted 10-K sections as plain text.")
    parser.add_argument("pattern", help="Search term, or a regex when --regex is passed.")
    parser.add_argument("--regex", action="store_true", help="Treat the pattern as a regular expression.")
    parser.add_argument("--company", help="Filter: MSFT / GOOGL / META")
    parser.add_argument("--year", type=int, help="Filter: fiscal year, e.g. 2023")
    parser.add_argument("--section", choices=sorted(config.SECTIONS), help="Filter: risk_factors / mdna")
    parser.add_argument("--context", type=int, default=350, help="Characters of context per hit.")
    parser.add_argument("--max-per-section", type=int, default=3, help="Cap hits shown per section.")
    args = parser.parse_args()

    # Windows consoles default to cp1252, which mangles the section sign we use
    # in section labels. Force UTF-8 where the stream supports it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pattern = args.pattern if args.regex else re.escape(args.pattern)
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        return 2

    records = load_sections(args.company, args.year, args.section)
    if not records:
        print("No sections matched those filters. Has the index been built?", file=sys.stderr)
        return 1

    total = 0
    for rec in records:
        text = rec["text"]
        hits = list(rx.finditer(text))
        if not hits:
            continue
        label = f"{rec['company']} FY{rec['fiscal_year']} §{rec['section']}"
        print(f"\n{'=' * 78}\n{label}  -  {len(hits)} hit(s)\n{'=' * 78}")
        for m in hits[: args.max_per_section]:
            half = args.context // 2
            start, end = max(0, m.start() - half), min(len(text), m.end() + half)
            snippet = text[start:end].replace("\n", " ").strip()
            print(f"\n  @char {m.start():,}\n  ...{snippet}...")
        if len(hits) > args.max_per_section:
            print(f"\n  ({len(hits) - args.max_per_section} more hit(s) not shown)")
        total += len(hits)

    print(f"\n{total} total hit(s) across {len(records)} section(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

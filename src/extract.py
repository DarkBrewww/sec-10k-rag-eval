"""Extract Item 1A (Risk Factors) and Item 7 (MD&A) from raw 10-K filings.

The extraction logic is heuristic and intentionally simple:

  1. Read the filing as text (HTML stripped).
  2. Find every "Item N" header in the document.
  3. For each target item (1A, 7), the *real* section is the one with the
     longest span to the next "Item" header. Table-of-contents entries have
     small spans between consecutive items; real section bodies have huge
     spans (often tens of thousands of characters).

This will fail on edge cases (unusual filing formats, items split across
pages, etc.). That's expected for Week 1 — we'll harden it later if the
eval harness flags retrieval problems traceable to bad extraction.
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from . import config


# Pattern matches real section headers like "Item 1A.", "ITEM 7.", "Item 7A:".
# The trailing period/colon is load-bearing: 10-Ks (MSFT especially) repeat a
# running "Item 7" page header on every page of a section and pepper the body
# with cross-references ("see Item 8", "Item 7 of this Form 10-K"). Without the
# punctuation requirement those ~20 spurious matches per section shred the
# longest-span heuristic into page-sized fragments. Real headers always carry
# the period; running headers and cross-refs do not.
_ITEM_RE = re.compile(r"Item\s+(\d+[A-Za-z]?)[.:]", re.IGNORECASE)

# Fiscal-year-end statement from the filing cover page. The window in
# _extract_fiscal_year must be wide enough to reach it — in these filings the
# cover sits ~30k chars in, past the SGML/iXBRL preamble.
_FY_PATTERNS = [
    re.compile(r"fiscal year ended\s+\w+\s+\d+,\s+(\d{4})", re.IGNORECASE),
    re.compile(r"year ended\s+\w+\s+\d+,\s+(\d{4})", re.IGNORECASE),
]

# How far into the document to scan for the cover-page fiscal-year statement.
# Generous headroom over the observed ~37k-char position; small enough to avoid
# matching prior-year references deep in the MD&A body.
_FY_SEARCH_WINDOW = 60_000


def _find_filing_file(filing_dir: Path) -> Path | None:
    """Locate the primary filing document inside a downloaded filing dir."""
    candidates = [
        "primary-document.html",
        "primary-document.htm",
        "full-submission.txt",
    ]
    for name in candidates:
        p = filing_dir / name
        if p.exists():
            return p
    # Fallback: any .htm/.html in the directory
    htmls = list(filing_dir.glob("*.htm*"))
    return htmls[0] if htmls else None


def _isolate_primary_document(content: str) -> str:
    """Return just the primary 10-K document from a raw filing string.

    `sec-edgar-downloader` v5 saves `full-submission.txt`: the entire SGML
    submission (10-K + every exhibit + XBRL), ~30 MB and ~10 M chars of text
    once flattened. Parsing all of it makes the 10-K's "Item N" headers
    indistinguishable from the same strings in exhibits and XBRL renderings.

    The submission is a sequence of <DOCUMENT> blocks, each tagged with a
    <TYPE>. We want the body (<TEXT>) of the first block whose type is exactly
    "10-K". If the content has no SGML markers (e.g. a genuine standalone HTML
    primary document), return it unchanged.
    """
    if "<DOCUMENT>" not in content:
        return content
    for doc in re.finditer(r"<DOCUMENT>(.*?)</DOCUMENT>", content, re.DOTALL):
        block = doc.group(1)
        type_match = re.search(r"<TYPE>([^\n<]+)", block)
        if type_match and type_match.group(1).strip() == "10-K":
            text_match = re.search(r"<TEXT>(.*?)</TEXT>", block, re.DOTALL)
            return text_match.group(1) if text_match else block
    return content  # no 10-K document found; let the caller parse the whole thing


def _file_to_text(path: Path) -> str:
    """Read filing file and return whitespace-normalized plain text."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    content = _isolate_primary_document(content)
    soup = BeautifulSoup(content, "lxml")
    text = soup.get_text(separator="\n")
    # Collapse repeated whitespace but preserve paragraph breaks
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def _extract_fiscal_year(text: str) -> int | None:
    head = text[:_FY_SEARCH_WINDOW]
    for pat in _FY_PATTERNS:
        m = pat.search(head)
        if m:
            return int(m.group(1))
    return None


def extract_sections(text: str) -> dict[str, str]:
    """Pull the two target sections out of filing text.

    Returns a dict keyed by section slug (e.g. "risk_factors", "mdna").
    Missing sections are simply absent from the dict.
    """
    matches = list(_ITEM_RE.finditer(text))
    if not matches:
        return {}

    out: dict[str, str] = {}
    for slug, item_num in config.SECTIONS.items():
        # Every match of this exact item number
        relevant = [
            (i, m) for i, m in enumerate(matches)
            if m.group(1).upper() == item_num.upper()
        ]
        if not relevant:
            continue

        # For each, the span runs from this match to the NEXT item header
        # (any item). The real section is the longest such span; TOC entries
        # are tiny by comparison.
        candidates = []
        for i, m in relevant:
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            candidates.append((start, end, end - start))

        best = max(candidates, key=lambda c: c[2])
        section_text = text[best[0]:best[1]].strip()

        # Sanity check: real sections are long. TOC entries are not.
        if len(section_text) >= 1500:
            out[slug] = section_text

    return out


def _filing_dirs() -> list[Path]:
    """All filing directories sec-edgar-downloader created."""
    root = config.RAW_DIR / "sec-edgar-filings"
    if not root.exists():
        return []
    # Structure: sec-edgar-filings/<TICKER>/10-K/<accession>/
    return [p for p in root.glob("*/10-K/*") if p.is_dir()]


def extract_all() -> list[dict]:
    """Extract sections from every downloaded filing.

    Writes one JSON file per filing to data/extracted/ and also returns the
    parsed records, so callers can pipe straight into indexing.
    """
    records: list[dict] = []

    for filing_dir in _filing_dirs():
        ticker = filing_dir.parts[-3]  # .../sec-edgar-filings/<TICKER>/10-K/<acc>
        accession = filing_dir.name
        file_path = _find_filing_file(filing_dir)
        if not file_path:
            print(f"[extract] {ticker} {accession}: no filing file found, skipping")
            continue

        text = _file_to_text(file_path)
        fiscal_year = _extract_fiscal_year(text)
        sections = extract_sections(text)

        if not sections:
            print(f"[extract] {ticker} {accession}: no sections extracted, skipping")
            continue

        for slug, section_text in sections.items():
            record = {
                "company": ticker,
                "accession": accession,
                "fiscal_year": fiscal_year,
                "section": slug,
                "text": section_text,
            }
            records.append(record)
            # Persist for inspection
            out_path = config.EXTRACTED_DIR / f"{ticker}_{fiscal_year}_{slug}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)
            print(
                f"[extract] {ticker} FY{fiscal_year} {slug}: "
                f"{len(section_text):,} chars -> {out_path.name}"
            )

    return records


if __name__ == "__main__":
    extract_all()

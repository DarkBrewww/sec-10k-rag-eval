"""Validate the golden evaluation dataset.

The dataset is the measuring instrument for the entire eval harness. If an item
is malformed — or worse, cites a filing that does not exist — every metric
computed downstream is quietly wrong. This script is the guard rail.

It checks three things:

  1. **Schema conformance** — required fields, types, and the invariants that
     tie fields together (a tier-4 item must expect abstention; an abstaining
     item must have no gold sources; etc).
  2. **Referential integrity against the real corpus** — every `gold_sources`
     entry is cross-checked against the sections actually on disk. This catches
     the most dangerous class of error: a plausible-looking question about, say,
     GOOGL FY2024, which our corpus does not contain (see the coverage note in
     data/golden/README.md).
  3. **Anti-pattern lint** — the question styles docs/GOLDEN_DATASET_SPEC.md
     calls out as unscoreable (yes/no, compound, undated time references).

Exits non-zero on any error, so it can run unchanged as a CI gate in Week 5.

Usage:
    python -m scripts.validate_golden
    python -m scripts.validate_golden --check-chunks  # also verify chunk IDs exist in the index
    python -m scripts.validate_golden --strict        # require the full target tier distribution
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from src import config

GOLDEN_DIR = config.DATA_DIR / "golden"
QUESTIONS_PATH = GOLDEN_DIR / "questions.jsonl"

# Target counts from docs/GOLDEN_DATASET_SPEC.md. Enforced only under --strict,
# because the file is legitimately incomplete while the dataset is being built.
TIER_TARGETS = {1: 40, 2: 30, 3: 30, 4: 20}
SUBTIER_TARGETS = {"4a": 5, "4b": 5, "4c": 5, "4d": 5}

REQUIRED_FIELDS = {
    "id", "question", "tier", "subtier", "expected_behavior",
    "gold_answer", "gold_sources", "gold_supporting_chunks", "notes",
}

# A leading auxiliary/copular verb makes the question answerable with yes or no,
# which is trivial to game and impossible to score for nuance.
YES_NO_OPENERS = {
    "is", "are", "was", "were", "does", "did", "do", "has", "have", "had",
    "can", "could", "will", "would", "should", "may", "might",
}

# "Currently" relative to what? Undated temporal references make the gold answer
# ambiguous the moment the corpus changes.
VAGUE_TIME_TERMS = ("currently", "right now", "at present", "nowadays", "these days")

# Two interrogatives joined together should be split into separate items.
COMPOUND_RE = re.compile(r"\band (?:how|what|why|when|which|where)\b", re.IGNORECASE)


def load_corpus_index() -> set[tuple[str, int, str]]:
    """Return the (company, year, section) triples that actually exist on disk."""
    triples: set[tuple[str, int, str]] = set()
    for path in sorted(config.EXTRACTED_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            rec = json.load(f)
        triples.add((rec["company"], rec["fiscal_year"], rec["section"]))
    return triples


def load_items(path: Path) -> list[dict]:
    """Read the JSONL dataset, tolerating blank lines and # comments."""
    if not path.exists():
        return []
    items = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path.name}:{lineno}: invalid JSON - {e}")
    return items


def validate_item(
    item: dict,
    corpus: set[tuple[str, int, str]],
    seen_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Check one dataset item. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    qid = item.get("id", "<no id>")

    missing = REQUIRED_FIELDS - item.keys()
    if missing:
        errors.append(f"missing field(s): {', '.join(sorted(missing))}")
        return errors, warnings  # further checks would just cascade

    if qid in seen_ids:
        errors.append("duplicate id")
    if not re.fullmatch(r"q\d{3}", str(qid)):
        warnings.append(f"id {qid!r} does not match the qNNN convention")

    question = item["question"].strip()
    if not question:
        errors.append("empty question")
    elif not question.endswith("?"):
        warnings.append("question does not end with '?'")

    tier, subtier = item["tier"], item["subtier"]
    behavior = item["expected_behavior"]

    if tier not in (1, 2, 3, 4):
        errors.append(f"tier must be 1-4, got {tier!r}")
    if behavior not in ("answer", "abstain"):
        errors.append(f"expected_behavior must be 'answer' or 'abstain', got {behavior!r}")

    # Tier 4 is the abstention tier; tiers 1-3 must be answerable. Keeping these
    # in lockstep is what lets the harness score the two regimes separately.
    if tier == 4:
        if behavior != "abstain":
            errors.append("tier 4 items must have expected_behavior 'abstain'")
        if subtier not in SUBTIER_TARGETS:
            errors.append(f"tier 4 requires subtier one of {sorted(SUBTIER_TARGETS)}, got {subtier!r}")
    else:
        if behavior != "answer":
            errors.append(f"tier {tier} items must have expected_behavior 'answer'")
        if subtier is not None:
            warnings.append(f"subtier should be null for tier {tier}")

    sources = item["gold_sources"]
    if behavior == "abstain":
        if sources:
            errors.append("abstaining items must have empty gold_sources")
        if item["gold_answer"].strip() != config.ABSTENTION_RESPONSE:
            errors.append("abstaining items must use the exact ABSTENTION_RESPONSE as gold_answer")
    else:
        if not item["gold_answer"].strip():
            errors.append("empty gold_answer")
        if not sources:
            errors.append("answerable items need at least one gold_source")
        for src in sources:
            try:
                triple = (src["company"], src["year"], src["section"])
            except (TypeError, KeyError):
                errors.append(f"malformed gold_source: {src!r}")
                continue
            # The high-value check: does this filing exist in our corpus at all?
            if triple not in corpus:
                errors.append(
                    f"gold_source {triple} is not in the corpus "
                    f"(check the fiscal-year coverage matrix)"
                )
        # A cross-document question that only cites one document is mislabeled.
        if tier == 3 and len({(s.get("company"), s.get("year")) for s in sources}) < 2:
            errors.append("tier 3 (cross-document) must cite 2+ distinct filings")

    if not isinstance(item["gold_supporting_chunks"], list):
        errors.append("gold_supporting_chunks must be a list")

    # ----- anti-pattern lint (warnings: judgement calls, not hard failures) ---
    first_word = question.split()[0].lower().rstrip(",") if question.split() else ""
    if first_word in YES_NO_OPENERS:
        warnings.append(f"looks like a yes/no question (opens with {first_word!r})")
    if COMPOUND_RE.search(question):
        warnings.append("looks compound - consider splitting into two items")
    if question.count("?") > 1:
        warnings.append("multiple question marks — likely two questions in one")
    lowered = question.lower()
    for term in VAGUE_TIME_TERMS:
        if term in lowered and not re.search(r"\b(19|20)\d{2}\b", question):
            warnings.append(f"undated temporal reference {term!r} - anchor to a fiscal year")
            break

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the golden evaluation dataset.")
    parser.add_argument("--path", type=Path, default=QUESTIONS_PATH,
                        help="Path to questions.jsonl")
    parser.add_argument("--strict", action="store_true",
                        help="Require the full target tier distribution (use once the set is complete).")
    parser.add_argument("--check-chunks", action="store_true",
                        help="Verify gold_supporting_chunks IDs exist in the Chroma index.")
    args = parser.parse_args()

    items = load_items(args.path)
    if not items:
        print(f"No items found in {args.path}. Nothing to validate yet.")
        return 0

    corpus = load_corpus_index()
    if not corpus:
        print("WARNING: no extracted sections found — run build_index first. "
              "Skipping corpus cross-checks.", file=sys.stderr)

    n_errors = n_warnings = 0
    seen_ids: set[str] = set()

    for item in items:
        errors, warnings = validate_item(item, corpus, seen_ids)
        seen_ids.add(item.get("id", ""))
        qid = item.get("id", "<no id>")
        for e in errors:
            print(f"ERROR  [{qid}] {e}")
        for w in warnings:
            print(f"WARN   [{qid}] {w}")
        n_errors += len(errors)
        n_warnings += len(warnings)

    # ----- chunk-ID verification (optional: needs a built index) -------------
    if args.check_chunks:
        try:
            from src.index import get_collection
            known = set(get_collection().get(include=[])["ids"])
            for item in items:
                for cid in item.get("gold_supporting_chunks", []):
                    if cid not in known:
                        print(f"ERROR  [{item.get('id')}] unknown chunk id {cid!r}")
                        n_errors += 1
        except Exception as e:  # index missing or unreadable — report, don't crash
            print(f"WARN   could not check chunk ids: {e}")
            n_warnings += 1

    # ----- distribution report ----------------------------------------------
    tier_counts = {t: sum(1 for i in items if i.get("tier") == t) for t in TIER_TARGETS}
    sub_counts = {s: sum(1 for i in items if i.get("subtier") == s) for s in SUBTIER_TARGETS}

    print()
    print(f"{'TIER':<8}{'COUNT':>7}{'TARGET':>8}")
    for tier, target in TIER_TARGETS.items():
        print(f"{tier:<8}{tier_counts[tier]:>7}{target:>8}")
    if any(sub_counts.values()):
        for sub, target in SUBTIER_TARGETS.items():
            print(f"  {sub:<6}{sub_counts[sub]:>7}{target:>8}")
    print(f"{'TOTAL':<8}{len(items):>7}{sum(TIER_TARGETS.values()):>8}")

    if args.strict:
        for tier, target in TIER_TARGETS.items():
            if tier_counts[tier] != target:
                print(f"ERROR  tier {tier}: expected {target}, found {tier_counts[tier]}")
                n_errors += 1
        for sub, target in SUBTIER_TARGETS.items():
            if sub_counts[sub] != target:
                print(f"ERROR  subtier {sub}: expected {target}, found {sub_counts[sub]}")
                n_errors += 1

    print()
    print(f"{len(items)} item(s): {n_errors} error(s), {n_warnings} warning(s).")
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())

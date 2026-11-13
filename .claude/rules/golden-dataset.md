---
paths: ["data/golden/**", "scripts/validate_golden.py"]
---

# Golden dataset rules

The golden set is the measuring instrument for every metric the harness reports. An error here is an error everywhere downstream. Full spec: @data/golden/README.md

- Write new items only into `data/golden/drafts/tier<N>_batch<NN>.jsonl`. Moving items into `questions.jsonl` needs Adwait's explicit say-so that the batch passed review.
- Source questions from the extracted text with `python -m scripts.corpus_search`, never from `scripts.ask` or the retriever. A dataset picked by the retriever inherits its blind spots and inflates recall.
- Tiers 1 and 4 can be drafted with tooling. Tiers 2 and 3 are written by hand; don't draft them unless asked.
- Every drafted item carries `evidence`: verbatim passages copied from the section text, never paraphrased. The validator checks them word for word.
- `gold_sources` must name cells that exist: MSFT FY2023/FY2024, GOOGL and META FY2022/FY2023. Three-way comparisons anchor on FY2023.
- Abstaining items (tier 4) have `expected_behavior: "abstain"`, empty `gold_sources`, and `gold_answer` equal to `config.ABSTENTION_RESPONSE` exactly.
- Leave `gold_supporting_chunks` empty in drafts unless an index exists to check them with `--check-chunks`.
- Avoid the anti-patterns: yes/no questions, questions that contain their answer, exact-figure traps, undated time words ("currently"), compound questions.
- Quality bar per item: verifiable in under 60 seconds, unambiguous to two readers, tier 4 genuinely unanswerable, tier 3 genuinely needs two or more filings.
- IDs follow `qNNN` and never get reused or renumbered once an item is in `questions.jsonl`.
- After any edit, `python -m scripts.validate_golden --path <file>` must pass. A hook runs it automatically.

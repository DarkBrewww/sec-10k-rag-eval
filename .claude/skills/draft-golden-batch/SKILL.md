---
name: draft-golden-batch
description: Draft a batch of tier 1 (single-document factual) or tier 4 (abstention) golden dataset items with verbatim evidence, sourced from corpus_search, into data/golden/drafts/. Use when asked to draft, write or add golden questions or a new batch.
argument-hint: '[tier 1|4] [batch number] [optional focus, e.g. META risk factors or 4b]'
allowed-tools: Bash(python -m scripts.corpus_search *) Bash(python -m scripts.validate_golden *) Read Write Edit
---

Arguments: $ARGUMENTS

Existing drafts:
!`ls data/golden/drafts/`

Follow `.claude/rules/golden-dataset.md` and the schema in `data/golden/README.md`.

1. If the tier is 2 or 3, stop: those are written by hand. Offer to help Adwait search the corpus for material instead.
2. Find the highest `id` across `data/golden/questions.jsonl` and every file in `data/golden/drafts/`, and continue from it.
3. Default batch size is 10 to 12 items. Spread them across companies, fiscal years and sections unless a focus was given, and avoid topics earlier batches already cover.
4. For each tier 1 item: find the passage with `python -m scripts.corpus_search` (filter by `--company`, `--year`, `--section`). Write the question from the passage, then a 1 to 3 sentence `gold_answer` that follows from it, and copy the exact supporting text into `evidence`. Prefer qualitative or rounded claims over exact figures.
5. For each tier 4 item: pick the subtier (4a entity, 4b time period, 4c plausible-but-absent topic, 4d something a 10-K never covers). For 4c, run corpus_search for the topic's key terms and record in `notes` that nothing came back. For 4b, use the fiscal-year gaps (MSFT FY2022, GOOGL and META FY2024).
6. Leave `gold_supporting_chunks` empty.
7. Write to `data/golden/drafts/tier<N>_batch<NN>.jsonl`, one object per line. The validation hook runs on save; fix every error it reports.
8. Finish with a table: id, question, source cell, one-line note on anything borderline. Then stop. Don't touch `questions.jsonl`. Suggest running the `golden-reviewer` subagent on the batch before Adwait's own review.

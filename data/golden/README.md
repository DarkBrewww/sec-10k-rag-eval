# Golden evaluation dataset

Hand-curated ground truth for the evaluation harness. Every metric the harness
reports is measured against this file, so an error here is an error everywhere
downstream. Treat it as the most carefully reviewed artifact in the repo.

## Files

| File | Contents |
|---|---|
| `questions.jsonl` | The dataset. One JSON object per line. |
| `human_labeled.jsonl` | ~20-item subset with human faithfulness judgments, used in Week 3 to measure how well the LLM judge agrees with a human. |

Validate at any time with:

```bash
python -m scripts.validate_golden                 # schema + corpus + lint
python -m scripts.validate_golden --check-chunks  # also verify chunk IDs resolve
python -m scripts.validate_golden --strict        # enforce final tier counts
```

## Tiers

| Tier | Description | Target | Expected behavior |
|---|---|---|---|
| 1 | Single-document factual | 40 | `answer` |
| 2 | Single-document synthesis | 30 | `answer` |
| 3 | Cross-document comparison (2+ filings) | 30 | `answer` |
| 4 | Adversarial / out-of-corpus | 20 | `abstain` |

Tier 4 splits further, because "should not answer" has distinct failure modes:

| Subtier | Description | Target |
|---|---|---|
| `4a` | Out-of-corpus entity (a company we don't have) | 5 |
| `4b` | Out-of-corpus time period | 5 |
| `4c` | Plausible-but-absent topic | 5 |
| `4d` | Question a 10-K would never address | 5 |

## Corpus coverage — read before writing questions

The corpus is **not** a clean 3 × 2 grid. Microsoft's fiscal year ends in June;
Alphabet's and Meta's end in December. Ten-Ks filed in the same calendar year
therefore cover different fiscal years:

|  | FY2022 | FY2023 | FY2024 |
|---|:---:|:---:|:---:|
| **GOOGL** | ✅ | ✅ | — |
| **META** | ✅ | ✅ | — |
| **MSFT** | — | ✅ | ✅ |

Each cell that exists has both `risk_factors` and `mdna`. Consequences:

- **FY2023 is the only year common to all three companies.** Any three-way
  comparison must be anchored there.
- Cross-company comparisons at FY2022 can only use GOOGL and META.
- Cross-year comparisons work within a company: GOOGL/META 2022↔2023,
  MSFT 2023↔2024.
- **This asymmetry is a gift for tier 4b.** "How did Microsoft and Meta each
  describe AI risk in FY2024?" sounds entirely reasonable and is genuinely
  unanswerable, because Meta FY2024 is not in the corpus.

`validate_golden.py` cross-checks every `gold_sources` entry against the
sections actually on disk, so a question referencing a missing cell fails loudly
rather than silently scoring as a retrieval failure.

## Schema

```json
{
  "id": "q001",
  "question": "Which segment did Microsoft identify as its largest source of revenue in fiscal 2023?",
  "tier": 1,
  "subtier": null,
  "expected_behavior": "answer",
  "gold_answer": "Intelligent Cloud was Microsoft's largest revenue segment in fiscal 2023.",
  "gold_sources": [{"company": "MSFT", "year": 2023, "section": "mdna"}],
  "gold_supporting_chunks": ["MSFT_2023_mdna_3"],
  "notes": "Free-form context that doesn't fit the schema."
}
```

| Field | Meaning |
|---|---|
| `expected_behavior` | `answer` or `abstain`. The harness scores the two regimes differently. Tier 4 is always `abstain`; tiers 1–3 always `answer`. |
| `gold_answer` | 1–3 sentences, verified against the filing by a human. For abstaining items this is the exact `ABSTENTION_RESPONSE` string. |
| `gold_sources` | Which filings should ground the answer. Drives retrieval scoring: did we retrieve anything from these? Empty for abstaining items. |
| `gold_supporting_chunks` | Specific chunk IDs that support the answer. Drives faithfulness scoring. Populated *after* an index build, since chunk IDs depend on chunking output. |
| `notes` | Anything worth recording — ambiguity resolved, why an item is tricky, verification caveats. |
| `evidence` | *Optional.* Verbatim passages the gold answer rests on. The validator checks each one appears word-for-word in a cited section, so a quote cannot be invented or paraphrased. Kept in the final dataset so any reviewer can re-verify an item in seconds. |

## Workflow: drafts → review → dataset

Items are written in batches into `drafts/`, reviewed by a human, and only then
moved into `questions.jsonl`. Tiers 1 and 4 are drafted with tooling assistance
and every draft carries `evidence`; tiers 2 and 3 are written by hand.

```bash
python -m scripts.validate_golden --path data/golden/drafts/tier1_batch01.jsonl
```

Reviewing a draft means checking three things: the gold answer follows from the
evidence, the question is unambiguous, and it isn't one of the anti-patterns
below. The validator has already ruled out the fourth failure mode, a quote that
isn't really in the filing.

## How questions are sourced

Questions are grounded by searching the extracted section text directly:

```bash
python -m scripts.corpus_search --company MSFT --year 2023 --section mdna "cloud revenue"
```

**Deliberately not** by asking the RAG system's retriever what it can find. A
dataset sourced from the retriever would consist of questions selected for being
easy to retrieve, inheriting the blind spots of the very system it is meant to
audit — retrieval recall would score far better than it deserves. Independence
between the measuring instrument and the system under test is the whole point.

## Quality bar

Before an item is accepted, all four must hold:

1. The gold answer is verifiable against the source filing in under 60 seconds.
2. The question is unambiguous — two reasonable readers interpret it the same way.
3. For abstention items: it is genuinely unanswerable, not merely hard.
4. For tier 3: it *really* needs multiple documents; one filing does not suffice.

## Anti-patterns

`validate_golden.py` flags most of these automatically.

- **Yes/no questions** — trivially gamed, impossible to score for nuance.
- **Questions containing their own answer** — "What competitive risks did Meta
  cite from TikTok?" presupposes TikTok was cited.
- **Numerical precision traps** — exact-figure matching is its own scoring
  rabbit hole; prefer qualitative or rounded claims.
- **Undated temporal references** — "currently" is undefined; anchor to a fiscal year.
- **Compound questions** — split them into separate items.

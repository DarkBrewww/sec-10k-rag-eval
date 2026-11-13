# Project: sec-10k-rag-eval

A from-scratch RAG system over SEC 10-K prose (Item 1A and Item 7 for MSFT, GOOGL and META, filed 2023 and 2024), built as the test subject for an LLM evaluation harness. The harness is the point of the project; the RAG pipeline exists so there is something to measure. Python 3.10+, ChromaDB, OpenAI embeddings, Anthropic generator, Gemini judge (later). No LangChain or LlamaIndex, on purpose.

## Commands

Run everything from the repo root as modules (`python -m scripts.x`), never `python scripts/x.py`, or the `src` imports break.

- Setup: `python -m venv .venv`, activate it, `pip install -r requirements.txt`, `cp .env.example .env`
- Build corpus + index: `python -m scripts.build_index` (downloads ~200MB from EDGAR and spends OpenAI credits; ask first)
- Query: `python -m scripts.ask "question"`, add `--show-chunks` to inspect retrieval, `--top-k N` to vary k
- Search source text directly: `python -m scripts.corpus_search --company MSFT --year 2023 --section mdna "cloud revenue"`
- Validate golden data: `python -m scripts.validate_golden` (add `--path <file>` for a draft, `--check-chunks`, `--strict`)
- Syntax check (there is no test suite yet): `python -m compileall -q src scripts`

## Conventions

- Every tunable (models, prompts, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, cost caps, `ABSTENTION_RESPONSE`) lives in `src/config.py` and nowhere else. The harness will sweep these one at a time, so a magic number anywhere else is a bug.
- Keep `src/rag.py` split into `retrieve()`, `generate()` and `answer()`. The harness scores retrieval and generation separately.
- Abstention is detected by exact match on `config.ABSTENTION_RESPONSE`. Never reword it in one place only.
- Judge and generator must stay in different model families. Don't make a Claude model the primary judge.
- No new dependencies without asking. No RAG frameworks, ever.
- Extraction is a deliberately simple heuristic (real `Item N.` headers, longest span). Fix it only for a concrete filing that breaks it, and say which one.
- The code is not ruff/black formatted. Don't reformat files beyond the lines you change.

## Cost discipline

The whole project runs on about $15. Anything that calls OpenAI, Anthropic or Gemini costs real money.

- Ask before `build_index`, any loop over many questions, or any eval run beyond a handful of `ask` calls.
- New eval code must cache deterministic calls, estimate spend up front, abort past `DEFAULT_MAX_COST_USD`, and print per-run cost.

## Golden dataset

`data/golden/` is hand-curated ground truth and the only tracked data. Its rules load from `.claude/rules/golden-dataset.md` when you touch those files. Short version: drafts go in `data/golden/drafts/`, a human reviews them, and only then do items move into `questions.jsonl`. Claude never adds to `questions.jsonl` without being told an item passed review.

## Workflow

- Plan first for anything touching more than two files or the extraction logic.
- A finding like the Meta AI-competition retrieval miss is a tracked result, not something to patch with a threshold. Ask before "fixing" anything the README lists as deliberately unfixed.
- Commit subject style: `Area: what changed` (e.g. `Golden dataset: tier 1 batch 1 drafts and verbatim-evidence check`), then a body saying why. One logical change per commit.
- Never credit Claude in commits or PRs. A hook enforces this.

## Gotchas

- `data/*` is gitignored except `data/golden/`. A fresh clone has no corpus, so `validate_golden` reports every item as "not in the corpus" until `build_index` has run. That is not a dataset error.
- Fiscal years are not a clean grid: MSFT has FY2023 and FY2024, GOOGL and META have FY2022 and FY2023. FY2023 is the only year all three share.
- `SEC_EDGAR_USER_AGENT` must be set in `.env` or EDGAR refuses downloads.
- Code comments reference `docs/GOLDEN_DATASET_SPEC.md` and `docs/COST_DISCIPLINE.md`, which don't exist yet. `data/golden/README.md` and the README's cost section are the current specs.
- `src/config.py` creates the `data/` subfolders on import.

## More context

- Project overview, design decisions, roadmap: @README.md

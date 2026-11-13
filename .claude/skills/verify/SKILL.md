---
name: verify
description: Check that the repo is in a committable state - syntax check, golden dataset validation, and a cheap RAG smoke test when pipeline code changed. Use before committing, before saying a change is done, or when asked to verify or check the work.
allowed-tools: Bash(python -m compileall *) Bash(python -m scripts.validate_golden *) Bash(python -m scripts.validate_golden) Bash(python -m scripts.ask *) Bash(git status *) Bash(git diff *) Read
---

Changed files right now:
!`git status --short`

Run these in order and stop at the first failure, reporting it with the exact output.

1. Syntax: `python -m compileall -q src scripts`. There is no test suite yet, so this is the floor.
2. Golden data: for every changed file under `data/golden/` ending in `.jsonl`, run `python -m scripts.validate_golden --path <file>`. If `data/extracted/` has no `*.json` files, the corpus isn't built and every item will fail the corpus check; report "golden validation skipped: no corpus" instead of treating it as a failure.
3. Smoke test, only if `src/rag.py`, `src/index.py`, `src/extract.py` or `src/config.py` changed and `data/chroma/` exists. Run exactly two questions (costs well under a cent):
   - `python -m scripts.ask "How did Microsoft describe its cloud business performance?"` must return an answer with `[MSFT ...]` citations.
   - `python -m scripts.ask "What is Apple's strategy for the automotive market?"` must return exactly `config.ABSTENTION_RESPONSE`.
   If `data/chroma/` is missing, say the smoke test was skipped and why.

Report one line per step: passed, failed (with output), or skipped (with reason). Don't fix anything inside this skill unless asked.

#!/usr/bin/env python3
"""PostToolUse hook: re-validate a golden dataset file every time Claude edits it.

Runs `python -m scripts.validate_golden --path <file>` on any .jsonl under
data/golden/. On failure, exits 2 so the validator's errors go straight back to
Claude to fix. If the corpus isn't built yet (data/extracted/ is empty), every
item would fail the corpus cross-check, so the hook says so and stands down.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def note(msg: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    sys.exit(0)


def main() -> None:
    event = json.load(sys.stdin)
    raw = (event.get("tool_input") or {}).get("file_path") or ""
    if not raw:
        sys.exit(0)

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        rel = path.relative_to(root)
    except ValueError:
        sys.exit(0)
    if rel.parts[:2] != ("data", "golden") or path.suffix != ".jsonl":
        sys.exit(0)

    if not any((root / "data" / "extracted").glob("*.json")):
        note(
            f"Golden validator skipped for {rel.as_posix()}: data/extracted/ is empty, so every "
            "gold_source would fail the corpus check. Build the corpus first "
            "(python -m scripts.build_index, ask before running) to validate."
        )

    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_golden", "--path", str(path)],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode != 0:
        sys.stderr.write(
            f"validate_golden failed for {rel.as_posix()}. Fix these before moving on:\n"
            + result.stdout + result.stderr
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"validate_golden_on_edit hook error: {exc!r}\n")
        sys.exit(1)

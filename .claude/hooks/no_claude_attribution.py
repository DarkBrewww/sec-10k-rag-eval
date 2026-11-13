#!/usr/bin/env python3
"""PreToolUse guard: Claude never shows up as an author, co-author or credit line.

Blocks (exit 2, reason sent back to Claude) when a tool call would put any of
these on the git or GitHub record:

  - a Co-Authored-By trailer naming Claude or Anthropic
  - a "Generated with Claude Code" footer or a claude.ai/code session link
  - a Claude-Session trailer
  - commits about to be pushed whose message, author or committer carries the above

Checks Bash commands that run git or gh (inline -m text, -F/--file and
--body-file message files, and the outgoing commits on `git push`), plus any
GitHub MCP tool call. Anything else passes through untouched.

Hook contract: JSON on stdin; exit 0 allows, exit 2 blocks with stderr fed back
to Claude, exit 1 is a non-blocking error (the guard itself broke, tool runs).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

CREDIT = re.compile(
    r"co-authored-by:[^\n]*(?:claude|anthropic)[^\n]*"
    r"|noreply@anthropic\.com"
    r"|generated with \[?claude"
    r"|claude\.(?:ai|com)/code"
    r"|^\s*claude-session:",
    re.IGNORECASE | re.MULTILINE,
)
IDENTITY = re.compile(r"claude|anthropic", re.IGNORECASE)
GIT_OR_GH = re.compile(r"(?:^|[\s;&|(])(?:git|gh)(?:\.exe)?\s")
# Only commands that write a message onto the record get their text scanned, so
# read-only commands like `git log --grep "Co-Authored-By: Claude"` pass.
WRITES = re.compile(
    r"\bgit(?:\.exe)?\b[^;&|]*?\b(?:commit|tag|notes|merge|revert|cherry-pick)\b"
    r"|\bgh(?:\.exe)?\b[^;&|]*?\b(?:pr|issue|release)\s+(?:create|edit|comment|merge)\b"
    r"|\bgh(?:\.exe)?\s+api\b"
)
MCP_WRITES = re.compile(r"create|update|edit|push|commit|merge|comment|review|write", re.IGNORECASE)
PUSH = re.compile(r"\bgit(?:\.exe)?\b(?:\s+-C\s+\S+)?[^;&|]*?\bpush\b")
FILE_FLAGS = {"-F", "--file", "--body-file"}


def found(text: str | None) -> list[str]:
    return sorted({m.group(0).strip() for m in CREDIT.finditer(text or "")})


def tokens(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return cmd.split()


def work_dir(cmd: str, cwd: str) -> Path:
    """Best guess at where git will run: last `cd X` or `git -C X`, else the session cwd."""
    base = Path(cwd or os.getcwd())
    targets = re.findall(r"""(?:\bcd|\bgit(?:\.exe)?\s+-C)\s+("[^"]+"|'[^']+'|[^\s;&|]+)""", cmd)
    if targets:
        p = Path(os.path.expanduser(targets[-1].strip("\"'")))
        return p if p.is_absolute() else base / p
    return base


def message_files(toks: list[str], where: Path) -> list[Path]:
    paths = []
    for i, tok in enumerate(toks):
        val = None
        if tok in FILE_FLAGS and i + 1 < len(toks):
            val = toks[i + 1]
        elif tok.startswith(("--file=", "--body-file=")):
            val = tok.split("=", 1)[1]
        if val and val != "-":
            p = Path(os.path.expanduser(val))
            paths.append(p if p.is_absolute() else where / p)
    return paths


def git(where: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(where), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
    )


def outgoing_problems(cmd: str, where: Path) -> list[str]:
    """Commits that exist locally but on no remote: what a push would publish."""
    if git(where, "rev-parse", "--git-dir").returncode != 0:
        return []
    refs = ["HEAD"]
    after_push = tokens(cmd.split("push", 1)[1]) if "push" in cmd else []
    for tok in after_push:
        if tok.startswith("-"):
            continue
        src = tok.lstrip("+").split(":", 1)[0]
        if src and git(where, "rev-parse", "--verify", "--quiet", src + "^{commit}").returncode == 0:
            refs.append(src)
    log = git(where, "log", "--format=%h%x00%an <%ae>%x00%cn <%ce>%x00%B%x1e", *refs, "--not", "--remotes")
    problems = []
    for rec in log.stdout.split("\x1e"):
        parts = rec.strip("\n").split("\x00")
        if len(parts) < 4:
            continue
        sha, author, committer, body = parts[0], parts[1], parts[2], parts[3]
        issues = found(body)
        if IDENTITY.search(author):
            issues.append(f"author is {author}")
        if IDENTITY.search(committer):
            issues.append(f"committer is {committer}")
        if issues:
            problems.append(f"{sha}: " + "; ".join(issues))
    return problems


def block(lines: list[str]) -> None:
    sys.stderr.write(
        "BLOCKED by no_claude_attribution hook. Adwait's rule: Claude is never credited "
        "on anything pushed to his GitHub (no Co-Authored-By trailer, no 'Generated with "
        "Claude Code' footer, no session links, no Claude author or committer).\n\nFound:\n"
        + "\n".join(f"  - {line}" for line in lines)
        + "\n\nFix: drop those lines from the commit message or PR body and retry. For commits "
        "already made, rewrite them before pushing: `git commit --amend -m \"<clean message>\"` "
        "for the last one, or for a range: FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f "
        "--msg-filter \"sed -E '/[Cc]o-[Aa]uthored-[Bb]y:.*([Cc]laude|[Aa]nthropic)/d; "
        "/[Gg]enerated with \\[?[Cc]laude/d; /[Cc]laude-[Ss]ession:/d'\" <base>..HEAD\n"
        "If a commit's author is Claude, reset it with `git commit --amend --reset-author --no-edit`.\n"
    )
    sys.exit(2)


def main() -> None:
    event = json.load(sys.stdin)
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}

    if tool != "Bash":
        if re.search(r"github|\bgit\b", tool, re.IGNORECASE) and MCP_WRITES.search(tool):
            hits = found(json.dumps(tool_input))
            if hits:
                block([f"{tool} input contains: {h}" for h in hits])
        sys.exit(0)

    cmd = tool_input.get("command", "")
    if not GIT_OR_GH.search(" " + cmd):
        sys.exit(0)

    where = work_dir(cmd, event.get("cwd", ""))
    problems = []
    if WRITES.search(cmd):
        problems += [f"command text contains: {h}" for h in found(cmd)]
        for path in message_files(tokens(cmd), where):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                problems += [f"{path.name} contains: {h}" for h in found(text)]
    if PUSH.search(cmd):
        problems += [f"outgoing commit {p}" for p in outgoing_problems(cmd, where)]

    if problems:
        block(problems)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # the guard broke; say so without blocking the tool
        sys.stderr.write(f"no_claude_attribution hook error (not enforced this call): {exc!r}\n")
        sys.exit(1)

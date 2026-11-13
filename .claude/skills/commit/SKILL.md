---
name: commit
description: Verify, then commit the current changes with a message in this repo's style. Only when Adwait types /commit.
disable-model-invocation: true
argument-hint: "[optional note on intent]"
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git add *) Bash(git commit *) Bash(python -m compileall *) Bash(python -m scripts.validate_golden *) Read
---

Intent from Adwait, if any: $ARGUMENTS

Current state:
!`git status --short`
!`git diff --stat HEAD`

Recent subjects, for style:
!`git log -5 --format=%s`

1. Run the `verify` skill's checks. If anything fails, stop and report; don't commit.
2. If the changes contain more than one logical change, say so and propose how to split them before committing anything.
3. Stage only the files that belong to this change. Never stage `.env`, anything under `data/` other than `data/golden/`, or `CLAUDE.local.md`.
4. Write the message:
   - Subject: `Area: what changed`, imperative, under 72 characters. Areas in use: `Golden dataset`, `Extraction`, `Retrieval`, `Generation`, `Index`, `Eval harness`, `Config`, `Docs`, `Tooling`.
   - Blank line, then a short body in plain prose explaining why, wrapped at 72. No bullet lists unless the change genuinely has separate parts. No em dashes.
   - No Co-Authored-By trailer, no "Generated with Claude Code" line, no session link. Nothing that credits Claude.
5. Commit with `git commit -F <tempfile>` or a heredoc, then show `git log -1 --stat`.
6. Don't push. Pushing is Adwait's call.

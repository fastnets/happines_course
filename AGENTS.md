# AGENTS.md

## Purpose
This file defines repository-level instructions for Codex.
It is not a Python module and is not imported in code.

## Working Language
- Reply to the user in Russian by default.
- Keep answers concise and practical.

## Collaboration Rules
- Before editing code, briefly state what will be changed.
- After changes, report:
  - what was changed,
  - which files were touched,
  - how to run/check result.
- If information is missing, ask one clear question.

## Code Change Rules
- Prefer minimal, targeted edits.
- Do not refactor unrelated code unless asked.
- Preserve existing project structure and style.
- Add comments only where logic is non-obvious.

## Task Materials
Use these files as the main context for current tasks:
- `docs/index.md` (entry point)
- `docs/TASK.md` (goal and acceptance criteria)
- `docs/CONSTRAINTS.md` (limits and must-follow rules)

If these files are missing, propose creating them from templates.

## Safety
- Do not run destructive commands without explicit user request.
- If a risky step is required, explain the risk first.

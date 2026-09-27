---
name: refactor-file
description: "Use when: refactoring the currently opened file, improving readability, removing duplication, simplifying logic, or applying Python best practices without changing behavior."
---

# Refactor File

Use this skill to improve the active file while preserving its behavior and keeping the change set small and reviewable.

## Goal

Refactor the currently opened file using professional engineering practices:
- improve clarity and maintainability
- reduce duplication and complexity
- preserve behavior and public interfaces
- align with the project’s Python style and conventions

## Workflow

1. Read the active file and identify the smallest meaningful refactor.
2. Prioritize correctness over cleverness. Do not change behavior unless the user explicitly asks for it.
3. Improve one area at a time:
   - naming and readability
   - function decomposition
   - guard clauses and simpler branching
   - constant extraction for magic values
   - import cleanup and unused code removal
   - type hints where they improve clarity
   - docstrings and inline comments only when they add real value
4. Keep the refactor focused on the current file. Avoid unrelated rewrites or broad architectural changes.
5. Preserve public APIs, return values, and side effects unless the user requests a change.
6. If the file is part of a module with tests, run the relevant targeted validation after the refactor.

## Python best practices to apply

- Prefer explicit, readable code over terse or overly clever constructs.
- Keep functions small and single-purpose.
- Replace repeated logic with helper functions or constants where appropriate.
- Favor early returns to reduce nesting.
- Use clear parameter names and idiomatic Python patterns.
- Keep imports sorted and remove unused imports.
- Follow project conventions from Ruff and pytest.
- Match the project’s Python version and typing style.

## Guardrails

- Do not add features unrelated to the refactor.
- Do not broaden scope into other files unless essential.
- Do not introduce new dependencies or major design changes without clear need.
- Do not reduce readability to save a few lines.
- Do not change runtime behavior while “cleaning up” code.

## Validation

After the refactor, verify the result with the smallest relevant command:
- run targeted pytest checks if the file has direct test coverage
- otherwise run a focused syntax or project validation command

Examples:
- `pytest tests/test_config.py`
- `ruff check src/tracking_visualized`
- `python -m compileall src`

## Deliverable

Provide a concise summary of:
- what was improved
- what behavior was preserved
- any validation that was run
- any remaining follow-ups, if relevant

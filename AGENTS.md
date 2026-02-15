# Agent Operating Instructions (Talmudpedia)

Last Updated: 2026-02-15

## Documentation Hygiene (Context-dependent)
- When asked for a chat summary, unless explicitly requested otherwise, create a markdown file in `backend/documentations/summary/` with a descriptive filename and include a "Last Updated" date.
- If needed, at the **start of a task**, list the files in the documentation directory to orient yourself. In this repo, check:
  - `backend/documentations/`
  - If a top-level `documentation/` or `documentations/` exists, list that too.
- **Do not read every doc**. Open only the files that look relevant based on their names and the task scope.
- If needed, at the **end of the task**, list the documentation files again and update any relevant doc(s):
  - Add or remove details so the docs reflect the work done.
  - Keep edits concise and focused (don't over-edit).
- If nothing is relevant, say so explicitly in your response.
- If you notice **documentation overlap** (two files covering the same topic), you may **propose a merge/refactor** of the docs for clarity and reduced duplication.
- Ensure **doc filenames are explicit and descriptive** so a reader can understand the topic without opening the file.
- **Every edited `.md` file must include a "Last Updated" date** (e.g., `Last Updated: 2026-02-14`) so contradictions can be resolved by recency.
- If you detect **contradictions between docs**, **raise it immediately** in your response so it can be corrected.

## Architecture Reference (Required when making architectural decisions)
- The `code_architect/architecture_tree.md` file is a **curated backend-only map** used for fast architectural orientation.
- **Context budget target** for this file: roughly **120-180 lines** (hard ceiling: **220 lines**).
- **No frontend tree in this file**. Keep frontend architecture elsewhere if needed.

### Granularity Rules
- List **core backend code** at file level (files directly used for architecture decisions).
- List **supporting systems** at directory level only.
  - Examples: `backend/alembic/`, `backend/tests/`, `backend/scripts/`, `backend/documentations/`.
- Do **not** list every file in tests, scripts, migrations, docs, or generated directories.

### Exclusion Rules
- Exclude non-architectural and high-noise entries:
  - Dotfiles/secrets/logs (`.env`, credential JSON, `*.log`).
  - Generated/cache artifacts (`__pycache__/`, `.pytest_cache/`).
  - Temporary outputs and machine-generated indexes.

### Agent Retrieval Workflow
1. Read `code_architect/architecture_tree.md` first.
2. Open only the specific files/directories needed for the task.
3. If required files are missing from the tree, inspect the filesystem minimally, then update the tree only if architecture-critical.

### Update Policy
- Update `code_architect/architecture_tree.md` when creating/deleting architecture-critical files.
- During refactors, update only the impacted branches of the tree.
- Avoid churn edits (do not edit only to reorder/reformat unless clarity materially improves).

### Frontend Layering (Enforced)
- Strictly forbid creating local `types.ts` or `api.ts` files within page directories.
- All API integrations, service logic, and shared types must reside in `frontend-reshet/src/services/` to ensure a single source of truth and avoid type collisions.

## File Size Guardrail (Enforced)
- Do not let source files grow beyond **800 lines**.
- If a file approaches or exceeds 800 lines, split it into cohesive modules grouped by responsibility (schemas, services/helpers, routes, etc.).
- Preserve stable import paths when refactoring large files (for example by keeping a thin composition/compatibility module when needed).

## Tests Organization (Required when asked to add/expand tests)
- All new tests must live under the project test roots:
  - Backend: `backend/tests/`
  - Frontend: `frontend-reshet/src/__tests__/`
- **Group tests by feature/functionality**, not by layer or file type.
  - Create one directory per feature you are testing.
  - Example: `backend/tests/agent_execution/`, `backend/tests/graph_compiler/`, `frontend-reshet/src/__tests__/agent_builder/`.
- Each feature test directory must include a **`test_state.md`** file that records:
  - Scope of the feature
  - Test files present
  - Key scenarios covered
  - Last run command + date/time + result (pass/fail)
  - Known gaps or follow-ups
- When you add or change tests, **update `test_state.md`** accordingly.
- If multiple distinct features are tested, split into multiple feature directories.

## Test Execution (When tests are requested)
- If the user asks you to run tests, **run them** and report the exact command and results.
- If tests cannot be run, explain why (missing env, credentials, time, etc.).

## Suggestions for Continuity
- If you repeatedly update the same doc/test structures, consider proposing a Codex skill to automate the workflow.

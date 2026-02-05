# Agent Operating Instructions (Talmudpedia)

Last Updated: 2026-02-04

## Documentation Hygiene (Context-dependent)
- When asked for a chat summary, unless explicitly requested otherwise, create a markdown file in `backend/documentations/summary/` with a descriptive filename and include a “Last Updated” date.
- If needed, at the **start of a task**, list the files in the documentation directory to orient yourself. In this repo, check:
  - `backend/documentations/`
  - If a top-level `documentation/` or `documentations/` exists, list that too.
- **Do not read every doc**. Open only the files that look relevant based on their names and the task scope.
- If needed, at the **end of the task**, list the documentation files again and update any relevant doc(s):
  - Add or remove details so the docs reflect the work done.
  - Keep edits concise and focused (don’t over‑edit).
- If nothing is relevant, say so explicitly in your response.
- If you notice **documentation overlap** (two files covering the same topic), you may **propose a merge/refactor** of the docs for clarity and reduced duplication.
- Ensure **doc filenames are explicit and descriptive** so a reader can understand the topic without opening the file.
- **Every edited `.md` file must include a “Last Updated” date** (e.g., `Last Updated: 2026-02-04`) so contradictions can be resolved by recency.
- If you detect **contradictions between docs**, **raise it immediately** in your response so it can be corrected.

## Architecture Reference (Required when making architectural decisions)
- The `code_architect/architecture_tree.md` file contains the current backend architecture. No need for frontend tree.
- The tree should be **as detailed as needed** for two goals:
  - Understanding the codebase architecture (avoid gaps or incorrect assumptions).
  - Knowing, at a high level, what exists in the codebase.
- **Granularity rule**:
  - List **core code** at the file level (things you read/modify or rely on for architecture).
  - List **supporting systems** at the directory level only (e.g., `backend/alembic/` should appear as a directory; do **not** enumerate individual migration files unless they are central to the architecture decision).
- **When you create or delete files**, update `code_architect/architecture_tree.md` to keep it current within the above granularity rules.
- **Before making architecture decisions**, consult `code_architect/architecture_tree.md` to align with current structure.
- **Frontend Layering**: Strictly forbid creating local `types.ts` or `api.ts` files within page directories. All API integrations, service logic, and shared types must reside in `src/services/` to ensure a single source of truth and avoid type collisions.

## Tests Organization (Required when asked to add/expand tests)
- All new tests must live under the project test roots:
  - Backend: `backend/tests/`
  - Frontend: `frontend/src/__tests__/`
- **Group tests by feature/functionality**, not by layer or file type.
  - Create one directory per feature you are testing.
  - Example: `backend/tests/agent_execution/`, `backend/tests/graph_compiler/`, `frontend/src/__tests__/agent_builder/`.
- Each feature test directory must include a **`test_state.md`** file that records:
  - Scope of the feature
  - Test files present
  - Key scenarios covered
  - Last run command + date/time + result (pass/fail)
  - Known gaps or follow‑ups
- When you add or change tests, **update `test_state.md`** accordingly.
- If multiple distinct features are tested, split into multiple feature directories.

## Test Execution (When tests are requested)
- If the user asks you to run tests, **run them** and report the exact command and results.
- If tests cannot be run, explain why (missing env, credentials, time, etc.).

## Suggestions for Continuity
- If you repeatedly update the same doc/test structures, consider proposing a Codex skill to automate the workflow.

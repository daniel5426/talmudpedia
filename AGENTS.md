# Agent Operating Instructions (Talmudpedia)

Last Updated: 2026-03-11

## Documentation Hygiene (Context-dependent)
- The repo-level documentation hub is `docs/`.
- Before creating or editing long-lived documentation, check these canonical entry points first:
  - `docs/README.md`
  - `docs/references/canonical_docs_guide.md`
  - `ARCHITECTURE.md`
  - `code_architect/architecture_tree.md`
- When asked for a chat summary, unless explicitly requested otherwise, create a markdown file in `backend/documentations/summary/` with a descriptive filename and include a "Last Updated" date.
  - Treat `backend/documentations/summary/` as a legacy mixed-history area, not as a canonical docs root.
- If needed, at the **start of a task**, list the files in the documentation directory to orient yourself. In this repo, check:
  - `docs/`
  - `backend/documentations/`
  - If a top-level `documentation/` or `documentations/` exists, list that too.
- **Do not read every doc**. Open only the files that look relevant based on their names and the task scope.
- Prefer `docs/` for current canonical documentation.
- Treat many files in `backend/documentations/` as legacy or historical unless they are explicitly still serving as focused references.
- If needed, at the **end of the task**, list the documentation files again and update any relevant doc(s):
  - Add or remove details so the docs reflect the work done.
  - Keep edits concise and focused (don't over-edit).
- For new long-lived docs, place them by intent under `docs/`:
  - `docs/design-docs/` for architecture and design
  - `docs/product-specs/` for canonical behavior/specs
  - `docs/references/` for guides and lookup docs
  - `docs/exec-plans/` for active/completed execution plans
  - `docs/generated/` for generated artifacts
- If nothing is relevant, say so explicitly in your response.
- If you notice **documentation overlap** (two files covering the same topic), you may **propose a merge/refactor** of the docs for clarity and reduced duplication.
- Ensure **doc filenames are explicit and descriptive** so a reader can understand the topic without opening the file.
- **Every edited `.md` file must include a "Last Updated" date** (e.g., `Last Updated: 2026-02-14`) so contradictions can be resolved by recency.
- If you detect **contradictions between docs**, **raise it immediately** in your response so it can be corrected.

### Legacy Docs Policy
- `backend/documentations/Plans/` is now a legacy execution-plan folder.
- `backend/documentations/summary/` is now a legacy mixed-history folder.
- Use `docs/exec-plans/legacy_plan_and_summary_map.md` when deciding how old plan/summary files map into the new structure.
- When replacing a legacy doc with a new canonical doc, prefer turning the old file into a short pointer instead of leaving competing canonical content in both places.

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

## Execution Logging (When requested)
- If the user asks to log every step of an agent or process run, prefer the shared execution-event logging path over ad-hoc prints or one-off debug files.
- Use `backend/app/agent/execution/trace_recorder.py` as the reusable logging mechanism and read logs through `GET /agents/runs/{run_id}/events` when applicable.
- Keep new logging reusable across runtimes and subsystems by preserving a consistent event shape and shared run/trace identifiers.

## Fallback Policy
- Keep fallbacks to a minimum across the app.
- Prefer explicit canonical contracts over permissive recovery behavior.
- Only add a fallback when it is clearly necessary, highly useful, and the tradeoff is documented.

## Clean-Cut Change Policy
- For new work, default to clean cuts over legacy compatibility.
- Do **not** preserve old-data migrations, legacy compatibility layers, fallback behavior, or adapter shims unless the user explicitly asks for them.
- Prefer removing obsolete code paths instead of keeping dual architectures alive.
- Optimize for clean architecture, runtime efficiency, and maintainability over backward compatibility by default.
- If you discover cleanup that is outside the current requested scope, do **not** silently include it; explicitly alert the user and ask whether they want that cleanup done.

# Documentation Migration Map

Last Updated: 2026-03-10

This document maps the current documentation layout to the proposed repo-level docs system.

## Current Problems
- `backend/documentations/` mixes canonical specs, plans, debug notes, summaries, and historical snapshots.
- Most docs are backend-scoped even when the subject is repo-wide or product-wide.
- Many filenames are descriptive, but the folder structure does not consistently communicate document intent.
- Some docs behave like indexes, but there is no single repo-level documentation entry point.
- `backend/ARCHITECTURE.md` appears stale relative to `code_architect/architecture_tree.md` and current backend modules.

## Target Mapping
- `backend/documentations/auth/`
  - Mostly `docs/design-docs/` for auth architecture and `docs/references/` for the auth read-order guide.
- `backend/documentations/architecture/`
  - `docs/design-docs/`
- `backend/documentations/Plans/`
  - `docs/exec-plans/active/` or `docs/exec-plans/completed/` depending on status.
- `backend/documentations/Debug/`
  - Keep temporary debug notes out of the canonical docs tree where possible. If they must be preserved, move them under `docs/references/debug/` in a later step.
- `backend/documentations/summary/`
  - Split by intent:
  - Handoffs and implementation notes go to `docs/exec-plans/completed/` if historical.
  - Canonical behavior extracted from summaries should move to `docs/design-docs/` or `docs/product-specs/`.
  - Generated dumps belong in `docs/generated/`.
- Standalone specs in `backend/documentations/*.md`
  - Move to `docs/product-specs/`, `docs/design-docs/`, or `docs/references/` based on intent.

## Migration Principles
1. Do not mass-move files immediately.
2. Create the repo-level structure first.
3. For each future doc edit, move or rewrite the document into the correct destination.
4. Leave a short pointer in the old location only when necessary.
5. Prefer extracting canonical truth from old summaries instead of renaming summaries into specs.

## Suggested Naming Conventions
- Design docs
  - `domain_or_subsystem_design.md`
  - `YYYYMMDD_short_decision_record.md` if date ordering matters
- Product specs
  - `feature_name_spec.md`
- Execution plans
  - `feature_or_project_plan.md`
- Generated
  - `artifact_name_YYYYMMDD.ext`
- References
  - `topic_reference.md`
  - `topic_docs_guide.md`

## Proposed Next Moves
- Refresh or replace the stale backend architecture overview.
- Create one repo-level documentation index for current canonical docs.
- Pick 5 to 10 high-value backend docs and re-home them into the new structure.
- Define a rule for whether `backend/documentations/summary/` remains temporary or is gradually retired.

## Progress So Far
- A repo-level `docs/` hub now exists.
- Canonical backend architecture and agent execution docs now live in `docs/design-docs/`.
- The overlapping backend architecture overview in `backend/ARCHITECTURE.md` has been reduced to a legacy pointer.
- The next overlap cluster to retire is the older backend/platform current-state docs under `backend/documentations/`.

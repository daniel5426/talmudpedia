# Repository Architecture

Last Updated: 2026-03-10

This file is the repo-level architecture entry point for Talmudpedia.

## Current Architecture Anchors
- `code_architect/architecture_tree.md`
  - Canonical fast-read backend architecture map for implementation work.
- `backend/ARCHITECTURE.md`
  - Legacy backend architecture overview that should be refreshed or replaced.
- `docs/design-docs/`
  - Long-lived architecture and design documents.
- `docs/product-specs/`
  - Canonical product behavior and contracts.

## Repository Shape
- `frontend-reshet/`
  - Frontend application and UI tests.
- `backend/`
  - FastAPI backend, agent runtime, RAG pipeline system, workers, and backend tests.
- `docs/`
  - Repo-level documentation hub organized by document intent.

## Documentation Policy
- Use `docs/` as the primary home for new long-lived documentation.
- Keep architecture decisions in `docs/design-docs/`.
- Keep implementation plans in `docs/exec-plans/`.
- Keep generated artifacts separate from hand-written documentation.
- Treat old documents in `backend/documentations/` as legacy locations until they are gradually migrated.

## Immediate Follow-Up
The backend architecture story currently spans multiple files with different ages. The next cleanup should consolidate the current backend architecture description so it does not conflict with the curated architecture tree.

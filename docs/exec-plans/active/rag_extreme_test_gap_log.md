# RAG Extreme Test Gap Log

Last Updated: 2026-03-31

## Purpose

This file is the running log for issues discovered during the RAG extreme test campaign.

Do not put fixes here. Log only:
- reproducible bugs
- contract mismatches
- missing validations
- runtime failures
- flaky behavior
- builder/runtime inconsistencies
- product/UX issues

## Fix Triage

### Safe For Autonomous Fix

- None currently open in this bucket.

### Needs Product Decision Before Fix

- 2026-03-30: Registry-visible operators without executor implementations need a product choice before the fix lands. Safe implementations are either: hide/disable them from builder/catalog until supported, or fully implement them. Choosing between those two changes the user-facing surface.
- 2026-03-30: Any later cleanup that merges, removes, or simplifies overlapping RAG node surfaces should wait for product direction. That is UX design, not just bug repair.
- 2026-03-30: Any change to the long-term local backend strategy for pgvector vs dedicated vector DB should be treated as an environment/product decision, not folded into a bug-fix pass implicitly.

## Environment Findings

- 2026-03-30: Docker was initially unavailable from the session. Resolved by starting Docker Desktop.
- 2026-03-30: Local dev Postgres at `127.0.0.1:5432/talmudpedia_dev` does not have the `vector` extension, so live pgvector coverage must use the dedicated local pgvector container at `127.0.0.1:65432`.
- 2026-03-30: Local backend API was not running on `http://127.0.0.1:8000` during environment preparation.

## Runtime Bugs

- 2026-03-30: Live embedding-backed pgvector retrieval smoke did not complete within an automation-friendly window (about 45s) and had to be stopped manually. This currently blocks using the live embedding path as part of a tight autonomous regression loop.

## Contract Gaps

- None currently open in this bucket after the RAG node-catalog refactor landed executor coverage for the canonical visible nodes.

## UX / Product Gaps

## Open Questions

- Should pgvector remain split between the app DB and the dedicated local vector DB for testing, or should the platform move toward one canonical local pgvector path?
- Which RAG nodes are intended to remain low-level expert surfaces, and which are expected to be simplified for normal admin users?
- Is the live embedding latency coming from provider/model resolution, outbound API latency, or missing request timeouts in the embedding adapter path?

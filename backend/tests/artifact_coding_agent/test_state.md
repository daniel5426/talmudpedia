# Artifact Coding Agent Tests

Last Updated: 2026-03-11

## Scope

Track backend coverage for the direct-use artifact coding agent wrapper, session state, and function tool pack.

## Test Files Present

- none yet

## Key Scenarios Intended

- seeded public `artifact-coding-agent` exists and is published
- wrapper prompt submission creates shared runs and `artifact_admin` threads
- create-mode session scoping via `draft_key`
- saved artifact session scoping via `artifact_id`
- relinking from `draft_key` to `artifact_id`
- session snapshot mutation without direct artifact row writes
- canonical artifact test execution from session draft state

## Last Run

- Command: not run yet
- Date: 2026-03-11
- Result: pending

## Known Gaps

- backend automated tests for the new session/router/tool flow still need to be added

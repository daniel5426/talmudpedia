# Coding Agent Runtime Editing Tests

Last Updated: 2026-02-18

## Scope of the feature
- Patch-first file editing semantics for coding-agent draft runtime.
- Range reads and metadata indexing for large-file context workflows.

## Test files present
- `backend/tests/coding_agent_runtime_editing/test_patch_runtime.py`

## Key scenarios covered
- Unified diff patch success updates files with atomic semantics.
- Hunk mismatch returns structured failure diagnostics and preserves file contents.
- Hash precondition mismatch fails without mutation.
- Workspace index returns per-file metadata and symbol outlines.
- `*** Begin Patch` update-file payloads apply successfully as a fallback to unified diff parsing.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py`
- Date: 2026-02-18 00:40 UTC
- Result: PASS (`5 passed`)

## Known gaps or follow-ups
- Add mixed create/delete/rename patch fixtures with multi-file transactions.
- Add remote-controller parity tests for `/files/apply-patch` and `/files/read-range` endpoints.

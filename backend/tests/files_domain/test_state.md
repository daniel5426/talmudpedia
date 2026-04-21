Last Updated: 2026-04-22

# Files Domain

## Scope
Durable project-scoped file spaces, workflow links, runtime grant injection, and file tools.

## Test Files
- `test_files_admin_api.py`
- `test_files_runtime_tools.py`

## Key Scenarios Covered
- File space create/list/get/archive
- Directory and file CRUD through admin API
- Text write/read/patch, binary upload, revisions, move, delete
- Directory move regression coverage for moving a folder into another folder path
- Workflow link create/list/delete
- Workflow run context gets linked file spaces
- `files_*` tool access enforcement for `read` vs `read_write`
- Strict tool-input compilation strips runtime-only file metadata before validation
- `space_id: "default"` resolves to the single linked workflow file space
- Standard agent prompt includes linked file-space metadata for the model
- Startup seeding creates one global `builtin_key`-backed system row per `files-*` tool and attaches the shared file-space toolset metadata

## Last Run
- Command: `PYTHONPATH=backend backend/.venv-codex-tests/bin/python` in-memory `FileSpaceService.move_entry` smoke check
- Date: 2026-04-16
- Result: Pass
- Command: `TEST_USE_REAL_DB=0 SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/files_domain/test_files_runtime_tools.py::test_seed_file_space_tools_creates_global_function_rows`
- Date: 2026-04-22
- Result: Pass

## Known Gaps
- Full `backend/tests/files_domain` pytest run is still blocked locally until the full backend dependency set is bootstrapped in the local test venv
- The older runtime/grants tests in this directory still need separate project-scope and `agent_runs` fixture cleanup; they were not part of this bootstrap hard-cut slice
- No published/embed negative-path assertions yet
- Frontend UI coverage is light in v1

Last Updated: 2026-04-16

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
- Workflow link create/list/delete
- Workflow run context gets linked file spaces
- `files_*` tool access enforcement for `read` vs `read_write`
- Strict tool-input compilation strips runtime-only file metadata before validation
- `space_id: "default"` resolves to the single linked workflow file space
- Standard agent prompt includes linked file-space metadata for the model

## Last Run
- Command: `TEST_USE_REAL_DB=0 python3 -m pytest backend/tests/files_domain -q`
- Date: 2026-04-16
- Result: Pass

## Known Gaps
- No published/embed negative-path assertions yet
- Frontend UI coverage is light in v1

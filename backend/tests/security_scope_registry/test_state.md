# Security Scope Registry Test State

Last Updated: 2026-03-14

## Scope
Validate canonical scope registry integrity and default role/profile coverage.

## Test Files
- test_scope_registry.py

## Key Scenarios Covered
- Action->scope requirements are represented in `ALL_SCOPES`
- Platform Architect profile includes model/knowledge-store write scopes
- Default tenant role bundles include expected admin/member boundaries
- Scope catalog shape includes groups and defaults
- Every platform action advertised to the seeded architect exists in the central scope registry

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/security_scope_registry backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-14 19:48 EET
- Result: pass (`9 passed, 1 warning`)

## Known Gaps
- Does not validate runtime enforcement against endpoint dependencies.

# Agent API Context Test State

Last Updated: 2026-03-16

## Scope
Tenant resolution behavior for agent API context, especially multi-tenant users deleting/managing agents under the correct tenant.

## Test Files
- `test_agent_context_tenant_resolution.py`

## Key Scenarios Covered
- `X-Tenant-ID` is honored when a user belongs to multiple tenants.
- Missing tenant context is rejected when `X-Tenant-ID` and token tenant context are absent.
- `GET /agents` and `GET /agents/{id}` expose `show_in_playground`.
- Newly created agents default `show_in_playground` to `true`.

## Last Run
- Command: `pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-03-05 (local)
- Result: pass (`2 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-03-16 Asia/Hebron
- Result: not run yet

## Known Gaps / Follow-ups
- Add HTTP-level integration test for `DELETE /agents/{agent_id}` using two tenant memberships and explicit `X-Tenant-ID`.

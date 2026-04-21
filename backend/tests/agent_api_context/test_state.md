# Agent API Context Test State

Last Updated: 2026-04-22

## Scope
Organization resolution behavior for agent API context, especially multi-tenant users deleting/managing agents under the correct tenant.

## Test Files
- `test_agent_context_tenant_resolution.py`

## Key Scenarios Covered
- `X-Organization-ID` is honored when a user belongs to multiple tenants.
- Missing tenant context is rejected when `X-Organization-ID` and token tenant context are absent.
- `GET /agents?view=summary` and `GET /agents/{id}` expose `show_in_playground`.
- `GET /agents?view=summary` and `GET /agents/{id}` expose `project_id` for project-scoped agents without async lazy-load failures.
- Newly created agents default `show_in_playground` to `true`.

## Last Run
- Command: `pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-03-05 (local)
- Result: pass (`2 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: pass (`2 passed`)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: pass (`3 passed`). Legacy role-based token/membership usage is removed; headers now inject explicit scopes.
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/agent_api_context/test_agent_context_tenant_resolution.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: pass (`3 passed`). Project-scoped agent list/get responses now include `project_id` without `MissingGreenlet` on compact rows.

## Known Gaps / Follow-ups
- Add HTTP-level integration test for `DELETE /agents/{agent_id}` using two tenant memberships and explicit `X-Organization-ID`.

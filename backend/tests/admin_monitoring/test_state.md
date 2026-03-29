# Admin Monitoring Test State

Last Updated: 2026-03-29

## Scope
Validate the unified monitored-users read model, thread attribution, and agent-scoped stats behavior for admin monitoring.

## Test Files
- test_admin_monitoring_api.py

## Key Scenarios Covered
- Mapped published-app accounts merge into the platform user actor
- Unmapped published-app accounts remain standalone monitored actors
- Embedded identities remain separate per `agent_id + external_user_id`
- Actor thread history includes merged mapped-account threads
- Thread list exposes actor and agent attribution and filters by agent
- Thread detail joins canonical per-run usage onto each turn and exposes thread total tokens
- Thread detail now splits exact usage from estimated fallback usage instead of presenting one ambiguous total
- Agent stats can scope to a single agent and keep merged actor counts
- Resource stats serialize slugless model-registry rows without crashing the admin stats summary

## Last Run
- Command: `PYTHONPATH=. pytest -q backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Date/Time: 2026-03-29 Asia/Hebron
- Result: PASS (`7 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-27 Asia/Hebron
- Result: PASS (`17 passed`)

## Known Gaps
- Does not yet cover dashboard overview payload or frontend rendering.

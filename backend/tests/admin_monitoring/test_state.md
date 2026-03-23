# Admin Monitoring Test State

Last Updated: 2026-03-23

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
- Agent stats can scope to a single agent and keep merged actor counts
- Resource stats serialize slugless model-registry rows without crashing the admin stats summary

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Date/Time: 2026-03-23 Asia/Hebron
- Result: PASS (`5 passed`)

## Known Gaps
- Does not yet cover dashboard overview payload or frontend rendering.

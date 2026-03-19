# Admin Monitoring Test State

Last Updated: 2026-03-19

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

## Last Run
- Command: `pytest -q backend/tests/admin_monitoring`
- Date/Time: 2026-03-19 03:05:07 EET
- Result: pass (4 passed)

## Known Gaps
- Does not yet cover dashboard overview payload or frontend rendering.

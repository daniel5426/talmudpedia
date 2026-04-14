# Organization Bootstrap Tests

Last Updated: 2026-04-14

## Scope

Validates organization/project bootstrap materialization of default agent profiles after the hard-cut removal of startup tenant scanning.

## Test Files Present

- `backend/tests/organization_bootstrap/test_default_agent_profiles.py`

## Key Scenarios Covered

- organization creation creates the canonical platform architect profile
- default project bootstrap creates coding-agent profiles
- additional project creation does not duplicate default profiles
- existing organizations can be backfilled through explicit ensure helpers without startup seeding
- `/agents` lazy backfill persists seeded profiles across requests instead of returning transient IDs
- `/agents` skips bootstrap writes once the canonical default profiles already exist for the tenant

## Last Run

- Command: `python3 -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py -q`
- Date: 2026-04-14
- Result: Not run yet after latest change
- Command: `python3 -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py backend/tests/platform_architect_runtime/test_architect_seeding.py -q`
- Date: 2026-04-14
- Result: Pass (`7 passed`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/organization_bootstrap/test_default_agent_profiles.py`
- Date: 2026-04-14
- Result: PASS

## Known Gaps

- legacy tenant-era agent APIs outside bootstrap/list flows are not covered here

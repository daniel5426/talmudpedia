# Test State: Admin Stats Accounting

Last Updated: 2026-03-29

**Scope**
Admin stats accounting rollups for exact, estimated, and unknown usage/cost coverage.

**Test Files**
- `test_admin_stats_accounting_api.py`

**Scenarios Covered**
- Overview stats separate exact tokens, estimated tokens, unknown usage coverage, and spend provenance
- Agent stats expose the same accounting provenance fields under agent-scoped drilldown

**Last Run**
- Command: `PYTHONPATH=. pytest -q backend/tests/admin_stats_accounting/test_admin_stats_accounting_api.py`
- Date/Time: 2026-03-29 Asia/Hebron
- Result: PASS (`2 passed, 7 warnings`)

**Known Gaps / Follow-ups**
- Does not yet cover provider/binding breakdown slices
- Does not yet cover partial historical rows migrated from legacy `usage_tokens` only data

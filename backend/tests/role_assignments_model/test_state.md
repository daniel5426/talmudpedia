# Role Assignments Model Test State

Last Updated: 2026-04-20

## Scope
Validate explicit organization/project role-assignment persistence and local effective-scope resolution.

## Test Files
- test_role_assignments_model.py

## Key Scenarios Covered
- Local role assignments resolve canonical effective scopes
- Project role assignments persist through explicit `project_id`

## Last Run
- Command: not run in this phase
- Date/Time: 2026-04-20 Asia/Hebron
- Result: pending

## Known Gaps
- No migration-level invalid legacy-row coverage yet.
- No DB uniqueness assertion for the new partial unique indexes yet.

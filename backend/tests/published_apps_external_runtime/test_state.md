# Test State: Published Apps External Runtime

Last Updated: 2026-03-16

## Scope
- Host-anywhere published-app runtime surface under `/public/external/apps/*`.
- Bearer-token published-app auth for externally hosted browser clients.
- External runtime bootstrap, chat streaming, and persisted thread/history APIs.
- Origin allowlist enforcement for external published-app traffic.

## Test Files Present
- `backend/tests/published_apps_external_runtime/test_external_runtime_api.py`

## Key Scenarios Covered
- External bootstrap returns the new runtime surface and CORS headers.
- External password auth returns bearer tokens and supports `me` and `logout`.
- External OIDC exchange returns a bearer session token.
- External authenticated stream persists threads and exposes list/detail history APIs.
- External thread detail remains app-account scoped.
- Auth-disabled apps stream ephemerally with no persisted thread.
- Disallowed origins are rejected on the external runtime surface.

## Last Run Command + Date/Time + Result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps_external_runtime/test_external_runtime_api.py`
- Date/Time: 2026-03-16
- Result: PASS (6 passed, 6 warnings)

## Known Gaps or Follow-ups
- Add explicit preflight `OPTIONS` coverage for allowed and blocked origins.
- Add negative tests for cross-app bearer token replay on bootstrap/history routes.

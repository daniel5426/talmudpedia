Last Updated: 2026-04-19

# WorkOS Native Auth Test State

## Scope
- Verify backend WorkOS auth service uses the native Python SDK session helpers.
- Cover native `load_sealed_session`, `session.refresh()`, and `authenticate_with_code()` integration points.

## Test Files Present
- `test_workos_native_auth_service.py`

## Key Scenarios Covered
- Expired session path loads the sealed session via the native helper and rotates the cookie with native refresh.
- Auth code exchange uses the native typed `authenticate_with_code()` API and passes session sealing config.

## Last Run
- 2026-04-19: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py` -> `2 passed`
- 2026-04-19: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py` -> `2 passed`

## Known Gaps
- Does not hit live WorkOS.
- Does not exercise the full browser callback flow end-to-end.

# Credentials Management Tests

Last Updated: 2026-02-22

## Scope
Credential default selection, env fallback behavior, and provider validation across tenant scope.

## Test Files
- `backend/tests/credentials_management/test_integration_credentials_defaults.py`

## Key Scenarios Covered
- Tenant default credentials override env fallback for the same provider.
- Creating a new default credential for a provider unsets the previous default in that scope.
- Provider key validation is strict for `tool_provider` and permissive for `custom`.
- Vector-store backend config falls back to env keys when no tenant default is set.
- Credential usage API returns linked model providers, knowledge stores, and tools.
- Delete without force returns `409` when linked; force delete disconnects links and removes the credential.

## Last Run
- Command: `PYTHONPATH=. pytest -q tests/credentials_management`
- Date: 2026-02-22
- Result: Pass (5 passed)

## Known Gaps / Follow-ups
- Add regression tests for provider-variant scoped defaults.
- Add coverage for settings credential update path when changing category/provider in a single patch call.

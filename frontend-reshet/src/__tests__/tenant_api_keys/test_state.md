# Tenant API Keys Test State

Last Updated: 2026-03-17

## Scope
Validate frontend tenant API keys service API wiring for embedded agent runtime admin.

## Test Files
- tenant_api_keys_service.test.ts

## Key Scenarios Covered
- List API keys endpoint wiring (GET /admin/security/api-keys)
- Create API key with default scopes
- Create API key with custom scopes
- Revoke API key endpoint wiring (POST /admin/security/api-keys/{key_id}/revoke)
- Error propagation from httpClient

## Last Run
- Command: `cd frontend-reshet && npx jest --runInBand src/__tests__/tenant_api_keys`
- Date/Time: 2026-03-17
- Result: pass (5/5)

## Known Gaps
- Does not validate API keys tab rendering (UI-level test).
- Does not validate create/revoke dialog interactions.

# Models Registry UI Tests

Last Updated: 2026-02-22

## Scope
Models Registry page editing flows for logical models and provider bindings.

## Test Files
- `frontend-reshet/src/__tests__/models_registry/models_registry.test.tsx`

## Key Scenarios Covered
- Edit Model dialog opens and triggers update call.
- Edit Provider dialog opens and triggers update call.
- Provider rows show `Platform Default (ENV)` when no explicit credential ref is set.

## Last Run
- Command: `npm test -- --runInBand src/__tests__/models_registry`
- Date: 2026-02-22
- Result: Pass (1 suite, 3 tests)

## Known Gaps / Follow-ups
- Add tests for credentials selection and delete confirmations.
- Add tests for Settings credentials page CRUD.

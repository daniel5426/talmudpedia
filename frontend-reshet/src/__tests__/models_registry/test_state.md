# Models Registry UI Tests

Last Updated: 2026-03-20

## Scope
Models Registry page editing flows for logical models and provider bindings.

## Test Files
- `frontend-reshet/src/__tests__/models_registry/models_registry.test.tsx`

## Key Scenarios Covered
- Create Model dialog works without a slug field and submits UUID-only model identity flows.
- Edit Model dialog opens and triggers update call.
- Edit Provider dialog opens and triggers update call.
- Provider rows show `Platform Default (ENV)` when no explicit credential ref is set.

## Last Run
- Command: `pnpm test -- --runInBand src/__tests__/models_registry/models_registry.test.tsx`
- Date: 2026-03-20
- Result: Pass (1 suite, 4 tests)

## Known Gaps / Follow-ups
- Add tests for capability-specific provider option filtering in the add-provider flow.
- Add tests for credentials selection and delete confirmations.

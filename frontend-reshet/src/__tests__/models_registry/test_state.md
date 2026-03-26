# Models Registry UI Tests

Last Updated: 2026-03-26

## Scope
Models Registry page editing flows for logical models and provider bindings.

## Test Files
- `frontend-reshet/src/__tests__/models_registry/models_registry.test.tsx`

## Key Scenarios Covered
- Create Model dialog works without a slug field and submits UUID-only model identity flows.
- Edit Model dialog opens and triggers update call.
- Edit Provider dialog opens and triggers update call with canonical `pricing_config`.
- Provider pricing UI exposes declarative pricing modes only; internal manual overrides are not editable there.
- Provider rows show `Platform Default (ENV)` when no explicit credential ref is set.
- Search input filters the visible models list client-side.

## Last Run
- Command: `pnpm test -- --runInBand src/__tests__/models_registry/models_registry.test.tsx`
- Date/Time: 2026-03-26 Asia/Hebron
- Result: PASS (`1 suite, 5 tests`)

## Known Gaps / Follow-ups
- Add tests for capability-specific provider option filtering in the add-provider flow.
- Add tests for credentials selection and delete confirmations.
- Add coverage for add-provider pricing modes beyond token pricing.

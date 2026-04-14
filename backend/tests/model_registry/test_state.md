# Model Registry Tests

Last Updated: 2026-04-14

## Scope
Model Registry credentials resolution, provider binding updates, and vector store credential merging.

## Test Files
- `backend/tests/model_registry/test_credentials_resolution.py`
- `backend/tests/model_registry/test_model_resolution_contract.py`
- `backend/tests/model_registry/test_models_api_contract.py`
- `backend/tests/model_registry/test_models_service_parity.py`
- `backend/tests/model_registry/test_provider_binding_update.py`
- `backend/tests/model_registry/test_vector_store_credentials.py`

## Key Scenarios Covered
- Explicit credential refs resolve provider API keys for LLM bindings.
- Default credential resolution follows tenant default then env fallback precedence.
- Embedding resolution uses integration credentials.
- Resolver ignores disabled tenant bindings when a lower-priority enabled fallback exists.
- Resolver rejects legacy non-UUID model identifiers.
- `/models` list responses keep filtered items and `total` aligned.
- `models.list` now returns the same filtered result across the service layer, direct router adapter, and native `platform-assets` tool adapter.
- `/models` create responses no longer expose slug-based identity.
- Setting a default model clears the previous default in the same tenant/capability scope.
- Unsupported provider/capability pairs are rejected before persistence.
- Built-in providers reject tenant pricing overrides on provider create/update.
- `custom` and `local` providers accept tenant-managed `pricing_config`.
- Global model reads expose seeded built-in binding pricing.
- Provider binding PATCH updates priority, enabled status, credentials ref, and pricing config for tenant-managed providers.
- Public registry APIs reject `billing_mode=manual`; that mode is internal-only.
- Vector store backend config merges credentials and rejects disabled secrets.

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/model_registry/test_models_api_contract.py backend/tests/model_registry/test_models_service_parity.py backend/tests/platform_architect_runtime/test_native_platform_tools.py`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: PASS (`12 passed`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/model_registry/test_model_resolution_contract.py`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: PASS (`2 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/model_registry/test_models_api_contract.py backend/tests/model_registry/test_provider_binding_update.py backend/tests/model_accounting/test_model_accounting_service.py`
- Date/Time: 2026-03-26 Asia/Hebron
- Result: PASS (`15 passed`)

## Known Gaps / Follow-ups
- Add migration-focused tests for the slug-to-`system_key` hard cut and default-index rollout.
- Add broader integration coverage for downstream agent graph persistence and RAG embedding consumers.
- Add explicit API coverage for flat-per-request and unknown billing-mode provider bindings on tenant-managed providers.

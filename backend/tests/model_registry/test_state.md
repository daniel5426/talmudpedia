# Model Registry Tests

Last Updated: 2026-03-20

## Scope
Model Registry credentials resolution, provider binding updates, and vector store credential merging.

## Test Files
- `backend/tests/model_registry/test_credentials_resolution.py`
- `backend/tests/model_registry/test_model_resolution_contract.py`
- `backend/tests/model_registry/test_models_api_contract.py`
- `backend/tests/model_registry/test_provider_binding_update.py`
- `backend/tests/model_registry/test_vector_store_credentials.py`

## Key Scenarios Covered
- Explicit credential refs resolve provider API keys for LLM bindings.
- Default credential resolution follows tenant default then env fallback precedence.
- Embedding resolution uses integration credentials.
- Resolver ignores disabled tenant bindings when a lower-priority enabled fallback exists.
- Resolver rejects legacy non-UUID model identifiers.
- `/models` list responses keep filtered items and `total` aligned.
- `/models` create responses no longer expose slug-based identity.
- Setting a default model clears the previous default in the same tenant/capability scope.
- Unsupported provider/capability pairs are rejected before persistence.
- Provider binding PATCH updates priority, enabled status, and credentials ref.
- Vector store backend config merges credentials and rejects disabled secrets.

## Last Run
- Command: `python3 -m pytest -q backend/tests/model_registry`
- Date: 2026-03-20
- Result: Pass (13 passed)

## Known Gaps / Follow-ups
- Add migration-focused tests for the slug-to-`system_key` hard cut and default-index rollout.
- Add broader integration coverage for downstream agent graph persistence and RAG embedding consumers.

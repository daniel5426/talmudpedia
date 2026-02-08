# Model Registry Tests

Last Updated: 2026-02-05

## Scope
Model Registry credentials resolution, provider binding updates, and vector store credential merging.

## Test Files
- `backend/tests/model_registry/test_credentials_resolution.py`
- `backend/tests/model_registry/test_provider_binding_update.py`
- `backend/tests/model_registry/test_vector_store_credentials.py`

## Key Scenarios Covered
- Integration credentials override legacy provider configs for LLMs.
- Embedding resolution uses integration credentials.
- Provider binding PATCH updates priority, enabled status, and credentials ref.
- Vector store backend config merges credentials and rejects disabled secrets.

## Last Run
- Command: `pytest backend/tests/model_registry`
- Date: 2026-02-05 23:28 EET
- Result: Pass

## Known Gaps / Follow-ups
- Add UI contract tests for settings credentials list.
- Add tests for credential deletion guardrails (in-use references).

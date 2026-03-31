# Test State: Model Accounting

Last Updated: 2026-03-30

**Scope**
Run-accounting normalization and pricing snapshot calculation.

**Test Files**
- `test_model_accounting_service.py`
- `test_run_invocation_service.py`

**Scenarios Covered**
- Canonical binding `pricing_config` snapshots are used as the sole runtime pricing source
- Structured pricing computes exact run cost from canonical `pricing_config`
- Built-in bindings without seeded pricing remain `unknown`
- Seeded built-in pricing and tenant-managed local/custom pricing both compute exact run cost from canonical `pricing_config`
- Manual pricing produces explicit manual-override cost provenance
- Invocation usage normalization preserves multimodal dimensions without coercing them into run-level token columns
- Non-LLM invocations do not replace the run-level chat context window when aggregates are recomputed

**Last Run**
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/model_accounting/test_run_invocation_service.py`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: PASS (`2 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/model_registry/test_models_api_contract.py backend/tests/model_registry/test_provider_binding_update.py backend/tests/model_accounting/test_model_accounting_service.py`
- Date/Time: 2026-03-26 Asia/Hebron
- Result: PASS (`15 passed`)

**Known Gaps / Follow-ups**
- Does not yet cover provider-reported cost precedence
- Does not yet cover minimum-charge behavior
- Does not yet cover the registry API write path for pricing config

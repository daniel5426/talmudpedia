# Test State: Model Accounting

Last Updated: 2026-03-26

**Scope**
Run-accounting normalization and pricing snapshot calculation.

**Test Files**
- `test_model_accounting_service.py`

**Scenarios Covered**
- Canonical binding `pricing_config` snapshots are used as the sole runtime pricing source
- Structured pricing computes exact run cost from canonical `pricing_config`
- Manual pricing produces explicit manual-override cost provenance

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/model_accounting/test_model_accounting_service.py`
- Date/Time: 2026-03-26 Asia/Hebron
- Result: PASS (`2 passed`)

**Known Gaps / Follow-ups**
- Does not yet cover provider-reported cost precedence
- Does not yet cover unknown multimodal dimensions or minimum-charge behavior
- Does not yet cover the registry API write path for pricing config

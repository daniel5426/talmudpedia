# Model Temperature Policy Tests

Last Updated: 2026-03-10

## Scope
- Shared backend temperature normalization for providers/models that only accept `temperature=1`.
- Seeded Platform Architect default temperature configuration.

## Test Files
- `backend/tests/model_temperature_policy/test_temperature_policy.py`
- `backend/tests/platform_architect_runtime/test_architect_seeding.py`

## Key Scenarios Covered
- OpenAI `gpt-5*` models normalize any requested temperature to `1.0`.
- OpenAI reasoning families `o1*`, `o3*`, and `o4*` normalize omitted or explicit temperatures to `1.0`.
- Azure-hosted OpenAI reasoning models follow the same `temperature=1` normalization.
- Non-restricted models and non-OpenAI providers preserve the requested temperature.
- Seeded `platform-architect` runtime config sets default temperature to `1`.

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest -q tests/model_temperature_policy tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-10 19:02 EET
- Result: Pass (`8 passed, 1 warning`)

## Known Gaps / Follow-ups
- Add provider-integration coverage that asserts normalized temperatures are passed through live LLM adapter calls.

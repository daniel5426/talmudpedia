# Context Window Tests

Last Updated: 2026-03-30

## Scope
Validate provider-aware prompt token counting and model-limit resolution for `context_window`.

## Test Files
- `test_token_counter_service.py`

## Key Scenarios Covered
- Google prompt counting uses native `count_tokens`
- Anthropic prompt counting uses native `messages.count_tokens`
- Non-native providers fall back to `tiktoken` tokenizer estimates
- Provider model-info limits override fallback sources when available
- Pre-run context window uses the shared token counter and model limits services

## Last Run
- Command: `PYTHONPATH=. pytest -q tests/context_window/test_token_counter_service.py`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: PASS (`5 passed, 1 warning`)
- Command: `set -a && source .env >/dev/null 2>&1 && set +a && PYTHONPATH=. python3 <live token counter probe>`
- Date/Time: 2026-03-30 19:49 EEST
- Result: PASS (`google=provider_count_api`, `anthropic=provider_count_api`, `openai=tokenizer_estimate`, `xai=tokenizer_estimate`)

## Known Gaps / Follow-ups
- Add registry fallback tests with a real DB session when the refactor stabilizes

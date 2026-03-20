# LLM Provider Adapter Tests

Last Updated: 2026-03-20

## Scope
Verifies the shared `LLMProviderAdapter` normalization layer that bridges platform `LLMProvider` streams into LangChain/LangGraph-compatible chunks.

## Test files present
- test_llm_provider_adapter.py

## Key scenarios covered
- Non-string chunk content is normalized into stable text tokens.
- Tool-call chunk metadata survives normalization.
- Raw provider delta formats aggregate into a valid final assistant response.
- Reasoning-only deltas are preserved in `additional_kwargs`.

## Last run command + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/llm_provider_adapter`
- Date/Time: 2026-03-20 Asia/Hebron
- Result: pass (`3 passed`)

## Known gaps or follow-ups
- No live-provider coverage; tests use deterministic fake providers.

# Model Capability Runtime Tests

Last Updated: 2026-04-09

## Scope
Shared capability-runtime resolution through the model registry, with STT as the first non-LLM runtime slice.

## Test Files
- `test_model_capability_runtime.py`

## Key Scenarios Covered
- Global model seeding includes the canonical default Google STT model.
- Default runtime adapter registration exposes `google` for `speech_to_text`.
- Default `speech_to_text` model resolution returns a typed execution receipt with merged config and binding metadata.
- Chat receipt resolution can return binding/config metadata without instantiating a live runtime client.
- STT resolution fails cleanly when a binding uses a provider that has no registered STT runtime adapter.
- `/stt/transcribe` routes through registry-backed default STT resolution instead of a legacy provider factory.
- Google STT accepts inline `GOOGLE_APPLICATION_CREDENTIALS` service-account JSON instead of misreading it as a file path.

## Last Run
- Command: `cd backend && python3 -m pytest -q tests/model_capability_runtime`
- Date/Time: 2026-04-09 Asia/Hebron
- Result: PASS (`7 passed`)

## Known Gaps / Follow-ups
- No end-to-end live-provider STT coverage yet.
- TTS and other non-LLM capabilities still need equivalent runtime tests once implemented.

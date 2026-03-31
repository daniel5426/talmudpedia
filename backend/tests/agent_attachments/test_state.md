# Agent Attachments Tests

Last Updated: 2026-03-30

## Scope
Attachment storage/preparation through `RuntimeAttachmentService` plus explicit audio transcription through `RuntimeInputPreparationService`.

## Test Files
- `test_runtime_attachment_service.py`

## Key Scenarios Covered
- Supported document attachments (`txt`, `md`, `csv`, `json`, `html`) are processed into extracted text and injected into the user message payload.
- PDF attachments exercise the document-extractor path without requiring an external provider.
- Audio attachments are marked processed by the shared attachment service without implicit transcription.
- Higher-level run input preparation explicitly invokes the shared STT runtime and injects transcripts into the user message payload.
- Image attachments are rejected when no supplied model is vision-capable.
- Image attachments are accepted for the current vision signals used by the backend:
  capability type `VISION` and model metadata flags (`vision=true` / `supports_vision=true`).
- Attachment processing state and extracted text are persisted after document preparation.

## Last Run
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_attachments`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: PASS (`13 passed`)

## Known Gaps / Follow-ups
- This suite exercises the shared attachment service directly, not the authenticated `/agents/...` HTTP surface.
- Add API-level agent attachment coverage so the authenticated `/agents/...` routes are exercised on top of the shared service.

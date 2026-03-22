# Agent Attachments Tests

Last Updated: 2026-03-22

## Scope
Provider-agnostic attachment handling for agent runtime pre-run preparation through `RuntimeAttachmentService`.

## Test Files
- `test_runtime_attachment_service.py`

## Key Scenarios Covered
- Supported document attachments (`txt`, `md`, `csv`, `json`, `html`) are processed into extracted text and injected into the user message payload.
- PDF attachments exercise the document-extractor path without requiring an external provider.
- Audio attachments are transcribed through a fake STT provider and injected into the user message payload.
- Image attachments are rejected when no supplied model is vision-capable.
- Image attachments are accepted for the current vision signals used by the backend:
  capability type `VISION` and model metadata flags (`vision=true` / `supports_vision=true`).
- Attachment processing state and extracted text are persisted after preparation.

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_attachments/test_runtime_attachment_service.py`
- Date/Time: 2026-03-22 Asia/Hebron
- Result: PASS (`12 passed`)

## Known Gaps / Follow-ups
- This suite exercises the shared attachment service directly, not the authenticated `/agents/...` HTTP surface.
- Add API-level agent attachment coverage so the authenticated `/agents/...` routes are exercised on top of the shared service.

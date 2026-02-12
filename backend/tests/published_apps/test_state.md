# Published Apps Backend Tests

Last Updated: 2026-02-12

## Scope of the feature
- Admin control plane CRUD and publish lifecycle for tenant published apps.
- Builder revisions/templates/snapshot publishing flow for apps.
- Public runtime app resolution/config retrieval.
- End-user auth flows (email/password, Google OAuth callback path).
- Public chat streaming and chat persistence scoping by `published_app_id`.

## Test files present
- `backend/tests/published_apps/test_admin_apps_crud.py`
- `backend/tests/published_apps/test_admin_apps_publish_rules.py`
- `backend/tests/published_apps/test_builder_revisions.py`
- `backend/tests/published_apps/test_public_app_resolve_and_config.py`
- `backend/tests/published_apps/test_public_auth_email_password.py`
- `backend/tests/published_apps/test_public_auth_google_oauth.py`
- `backend/tests/published_apps/test_public_chat_scope_and_persistence.py`

## Key scenarios covered
- Tenant admin can create/list/update/delete apps.
- Create accepts `template_key`, auto-generates slug, and seeds initial draft revision.
- Only published agents can be attached/published.
- Publish and unpublish lifecycle updates URL/status.
- Builder state returns app/templates/current draft/current published revision snapshot info.
- Revision writes enforce optimistic concurrency with `REVISION_CONFLICT` 409 contract.
- Builder revision writes enforce patch policy guardrails (path normalization, root/extension restrictions, operation and size limits).
- Builder revision writes reject invalid rename operations (missing source/duplicate target).
- Builder revision writes reject oversized payloads by file-byte limits.
- Builder revision writes enforce Vite project policy rules (allowed root files, no path traversal, file/size guards).
- Builder revision writes enforce curated dependency policy (`package.json` required, pinned package catalog, no network/absolute imports, local import resolution).
- Template reset overwrites draft from selected template baseline.
- `chat-grid` template metadata resolves to premium LayoutShell-style identity in templates catalog.
- Template reset to `chat-grid` returns multi-file shell layout assets (`LayoutShell`, `ChatPane`, `SourceListPane`, `SourceViewerPane`).
- Builder validate endpoint (`POST /admin/apps/{app_id}/builder/validate`) returns compile diagnostics for dry-run checks.
- Builder revision build lifecycle endpoints expose build state and retry sequence bumps:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Build enqueue failures (or disabled automation) mark revision `build_status=failed` with actionable `build_error` instead of leaving draft revisions indefinitely pending.
- Builder chat stream emits richer envelopes with `stage` and `request_id`.
- Builder chat stream persists conversation turns for replay/audit, including success and failure metadata.
- Builder conversation replay endpoint (`GET /admin/apps/{app_id}/builder/conversations`) returns persisted turns newest-first.
- Publish endpoint enforces build-status gate contract (`BUILD_PENDING`/`BUILD_FAILED`) for every publish request.
- Worker-build preflight gate (`APPS_BUILDER_WORKER_BUILD_GATE_ENABLED=1`) blocks revision save, validate, and chat patch apply on failed `npm`/`vite` preflight.
- Publish clones draft into immutable published revision snapshot.
- Public runtime descriptor endpoint returns static runtime contract:
- `GET /public/apps/{slug}/runtime`
- Preview runtime descriptor endpoint returns preview asset base URL:
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- Preview runtime descriptor now returns `preview_url` pointing to entry HTML (for iframe loading), with `asset_base_url` kept for static asset resolution.
- Preview asset proxy endpoint streams dist assets with preview token auth:
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Public `/public/apps/{slug}/ui` is permanently removed and returns `410 UI_SOURCE_MODE_REMOVED`.
- Publish returns `500 BUILD_ARTIFACT_COPY_FAILED` when dist artifact promotion fails and leaves existing publish pointer unchanged.
- Hostname resolve and app config retrieval for public runtime.
- Signup/login/logout and auth-me using published app session tokens.
- Google OAuth start and callback issuance path with tenant credentials.
- Chat stream persists user/assistant messages only when auth is enabled.
- Public mode chat is ephemeral and does not persist chat rows.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/published_apps/test_admin_apps_crud.py::test_admin_apps_crud`
- Date: 2026-02-12 22:23 UTC
- Result: PASS (1 passed)
- Command: `pytest -q backend/tests/published_apps/test_builder_revisions.py::test_builder_revision_build_status_and_retry_endpoints`
- Date: 2026-02-12 22:22 UTC
- Result: PASS (1 passed)
- Command: `pytest backend/tests/published_apps/test_builder_revisions.py -q`
- Date: 2026-02-12 21:08 UTC
- Result: PASS (12 passed)
- Command: `pytest backend/tests/published_apps/test_admin_apps_publish_rules.py backend/tests/published_apps/test_public_app_resolve_and_config.py -q`
- Date: 2026-02-12 21:08 UTC
- Result: PASS (8 passed)
- Notes: verifies builder revision/chat reliability contracts plus publish/runtime descriptor and preview asset flows.

## Known gaps or follow-ups
- Add negative tests for cross-app token replay attempts.
- Add coverage for revoked-session rejection on chat endpoints.
- Add preview-token invalid-claim and expiration-path tests for builder preview UI endpoints.

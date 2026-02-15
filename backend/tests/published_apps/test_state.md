# Published Apps Backend Tests

Last Updated: 2026-02-14

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
- Builder validation accepts expanded Vite root lock/config/test files (`pnpm-lock.yaml`, `yarn.lock`, `vite.config.*`, `vitest.config.*`, `eslint/prettier/jest/playwright` configs).
- Template reset overwrites draft from selected template baseline.
- `chat-grid` template metadata resolves to premium LayoutShell-style identity in templates catalog.
- Template reset to `chat-grid` returns multi-file shell layout assets (`LayoutShell`, `ChatPane`, `SourceListPane`, `SourceViewerPane`).
- Builder validate endpoint (`POST /admin/apps/{app_id}/builder/validate`) returns compile diagnostics for dry-run checks.
- Builder revision build lifecycle endpoints expose build state and retry sequence bumps:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Build enqueue failures (or disabled automation) mark revision `build_status=failed` with actionable `build_error` instead of leaving draft revisions indefinitely pending.
- Builder chat stream emits richer envelopes with `stage` and `request_id`.
- Builder chat stream now emits typed timeline events (`tool_started`, `tool_completed`, `tool_failed`, `file_changes`, `checkpoint_created`, `done`).
- Builder chat stream persists conversation turns for replay/audit, including success and failure metadata.
- Builder chat stream now auto-persists successful runs into new draft revisions and stores `result_revision_id`, checkpoint type/label, and tool summary metadata.
- Agentic loop (`BUILDER_AGENTIC_LOOP_ENABLED=1`) now emits worker tool stages (`build_project_worker`, `prepare_static_bundle`) in trace events when model-backed generation is enabled.
- Agentic loop surfaces worker build failures in persisted conversation tool traces with `build_project_worker` failure status.
- Agentic loop now parses prompt `@file` mentions and emits `read_file` tool events for the mentioned files during inspect stage.
- Agentic loop now blocks patch generation success when targeted tests fail (`run_targeted_tests` tool status `failed`) and persists failure tool traces for replay.
- Builder conversation replay endpoint (`GET /admin/apps/{app_id}/builder/conversations`) returns persisted turns newest-first.
- Builder checkpoint/rollback APIs are covered:
- `GET /admin/apps/{app_id}/builder/checkpoints`
- `POST /admin/apps/{app_id}/builder/undo`
- `POST /admin/apps/{app_id}/builder/revert-file`
- Builder chat sandbox command allowlist gate blocks non-allowlisted command execution and returns compile-style diagnostics.
- Publish endpoint returns async job metadata and publish jobs move through `queued/running/succeeded/failed`.
- Publish no longer gates on draft revision `build_status`; deterministic checks happen in publish worker full-build path.
- Worker-build preflight gate does not block draft save/chat flows in draft mode.
- Publish failures keep the previous `current_published_revision_id` unchanged.
- Draft-dev session APIs support ensure/sync/heartbeat/read/stop lifecycle per `(app_id, user_id)`.
- Public runtime descriptor endpoint returns static runtime contract:
- `GET /public/apps/{slug}/runtime`
- Preview runtime descriptor endpoint returns preview asset base URL:
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- Preview runtime descriptor now returns `preview_url` pointing to entry HTML (for iframe loading), with `asset_base_url` kept for static asset resolution.
- Preview asset proxy endpoint streams dist assets with preview token auth:
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Preview principal auth now falls back across bearer/query/cookie token sources and accepts a valid query token even when an invalid bearer token is present.
- Preview HTML assets now rewrite relative `src`/`href` links to include `preview_token` query propagation, reducing iframe/cookie-related token failures for JS/CSS fetches.
- Public `/public/apps/{slug}/ui` is permanently removed and returns `410 UI_SOURCE_MODE_REMOVED`.
- Hostname resolve and app config retrieval for public runtime.
- Signup/login/logout and auth-me using published app session tokens.
- Google OAuth start and callback issuance path with tenant credentials.
- Chat stream persists user/assistant messages only when auth is enabled.
- Public mode chat is ephemeral and does not persist chat rows.

## Last run command + date/time + result
- Command: `pytest backend/tests/published_apps/test_public_app_resolve_and_config.py -q`
- Date: 2026-02-12 23:30 UTC
- Result: PASS (6 passed)
- Command: `npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand` (from `frontend-reshet/`)
- Date: 2026-02-12 23:30 UTC
- Result: PASS (3 passed)
- Command: `pytest backend/tests/published_apps/test_builder_revisions.py -q`
- Date: 2026-02-12 23:30 UTC
- Result: PASS (17 passed)
- Command: `pytest -q backend/tests/published_apps/test_admin_apps_crud.py::test_admin_apps_crud`
- Date: 2026-02-12 22:23 UTC
- Result: PASS (1 passed)
- Command: `pytest backend/tests/published_apps/test_admin_apps_publish_rules.py backend/tests/published_apps/test_public_app_resolve_and_config.py -q`
- Date: 2026-02-12 21:08 UTC
- Result: PASS (8 passed)
- Notes: verifies builder revision/chat reliability contracts plus publish/runtime descriptor and preview asset flows.
- Command: `pytest -q backend/tests/published_apps`
- Date: 2026-02-14 18:10 UTC
- Result: PASS (34 passed)
- Command: `pytest -q backend/tests/published_apps/test_builder_revisions.py`
- Date: 2026-02-14 20:42 UTC
- Result: PASS (21 passed)

## Known gaps or follow-ups
- Add negative tests for cross-app token replay attempts.
- Add coverage for revoked-session rejection on chat endpoints.
- Add preview-token invalid-claim and expiration-path tests for builder preview UI endpoints.

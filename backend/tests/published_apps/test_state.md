# Published Apps Backend Tests

Last Updated: 2026-02-21

## Scope of the feature
- Admin control plane CRUD and publish lifecycle for tenant published apps.
- Builder revision/template/validation/build retry flows (non-chat).
- Public runtime app resolution/config retrieval.
- End-user auth flows (email/password, Google OAuth callback path).
- Public chat streaming and persistence scoping by `published_app_id`.

## Test files present
- `backend/tests/published_apps/test_admin_apps_crud.py`
- `backend/tests/published_apps/test_admin_apps_publish_rules.py`
- `backend/tests/published_apps/test_builder_agent_integration_contract.py`
- `backend/tests/published_apps/test_builder_revisions.py`
- `backend/tests/published_apps/test_public_app_resolve_and_config.py`
- `backend/tests/published_apps/test_public_auth_email_password.py`
- `backend/tests/published_apps/test_public_auth_google_oauth.py`
- `backend/tests/published_apps/test_public_chat_scope_and_persistence.py`

## Key scenarios covered
- Tenant admin can create/list/update/delete apps.
- App create/update/list/get payloads include branding/template/visibility fields (`description`, `logo_url`, `visibility`, `auth_template_key`).
- Auth template catalog endpoint is covered (`GET /admin/apps/auth/templates`).
- Create accepts `template_key`, auto-generates slug, and seeds initial draft revision.
- Users admin endpoints are covered (`GET /admin/apps/{app_id}/users`, `PATCH /admin/apps/{app_id}/users/{user_id}`), including block/unblock and session revocation behavior.
- Domains admin endpoints are covered (`GET/POST/DELETE /admin/apps/{app_id}/domains...`) with pending-request workflow.
- Public visibility gate is covered on resolve/config/runtime/auth/chat endpoints for `visibility=private`.
- Only published agents can be attached/published.
- Publish and unpublish lifecycle updates URL/status.
- Builder state returns app/templates/current draft/current published revision snapshot info.
- Builder agent integration contract endpoint is covered:
- `GET /admin/apps/{app_id}/builder/agent-contract`
- Contract payload includes selected agent summary, resolved tool schemas, optional `x-ui` hints, and unresolved tool diagnostics.
- Revision writes enforce optimistic concurrency with `REVISION_CONFLICT` 409 contract.
- Builder revision writes enforce patch policy guardrails (path normalization, blocked generated/system directories, extension restrictions, operation and size limits).
- Builder revision writes reject invalid rename operations and oversized payloads.
- Builder revision and validate endpoints enforce Vite project validation and import security diagnostics.
- Builder revision allows unrestricted third-party package declarations/imports (no curated dependency allowlist).
- Builder validate accepts Vite root lock/config/test files (`pnpm-lock.yaml`, `yarn.lock`, `vite.config.*`, `vitest.config.*`, lint/test config files).
- Builder validate accepts non-`src`/`public` project paths (for example `tests/` and `scripts/`) while still blocking generated/system paths (for example `node_modules/`).
- Template catalog now includes `fresh-start` (minimal Vite + runtime SDK baseline).
- Draft revisions seeded from template create/reset now include canonical OpenCode bootstrap files under `.opencode/tools/*` + `.opencode/package.json`.
- Template reset overwrites draft from selected template baseline and includes `chat-grid` shell assets.
- Builder revision build lifecycle endpoints expose build state and retry sequence bumps:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Publish endpoint returns async job metadata and publish jobs move through `queued/running/succeeded/failed`.
- Publish failures keep previous `current_published_revision_id` unchanged.
- Draft-dev session APIs support ensure/sync/heartbeat/read/stop lifecycle per `(app_id, user_id)`.
- Public runtime descriptor and preview runtime/asset endpoints are covered.
- Preview chat stream endpoint is covered (`POST /public/apps/preview/revisions/{revision_id}/chat/stream`), including preview-token auth requirement and ephemeral execution semantics.
- Published runtime static asset proxy is covered (`GET /public/apps/{slug}/assets/{asset_path}`), including SPA route fallback to `index.html`.
- Public `/public/apps/{slug}/ui` is permanently removed and returns `410 UI_SOURCE_MODE_REMOVED`.
- Hostname resolve and app config retrieval for public runtime are covered.
- Signup/login/logout/auth-me and Google OAuth callback paths are covered.
- Public chat persists messages only when auth is enabled; public mode chat is ephemeral.
- Legacy builder chat endpoints (`/builder/chat/stream`, `/builder/checkpoints`, `/builder/undo`, `/builder/revert-file`) are intentionally removed and are no longer part of this suite.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps/test_builder_revisions.py`
- Date: 2026-02-21
- Result: PASS (9 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/published_apps/test_public_app_resolve_and_config.py`
- Date: 2026-02-16 22:19 EET
- Result: PASS (9 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/published_apps`
- Date: 2026-02-16 20:04 UTC
- Result: PASS (31 passed)
- Notes: publish URL assertion now tracks environment-derived URL builder behavior.
- Command: `PYTHONPATH=backend pytest -q backend/tests/published_apps/test_builder_revisions.py`
- Date: 2026-02-16 19:58 UTC
- Result: PASS (7 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/published_apps/test_builder_revisions.py`
- Date: 2026-02-17 14:10 UTC
- Result: PASS (9 passed)
- Command: `cd backend && pytest -q tests/published_apps/test_admin_apps_publish_rules.py`
- Date: 2026-02-16 19:26 EET
- Result: PASS (6 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/published_apps/test_builder_revisions.py -q`
- Date: 2026-02-19 19:50:15 UTC
- Result: PASS (9 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/published_apps/test_builder_agent_integration_contract.py tests/coding_agent_api/test_agent_integration_contract_context.py -q`
- Date: 2026-02-19 20:03:59 UTC
- Result: PASS (2 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/published_apps -q`
- Date: 2026-02-19 19:54 UTC
- Result: PASS (35 passed)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps/test_public_chat_scope_and_persistence.py tests/published_apps/test_public_app_resolve_and_config.py`
- Date: 2026-02-19 20:44:00 UTC
- Result: PASS (13 passed)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps`
- Date: 2026-02-19 20:47 UTC
- Result: PASS (38 passed)

## Known gaps or follow-ups
- Add negative tests for cross-app token replay attempts.
- Add coverage for revoked-session rejection on chat endpoints.
- Add preview-token invalid-claim and expiration-path tests for builder preview UI endpoints.
- Coding-agent run/checkpoint API coverage is tracked in:
- `backend/tests/coding_agent_api/test_state.md`
- `backend/tests/coding_agent_checkpoints/test_state.md`

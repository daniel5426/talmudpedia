# Published Apps Backend Tests

Last Updated: 2026-02-10

## Scope of the feature
- Admin control plane CRUD and publish lifecycle for tenant published apps.
- Public runtime app resolution/config retrieval.
- End-user auth flows (email/password, Google OAuth callback path).
- Public chat streaming and chat persistence scoping by `published_app_id`.

## Test files present
- `backend/tests/published_apps/test_admin_apps_crud.py`
- `backend/tests/published_apps/test_admin_apps_publish_rules.py`
- `backend/tests/published_apps/test_public_app_resolve_and_config.py`
- `backend/tests/published_apps/test_public_auth_email_password.py`
- `backend/tests/published_apps/test_public_auth_google_oauth.py`
- `backend/tests/published_apps/test_public_chat_scope_and_persistence.py`

## Key scenarios covered
- Tenant admin can create/list/update/delete apps.
- Only published agents can be attached/published.
- Publish and unpublish lifecycle updates URL/status.
- Hostname resolve and app config retrieval for public runtime.
- Signup/login/logout and auth-me using published app session tokens.
- Google OAuth start and callback issuance path with tenant credentials.
- Chat stream persists user/assistant messages only when auth is enabled.
- Public mode chat is ephemeral and does not persist chat rows.

## Last run command + date/time + result
- Command: `pytest backend/tests/published_apps -q`
- Date: 2026-02-10 14:39 UTC
- Result: PASS (11 passed)

## Known gaps or follow-ups
- Add negative tests for cross-app token replay attempts.
- Add coverage for revoked-session rejection on chat endpoints.
- Add non-ASCII or very-long message streaming persistence tests.

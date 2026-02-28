Last Updated: 2026-02-26

# Test State: Published Apps Host Runtime (Same-URL Auth Gate)

## Scope
Backend same-URL published app host runtime flow for `*.apps` domains:
- same-URL auth shell render
- cookie-based signup/auth state
- cookie-protected chat stream access
- chat persistence with host runtime endpoint

## Test Files Present
- `backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`

## Key Scenarios Covered
- Unauthenticated root request on app host renders branded auth shell HTML
- Signup on `/_talmudpedia/auth/signup` sets `published_app_session` cookie
- `/_talmudpedia/auth/state` reflects authenticated user from cookie
- `/_talmudpedia/chat/stream` requires auth when `auth_enabled=true`
- Authenticated `/_talmudpedia/chat/stream` streams and persists chat/messages
- Legacy `/public/apps/{slug}` published runtime/auth/chat endpoints return `410`

## Last Run
- Command: `pytest backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Date/Time: 2026-02-26 (local run)
- Result: pass (5 tests)

## Known Gaps / Follow-ups
- No host asset/document authenticated bundle-serving tests yet (requires revision + bundle storage mocking)
- No Google OAuth callback host tests yet
- No external OIDC exchange host tests yet
- No stale/invalid cookie auto-clear tests yet
- No host-side chat history list/detail endpoints (not implemented in hard cut)

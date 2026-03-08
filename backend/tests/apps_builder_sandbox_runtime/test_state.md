Last Updated: 2026-03-08

# Apps Builder Sandbox Runtime Tests

## Scope of the feature
- Provider-abstracted draft-dev sandbox runtime selection and delegation.
- Platform preview proxy behavior for draft-dev sessions backed by remote sandbox hosts.
- Draft-dev runtime lifecycle behavior through the admin API for ensure, stale-session recovery, stop, and re-entry flows.

## Test files present
- `backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- `backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- `backend/tests/apps_builder_sandbox_runtime/test_e2b_live_smoke.py`

## Key scenarios covered
- The draft-dev runtime client delegates `start_session` to the selected sandbox backend and injects the stable preview proxy base path.
- The preview proxy enforces preview token validation before forwarding to the upstream sandbox host.
- The preview proxy strips `runtime_token` from upstream requests, forwards the sandbox traffic access token header, and sets the preview auth cookie on successful bootstrap.
- The preview proxy rewrites asset requests against the sandbox preview base path rather than the backend API route path.
- A failed initial sandbox start does not persist a placeholder sandbox id in the draft-dev session row.
- A stale sandbox id error during `ensure` triggers a clean restart path and updates the session to the new sandbox id.
- Stopping a draft-dev session and re-entering the app starts a fresh runtime cleanly.
- A gated live E2B smoke test now exists for create -> ensure -> preview -> kill -> recover -> stop, but it is not passing yet in real provider runs.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- Date: 2026-03-08 16:55:00 EET
- Result: PASS (7 passed, 6 warnings)

## Live provider run
- Command: `cd backend && E2B_API_KEY=... TEST_E2B_LIVE=1 APPS_SANDBOX_BACKEND=e2b PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_e2b_live_smoke.py -s`
- Date: 2026-03-08 17:00 EET
- Result: FAIL / HANG during preview readiness validation against real E2B

## Known gaps or follow-ups
- Add websocket proxy coverage once the proxied Vite/HMR path is exercised against a live draft-dev sandbox.
- Add contract tests for the real E2B backend once a deterministic fake sandbox harness is available.
- Investigate why live E2B Vite previews eventually die with `esbuild` `write EPIPE` inside the sandbox.
- Fix leaked/orphaned E2B sandboxes for the same draft-dev session scope during restart/recovery flows.

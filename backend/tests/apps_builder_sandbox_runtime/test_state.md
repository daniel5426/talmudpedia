Last Updated: 2026-03-09

# Apps Builder Sandbox Runtime Tests

## Scope of the feature
- Sprite-first App Builder draft-dev runtime selection, configuration, and live provider behavior.
- Platform preview proxy behavior for shared app workspaces backed by Sprite URLs.
- Shared-workspace runtime lifecycle behavior through the admin API for ensure, detach, dormant sweep, provider deletion recovery, and app cleanup flows.

## Test files present
- `backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- `backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- `backend/tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py`
- `backend/tests/apps_builder_sandbox_runtime/test_sprite_live_smoke.py`

## Key scenarios covered
- The draft-dev runtime client delegates `start_session` to the selected Sprite backend and injects the stable preview proxy base path.
- The preview proxy enforces preview token validation before forwarding to the upstream Sprite URL.
- The preview proxy strips `runtime_token` from upstream requests, forwards provider-neutral auth headers, and sets the preview auth cookie on successful bootstrap.
- The preview proxy rewrites Vite dev HTML so `@vite/client`, `@react-refresh`, and `/src/...` requests stay under the draft-dev preview proxy path instead of escaping to the backend root.
- The preview proxy rewrites Vite JS module imports like `/src/...` and `/node_modules/.vite/...`, and disables stale conditional caching for rewritten preview assets.
- The preview proxy retries transient `404/5xx/timeout` warmup failures for GET/HEAD preview assets so Sprite wake/service warmup does not immediately white-screen the iframe.
- The preview proxy rewrites asset requests against the Sprite upstream path instead of the backend API route path.
- The preview websocket proxy forwards auth headers, browser origin, user-agent, and requested subprotocols into the upstream websocket handshake.
- Sprite heartbeat waits for preview readiness without restarting the services on every reopen.
- Stage-to-live promotion now mirrors files into the existing live workspace instead of deleting the live root and restarting preview services.
- Sprite live sync preserves `node_modules/` across no-op file syncs, and start/sync can force a dependency repair plus Vite cache rebuild when preview readiness fails.
- Shared app-level draft workspaces are reused across multiple editors on the same app.
- Session stop detaches one editor without destroying the shared Sprite while another editor remains attached.
- Dormant workspace sweep destroys the shared Sprite only after all sessions detach and retention elapses.
- App delete destroys the shared Sprite and removes workspace metadata.
- Sprite backend env validation requires a Sprite token and hard-rejects archived E2B backend selection.
- The live Sprite smoke covers create -> ensure -> preview HTML -> proxied Vite asset -> second editor attach -> direct filesystem write/read -> detach/reattach -> provider-side Sprite delete -> recovery ensure -> preview recovery -> app delete -> provider cleanup.

## Last run command + date/time + result
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- Date: 2026-03-09 02:07 EET
- Result: PASS (17 passed, 6 warnings)
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py`
- Date: 2026-03-09 02:01 EET
- Result: PASS (16 passed, 6 warnings)
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/opencode_server_client/test_sprite_proxy_tunnel.py tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- Date: 2026-03-09 01:36 EET
- Result: PASS (8 passed, 6 warnings)
- Command: `cd backend && set -a; source .env >/dev/null 2>&1; PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py tests/apps_builder_sandbox_runtime/test_sprite_live_smoke.py tests/coding_agent_api/test_batch_finalizer.py tests/app_versions/test_coding_run_versions.py`
- Date: 2026-03-09 00:23 EET
- Result: PASS (20 passed, 6 warnings)

## Known gaps or follow-ups
- Add live websocket/HMR coverage against the Sprite preview path.
- Add a live coding-agent/OpenCode run test against the Sprite-backed shared workspace once the end-to-end OpenCode path is exercised in CI.
- Add an explicit scheduled sweeper entrypoint so orphan cleanup does not rely only on request-driven best-effort sweeps.

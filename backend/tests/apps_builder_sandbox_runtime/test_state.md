Last Updated: 2026-04-15

# Apps Builder Sandbox Runtime Tests

## Scope of the feature
- Sprite-first App Builder draft-dev runtime selection, configuration, and live provider behavior.
- Platform preview proxy behavior for shared app workspaces backed by Sprite URLs.
- Shared-workspace runtime lifecycle behavior through the admin API for ensure, detach, dormant sweep, provider deletion recovery, and app cleanup flows.

## Test files present
- `backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- `backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- `backend/tests/apps_builder_sandbox_runtime/test_coding_agent_runtime_sandbox.py`
- `backend/tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py`
- `backend/tests/apps_builder_sandbox_runtime/test_sprite_live_smoke.py`
- `backend/tests/apps_builder_sandbox_runtime/test_live_coding_run_e2e.py`

## Key scenarios covered
- The draft-dev runtime client delegates `start_session` to the selected Sprite backend and injects the stable preview proxy base path.
- The preview proxy enforces preview token validation before forwarding to the upstream Sprite URL.
- The preview proxy strips `runtime_token` from upstream requests, forwards provider-neutral auth headers, and sets the preview auth cookie on successful bootstrap.
- The preview proxy rewrites Vite dev HTML so `@vite/client`, `@react-refresh`, and `/src/...` requests stay under the draft-dev preview proxy path instead of escaping to the backend root.
- The preview proxy exposes the canonical builder preview base path to the runtime SDK and no longer depends on query-plumbed runtime bootstrap URLs.
- The preview proxy rewrites Vite JS module imports like `/src/...` and `/node_modules/.vite/...`, and disables stale conditional caching for rewritten preview assets.
- The preview proxy retries transient `404/5xx/timeout` warmup failures for GET/HEAD preview assets so Sprite wake/service warmup does not immediately white-screen the iframe.
- For Sprite-backed draft-dev sessions, the preview proxy resolves a local Sprite control-plane tunnel and proxies preview traffic through that tunnel instead of dialing the provider HTTPS hostname directly.
- The preview proxy now refreshes stale Sprite preview metadata on connect/TLS failures and retries once against the refreshed upstream URL.
- The preview proxy also refreshes stale preview metadata on upstream remote-protocol disconnects before failing the iframe request.
- The preview proxy rewrites asset requests against the Sprite upstream path instead of the backend API route path.
- The preview websocket proxy forwards auth headers, browser origin, user-agent, and requested subprotocols into the upstream websocket handshake.
- Sprite heartbeat waits for preview readiness without restarting the services on every reopen.
- Sprite heartbeat returns refreshed backend preview metadata, and the draft-dev runtime persists that refreshed metadata on session heartbeat.
- Sprite heartbeat preserves `live_workspace_snapshot` metadata that was recorded after coding-run reconciliation, instead of wiping it on the next refresh.
- Sprite heartbeat can repopulate a missing `live_workspace_snapshot` from the live workspace when an older session has already lost that metadata.
- Restored live workspace snapshots use the same builder file policy as save/materialization paths, so invalid files like no-extension roots never enter builder state.
- Stage-to-live promotion now mirrors files into the existing live workspace instead of deleting the live root and restarting preview services.
- Sprite workspace snapshots filter generated/high-noise paths before serializing payloads back to the backend.
- Sprite live sync preserves `node_modules/` across no-op file syncs, and start/sync can force a dependency repair plus Vite cache rebuild when preview readiness fails.
- Shared app-level draft workspaces are reused across multiple editors on the same app.
- Coding-run bootstrap can reuse a healthy live workspace even when the saved draft revision has advanced, instead of forcing a revision-driven resync.
- The public draft-dev `ensure` route reuses an already-serving live workspace via `ensure_active_session(..., prefer_live_workspace=True)` instead of falling back to the legacy full-sync path.
- Draft-dev incremental sync treats delete operations as idempotent when the target file is already absent in the live sandbox, instead of failing the whole sync on a stale delete.
- Coding-agent workspace-write detection ignores read-only `bash` probes like `git status`, while still flagging mutating shell commands and explicit write tools.
- Session stop detaches one editor without destroying the shared Sprite while another editor remains attached.
- Dormant workspace sweep destroys the shared Sprite only after all sessions detach and retention elapses.
- App delete destroys the shared Sprite and removes workspace metadata.
- Sprite backend env validation requires a Sprite token and hard-rejects archived E2B backend selection.
- The live Sprite smoke covers create -> ensure -> preview HTML -> proxied Vite asset -> second editor attach -> direct filesystem write/read -> detach/reattach -> provider-side Sprite delete -> recovery ensure -> preview recovery -> app delete -> provider cleanup.
- The live coding-run e2e covers create -> ensure draft-dev preview -> submit a real coding-agent prompt -> stream the live run -> poll preview/version/run state every second -> send recurring draft-dev heartbeats during long waits -> verify preview source updates without publish -> verify a new draft revision/version is created automatically -> drive the queued revision build in-test when no worker is present -> verify the built preview asset becomes reachable.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- Date: 2026-03-15
- Result: PASS (6 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- Date: 2026-03-17
- Result: PASS (7 passed, 6 warnings)
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py tests/coding_agent_api/test_batch_finalizer.py tests/app_versions/test_coding_run_versions.py tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py tests/apps_publish_sandbox/test_publish_runtime_helpers.py tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-03-09 19:03 EET
- Result: PASS (29 passed, 6 warnings)
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
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_live_coding_run_e2e.py`
- Date: 2026-03-09 19:40 EET
- Result: SKIPPED by default unless `APPS_BUILDER_LIVE_CODING_E2E=1`
- Command: `APPS_BUILDER_LIVE_CODING_E2E=1 PYTHONPATH=. pytest -q backend/tests/apps_builder_sandbox_runtime/test_live_coding_run_e2e.py -s`
- Date: 2026-03-09 21:26 EET
- Result: PASS (1 passed, 423 warnings, 163.30s)
- Command: `PYTHONPATH=. pytest -q backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py backend/tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py`
- Date: 2026-03-09 22:19 EET
- Result: PASS (25 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'heartbeat_preserves_existing_preview_base_path_when_refresh_returns_root or heartbeat_preserves_live_workspace_snapshot_metadata'`
- Date: 2026-04-14
- Result: PASS
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'heartbeat_preserves_existing_preview_base_path_when_refresh_returns_root or heartbeat_preserves_live_workspace_snapshot_metadata or heartbeat_restores_missing_live_workspace_snapshot_from_runtime'`
- Date: 2026-04-14
- Result: PASS
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'heartbeat_restores_missing_live_workspace_snapshot_from_runtime or heartbeat_restores_live_snapshot_with_shared_builder_file_policy'`
- Date: 2026-04-14
- Result: PASS
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py -k 'refreshes_stale_upstream_target_after_connect_error or refreshes_stale_upstream_target_after_remote_protocol_error'`
- Date: 2026-04-14
- Result: PASS
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- Date: 2026-04-14 Asia/Hebron
- Result: PASS (`14 passed, 8 warnings`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py`
- Date: 2026-04-14 18:24 EEST
- Result: PASS (`14 passed, 8 warnings`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session'`
- Date: 2026-04-14 18:02 EEST
- Result: PASS (`1 passed, 10 deselected`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'touch_session_activity_renews_expiry_without_detaching_workspace or ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session'`
- Date: 2026-04-14 18:26 EEST
- Result: PASS (`2 passed, 9 deselected`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'sync_route_ignores_delete_error_when_file_is_already_absent or ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session'`
- Date: 2026-04-14 18:43 EEST
- Result: PASS (`2 passed, 11 deselected`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/apps_builder_sandbox_runtime/test_coding_agent_runtime_sandbox.py`
- Date: 2026-04-15 Asia/Hebron
- Result: PASS

## Known gaps or follow-ups
- Add live websocket/HMR coverage against the Sprite preview path.
- Run the live coding-run e2e regularly in an environment with Sprite + OpenCode credentials so timing regressions are caught before manual QA.
- The live coding-run e2e currently drives the queued revision build itself because the pytest process does not run a background worker.
- Add an explicit scheduled sweeper entrypoint so orphan cleanup does not rely only on request-driven best-effort sweeps.

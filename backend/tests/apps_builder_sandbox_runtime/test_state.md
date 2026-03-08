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
- `backend/tests/apps_builder_sandbox_runtime/test_e2b_backend_config.py`
- `backend/tests/apps_builder_sandbox_runtime/test_e2b_workspace_paths.py`

## Key scenarios covered
- The draft-dev runtime client delegates `start_session` to the selected sandbox backend and injects the stable preview proxy base path.
- The preview proxy enforces preview token validation before forwarding to the upstream sandbox host.
- The preview proxy strips `runtime_token` from upstream requests, forwards the sandbox traffic access token header, and sets the preview auth cookie on successful bootstrap.
- The preview proxy rewrites asset requests against the sandbox preview base path rather than the backend API route path.
- The preview websocket proxy now forwards traffic token, browser origin, user-agent, and requested subprotocols into the upstream sandbox websocket handshake.
- A failed initial sandbox start does not persist a placeholder sandbox id in the draft-dev session row.
- A stale sandbox id error during `ensure` triggers a clean restart path and updates the session to the new sandbox id.
- Stopping a draft-dev session and re-entering the app starts a fresh runtime cleanly.
- Heartbeat no longer upgrades a draft-dev session to `running` when its `sandbox_id` is missing.
- Transient remote heartbeat timeouts no longer degrade the draft-dev session into a forced sandbox restart on the next `ensure`.
- Runtime restart now increments `runtime_generation`, reconciles remote ownership, and sweeps stale E2B sandboxes against DB-owned sessions.
- Draft-dev session API/runtime state now distinguishes `building`, `serving`, `degraded`, and `stopping` instead of collapsing everything into `running`.
- E2B workspace listing preserves leading-dot filenames, which fixes the coding-agent stage-prepare path that depends on `.draft-dev-dependency-hash`.
- E2B backend startup validation now requires both `E2B_API_KEY` and an explicit `APPS_E2B_TEMPLATE` unless the default-template bypass is deliberately enabled.
- E2B backend config now resolves `APPS_E2B_TEMPLATE` plus `APPS_E2B_TEMPLATE_TAG` into a concrete tagged template reference so sandbox creation targets a specific built template revision.
- E2B backend now forwards only non-empty provider env vars into the sandbox and the dedicated template is built from the `opencode` base template.
- OpenCode sandbox startup now creates the `.opencode` log directory first and launches through `bash -lc`, which matches the OpenCode binary path layout inside the E2B template.
- The gated live E2B smoke test now covers create -> ensure -> preview HTML -> proxied Vite asset -> out-of-band kill -> recover -> remote sandbox collapse -> stop -> zero remaining provider sandboxes for the session.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py`
- Date: 2026-03-08 21:42 EET
- Result: PASS (11 passed, 6 warnings)

## Live provider run
- Command: `cd backend && TEST_E2B_LIVE=1 PYTHONPATH=. pytest -q tests/apps_builder_sandbox_runtime/test_e2b_live_smoke.py -s`
- Date: 2026-03-08 23:18 EET
- Result: PASS (1 passed, 6 warnings) with runtime generation recovery, Vite asset fetch, and provider-side cleanup assertions

## Known gaps or follow-ups
- Add websocket proxy coverage once the proxied Vite/HMR path is exercised against a live draft-dev sandbox.
- Add contract tests for the real E2B backend once a deterministic fake sandbox harness is available.
- Add a second live E2B scenario that asserts proxied asset fetches and HMR websocket behavior, not only initial HTML preview health.
- Add an explicit scheduled sweeper entrypoint so orphan cleanup does not rely only on request-driven best-effort sweeps.
- Add a live coding-agent/OpenCode test that goes beyond server startup and verifies a real run lifecycle against the E2B sandbox backend.

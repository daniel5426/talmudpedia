# Platform Architect Runtime Tests

Last Updated: 2026-04-22

## Scope
- Platform Architect v1.2 direct domain-tool loop runtime (no `architect.run` path).
- Success, repair, approval-blocked, tenant/scope-denied, and replay idempotency behaviors.

## Test files present
- test_platform_architect_runtime.py
- test_architect_seeding.py
- test_native_platform_tools.py
- test_native_platform_assets_actions.py

## Key scenarios covered
- Happy path executes direct `rag.*` and `agents.*` calls for create/compile/validate/execute.
- Recovery path handles first compile failure, applies patch action, and succeeds on retry.
- Repeated identical architect mutation failures now stop with a blocker instead of looping indefinitely.
- Non-canonical Platform SDK contract failures now get three repair retries before blocking, and blocker attribution preserves the wrapped attempted action instead of collapsing to `noop`.
- Unsupported RAG actions get one replan opportunity and then block instead of looping.
- Repeated identical architect mutation failures now block on the fifth matching failure instead of the second.
- RAG create blocker payloads preserve FastAPI-style field validation details and derive a readable target from create payload names.
- Approval-sensitive mutation maps to `blocked_approval` with explicit next actions.
- Domain tool boundaries deny cross-domain action usage with `SCOPE_DENIED`.
- Missing tenant context for mutations fails with deterministic `TENANT_REQUIRED`.
- Runtime tenant context is sufficient for mutations even when payload omits `organization_id`.
- Explicit payload tenant override is rejected when it conflicts with runtime tenant context.
- Platform SDK tool output meta now includes redacted auth context for runtime debugging without leaking bearer tokens.
- Replay path reuses existing resources rather than duplicating them.
- `agents.create` propagates structured SDK validation details (including normalized `validation_errors`) for deterministic repair.
- Platform architect domain schema includes `agents.nodes.catalog/schema/validate` action contracts.
- Platform architect domain schema now includes `rag.operators.catalog/schema` action contracts for RAG-native discovery.
- Platform architect domain schema now includes `agents.create_shell` and `rag.create_pipeline_shell` as the preferred lightweight creation actions.
- Platform SDK bootstrap seeding now locks to canonical `builtin_key=platform_sdk` plus system artifact binding metadata and is covered directly.
- Seeded architect runtime no longer forces JSON-only output in prompt or node config.
- Seeded architect runtime now defaults `temperature` to `1`.
- Seeded architect runtime now sets `max_tool_iterations` to `26`.
- Seeded architect prompt now instructs artifact binding creation through `title_prompt + draft_seed.kind` and explicitly forbids low-level guesses like `create`, `files`, `entrypoint`, and `text`.
- Seeded architect prompt now treats artifact-coding delegated workers as draft-mutation-only workers and keeps persistence architect-owned through `architect-worker-binding-persist-artifact`.
- Seeded architect prompt now forbids asking artifact-coding workers to mutate runtime-owned readiness fields like `persistence_readiness`.
- Seeded architect prompt now treats ambiguous read-surface prompts more explicitly: prompt/template discovery must use `prompts.list`, and platform tool inventory must treat tools as canonical action ids by domain, not domain container slugs, without inventing `help` actions or leaking architect-worker tools.
- Seeded architect prompt now makes shell-create payload contracts explicit: `agents.create_shell` must use `name` only, `rag.create_pipeline_shell` must use only `name` plus optional `pipeline_type=retrieval`, and knowledge-store create flows must resolve an embedding-capable model before create.
- Direct guardrail tests now call the live guardrail contract shape with `builtin_key` and `state_context.agent_system_key`, matching runtime tool execution.
- Seeded artifact-coding worker instructions now spell out the required draft fields for a new artifact before the architect can persist it.
- Architect domain tools now bind to native backend control-plane function dispatch instead of the runtime SDK shim.
- Native `platform-*` dispatch preserves runtime auth/tenant context and rejects cross-domain action mismatch before execution.
- Native `platform-*` list actions now default to bounded `view=summary` responses with the shared `items/total/has_more/skip/limit/view` envelope.
- Native `platform-assets` now exposes canonical `prompts.list` reads backed by the prompt library service.
- Seeded architect domain-tool registry schema now matches the shared list contract, including `view`, `limit<=100`, and removal of stale `agents.list.compact`.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-10 19:02 EET
- Result: passed (`3 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_execution backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_propagates_delegation_context`
- Date/Time: 2026-03-12 02:04 EET
- Result: passed (`20 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_architect_runtime/test_local_platform_sdk_tools.py backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py`
- Date/Time: 2026-03-12 03:07 EET
- Result: passed (`28 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_local_platform_sdk_tools.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py`
- Date/Time: 2026-03-12 03:39 EET
- Result: passed (`28 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-14 20:39 EET
- Result: passed (`10 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-15 01:01 Asia/Hebron
- Result: passed (`19 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
- Date/Time: 2026-03-15 00:27 EET
- Result: passed (`55 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py`
- Date/Time: 2026-03-16 01:16 Asia/Hebron
- Result: passed (`38 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-16 17:14 EET
- Result: passed (`4 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-16 19:20 Asia/Hebron
- Result: passed (`4 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-16 20:12 EET
- Result: passed (`15 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
- Date/Time: 2026-03-17 18:32 Asia/Hebron
- Result: passed (`65 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: passed (`8 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_platform_architect_runtime.py -k 'redacted_auth_context or models or tenant_and_scope_denial_paths'`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: passed (`2 passed, 12 deselected, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 00:07 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py`
- Date/Time: 2026-04-15 01:59 EEST
- Result: passed (`11 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 02:15 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 02:30 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 02:39 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 02:46 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py`
- Date/Time: 2026-04-15 02:46 EEST
- Result: passed (`8 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-04-15 03:00 EEST
- Result: passed (`4 passed, 6 warnings`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/settings_people_permissions/test_settings_people_permissions_api.py backend/tests/graph_mutation_agents/test_agent_graph_mutation_routes.py backend/tests/rag_extreme_campaign/test_admin_graph_and_jobs_api.py backend/tests/artifact_runtime/test_artifact_versions_api.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS (`30 passed`). Architect seeding assertions now match the id-only tool contracts and the current prompt language after the slug hard cut.

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
- Add deeper live/runtime coverage beyond direct native `platform-assets` action adapter tests for publish and execution-heavy flows.

## Latest Validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/platform_architect_runtime/test_native_platform_assets_actions.py tests/platform_architect_runtime/test_native_platform_tools.py tests/platform_native_adapter/test_platform_native_adapter.py tests/organization_bootstrap/test_default_agent_profiles.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: Pass (`18 passed, 6 warnings`)

## 2026-04-21 validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/platform_native_adapter/test_platform_native_adapter.py`
- Result: `11 passed`

- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS (`4 passed`). Agent response/runtime metadata now expose `system_key`-based architect identification without slug-era frontend contracts.

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/platform_architect_runtime/test_native_platform_assets_actions.py tests/platform_architect_runtime/test_native_platform_tools.py tests/platform_native_adapter/test_platform_native_adapter.py tests/organization_bootstrap/test_default_agent_profiles.py`
- Result: PASS (`18 passed, 6 warnings`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)

## 2026-04-21 guardrail alignment validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_platform_architect_runtime.py -k 'guardrails'`
- Result: PASS (`4 passed, 14 deselected, 6 warnings`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Result: PASS (`4 passed, 6 warnings`)

## 2026-04-22 system bootstrap validation
- Command: `TEST_USE_REAL_DB=0 SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py::test_seed_platform_sdk_tool_creates_published_system_artifact_binding`
- Result: PASS (`1 passed`)

# Platform Architect Runtime Tests

Last Updated: 2026-04-22

## Scope
- Platform Architect action-level tool surface and native backend dispatch wiring.
- Success, repair, approval-blocked, tenant/scope-denied, replay idempotency, and seeded architect tool-surface behaviors.

## Test files present
- test_platform_architect_runtime.py
- test_architect_seeding.py
- test_native_platform_tools.py
- test_native_platform_assets_actions.py

## Key scenarios covered
- Canonical architect surface is now a hard cut to `38` action-level platform tools plus `5` worker tools, with no architect-mounted `platform-rag` / `platform-agents` / `platform-assets` / `platform-governance` container tools.
- Seeded architect prompt is graph-first: discover nodes/operators, author full graphs, rely on normalization/defaulting, validate/compile, then run/publish.
- Seeded architect prompt now forbids `action` / `payload` wrappers for platform action tools because each mounted tool fixes its own action id.
- Action-tool schemas are direct-field tool contracts and no longer require model-authored `action` or nested `payload`.
- Canonical graph-authoring actions are now clean-cut contracts: `agents.update` and `rag.update_visual_pipeline` no longer expose `patch`, `rag.create_visual_pipeline` no longer accepts `graph_definition`, and `agents.validate` no longer accepts a loose `validation` bag.
- Native adapter coverage now rejects legacy `patch` / `graph_definition` inputs directly and enforces top-level update-field requirements plus `nodes+edges` pairing for RAG graph updates.
- Canonical action-tool rows seed as real global system tools whose `builtin_key` is the canonical action id and whose function binding is a generated `platform_action_*` wrapper.
- Action-level wrapper functions reconstruct the fixed canonical action id and dispatch through the shared native platform runtime.
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
- Mounted architect action schemas now forbid model-authored scope selectors like `organization_id`, `project_id`, `tenant_slug`, and `org_unit_id`.
- The mounted architect asset surface now uses explicit `tools.create` / `tools.update` and `knowledge_stores.create` / `knowledge_stores.update` actions instead of mixed `create_or_update` contracts.
- Platform SDK tool output meta now includes redacted auth context for runtime debugging without leaking bearer tokens.
- Replay path reuses existing resources rather than duplicating them.
- `agents.create` propagates structured SDK validation details (including normalized `validation_errors`) for deterministic repair.
- Platform architect domain schema still serves as the internal action catalog source of truth, while architect-facing seeded rows now expose the kept actions directly.
- Platform architect action schema includes `agents.nodes.catalog/schema` and `rag.operators.catalog/schema` for graph discovery.
- Discovery schema responses now expose canonical `node_template` and `normalization_defaults` hints so the architect can author graph nodes using the same omit-safe defaults the backend applies on write.
- RAG discovery/authoring now treats runtime-only node config fields as runtime-only instead of persisted authoring requirements, and the architect prompt now explicitly distinguishes retrieval graph output nodes from runtime query input values.
- The architect prompt now forbids calling `rag.get_executable_*` before successful compile and steers failed compile loops toward repairing the same pipeline instead of creating duplicates.
- Native `agents.nodes.catalog` and `agents.nodes.schema` adapter coverage now verifies control-plane `ctx` is passed through, matching the live architect runtime path.
- Platform SDK bootstrap seeding now locks to canonical `builtin_key=platform_sdk` plus system artifact binding metadata and is covered directly.
- Seeded architect runtime no longer forces JSON-only output in prompt or node config.
- Seeded architect runtime now defaults `temperature` to `1`.
- Seeded architect runtime now sets `max_tool_iterations` to `26`.
- Seeded architect prompt now instructs artifact binding creation through `title_prompt + draft_seed.kind` and explicitly forbids low-level guesses like `create`, `files`, `entrypoint`, and `text`.
- Seeded architect prompt now treats artifact-coding delegated workers as draft-mutation-only workers and keeps persistence architect-owned through `architect-worker-binding-persist-artifact`.
- Seeded architect prompt now forbids asking artifact-coding workers to mutate runtime-owned readiness fields like `persistence_readiness`.
- Seeded architect prompt now treats platform tool inventory as the mounted canonical action ids by family rather than the old domain container slugs.
- Seeded architect prompt now makes graph-first create/update the normal path and removes shell/helper authoring guidance.
- Direct guardrail tests now call the live guardrail contract shape with `builtin_key` and `state_context.agent_system_key`, matching runtime tool execution.
- Seeded artifact-coding worker instructions now spell out the required draft fields for a new artifact before the architect can persist it.
- Architect domain tools now bind to native backend control-plane function dispatch instead of the runtime SDK shim.
- Native `platform-*` dispatch preserves runtime auth/tenant context and rejects cross-domain action mismatch before execution.
- Native `platform-*` list actions now default to bounded `view=summary` responses with the shared `items/total/has_more/skip/limit/view` envelope.
- Native `platform-assets` now exposes canonical `prompts.list` reads backed by the prompt library service.
- Seeded architect action-tool registry schema now matches the shared list contract, including `view`, `limit<=100`, and removal of stale `agents.list.compact`.

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

## 2026-04-22 architect action-tool hard-cut validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/tool_execution/test_function_tool_execution.py -k 'strict_platform or test_architect_seeding or test_native_platform_tools'`
- Result: PASS (`19 passed, 12 deselected`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/graph_authoring`
- Result: PASS (`7 passed`)

## 2026-04-22 graph-first contract tightening validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py`
- Result: PASS (`23 passed`)

## 2026-04-22 discovery-surface validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/schema_contracts/test_schema_contract_surfaces.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py`
- Result: PASS (`28 passed`)

## 2026-04-22 node-discovery adapter validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_native_platform_tools.py -k 'agents_nodes_catalog or agents_nodes_schema'`
- Result: PASS (`2 passed, 23 deselected`)

## 2026-04-22 scope hard-cut validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py`
- Result: PASS (`39 passed, 6 warnings`)

## 2026-04-22 node-contract and architect-rag guidance validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/graph_authoring backend/tests/schema_contracts/test_schema_contract_surfaces.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py`
- Result: PASS (`42 passed, 6 warnings`)

# Platform Architect Tool Harness Phase 1-3 Findings

Last Updated: 2026-04-14

## Resolution Status

Implemented on 2026-04-14 for the scoped phase-1 to phase-3 fix plan:
- agent-call child lineage/events now preserve caller node ids
- reasoning alias coercion is restored in the reasoning executor
- stale artifact-bound `/tools` test was moved to the artifact-native publish flow
- stale `rag.create_pipeline_shell` parity expectation was updated to the current shell graph
- model/credential/vector-store fixtures now seed tenant rows explicitly

Verification command:

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/tool_execution/test_agent_call_tool_execution.py \
  backend/tests/tool_execution/test_reasoning_tool_input_aliases.py \
  backend/tests/tool_execution/test_artifact_runtime_tool_execution.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/model_registry/test_credentials_resolution.py \
  backend/tests/model_registry/test_vector_store_credentials.py
```

Result:
- `100 passed`

Phase 4 artifact/runtime drift was also cleaned up on 2026-04-14:
- artifact publish/version tests now stub deployment at the test boundary instead of requiring Cloudflare env
- artifact API tests now expect the current structured `422` / `429` error envelopes
- artifact run status fixtures now seed real revision ids instead of violating FK constraints
- queued cancel tests now stub enqueueing so they stay queued without triggering deployment

Phase 4 verification commands:

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/artifact_runtime/test_artifact_working_draft_api.py \
  backend/tests/artifact_runtime/test_artifact_versions_api.py \
  backend/tests/artifact_runtime/test_revision_service.py \
  backend/tests/artifact_runtime/test_execution_service.py \
  backend/tests/artifact_test_runs/test_artifact_test_run_api.py \
  backend/tests/tool_execution/test_artifact_runtime_tool_execution.py
```

Result:
- `47 passed`

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/control_plane_sdk/test_client_and_modules.py
```

Result:
- `97 passed`

## Scope

Initial audit plus subsequent resolution log for phases 1 to 8.

Phases covered:
- Phase 1: Harness Core
- Phase 2: Discovery And Schema Introspection
- Phase 3: Platform Assets And Registry
- Phase 4: Artifact Authoring And Publishing
- Phase 5: Agent Authoring
- Phase 6: RAG Authoring
- Phase 7: Runtime Execution
- Phase 8: Worker And Orchestration

## Commands Run

### Phase 1

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/tool_execution/test_function_tool_execution.py \
  backend/tests/tool_execution/test_mcp_tool_execution.py \
  backend/tests/tool_execution/test_agent_call_tool_execution.py \
  backend/tests/tool_execution/test_artifact_runtime_tool_execution.py \
  backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py \
  backend/tests/tool_execution/test_reasoning_tool_input_aliases.py \
  backend/tests/platform_native_adapter/test_platform_native_adapter.py \
  backend/tests/control_plane_contracts/test_control_plane_contracts.py \
  backend/tests/platform_architect_runtime/test_native_platform_tools.py
```

Result:
- `10 failed, 53 passed`

### Phase 2

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_architect_runtime/test_architect_seeding.py \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py
```

Result:
- `17 passed`

### Phase 3

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/model_registry \
  backend/tests/control_plane_contracts/test_route_adapter_parity.py \
  backend/tests/control_plane_operations/test_control_plane_operations.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py
```

Result:
- `7 failed, 90 passed`

## Findings

### Phase 1: Real Regressions

1. Agent-call child-run metadata is losing the caller node id.
   - Failing tests:
     - `test_agent_call_tool_emits_hidden_child_run_started_with_target_agent_name`
     - `test_agent_call_tool_derives_child_lineage_from_current_run`
     - `test_agent_call_tool_emits_hidden_child_run_started_event_for_overlay`
   - Current behavior:
     - expected `source_node_id` / `parent_node_id` from runtime context like `agent_1`, `agent_node_1`, `agent_node_overlay`
     - actual value is hardcoded or collapsed to `tool_node`
   - Impact:
     - child-run overlays and lineage attribution are wrong
     - nested execution tracing is less reliable

2. Reasoning executor alias coercion is currently broken for path/content rename helpers.
   - Failing tests:
     - `test_coerce_tool_input_maps_path_aliases`
     - `test_coerce_tool_input_maps_nested_path_aliases`
     - `test_coerce_tool_input_maps_parameters_wrapper_path_aliases`
     - `test_coerce_tool_input_maps_json_string_value_path_aliases`
     - `test_coerce_tool_input_maps_content_aliases`
     - `test_coerce_tool_input_maps_rename_aliases`
   - Current behavior:
     - `_coerce_tool_input(...)` is not mapping aliases like `file_path`, `filePath`, `relativePath`, `fromPath`, `toPath`, `code`
   - Impact:
     - reasoning-model tool calls are less resilient
     - file/path oriented tools may fail even when the model intent is clear

### Phase 1: Contract/Test Mismatch

3. Artifact-bound tool publish test is stale relative to the current domain-owned tool contract.
   - Failing test:
     - `test_tool_publish_pins_artifact_revision_id`
   - Current behavior:
     - `/tools` rejects creation of artifact-backed tool rows with:
       - `artifact and rag_pipeline tools are domain-owned. Create them from the artifact or pipeline editor.`
   - Spec alignment:
     - this matches `docs/product-specs/tools_domain_spec.md`
   - Assessment:
     - likely a stale test, not a new platform bug

### Phase 2

4. Phase 2 suites passed.
   - `17 passed`
   - The seeded architect runtime and direct domain-tool loop for discovery/schema did not show immediate regressions in this batch.

### Phase 3: Likely Test Fixture Breakage

5. Model credential-resolution tests now violate tenant foreign keys.
   - Failing tests:
     - `test_resolve_credentials_prefers_integration_credentials`
     - `test_resolve_credentials_prefers_tenant_default_over_env_fallback`
     - `test_resolve_credentials_falls_back_to_env_platform_default`
     - `test_resolve_embedding_uses_integration_credentials`
     - `test_vector_store_credentials_merge`
     - `test_vector_store_credentials_disabled_raises`
   - Current behavior:
     - tests create tenant-scoped rows using random `tenant_id` values without inserting tenant records first
     - DB now rejects these inserts with FK violations
   - Assessment:
     - likely stale fixtures after stricter tenant integrity
     - not enough evidence here of a runtime regression in resolver behavior itself

### Phase 3: SDK/Native Parity Drift

6. SDK parity expectation for `rag.create_pipeline_shell` is stale.
   - Failing test:
     - `test_rag_create_pipeline_shell_builds_minimal_retrieval_graph`
   - Current expectation in test:
     - node[0] `query_input`
     - node[1] `retrieval_result`
   - Current native implementation:
     - `query_input -> model_embedder -> vector_search -> retrieval_result`
   - Assessment:
     - parity test is behind the current shell-graph contract

## Coverage Gaps Found During Audit

### Phase 1 Gaps

- Harness-core tests do not yet prove full end-to-end trace parity for all architect-visible native domains.
- The existing `platform_native_adapter` coverage is still very thin and mostly adapter-shape level.

### Phase 2 Gaps

- Discovery coverage is strong for:
  - `agents.nodes.*`
  - `rag.operators.*`
- But there is no equivalent broad discovery/read audit for:
  - `tools.*`
  - `credentials.*`
  - `knowledge_stores.*`

### Phase 3 Gaps

- Direct native architect/runtime coverage is still weak for:
  - `tools.list`
  - `tools.get`
  - `tools.create_or_update`
  - `tools.publish`
  - `credentials.list`
  - `credentials.create_or_update`
  - `knowledge_stores.list`
  - `knowledge_stores.create_or_update`
- Current coverage for those actions is mostly:
  - SDK/client parity tests
  - route/service parity in limited places
  - one blocked `tools.publish` path in architect runtime
- `models.list` has direct native parity coverage.
- The rest of the assets/registry group does not yet have the same native-architect depth.

## Current Assessment

- Phases 1 to 8 are now green in the audited batches.
- The remaining work is no longer this regression set; it is the next platform-architect tool phases.

## Phase 7 Addendum: Runtime Execution

### Command Run

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/control_plane_sdk/test_http_integration.py \
  -k 'agents_execute or agents.execute or start_run or get_run or rag.create_job or rag.get_job or get_run_tree'
```

Result:
- `5 passed, 98 deselected`

### Findings

10. Phase 7 runtime execution coverage was green without code changes.
   - `agents.execute`
   - `agents.start_run`
   - `agents.get_run`
   - `agents.get_run_tree`
   - `rag.create_job`
   - `rag.get_job`

## Phase 8 Addendum: Worker And Orchestration

### Fixes Applied

- worker/orchestration fixtures now seed real `Agent` rows instead of invalid FK placeholder UUIDs
- root orchestrator runs now seed real `AgentThread` rows so child thread lineage resolves correctly
- cross-session worker binding tests now commit between prepare and spawn when a second tool session is intentionally used
- architect-worker integration tests now use session-safe mocks
- stale GraphSpec-v2 expectations were aligned to the current compiler/runtime split:
  - runtime policy enforcement is covered in kernel tests
  - compile-time routing/feature-flag behavior is covered in graphspec tests

### Verification Command

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_architect_workers/test_worker_runtime.py \
  backend/tests/platform_architect_workers/test_architect_worker_integration.py \
  backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py \
  backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py \
  backend/tests/orchestration_join_policies/test_join_policies.py \
  backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py \
  backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py
```

Result:
- `40 passed`

### Final Phase 7-8 Combined Audit Batch

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/control_plane_sdk/test_http_integration.py \
  backend/tests/platform_architect_workers/test_worker_runtime.py \
  backend/tests/platform_architect_workers/test_architect_worker_integration.py \
  backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py \
  backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py \
  backend/tests/orchestration_join_policies/test_join_policies.py \
  backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py \
  backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py \
  -k 'agents_execute or agents.execute or start_run or get_run or rag.create_job or rag.get_job or get_run_tree or architect-worker or orchestration or spawn_run or spawn_group or join or cancel_subtree or evaluate_and_replan or query_tree'
```

Result:
- `45 passed, 107 deselected`

## Phase 5 Addendum: Agent Authoring

### Command Run

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py \
  backend/tests/graph_mutation_agents/test_agent_graph_mutation_routes.py \
  backend/tests/agent_graph_validation/test_agent_graph_validation.py \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  -k 'agents or graph or validate or publish or create_shell'
```

Result:
- `6 failed, 41 passed, 54 deselected`

### Findings

9. `agent_graph_validation` route tests are now failing at the auth/scope layer, not the graph-validation layer.
   - Failing tests:
     - `test_create_endpoint_missing_graph_returns_validation_error`
     - `test_update_endpoint_accepts_incomplete_graph`
     - `test_update_graph_endpoint_accepts_incomplete_graph`
     - `test_validate_endpoint_returns_structured_errors_and_warnings`
     - `test_nodes_catalog_and_schema_endpoints`
     - `test_nodes_schema_requires_non_empty_node_types`
   - Current behavior:
     - every failing route returns `403`
     - service-level tests in the same file still pass
   - Strong assessment:
     - this is concentrated route-contract drift after stricter scope enforcement on `agents.*` endpoints
     - likely stale auth headers/helpers in the test file rather than a broad agent-authoring runtime regression

10. Agent-authoring control-plane core outside that auth path looks healthy in this batch.
   - Passing areas:
     - `graph_mutation_agents` service and route tests
     - `platform_architect_runtime` agent/control-plane adapter tests in the selected subset
     - SDK parity coverage for agent actions in the selected subset

### Recommended Next Step

- Patch `backend/tests/agent_graph_validation/test_agent_graph_validation.py` to use the current scoped auth shape expected by `/agents` routes.
- Then rerun the same phase 5 batch before widening to deeper agent-authoring coverage.

### Resolution Status

Implemented on 2026-04-14:
- route test helper now mints scoped bearer tokens for `agents.read` / `agents.write`
- stale create-validation assertion now matches the shared `VALIDATION_ERROR` envelope with nested `details.errors`
- stale node-schema success test now uses the current contract where unknown node types are validation errors, not partial-success payload items

Verification command:

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py \
  backend/tests/graph_mutation_agents/test_agent_graph_mutation_routes.py \
  backend/tests/agent_graph_validation/test_agent_graph_validation.py \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  -k 'agents or graph or validate or publish or create_shell'
```

Result:
- `47 passed, 55 deselected`

## Phase 6 Addendum: RAG Authoring

### Command Run

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py \
  backend/tests/graph_mutation_rag/test_rag_graph_mutation_routes.py \
  backend/tests/platform_architect_runtime/test_platform_architect_runtime.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/control_plane_sdk/test_http_integration.py \
  -k 'rag or pipeline or operators or compile_visual_pipeline or create_pipeline_shell or attach_knowledge_store_to_node or set_pipeline_node_config or executable'
```

Result:
- `29 passed, 62 deselected`

### Findings

11. Phase 6 passed clean on the first batch.
   - Passing areas:
     - RAG graph mutation service
     - RAG graph mutation routes
     - architect runtime RAG action subset
     - SDK parity coverage for operator discovery, shell creation, graph patching, compile, and executable reads
     - control-plane HTTP integration subset for RAG list/read paths

### Current Assessment

- Phases 1 to 6 are green at the current audit-batch level.
- The next useful batch is phase 7: runtime execution for `agents.execute/start_run/get_run` and `rag.create_job/get_job`.

## Recommended Next Step

Do not fix ad hoc.

Next phase should be a dedicated fixing plan that groups work into:
1. Harness regressions
2. Stale tests vs changed contracts
3. Missing native-architect coverage for assets/registry actions

## Phase 4 Addendum: Artifact Authoring And Publishing

### Commands Run

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/artifact_runtime/test_artifact_working_draft_api.py \
  backend/tests/artifact_runtime/test_artifact_versions_api.py \
  backend/tests/artifact_runtime/test_revision_service.py \
  backend/tests/artifact_runtime/test_execution_service.py \
  backend/tests/artifact_test_runs/test_artifact_test_run_api.py \
  backend/tests/tool_execution/test_artifact_runtime_tool_execution.py
```

Result:
- `7 failed, 40 passed`

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py \
  backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py \
  backend/tests/control_plane_sdk/test_client_and_modules.py
```

Result:
- `1 failed, 96 passed`

### Additional Findings

#### Phase 4: Stale Test Updates

7. SDK parity test for `rag.create_pipeline_shell` still expects the old shell graph.
   - Failing test:
     - `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py::test_rag_create_pipeline_shell_builds_minimal_retrieval_graph`
   - Current native behavior:
     - shell graph is `query_input -> model_embedder -> vector_search -> retrieval_result`
   - Assessment:
     - stale parity expectation, not a new runtime regression

8. Artifact-bound tool publish test through `/tools` remains stale in phase 4 too.
   - Failing test:
     - `backend/tests/tool_execution/test_artifact_runtime_tool_execution.py::test_tool_publish_pins_artifact_revision_id`
   - Reason:
     - generic `/tools` creation of artifact-bound tools is now correctly blocked by the domain-owned tool contract

#### Phase 4: Likely Real Runtime / Contract Drift

9. Artifact version publish flow is tripping over artifact-run revision integrity.
   - Failing tests:
     - `backend/tests/artifact_runtime/test_artifact_versions_api.py::test_artifact_version_endpoints_list_and_get_saved_revisions`
     - `backend/tests/artifact_runtime/test_artifact_versions_api.py::test_update_artifact_returns_clean_python_syntax_error`
   - Evidence:
     - `artifact_runs.revision_id` FK violations against missing `artifact_revisions`
   - Assessment:
     - likely real runtime/infrastructure drift in artifact run persistence or publish/test-run orchestration

10. Artifact test-run API now shows error-shape drift and run-persistence drift.
    - Failing tests:
      - `backend/tests/artifact_test_runs/test_unsaved_artifact_test_run_returns_clean_execute_contract_error`
      - `backend/tests/artifact_test_runs/test_artifact_test_run_can_be_cancelled_while_queued`
      - `backend/tests/artifact_test_runs/test_artifact_runtime_status_endpoint_reports_active_count_and_limit`
      - `backend/tests/artifact_test_runs/test_unsaved_artifact_test_run_returns_429_when_capacity_is_exhausted`
    - Evidence:
      - some tests expect old plain-string `detail` payloads, but current responses are structured error objects
      - one runtime-status test inserts an `ArtifactRun` with a fake `revision_id`, which now violates FK integrity
    - Assessment:
      - mixed bucket:
        - plain-string error assertions look stale
        - fake-run fixture with nonexistent `revision_id` is stale under stricter integrity
        - queued cancel/runtime-status behavior still needs a dedicated recheck after fixture cleanup

### Phase 4 Coverage Note

11. Artifact authoring coverage exists and is broader than phases 1-3, but it is split across multiple layers:
    - artifact API/runtime tests
    - SDK parity tests
    - tool-execution artifact tests
    - artifact test-run API tests
    - direct architect-native coverage is still lighter than the artifact-domain coverage itself

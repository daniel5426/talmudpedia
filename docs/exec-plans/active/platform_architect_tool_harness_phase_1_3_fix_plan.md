# Platform Architect Tool Harness Phase 1-3 Fix Plan

Last Updated: 2026-04-14

## Status

Implemented on 2026-04-14 for the scoped regression batch in this plan.

Verification:

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

## Scope

Planning only. No runtime fixes applied in this phase.

This plan follows:
- [platform_architect_tool_harness_phase_1_3_findings.md](/Users/danielbenassaya/Code/personal/talmudpedia/docs/exec-plans/active/platform_architect_tool_harness_phase_1_3_findings.md)

## Goal

Stabilize the architect tool/harness for phases 1 to 3 by separating:
- real runtime regressions
- stale tests caused by contract evolution
- broken fixtures
- missing native-harness coverage

## Fix Workstreams

### 1. Real Harness Regressions

These should be fixed in runtime code first.

#### 1.1 Agent-call child lineage metadata

Symptoms:
- child-run events and parent linkage use `tool_node` instead of the actual caller node id

Failing tests:
- `backend/tests/tool_execution/test_agent_call_tool_execution.py::test_agent_call_tool_emits_hidden_child_run_started_with_target_agent_name`
- `backend/tests/tool_execution/test_agent_call_tool_execution.py::test_agent_call_tool_derives_child_lineage_from_current_run`
- `backend/tests/tool_execution/test_agent_call_tool_execution.py::test_agent_call_tool_emits_hidden_child_run_started_event_for_overlay`

Fix target:
- preserve runtime `context.node_id` through:
  - child-run creation
  - overlay/internal events
  - lineage metadata

Likely code area:
- `backend/app/agent/executors/tool.py`
- possibly `backend/app/agent/execution/tool_event_metadata.py`

#### 1.2 Reasoning tool-input alias coercion

Symptoms:
- aliases like `file_path`, `filePath`, `relativePath`, `fromPath`, `toPath`, `code` are no longer coerced into canonical tool args

Failing tests:
- `backend/tests/tool_execution/test_reasoning_tool_input_aliases.py`

Fix target:
- restore alias-to-canonical mapping in the reasoning executor without reintroducing generic executor fallback normalization

Likely code area:
- `backend/app/agent/executors/standard.py`

Constraint:
- keep the hard-cut executor/compiler rules intact
- only reasoning-node local coercion should do this mapping

### 2. Stale Test Updates

These should be updated to match current contracts, not “fixed” in runtime.

#### 2.1 Artifact-bound tool creation through `/tools`

Failing test:
- `backend/tests/tool_execution/test_artifact_runtime_tool_execution.py::test_tool_publish_pins_artifact_revision_id`

Reason:
- test still expects artifact-backed tool creation through generic `/tools`
- current spec correctly marks artifact/rag-pipeline tools as domain-owned

Update:
- rewrite test to create/publish through the artifact-native flow, then validate tool pinning behavior from the bound-tool lifecycle

#### 2.2 RAG pipeline shell parity expectation

Failing test:
- `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py::test_rag_create_pipeline_shell_builds_minimal_retrieval_graph`

Reason:
- test expects the older 2-node shell
- native shell now uses:
  - `query_input`
  - `model_embedder`
  - `vector_search`
  - `retrieval_result`

Update:
- align parity assertion to the current shell graph or make the shell shape come from one shared contract source

### 3. Fixture Repairs

These are test-environment issues, not product regressions.

#### 3.1 Tenant foreign-key setup in model/credential tests

Failing tests:
- `backend/tests/model_registry/test_credentials_resolution.py`
- `backend/tests/model_registry/test_vector_store_credentials.py`

Reason:
- tests create tenant-scoped rows using random `tenant_id` values without inserting tenant rows first

Update:
- seed a `Tenant` row explicitly in those tests before creating model/credential/knowledge-store rows

### 4. Coverage Build-Out

These are now partially improved but still need deeper follow-up.

#### 4.1 Added in this phase

New native-harness tests now cover:
- `tools.list`
- `tools.create_or_update`
- `credentials.list`
- `credentials.create_or_update`
- `knowledge_stores.list`
- `knowledge_stores.create_or_update`

Files:
- [backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py)

Verified with:
- `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py`
- result: `8 passed`

#### 4.2 Still missing

Need deeper native-harness coverage for:
- `tools.get`
- `tools.publish`
- `models.create_or_update`
- knowledge-store update path
- error-path coverage for assets actions under tenant/scope/publish-policy constraints

Need broader integration coverage for:
- artifact -> tool row -> publish
- knowledge store -> pipeline attachment -> compile
- assets actions from seeded architect runtime, not only direct native dispatch

## Recommended Execution Order

1. Fix real regressions:
   - agent-call lineage
   - reasoning alias coercion
2. Repair stale tests to current contracts:
   - artifact-bound tool test
   - rag shell parity test
3. Repair broken fixtures:
   - model/credential/vector-store tenant setup
4. Expand native assets coverage:
   - remaining actions and error paths
5. Re-run the phase 1-3 audit batches

## Success Criteria

- Phase 1 harness batch passes without excluding current failing tests
- Phase 3 asset/registry batch passes after fixture and stale-test cleanup
- Native architect-harness coverage exists for all core `platform-assets` actions used by the architect
- Findings doc can be reduced to true open product gaps instead of mixed regressions/test drift

# Design Docs Index

Last Updated: 2026-03-31

This section is for architecture and design documents that explain system shape, constraints, and tradeoffs.

## Put Here
- Domain architecture docs
- Decision records
- Security and auth design docs
- Runtime model docs
- Cross-cutting platform design docs

## Do Not Put Here
- Task checklists
- Temporary implementation plans
- Debug notes
- Generated inventories
- User-facing product behavior specs

## Initial Migration Targets
- `backend/documentations/platform_layered_architecture_abstract.md`
- `backend/documentations/agent_execution_overview.md`
- `backend/documentations/platform_architect_spec.md`
- `backend/documentations/auth/`
- `backend/documentations/architecture/`
- `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md`
- `backend/documentations/summary/CustomCodingAgent.md`

## Current Canonical Docs
- `backend_architecture_current.md`
  - Current backend architecture overview grounded in the live codebase.
- `agent_execution_current.md`
  - Current agent execution architecture and runtime responsibilities.
- `platform_current_state.md`
  - Current platform-level overview across domains and runtime surfaces.
- `platform_architecture_layers.md`
  - Conceptual layered architecture and boundary model.
- `auth_current.md`
  - Current authentication, authorization, and workload-security overview.
- `apps_builder_current.md`
  - Current Apps Builder runtime, preview, revision, and publish model.
- `artifact_execution_current.md`
  - Current artifact execution architecture and runtime surfaces.
- `coding_agent_runtime_current.md`
  - Current published-app coding-agent runtime and OpenCode-backed API surface.
- `platform_architect_worker_orchestration_current.md`
  - Current architect async worker orchestration model and binding-backed artifact flow.
- `platform_architect_artifact_delegation_current.md`
  - Current architect artifact delegation model and responsibilities.
- `artifact_coding_agent_direct_use_current.md`
  - Current direct artifact-usage model in coding-agent flows.
- `voice_runtime_current.md`
  - Current voice websocket/provider runtime shape and security reality.
- `prompt_library_shared_resource_design.md`
  - Shared-resource design for a platform-wide prompt library and cross-surface prompt references.
- `rag_agent_node_architecture_decision.md`
  - Decision record for keeping Agent and RAG node registries/contracts separate and avoiding premature shared-node abstraction.

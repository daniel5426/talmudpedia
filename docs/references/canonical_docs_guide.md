# Canonical Docs Guide

Last Updated: 2026-03-19

This guide lists the current canonical documentation entry points after the first documentation-system refactor.

## Start Here

- `AGENTS.md`
  - Repo operating rules for agents.
- `ARCHITECTURE.md`
  - Repo-level architecture entry point.
- `docs/README.md`
  - Repo-level docs hub and section purposes.
- `docs/references/legacy_docs_coverage_map.md`
  - Complete coverage map for the legacy `backend/documentations/` tree.

## Current Canonical Architecture Docs

- `code_architect/architecture_tree.md`
  - Fast-read backend architecture map for implementation work.
- `docs/design-docs/backend_architecture_current.md`
  - Current backend architecture overview.
- `docs/design-docs/agent_execution_current.md`
  - Current agent execution architecture.
- `docs/design-docs/platform_current_state.md`
  - Current platform-level domain overview.
- `docs/design-docs/platform_architecture_layers.md`
  - Conceptual architecture layers and boundaries.
- `docs/design-docs/auth_current.md`
  - Current auth, authorization, and workload-security overview.
- `docs/design-docs/apps_builder_current.md`
  - Current Apps Builder architecture, preview runtime, revision flow, and publish model.
- `docs/design-docs/apps_builder_live_workspace_hmr_architecture.md`
  - Focused design note for the unified live-workspace model, Vite HMR proxying, and the concrete preview bug chain that had to be fixed.
- `docs/design-docs/artifact_execution_current.md`
  - Current artifact execution architecture.
- `docs/design-docs/coding_agent_runtime_current.md`
  - Current published-app coding-agent runtime and API model.
- `docs/design-docs/platform_architect_worker_orchestration_current.md`
  - Current platform-architect async worker orchestration model and binding-backed artifact flow.
- `docs/design-docs/platform_architect_artifact_delegation_current.md`
  - Current platform-architect artifact delegation model.
- `docs/design-docs/artifact_coding_agent_direct_use_current.md`
  - Current direct artifact usage model in coding-agent flows.

## Current Canonical Product Specs

- `docs/product-specs/published_apps_spec.md`
  - Published-app product behavior and runtime surface.
- `docs/product-specs/embedded_agent_runtime_spec.md`
  - Agent-native external embed/plugin runtime contract.
- `docs/product-specs/settings_hub_spec.md`
  - Tenant settings hub behavior and APIs.
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
  - Published-app runtime SDK contract.
- `docs/product-specs/agent_graph_spec.md`
  - Current agent graph contract shared by builder and compiler.
- `docs/product-specs/artifacts_domain_spec.md`
  - Current artifact-domain behavior and lifecycle.
- `docs/product-specs/tools_domain_spec.md`
  - Current tools-domain behavior and guardrails.
- `docs/product-specs/admin_stats_spec.md`
  - Current admin stats contract.

## Current Canonical References

- `docs/references/classic_chat_template_reference.md`
  - Current dependency and component inventory for the `classic-chat` published-app starter template.
- `docs/references/embedded_agent_sdk_standalone_integration_guide.md`
  - Canonical customer integration guide for building a standalone app with `@agents24/embed-sdk`.
  - Use this alongside `packages/embed-sdk/README.md` for the server-only embed SDK contract and customer-backend architecture.
- `docs/references/embed_sdk_release_runbook.md`
  - Operational runbook for releasing `@agents24/embed-sdk`, including direct GitHub Actions publish, npm auth, provenance, and fallback manual publish steps.

## Focused Current Detail Docs Still Under `backend/documentations/`

- `backend/documentations/auth/10_auth_current_state_overview.md`
  - Detailed auth current-state reference.
- `backend/documentations/auth/20_auth_delegated_workload_tokens.md`
  - Detailed delegated-workload token contract.
- `backend/documentations/auth/30_auth_workload_delegation_design.md`
  - Detailed workload-delegation design note.
- `backend/documentations/auth/40_auth_published_apps_unified_gate_and_user_scope.md`
  - Detailed published-app auth behavior reference.
- `backend/documentations/architecture/001_agent_execution_modes.md`
  - Focused ADR that still supports the current execution model.
- `backend/documentations/platform_architect_spec.md`
  - Focused platform-architect contract/detail doc.
- `backend/documentations/platform_control_plane_sdk_spec_v1.md`
  - Focused platform control-plane SDK contract reference.
- `backend/documentations/sandbox_spec.md`
  - Focused sandbox/runtime reference.
- `backend/documentations/summary/chat_thread_token_spec.md`
  - Focused thread/token/quota behavior reference.
- `backend/documentations/web_crawler_crawl4ai_dev_setup.md`
  - Focused operational setup reference.

## Legacy Files That Now Act As Pointers

- `backend/ARCHITECTURE.md`
- `backend/documentations/agent_execution_overview.md`
- `backend/documentations/backend_state.md`
- `backend/documentations/platform_current_state.md`
- `backend/documentations/current_platform_status.md`
- `backend/documentations/overview_of_the_platform.md`
- `backend/documentations/platform_layered_architecture_abstract.md`
- `backend/documentations/Apps.md`
- `backend/documentations/settings_page_spec.md`
- `backend/documentations/runtime_sdk_v1_host_anywhere.md`
- `backend/documentations/graphspec_v1.md`
- `backend/documentations/artifacts_spec.md`
- `backend/documentations/artifacts_execution_infra_spec.md`
- `backend/documentations/artifact_execution_architecture_difysandbox_spec.md`
- `backend/documentations/tools_overview.md`
- `backend/documentations/mcp_tools_overview.md`
- `backend/documentations/stats.md`
- `backend/documentations/voice_mode_architecture.md`

## Rule Of Thumb

- If the question is “how is the system implemented now?”, start with the docs in `docs/design-docs/` plus `code_architect/architecture_tree.md`.
- If the question is “what did we previously write about this?”, inspect legacy docs in `backend/documentations/`.
- If the question is “have we covered this old doc yet?”, check `docs/references/legacy_docs_coverage_map.md`.
- If the question is “which old docs are still intentionally authoritative?”, use the focused-detail section above plus the `canonical_detail` entries in `docs/references/legacy_docs_coverage_map.md`.

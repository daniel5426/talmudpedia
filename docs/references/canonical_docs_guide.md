# Canonical Docs Guide

Last Updated: 2026-03-12

This guide lists the current canonical documentation entry points after the first documentation-system refactor.

## Start Here

- `AGENTS.md`
  - Repo operating rules for agents.
- `ARCHITECTURE.md`
  - Repo-level architecture entry point.
- `docs/README.md`
  - Repo-level docs hub and section purposes.

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
- `docs/design-docs/artifact_execution_current.md`
  - Current artifact execution architecture.
- `docs/design-docs/platform_architect_artifact_delegation_current.md`
  - Current platform-architect artifact lifecycle and artifact-coding delegation model.

## Current Canonical Product Specs

- `docs/product-specs/published_apps_spec.md`
  - Published-app product behavior and runtime surface.
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

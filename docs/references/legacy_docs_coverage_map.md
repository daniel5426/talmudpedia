# Legacy Docs Coverage Map

Last Updated: 2026-03-12

This document maps every meaningful documentation file under `backend/documentations/` into the new documentation system.

## Status Meanings

- `canonical_detail`
  - still useful as an active focused reference, even if the top-level canonical entry point now lives under `docs/`
- `legacy_pointer`
  - old location now redirects to newer canonical docs
- `historical_plan`
  - implementation plan/history, not current source of truth
- `historical_summary`
  - handoff or implementation summary, not current source of truth
- `generated_artifact`
  - generated file, not human-authored canonical documentation
- `legacy_reference_pending_promotion`
  - still useful, but not yet rewritten into a canonical `docs/` location

Noise files such as `.DS_Store` are not part of the documentation inventory.

## Legacy Tree Guide

- `backend/documentations/README.md`
  - `canonical_detail`
  - Entry point for interpreting the legacy tree after the refactor

## Root-Level Legacy Docs

- `backend/documentations/Apps.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/published_apps_spec.md`
- `backend/documentations/Templates.md`
  - `legacy_reference_pending_promotion`
  - Related current domains: published apps, runtime SDK, builder runtime
- `backend/documentations/agent_domain_architecture(1).md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `docs/design-docs/backend_architecture_current.md`, `docs/design-docs/agent_execution_current.md`
- `backend/documentations/agent_execution_overview.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/agent_execution_current.md`
- `backend/documentations/agent_management_state.md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `docs/design-docs/backend_architecture_current.md`, `docs/design-docs/agent_execution_current.md`
- `backend/documentations/agent_playground.md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `docs/design-docs/agent_execution_current.md`
- `backend/documentations/agent_streaming_response_ui.md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `docs/design-docs/agent_execution_current.md`
- `backend/documentations/apps_builder_e2b_runtime_migration_status.md`
  - `historical_summary`
  - Related current canonicals: `backend/documentations/sandbox_spec.md`, `backend/documentations/apps_builder_sprite_hard_cut_status.md`
- `backend/documentations/apps_builder_sprite_hard_cut_status.md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `backend/documentations/sandbox_spec.md`
- `backend/documentations/artifact_execution_architecture_difysandbox_spec.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/artifact_execution_current.md`
- `backend/documentations/artifacts_execution_infra_spec.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/artifact_execution_current.md`
- `backend/documentations/artifacts_spec.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/artifacts_domain_spec.md`
- `backend/documentations/backend_dev_rules.md`
  - `legacy_reference_pending_promotion`
  - Candidate destination: `docs/references/`
- `backend/documentations/backend_state.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/backend_architecture_current.md`
- `backend/documentations/current_platform_status.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/platform_current_state.md`
- `backend/documentations/graphspec_v1.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/agent_graph_spec.md`
- `backend/documentations/mcp_tools_overview.md`
  - `legacy_pointer`
  - Canonical: `docs/references/mcp_tools_reference.md`
- `backend/documentations/overview_of_the_platform.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/platform_current_state.md`
- `backend/documentations/pipeline_execution_transparency.md`
  - `legacy_reference_pending_promotion`
  - Related domain: RAG execution transparency
- `backend/documentations/pipeline_input_ui.md`
  - `legacy_reference_pending_promotion`
  - Related domain: RAG runtime forms and builder UX
- `backend/documentations/pipeline_pagination_technical_summary.md`
  - `legacy_reference_pending_promotion`
  - Related domain: pipeline UI/backend behavior
- `backend/documentations/pipeline_ui_and_execution_fixes.md`
  - `legacy_reference_pending_promotion`
  - Related domain: RAG builder runtime UX
- `backend/documentations/platform_architect_spec.md`
  - `canonical_detail`
  - Related current canonicals: `docs/design-docs/platform_architect_worker_orchestration_current.md`, `docs/design-docs/platform_architect_artifact_delegation_current.md`
- `backend/documentations/platform_control_plane_sdk_hard_cut_legacy_removal_plan.md`
  - `historical_plan`
  - Related current detail: `backend/documentations/platform_control_plane_sdk_spec_v1.md`
- `backend/documentations/platform_control_plane_sdk_spec_v1.md`
  - `canonical_detail`
  - Focused SDK contract reference
- `backend/documentations/platform_current_state.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/platform_current_state.md`
- `backend/documentations/platform_layered_architecture_abstract.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/platform_architecture_layers.md`
- `backend/documentations/rag_management_state.md`
  - `legacy_reference_pending_promotion`
  - Related current canonicals: `docs/design-docs/backend_architecture_current.md`
- `backend/documentations/react_artifacts_live_preview.md`
  - `legacy_reference_pending_promotion`
  - Related domain: frontend artifact preview
- `backend/documentations/runtime_sdk_v1_host_anywhere.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `backend/documentations/sandbox_spec.md`
  - `canonical_detail`
  - Focused sandbox/platform runtime reference
- `backend/documentations/sdk_specification.md`
  - `legacy_pointer`
  - Canonical detail refs: `backend/documentations/platform_control_plane_sdk_spec_v1.md`, `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `backend/documentations/settings_page_spec.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/settings_hub_spec.md`
- `backend/documentations/stats.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/admin_stats_spec.md`
- `backend/documentations/tools_overview.md`
  - `legacy_pointer`
  - Canonical: `docs/product-specs/tools_domain_spec.md`
- `backend/documentations/voice_mode_architecture.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/voice_runtime_current.md`
- `backend/documentations/web_crawler_crawl4ai_dev_setup.md`
  - `canonical_detail`
  - Focused operational setup reference

## Architecture ADR

- `backend/documentations/architecture/001_agent_execution_modes.md`
  - `canonical_detail`
  - Focused ADR supporting `docs/design-docs/agent_execution_current.md`

## Auth Folder

- `backend/documentations/auth/00_auth_docs_guide.md`
  - `canonical_detail`
  - Related canonicals: `docs/design-docs/auth_current.md`, `docs/references/auth_docs_guide.md`
- `backend/documentations/auth/10_auth_current_state_overview.md`
  - `canonical_detail`
- `backend/documentations/auth/20_auth_delegated_workload_tokens.md`
  - `canonical_detail`
- `backend/documentations/auth/30_auth_workload_delegation_design.md`
  - `canonical_detail`
- `backend/documentations/auth/40_auth_published_apps_unified_gate_and_user_scope.md`
  - `canonical_detail`
- `backend/documentations/auth/95_auth_security_unification_status_2026_03_05.md`
  - `historical_summary`

## Plans Folder

- `backend/documentations/Plans/README.md`
  - `canonical_detail`
  - Guide for legacy plan interpretation
- `backend/documentations/Plans/Agents_Tools_Production_Readiness_Refinement_Testing_Plan.md`
  - `historical_plan`
- `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/apps_builder_current.md`
- `backend/documentations/Plans/Base44_ConfigMigration_Plan.md`
  - `historical_plan`
- `backend/documentations/Plans/CodingAgent_PerRunSandboxIsolation_Implementation.md`
  - `historical_plan`

## Summary Folder

- `backend/documentations/summary/README.md`
  - `canonical_detail`
  - Guide for legacy summary interpretation
- `backend/documentations/summary/AppsBuilder_SandboxPublishRefactor_WYSIWYG.md`
  - `historical_summary`
- `backend/documentations/summary/CustomCodingAgent.md`
  - `legacy_pointer`
  - Canonical: `docs/design-docs/coding_agent_runtime_current.md`
- `backend/documentations/summary/OpenCodeProtocolInvestigation_2026-02-25.md`
  - `historical_summary`
- `backend/documentations/summary/agent_builder_runtime_adapter_summary.md`
  - `historical_summary`
- `backend/documentations/summary/agent_builder_tests_creation_notes.md`
  - `historical_summary`
- `backend/documentations/summary/agent_builder_tests_sdk_summary.md`
  - `historical_summary`
- `backend/documentations/summary/agent_builder_v2_frontend_refactor_handoff.md`
  - `historical_summary`
- `backend/documentations/summary/agent_sota_architecture_gap_overview.md`
  - `historical_summary`
- `backend/documentations/summary/agent_tool_agents_tests_creation_notes.md`
  - `historical_summary`
- `backend/documentations/summary/chat_thread_token_spec.md`
  - `canonical_detail`
  - Focused current-state reference for unified run/thread/quota behavior
- `backend/documentations/summary/langchain_tool_loop_implementation_summary.md`
  - `historical_summary`
- `backend/documentations/summary/multi_agent_orchestration_v2_phase1_phase2_handoff_prompt.md`
  - `historical_summary`
- `backend/documentations/summary/opencode_tools_protocol_probe_2026-02-25.json`
  - `generated_artifact`
- `backend/documentations/summary/opencode_tools_protocol_probe_legacy_2026-02-25.json`
  - `generated_artifact`
- `backend/documentations/summary/orchestration_kernel_phase1_phase2_implementation_status.md`
  - `historical_summary`
- `backend/documentations/summary/unified_run_native_threads_hard_cut_implementation_2026-03-02.md`
  - `historical_summary`

## Debug Folder

- `backend/documentations/Debug/coding_agent_run_stuck_infinite_queue_debug_summary_2026-02-22.md`
  - `historical_summary`

## Notes

- This map is the canonical answer to “have we covered every old doc yet?”
- “Covered” does not always mean “fully rewritten into `docs/`.” It means every legacy file now has an explicit role in the new system.
- The next promotion candidates are the files currently marked `legacy_reference_pending_promotion`.

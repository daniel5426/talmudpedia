# Documentation System

Last Updated: 2026-03-10

This directory is the repo-level documentation hub for Talmudpedia.

## Purpose
- Separate documentation by intent, not just by backend topic.
- Make it obvious which docs are canonical, active, historical, generated, or external.
- Reduce drift between root guidance, backend documentation, and architecture references.

## Sections
- `design-docs/`
  - Architecture and design decisions. These explain why the system is shaped the way it is.
- `exec-plans/active/`
  - Work that is currently planned or in flight.
- `exec-plans/completed/`
  - Finished plans kept for historical traceability.
- `generated/`
  - Machine-derived artifacts such as schema snapshots or generated inventories.
- `product-specs/`
  - Canonical product behavior and user-facing contracts.
- `references/`
  - Stable supporting material, external references, conventions, and agent-oriented lookup docs.

## Canonical Top-Level Docs
- Root `AGENTS.md`
  - Operating instructions for agents working in this repository.
- `code_architect/architecture_tree.md`
  - Curated backend architecture map used for fast architectural orientation.
- `backend/ARCHITECTURE.md`
  - Legacy backend overview. This should be refreshed or replaced because it appears older than the current backend shape.

## Documentation Rules
- Every edited Markdown file must include a `Last Updated` date.
- Prefer one canonical doc per concern. Avoid writing a spec, plan, and summary that all restate the same facts.
- Put temporary execution details in `exec-plans/`, not in long-lived architecture docs.
- Put generated material in `generated/`, not beside hand-written specs.
- Add section-level index files when a folder holds more than a few documents.

## Current State
Most existing long-form documentation still lives in `backend/documentations/`. That folder remains the source location for existing docs until they are gradually migrated or replaced.

## Canonical Entry Points Right Now
- `docs/design-docs/backend_architecture_current.md`
- `docs/design-docs/agent_execution_current.md`
- `docs/design-docs/platform_current_state.md`
- `docs/design-docs/platform_architecture_layers.md`
- `docs/design-docs/auth_current.md`
- `docs/design-docs/artifact_execution_current.md`
- `docs/design-docs/voice_runtime_current.md`
- `docs/product-specs/published_apps_spec.md`
- `docs/product-specs/settings_hub_spec.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `docs/product-specs/agent_graph_spec.md`
- `docs/product-specs/artifacts_domain_spec.md`
- `docs/product-specs/tools_domain_spec.md`
- `docs/product-specs/admin_stats_spec.md`
- `docs/references/canonical_docs_guide.md`

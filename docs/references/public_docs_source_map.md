# Public Docs Source Map

Last Updated: 2026-04-10

This file maps the public docs pages in `docs-site/` to the internal canonical docs that currently back them.

## Page Metadata Contract

Every public `page.mdx` file must include:

- `title`
- `description`
- `status`
- `audience`
- `lastUpdated`
- `lastValidated`
- `canonicalSources`
- `verificationStatus`

Allowed values:

- `status`: `draft | published`
- `verificationStatus`: `not-run | partial | validated`

## Source Map

| Public page | Internal canonical sources | Owner/update note |
| --- | --- | --- |
| `docs-site/app/page.mdx` | `docs/design-docs/platform_current_state.md`, `docs/design-docs/platform_architecture_layers.md`, `docs/product-specs/published_apps_spec.md` | Update when the public platform shape or docs IA changes. |
| `docs-site/app/quickstart/page.mdx` | `docs/design-docs/platform_current_state.md`, `docs/product-specs/agent_graph_spec.md`, `docs/product-specs/rag_pipeline_spec.md`, `docs/product-specs/tools_domain_spec.md` | Update with any external behavior change in the first-run workflow. |
| `docs-site/app/concepts/agents/page.mdx` | `docs/design-docs/agent_execution_current.md`, `docs/product-specs/agent_graph_spec.md` | Update when the persisted graph or run mental model changes. |
| `docs-site/app/concepts/knowledge-and-retrieval/page.mdx` | `docs/design-docs/platform_current_state.md`, `docs/product-specs/rag_pipeline_spec.md` | Update when knowledge-store or retrieval behavior changes. |
| `docs-site/app/concepts/tools/page.mdx` | `docs/product-specs/tools_domain_spec.md`, `docs/product-specs/artifacts_domain_spec.md` | Update when public tool behavior, ownership, or runtime rules change. |
| `docs-site/app/guides/page.mdx` | `docs/design-docs/agent_execution_current.md` | Update when the public debugging guidance entry point changes. |
| `docs-site/app/guides/runs-and-debugging/page.mdx` | `docs/design-docs/agent_execution_current.md`, `docs/product-specs/admin_stats_spec.md`, `backend/documentations/summary/chat_thread_token_spec.md` | Update when run inspection surfaces or trace visibility change. |
| `docs-site/app/tutorials/page.mdx` | `docs/design-docs/platform_current_state.md` | Update when the tutorial program framing changes. |
| `docs-site/app/tutorials/first-agent-with-retrieval-and-tools/page.mdx` | `docs/design-docs/platform_current_state.md`, `docs/product-specs/agent_graph_spec.md`, `docs/product-specs/rag_pipeline_spec.md`, `docs/product-specs/tools_domain_spec.md` | Update together with the quickstart whenever the anchor journey changes. |
| `docs-site/app/sdk-api/page.mdx` | `docs/product-specs/embedded_agent_runtime_spec.md`, `docs/product-specs/runtime_sdk_host_anywhere_spec.md`, `docs/product-specs/published_apps_spec.md` | Update when public runtime surfaces expand or stabilize. |
| `docs-site/app/deployment/page.mdx` | `docs/references/deployment_spec.md`, `docs/references/railway_launch_runbook.md` | Expand once public deployment guidance is validated. |
| `docs-site/app/security/page.mdx` | `docs/design-docs/auth_current.md`, `docs/product-specs/embedded_agent_runtime_spec.md` | Expand once public security guidance is ready. |
| `docs-site/app/changelog/page.mdx` | `docs/exec-plans/active/public_docs_gap_log.md`, `docs/references/public_docs_source_map.md` | Update for visible public docs changes only. |

## Update Rule

When a canonical internal doc changes in a way that affects public behavior:

1. update the mapped public page in `docs-site/`
2. update that page's `lastValidated` date if the flow was rechecked
3. add a gap-log entry if validation exposes product friction or unclear contracts

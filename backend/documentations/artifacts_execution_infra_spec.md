Last Updated: 2026-03-11

# Artifacts Execution Infra Spec

This file is now a legacy location.

For the current canonical artifact execution architecture, read:
- `docs/design-docs/artifact_execution_current.md`
- `docs/product-specs/artifacts_domain_spec.md`

Do not add new canonical artifact-execution detail here.

Current artifact-runtime env surface is centered on:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `ARTIFACT_CF_DISPATCH_BASE_URL`
- `ARTIFACT_CF_DISPATCH_TOKEN`
- `ARTIFACT_CF_RUNTIME_MODE`
- `ARTIFACT_CF_DISPATCH_TIMEOUT_SECONDS`

Fallback bundle envs:
- `APPS_BUNDLE_BUCKET`
- `APPS_BUNDLE_REGION`
- `APPS_BUNDLE_ENDPOINT`
- `APPS_BUNDLE_ACCESS_KEY`
- `APPS_BUNDLE_SECRET_KEY`

## Current Limitations

- no production-grade fairness scheduler yet beyond queue classes plus tenant concurrency caps
- tenant artifacts must fit the Cloudflare Workers Python/runtime constraints
- builtin repo artifacts still remain on their separate backend-local execution path

## Target Direction

The current direction now is:
- one shared artifact execution service
- Cloudflare Workers-compatible runtime boundaries for tenant artifact execution
- published revision pinning for production execution
- thin agent/rag/tool integrations over the same execution substrate
- stronger queueing, fairness, outbound policy, and secret-broker hardening on top of this stack

Current implementation note:
- `workers_for_platforms` is the intended production mode
- `standard_worker_test` is the temporary free-plan validation mode currently used when dispatch namespaces are not available

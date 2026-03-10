Last Updated: 2026-03-10

# Artifacts Execution Infra Spec

This file is now a legacy location.

For the current canonical artifact execution architecture, read:
- `docs/design-docs/artifact_execution_current.md`
- `docs/product-specs/artifacts_domain_spec.md`

Do not add new canonical artifact-execution detail here.
- `ARTIFACT_WORKER_DEPENDENCY_CACHE_DIR`
- `ARTIFACT_SANDBOX_PROVIDER`
- `ARTIFACT_SANDBOX_TIMEOUT_SECONDS`
- `ARTIFACT_SANDBOX_ALLOW_NETWORK`
- `DIFYSANDBOX_API_BASE_URL`
- `DIFYSANDBOX_API_KEY`
- `LOCAL_DIFYSANDBOX_AUTO_BOOTSTRAP`
- `ARTIFACT_WORKER_BUNDLE_CACHE_DIR`
- `ARTIFACT_BUNDLE_BUCKET`
- `ARTIFACT_BUNDLE_REGION`
- `ARTIFACT_BUNDLE_ENDPOINT`
- `ARTIFACT_BUNDLE_ACCESS_KEY`
- `ARTIFACT_BUNDLE_SECRET_KEY`

Fallback bundle envs:
- `APPS_BUNDLE_BUCKET`
- `APPS_BUNDLE_REGION`
- `APPS_BUNDLE_ENDPOINT`
- `APPS_BUNDLE_ACCESS_KEY`
- `APPS_BUNDLE_SECRET_KEY`

## Current Limitations

- no true external DifySandbox container pool yet
- no production-grade per-tenant scheduler yet
- no artifact production traffic on `artifact_prod_interactive` or `artifact_prod_background` yet
- no fully packaged dependency-vendoring workflow yet beyond the current simple bundle format
- current local bootstrap is aimed at developer convenience, not final deployment topology

## Target Direction

The target direction remains:
- one shared artifact execution service
- DifySandbox as the isolation boundary for tenant artifact code
- published revision pinning for production execution
- thin agent/rag/tool integrations over the same execution substrate
- stronger queueing, fairness, and worker isolation once live domain traffic is moved onto this stack

Last Updated: 2026-03-25

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
- `ARTIFACT_CF_DISPATCH_NAMESPACE_STAGING`
- `ARTIFACT_CF_DISPATCH_NAMESPACE_PRODUCTION`
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
- builtin/system artifacts now converge on the same canonical revision/runtime substrate; do not treat repo-local execution as the control-plane source of truth

## Target Direction

The current direction now is:
- one shared artifact execution service
- Cloudflare Workers-compatible runtime boundaries for tenant artifact execution
- published revision pinning for production execution
- thin agent/rag/tool integrations over the same execution substrate
- stronger queueing, fairness, and runtime validation on top of this stack

Current implementation note:
- the canonical runtime is now Cloudflare Workers for Platforms with dispatch namespaces, transient `@{credential-id}` string-literal rewriting, and `uv run pywrangler deploy` for Python dependency packaging
- older references to outbound broker injection, `artifact_runtime_sdk.resolve_secret(...)`, or direct multipart Python deploy uploads are historical and should not be treated as current architecture
- successful `pywrangler` packaging does not imply package-runtime compatibility; heavyweight Python SDK imports can still fail inside Cloudflare Python Workers

# Control Plane SDK Tests

Last Updated: 2026-03-16

Scope:
- Python `talmudpedia_control_sdk` client transport contract.
- Method serialization for control-plane modules (`catalog`, `agents`, `tools`, `artifacts`, `rag`, `models`, `credentials`, `knowledge_stores`, `auth`, `orchestration`, `workload_security`, `embedded_agents`).
- Envelope normalization and structured error mapping.
- Legacy route guardrails for control-plane SDK/tool code paths.

Test files present:
- test_client_and_modules.py
- test_additional_modules.py
- test_http_integration.py
- test_no_legacy_api_agents_refs.py

Key scenarios covered:
- Mutation requests include contract/idempotency/auth/tenant headers.
- Dynamic tenant resolution via `tenant_resolver` is validated per request.
- Environment bootstrap via `ControlPlaneClient.from_env(...)` is validated.
- Non-envelope API responses are wrapped into SDK response envelopes.
- Structured backend errors are converted into `ControlPlaneSDKError`.
- Route + parameter serialization for representative methods across all implemented modules.
- Canonical artifact SDK serialization for `artifacts.create`, `artifacts.convert_kind`, and `artifacts.publish`.
- Agents node-intelligence SDK route serialization (`/agents/nodes/catalog`, `/agents/nodes/schema`, `/agents/{id}/validate` via `validate_nodes`).
- RAG file upload request serialization (`/admin/pipelines/pipeline-inputs/upload`).
- Orchestration/internal auth/workload security endpoint route coverage.
- Embedded-agent SDK route serialization for stream and thread-history helpers.
- Env-gated HTTP smoke coverage for SDK read surfaces (`catalog`, `agents`, `tools`, `models`, `credentials`, `auth`) and tenant-slug surfaces (`artifacts`, `rag`, `knowledge_stores`).
- Guardrail test blocks `/api/agents` references in control-plane SDK/tool Python code.

Last run command: `cd backend && PYTHONPATH=. pytest -q tests/tenant_api_keys/test_api_keys_api.py tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py tests/control_plane_sdk tests/published_apps_external_runtime/test_external_runtime_api.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/security_scope_registry/test_scope_registry.py`
Last run date/time: 2026-03-16 19:38 EET
Last run result: pass (`45 passed, 2 skipped`)

Known gaps / follow-ups:
- Add real HTTP integration tests (env-gated) against each implemented module route set.
- Add cross-surface parity tests comparing SDK calls and platform tool wrappers.
- Wire the guardrail test into always-on CI workflow execution if CI selection rules are narrowed.

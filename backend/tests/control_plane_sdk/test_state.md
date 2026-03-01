# Control Plane SDK Tests

Last Updated: 2026-03-01

Scope:
- Python `talmudpedia_control_sdk` client transport contract.
- Method serialization for control-plane modules (`catalog`, `agents`, `tools`, `artifacts`, `rag`, `models`, `credentials`, `knowledge_stores`, `auth`, `orchestration`, `workload_security`).
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
- RAG file upload request serialization (`/admin/pipelines/pipeline-inputs/upload`).
- Orchestration/internal auth/workload security endpoint route coverage.
- Env-gated HTTP smoke coverage for SDK read surfaces (`catalog`, `agents`, `tools`, `models`, `credentials`, `auth`) and tenant-slug surfaces (`artifacts`, `rag`, `knowledge_stores`).
- Guardrail test blocks `/api/agents` references in control-plane SDK/tool Python code.

Last run command: `pytest -q backend/tests/control_plane_sdk/test_no_legacy_api_agents_refs.py`
Last run date/time: 2026-03-01 18:28:32 EET
Last run result: pass (1 passed)

Known gaps / follow-ups:
- Add real HTTP integration tests (env-gated) against each implemented module route set.
- Add cross-surface parity tests comparing SDK calls and platform tool wrappers.
- Wire the guardrail test into always-on CI workflow execution if CI selection rules are narrowed.

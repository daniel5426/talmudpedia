# Control Plane SDK Tests

Last Updated: 2026-03-01

Scope:
- Python `talmudpedia_control_sdk` client transport contract.
- Method serialization for control-plane modules (`catalog`, `agents`, `tools`, `artifacts`, `rag`, `models`, `credentials`, `knowledge_stores`, `auth`, `orchestration`, `workload_security`).
- Envelope normalization and structured error mapping.

Test files present:
- test_client_and_modules.py
- test_additional_modules.py

Key scenarios covered:
- Mutation requests include contract/idempotency/auth/tenant headers.
- Non-envelope API responses are wrapped into SDK response envelopes.
- Structured backend errors are converted into `ControlPlaneSDKError`.
- Route + parameter serialization for representative methods across all implemented modules.
- RAG file upload request serialization (`/admin/pipelines/pipeline-inputs/upload`).
- Orchestration/internal auth/workload security endpoint route coverage.

Last run command: `pytest -q backend/tests/control_plane_sdk`
Last run date/time: 2026-03-01 17:54:45 EET
Last run result: pass (13 passed)

Known gaps / follow-ups:
- Add real HTTP integration tests (env-gated) against each implemented module route set.
- Add cross-surface parity tests comparing SDK calls and platform tool wrappers.

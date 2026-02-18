# Architecture Tree (Curated)

Last Updated: 2026-02-18

This file is a backend-only architecture map optimized for agent context efficiency.

Rules applied in this map:
- Core runtime and architecture-critical code is listed at file level.
- Supporting systems are listed at directory level only.
- Frontend paths are intentionally excluded.

```text
backend/
backend/main.py
backend/run_celery.py
backend/run_voice_agent.py

backend/app/

backend/app/api/
backend/app/api/dependencies.py
backend/app/api/routers/
backend/app/api/schemas/

backend/app/core/
backend/app/core/security.py
backend/app/core/rbac.py
backend/app/core/audit.py
backend/app/core/internal_token.py
backend/app/core/jwt_keys.py
backend/app/core/workload_jwt.py

backend/app/agent/
backend/app/agent/config.py
backend/app/agent/models.py
backend/app/agent/registry.py
backend/app/agent/factory.py
backend/app/agent/resolution.py
backend/app/agent/cel_engine.py
backend/app/agent/agent_artifact_spec.py

backend/app/agent/core/
backend/app/agent/core/base.py
backend/app/agent/core/interfaces.py
backend/app/agent/core/llm_adapter.py
backend/app/agent/core/state.py

backend/app/agent/graph/
backend/app/agent/graph/compiler.py
backend/app/agent/graph/runtime.py
backend/app/agent/graph/executable.py
backend/app/agent/graph/ir.py
backend/app/agent/graph/schema.py
backend/app/agent/graph/node_factory.py

backend/app/agent/execution/
backend/app/agent/execution/service.py
backend/app/agent/execution/durable_checkpointer.py
backend/app/agent/execution/adapter.py
backend/app/agent/execution/field_resolver.py
backend/app/agent/execution/emitter.py
backend/app/agent/execution/types.py

backend/app/agent/executors/
backend/app/agent/runtime/
backend/app/agent/components/
backend/app/agent/workflows/

backend/app/rag/
backend/app/rag/factory.py

backend/app/rag/pipeline/
backend/app/rag/pipeline/compiler.py
backend/app/rag/pipeline/executor.py
backend/app/rag/pipeline/operator_executor.py
backend/app/rag/pipeline/registry.py
backend/app/rag/pipeline/input_storage.py

backend/app/rag/interfaces/
backend/app/rag/providers/
backend/app/rag/adapters/

backend/app/db/
backend/app/db/connection.py
backend/app/db/models/

backend/app/db/postgres/
backend/app/db/postgres/engine.py
backend/app/db/postgres/session.py
backend/app/db/postgres/models/
backend/app/db/postgres/seeds/

backend/app/services/
backend/app/services/agent_service.py
backend/app/services/retrieval_service.py
backend/app/services/rag_admin_service.py
backend/app/services/model_resolver.py
backend/app/services/credentials_service.py
backend/app/services/tool_function_registry.py
backend/app/services/artifact_registry.py
backend/app/services/builtin_tools.py
backend/app/services/delegation_service.py
backend/app/services/workload_identity_service.py
backend/app/services/token_broker_service.py
backend/app/services/orchestration_kernel_service.py
backend/app/services/orchestration_policy_service.py
backend/app/services/orchestration_lineage_service.py
backend/app/services/mcp_client.py
backend/app/services/web_search.py
backend/app/services/published_app_auth_service.py
backend/app/services/published_app_bundle_storage.py
backend/app/services/published_app_draft_dev_runtime.py
backend/app/services/published_app_draft_dev_local_runtime.py
backend/app/services/published_app_draft_dev_runtime_client.py
backend/app/services/published_app_draft_dev_patching.py
backend/app/services/published_app_coding_agent_tools.py
backend/app/services/published_app_coding_agent_profile.py
backend/app/services/published_app_coding_agent_runtime.py
backend/app/services/published_app_coding_agent_engines/base.py
backend/app/services/published_app_coding_agent_engines/native_engine.py
backend/app/services/published_app_coding_agent_engines/opencode_engine.py
backend/app/services/opencode_server_client.py
backend/app/services/published_app_templates.py
backend/app/services/published_app_auth_templates.py
backend/app/services/apps_builder_dependency_policy.py
backend/app/services/library/
backend/app/services/stt/
backend/app/services/text/
backend/app/services/voice/

backend/app/workers/
backend/app/workers/celery_app.py
backend/app/workers/tasks.py
backend/app/workers/job_manager.py
backend/app/workers/livekit_worker.py

backend/app/templates/

backend/alembic/
backend/artifacts/
backend/ingestion/
backend/sdk/
backend/library_chunks/
backend/scripts/
backend/tests/
backend/tests_legacy/
backend/documentations/
```

Excluded by design:
- Frontend trees (for this file).
- Dotfiles and secrets (`.env`, credential JSON files).
- Runtime/generated noise (`__pycache__/`, `.pytest_cache/`, logs, temporary outputs).
- Full file-level inventories for `scripts/`, `tests/`, `documentations/`, and migration files.

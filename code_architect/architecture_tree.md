# Architecture Tree (Curated)

Last Updated: 2026-03-14

This file is a backend-only architecture map optimized for agent context efficiency.

Rules applied in this map:
- Core runtime and architecture-critical code is listed at file level.
- Supporting systems are listed at directory level only.
- Frontend paths are intentionally excluded.

```text
backend/
backend/main.py
backend/run_celery.py

backend/app/

backend/app/api/
backend/app/api/dependencies.py
backend/app/api/routers/
backend/app/api/routers/sandbox_controller_dev_shim.py
backend/app/api/routers/published_apps_builder_preview_proxy.py
backend/app/api/routers/published_apps_admin_routes_coding_agent_v2.py
backend/app/api/routers/published_apps_host_runtime.py
backend/app/api/routers/agent_graph_mutations.py
backend/app/api/routers/rag_graph_mutations.py
backend/app/api/routers/rag_operator_contracts.py
backend/app/api/routers/artifacts.py
backend/app/api/routers/artifact_runs.py
backend/app/api/routers/artifact_coding_agent.py
backend/app/api/schemas/

backend/app/core/
backend/app/core/security.py
backend/app/core/rbac.py
backend/app/core/scope_registry.py
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
backend/app/agent/execution/trace_recorder.py
backend/app/agent/execution/stream_contract_v2.py
backend/app/agent/execution/tool_event_metadata.py
backend/app/agent/execution/tool_input_contracts.py
backend/app/agent/execution/types.py

backend/app/agent/executors/
backend/app/agent/runtime/
backend/app/agent/components/
backend/app/agent/workflows/

backend/app/rag/
backend/app/rag/factory.py

backend/app/rag/pipeline/
backend/app/rag/pipeline/compiler.py
backend/app/rag/pipeline/custom_operator_sync.py
backend/app/rag/pipeline/executor.py
backend/app/rag/pipeline/operator_executor.py
backend/app/rag/pipeline/registry.py
backend/app/rag/pipeline/input_storage.py

backend/app/rag/interfaces/
backend/app/rag/interfaces/web_crawler.py
backend/app/rag/providers/
backend/app/rag/providers/crawler/
backend/app/rag/providers/crawler/crawl4ai.py
backend/app/rag/adapters/

backend/app/db/
backend/app/db/connection.py
backend/app/db/models/

backend/app/db/postgres/
backend/app/db/postgres/engine.py
backend/app/db/postgres/session.py
backend/app/db/postgres/models/
backend/app/db/postgres/models/artifact_runtime.py
backend/app/db/postgres/models/agent_threads.py
backend/app/db/postgres/models/usage_quota.py
backend/app/db/postgres/seeds/

backend/app/services/
backend/app/services/agent_service.py
backend/app/services/security_bootstrap_service.py
backend/app/services/retrieval_service.py
backend/app/services/rag_admin_service.py
backend/app/services/model_resolver.py
backend/app/services/model_temperature_policy.py
backend/app/services/credentials_service.py
backend/app/services/integration_provider_catalog.py
backend/app/services/registry_seeding.py
backend/app/services/artifact_coding_chat_history_service.py
backend/app/services/artifact_coding_shared_draft_service.py
backend/app/services/artifact_coding_agent_tools.py
backend/app/services/artifact_coding_agent_profile.py
backend/app/services/artifact_coding_runtime_service.py
backend/app/services/platform_architect_contracts.py
backend/app/services/platform_architect_worker_bindings.py
backend/app/services/platform_architect_worker_runtime_service.py
backend/app/services/platform_architect_worker_tools.py
backend/app/services/platform_sdk_local_tools.py
backend/app/services/platform_architect_guardrails.py
backend/app/services/graph_mutation_service.py
backend/app/services/agent_graph_mutation_service.py
backend/app/services/rag_graph_mutation_service.py
backend/app/services/tool_function_registry.py
backend/app/services/artifact_registry.py
backend/app/services/artifact_runtime/
backend/app/services/artifact_runtime/registry_service.py
backend/app/services/artifact_runtime/revision_service.py
backend/app/services/artifact_runtime/bundle_builder.py
backend/app/services/artifact_runtime/dependency_packager.py
backend/app/services/artifact_runtime/bundle_storage.py
backend/app/services/artifact_runtime/execution_service.py
backend/app/services/artifact_runtime/run_service.py
backend/app/services/artifact_runtime/source_utils.py
backend/app/services/artifact_runtime/workers_validation.py
backend/app/services/artifact_runtime/cloudflare_package_builder.py
backend/app/services/artifact_runtime/cloudflare_client.py
backend/app/services/artifact_runtime/cloudflare_dispatch_client.py
backend/app/services/artifact_runtime/deployment_service.py
backend/app/services/artifact_runtime/policy_service.py
backend/app/services/artifact_runtime/handler_runner.py
backend/app/services/builtin_tools.py
backend/app/services/delegation_service.py
backend/app/services/workload_provisioning_service.py
backend/app/services/workload_identity_service.py
backend/app/services/token_broker_service.py
backend/app/services/orchestration_kernel_service.py
backend/app/services/orchestration_policy_service.py
backend/app/services/orchestration_lineage_service.py
backend/app/services/mcp_client.py
backend/app/services/web_search.py
backend/app/services/apps_builder_trace.py
backend/app/services/published_app_builder_snapshot_filter.py
backend/app/services/published_app_auth_service.py
backend/app/services/published_app_auth_shell_renderer.py
backend/app/services/published_app_bundle_storage.py
backend/app/services/published_app_sandbox_backend.py
backend/app/services/published_app_sandbox_backend_factory.py
backend/app/services/published_app_sandbox_backend_local.py
backend/app/services/published_app_sandbox_backend_controller.py
backend/app/services/published_app_sandbox_backend_sprite.py
backend/app/services/published_app_sprite_proxy_tunnel.py
backend/app/services/published_app_sandbox_backend_e2b_workspace.py
backend/app/services/published_app_sandbox_backend_e2b_runtime.py
backend/app/services/published_app_sandbox_backend_e2b.py
backend/app/services/published_app_draft_dev_runtime.py
backend/app/services/published_app_draft_dev_local_runtime.py
backend/app/services/published_app_draft_dev_runtime_client.py
backend/app/services/published_app_draft_dev_patching.py
backend/app/services/published_app_preview_builds.py
backend/app/services/published_app_preview_runtime_scripts.py
backend/app/services/published_app_coding_chat_history_service.py
backend/app/services/published_app_coding_agent_tools.py
backend/app/services/published_app_agent_integration_contract.py
backend/app/services/published_app_coding_agent_profile.py
backend/app/services/published_app_coding_agent_runtime.py
backend/app/services/published_app_coding_agent_runtime_sandbox.py
backend/app/services/published_app_coding_agent_runtime_checkpoints.py
backend/app/services/published_app_coding_agent_runtime_streaming.py
backend/app/services/published_app_coding_run_monitor.py
backend/app/services/published_app_coding_run_monitor_config.py
backend/app/services/published_app_coding_pipeline_trace.py
backend/app/services/published_app_revision_store.py
backend/app/services/published_app_revision_build_dispatch.py
backend/app/services/published_app_publish_runtime.py
backend/app/services/published_app_publish_autofix.py
backend/app/services/usage_quota_service.py
backend/app/services/thread_service.py
backend/app/services/published_app_coding_agent_engines/base.py
backend/app/services/published_app_coding_agent_engines/opencode_engine.py
backend/app/services/published_app_coding_agent_engines/prompt_history.py
backend/app/services/library/
backend/app/services/stt/
backend/app/services/text/
backend/app/services/voice/

backend/app/middleware/
backend/app/middleware/published_apps_cors.py
backend/app/middleware/published_apps_host_runtime.py

backend/app/workers/
backend/app/workers/celery_app.py
backend/app/workers/tasks.py
backend/app/workers/artifact_tasks.py
backend/app/workers/job_manager.py
backend/app/workers/livekit_worker.py

backend/app/templates/

backend/alembic/
backend/artifacts/
backend/artifacts/builtin/
backend/artifacts/builtin/platform_sdk/
backend/artifacts/builtin/platform_sdk/handler.py
backend/artifacts/builtin/platform_sdk/actions/
backend/artifacts/builtin/platform_sdk/actions/catalog.py
backend/artifacts/builtin/platform_sdk/actions/agents.py

runtime/
runtime/cloudflare-artifacts/
runtime/cloudflare-artifacts/dispatch-worker/
runtime/cloudflare-artifacts/outbound-worker/
backend/artifacts/builtin/platform_sdk/actions/artifacts.py
backend/artifacts/builtin/platform_sdk/actions/tools.py
backend/artifacts/builtin/platform_sdk/actions/orchestration.py
backend/artifacts/builtin/platform_sdk/actions/rag.py
backend/artifacts/builtin/platform_sdk/actions/models.py
backend/artifacts/builtin/platform_sdk/actions/credentials.py
backend/artifacts/builtin/platform_sdk/actions/knowledge_stores.py
backend/artifacts/builtin/platform_sdk/actions/auth.py
backend/artifacts/builtin/platform_sdk/actions/workload_security.py
backend/artifacts/builtin/platform_sdk/actions/shared.py
backend/ingestion/
backend/sdk/
backend/talmudpedia_control_sdk/
backend/talmudpedia_control_sdk/client.py
backend/talmudpedia_control_sdk/catalog.py
backend/talmudpedia_control_sdk/agents.py
backend/talmudpedia_control_sdk/tools.py
backend/talmudpedia_control_sdk/artifacts.py
backend/talmudpedia_control_sdk/rag.py
backend/talmudpedia_control_sdk/models.py
backend/talmudpedia_control_sdk/credentials.py
backend/talmudpedia_control_sdk/knowledge_stores.py
backend/talmudpedia_control_sdk/workload_security.py
backend/talmudpedia_control_sdk/auth.py
backend/talmudpedia_control_sdk/orchestration.py
backend/talmudpedia_control_sdk/errors.py
backend/talmudpedia_control_sdk/types.py
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

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.agent.execution.run_task_registry import is_run_cancel_requested
from app.agent.registry import AgentExecutorRegistry, AgentOperatorRegistry
from app.agent.graph.contracts import (
    extract_runtime_node_output,
    get_node_output_contract,
    resolve_node_display_name,
)
from app.agent.graph.ir import GraphIRNode
from app.db.postgres.models.agents import AgentRun, RunStatus

logger = logging.getLogger(__name__)


def build_node_fn(node: GraphIRNode, tenant_id: Optional[UUID], db: Any):
    executor_cls = AgentExecutorRegistry.get_executor_cls(node.type)
    if not executor_cls:
        logger.error(f"No executor registered for node type: {node.type}")

        async def error_node(state: Any):
            return state

        return error_node

    executor = executor_cls(tenant_id, db)
    operator_spec = AgentOperatorRegistry.get(node.type)
    node_display_name = resolve_node_display_name(node, operator_spec=operator_spec, node_type=node.type)

    async def node_fn(state: Any, config: Any = None):
        configurable = config.get("configurable", {}) if config else {}
        emitter = configurable.get("emitter")
        state_context = {}
        if isinstance(state, dict):
            raw_ctx = state.get("context")
            if isinstance(raw_ctx, dict):
                state_context = raw_ctx
            nested_state = state.get("state")
            if isinstance(nested_state, dict):
                nested_ctx = nested_state.get("context")
                if isinstance(nested_ctx, dict):
                    state_context = {**nested_ctx, **state_context}

        context = {
            "langgraph_config": config,
            "emitter": emitter,
            "node_id": node.id,
            "node_type": node.type,
            "node_name": node_display_name,
            "mode": configurable.get("mode") or state_context.get("mode"),
            "run_id": configurable.get("run_id") or configurable.get("thread_id") or state_context.get("run_id"),
            "root_run_id": configurable.get("root_run_id") or state_context.get("root_run_id"),
            "parent_run_id": configurable.get("parent_run_id") or state_context.get("parent_run_id"),
            "parent_node_id": configurable.get("parent_node_id") or state_context.get("parent_node_id"),
            "depth": configurable.get("depth", state_context.get("depth")),
            "spawn_key": configurable.get("spawn_key") or state_context.get("spawn_key"),
            "orchestration_group_id": configurable.get("orchestration_group_id") or state_context.get("orchestration_group_id"),
            "initiator_user_id": configurable.get("initiator_user_id") or state_context.get("initiator_user_id"),
            "tenant_id": configurable.get("tenant_id") or state_context.get("tenant_id"),
            "user_id": configurable.get("user_id") or state_context.get("user_id"),
            "agent_id": configurable.get("agent_id") or state_context.get("agent_id"),
            "agent_slug": configurable.get("agent_slug") or state_context.get("agent_slug"),
            "architect_mode": configurable.get("architect_mode") or state_context.get("architect_mode"),
            "architect_effective_scopes": configurable.get("architect_effective_scopes") or state_context.get("architect_effective_scopes"),
            "token": configurable.get("auth_token") or state_context.get("token"),
            "state_context": state_context,
        }

        current_run_id = context.get("run_id")
        if is_run_cancel_requested(
            run_id=current_run_id,
            root_run_id=context.get("root_run_id"),
            parent_run_id=context.get("parent_run_id"),
        ):
            return {}
        if db is not None and current_run_id:
            try:
                current_status = (
                    await db.execute(
                        select(AgentRun.status).where(AgentRun.id == UUID(str(current_run_id)))
                    )
                ).scalar_one_or_none()
            except Exception:
                current_status = None
            current_status = str(getattr(current_status, "value", current_status) or "").strip().lower()
            if current_status == RunStatus.cancelled.value:
                return {}

        if not await executor.can_execute(state, node.config, context):
            return {}

        node_config = dict(node.config or {})
        if node.input_mappings:
            node_config["input_mappings"] = node.input_mappings

        try:
            state_update = await executor.execute(state, node_config, context)

            if state_update and isinstance(state_update, dict):
                node_outputs = state.get("node_outputs", {})
                if not isinstance(node_outputs, dict):
                    node_outputs = {}
                legacy_node_outputs = state.get("_node_outputs", {})
                if not isinstance(legacy_node_outputs, dict):
                    legacy_node_outputs = {}
                published_output = extract_runtime_node_output(
                    node_type=node.type,
                    config=node_config,
                    operator_spec=AgentOperatorRegistry.get(node.type),
                    state_update=state_update,
                    previous_state=state,
                )
                if published_output:
                    node_outputs[node.id] = published_output
                    legacy_node_outputs[node.id] = published_output
                    state_update["node_outputs"] = node_outputs
                    state_update["_node_outputs"] = legacy_node_outputs
                    if emitter:
                        declared_contract = get_node_output_contract(
                            node_id=node.id,
                            node_type=node.type,
                            node_label=node_display_name,
                            config=node_config,
                            operator_spec=operator_spec,
                        )
                        emitter.emit_internal_event(
                            "workflow.node_output_published",
                            {
                                "node_id": node.id,
                                "node_name": node_display_name,
                                "node_type": node.type,
                                "declared_output_keys": [
                                    str(item.get("key") or "").strip()
                                    for item in (declared_contract.get("fields") or [])
                                    if isinstance(item, dict) and str(item.get("key") or "").strip()
                                ],
                                "published_output_keys": sorted(published_output.keys()),
                                "published_output": published_output,
                            },
                            node_id=node.id,
                            category="workflow_contract",
                        )

            return state_update
        except Exception as e:
            logger.error(f"Error executing node {node.id} ({node.type}): {e}")
            if emitter:
                emitter.emit_error(str(e), node.id)
            try:
                from app.services.platform_architect_guardrails import PlatformArchitectBlockedError
            except Exception:
                PlatformArchitectBlockedError = None
            if PlatformArchitectBlockedError is not None and isinstance(e, PlatformArchitectBlockedError):
                raise
            state_payload = state.get("state", {}) if isinstance(state, dict) else {}
            if not isinstance(state_payload, dict):
                state_payload = {}
            return {
                "messages": [AIMessage(content=f"[{node.id}] execution error: {e}")],
                "state": {
                    **state_payload,
                    "last_error": {
                        "code": "NODE_EXECUTION_ERROR",
                        "node_id": node.id,
                        "node_type": node.type,
                        "message": str(e),
                    },
                },
                "error": str(e),
            }

    return node_fn

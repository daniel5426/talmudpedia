import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.agent.registry import AgentExecutorRegistry
from app.agent.graph.ir import GraphIRNode

logger = logging.getLogger(__name__)


def build_node_fn(node: GraphIRNode, tenant_id: Optional[UUID], db: Any):
    executor_cls = AgentExecutorRegistry.get_executor_cls(node.type)
    if not executor_cls:
        logger.error(f"No executor registered for node type: {node.type}")

        async def error_node(state: Any):
            return state

        return error_node

    executor = executor_cls(tenant_id, db)

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
            "node_name": node.config.get("label", node.id),
            "run_id": configurable.get("run_id") or configurable.get("thread_id") or state_context.get("run_id"),
            "grant_id": configurable.get("grant_id") or state_context.get("grant_id"),
            "principal_id": configurable.get("principal_id") or state_context.get("principal_id"),
            "initiator_user_id": configurable.get("initiator_user_id") or state_context.get("initiator_user_id"),
            "tenant_id": configurable.get("tenant_id") or state_context.get("tenant_id"),
            "user_id": configurable.get("user_id") or state_context.get("user_id"),
            "token": configurable.get("auth_token") or state_context.get("token"),
            "state_context": state_context,
        }

        if not await executor.can_execute(state, node.config, context):
            return {}

        node_config = dict(node.config or {})
        if node.input_mappings:
            node_config["input_mappings"] = node.input_mappings

        try:
            state_update = await executor.execute(state, node_config, context)

            if state_update and isinstance(state_update, dict):
                node_outputs = state.get("_node_outputs", {})
                safe_update = {k: v for k, v in state_update.items() if k != "_node_outputs"}
                node_outputs[node.id] = safe_update
                state_update["_node_outputs"] = node_outputs

            return state_update
        except Exception as e:
            logger.error(f"Error executing node {node.id} ({node.type}): {e}")
            raise e

    return node_fn

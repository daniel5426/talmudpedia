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

        context = {
            "langgraph_config": config,
            "emitter": emitter,
            "node_id": node.id,
            "node_type": node.type,
            "node_name": node.config.get("label", node.id),
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

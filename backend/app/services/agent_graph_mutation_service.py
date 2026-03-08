from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executors.standard import register_standard_operators
from app.agent.registry import AgentOperatorRegistry
from app.services.agent_service import AgentGraphValidationError, AgentService, UpdateAgentData
from app.services.graph_mutation_service import GraphMutationError, apply_graph_operations

logger = logging.getLogger(__name__)


class AgentGraphMutationService:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.agent_service = AgentService(db=db, tenant_id=tenant_id)

    async def get_graph(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self.agent_service.get_agent(agent_id)
        graph_definition = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
        return {
            "agent_id": str(agent.id),
            "agent_slug": agent.slug,
            "graph_definition": graph_definition,
        }

    async def validate_patch(self, agent_id: UUID, operations: list[dict[str, Any]]) -> dict[str, Any]:
        agent = await self.agent_service.get_agent(agent_id)
        current_graph = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
        mutation = apply_graph_operations(
            current_graph,
            operations,
            validate_node_config_path=self._validate_node_config_path,
        )
        validated_graph = await self.agent_service._validate_graph_for_write(mutation.graph, agent_id=agent.id)
        validation_result = await self.agent_service.validate_agent(agent.id)
        return self._build_result(
            agent_id=agent.id,
            graph_definition=validated_graph,
            mutation=mutation,
            validation_result=validation_result,
        )

    async def apply_patch(
        self,
        agent_id: UUID,
        operations: list[dict[str, Any]],
        *,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        phase = "preview_validation"
        try:
            preview = await self.validate_patch(agent_id, operations)
            if not preview["validation"]["valid"]:
                raise AgentGraphValidationError(preview["validation"]["errors"])

            phase = "persist_graph"
            agent = await self.agent_service.update_agent(
                agent_id,
                UpdateAgentData(graph_definition=preview["graph_definition"]),
                user_id=user_id,
            )

            phase = "post_write_validation"
            validation_result = await self.agent_service.validate_agent(agent.id)
            return self._build_result(
                agent_id=agent.id,
                graph_definition=agent.graph_definition if isinstance(agent.graph_definition, dict) else {},
                mutation=preview["mutation"],
                validation_result=validation_result,
            )
        except Exception as exc:
            setattr(exc, "graph_mutation_phase", phase)
            logger.exception(
                "Agent graph patch failed",
                extra={
                    "agent_id": str(agent_id),
                    "tenant_id": str(getattr(self, "tenant_id", "") or ""),
                    "phase": phase,
                    "operation_count": len(operations or []),
                },
            )
            raise

    async def add_tool_to_agent_node(
        self,
        agent_id: UUID,
        *,
        node_id: str,
        tool_id: str,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            agent_id,
            [
                {
                    "op": "append_unique_node_config_list_item",
                    "node_id": node_id,
                    "path": "tools",
                    "value": tool_id,
                }
            ],
            user_id=user_id,
        )

    async def remove_tool_from_agent_node(
        self,
        agent_id: UUID,
        *,
        node_id: str,
        tool_id: str,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            agent_id,
            [
                {
                    "op": "remove_node_config_list_item",
                    "node_id": node_id,
                    "path": "tools",
                    "value": tool_id,
                }
            ],
            user_id=user_id,
        )

    async def set_agent_model(
        self,
        agent_id: UUID,
        *,
        node_id: str,
        model_id: str,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            agent_id,
            [
                {
                    "op": "set_node_config_value",
                    "node_id": node_id,
                    "path": "model_id",
                    "value": model_id,
                }
            ],
            user_id=user_id,
        )

    async def set_agent_instructions(
        self,
        agent_id: UUID,
        *,
        node_id: str,
        instructions: str,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            agent_id,
            [
                {
                    "op": "set_node_config_value",
                    "node_id": node_id,
                    "path": "instructions",
                    "value": instructions,
                }
            ],
            user_id=user_id,
        )

    def _validate_node_config_path(self, node: dict[str, Any], segments: list[str | int]) -> None:
        register_standard_operators()
        node_type = str(node.get("type") or "").strip()
        spec = AgentOperatorRegistry.get(node_type)
        if spec is None or not segments:
            return
        first_segment = segments[0]
        if isinstance(first_segment, int):
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_INVALID_PATH",
                        "message": "Agent node config paths must begin with a field name",
                        "node_id": node.get("id"),
                    }
                ]
            )
        config_schema = spec.config_schema if isinstance(spec.config_schema, dict) else {}
        allowed = set(config_schema.get("properties", {}).keys()) if isinstance(config_schema.get("properties"), dict) else set()
        existing = set((node.get("config") or {}).keys()) if isinstance(node.get("config"), dict) else set()
        if allowed and first_segment not in allowed and first_segment not in existing:
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_UNKNOWN_CONFIG_FIELD",
                        "message": f"Config field '{first_segment}' is not valid for agent node type '{node_type}'",
                        "node_id": node.get("id"),
                        "path": ".".join(str(part) for part in segments),
                    }
                ]
            )

    @staticmethod
    def _build_result(
        *,
        agent_id: UUID,
        graph_definition: dict[str, Any],
        mutation: Any,
        validation_result: Any,
    ) -> dict[str, Any]:
        return {
            "agent_id": str(agent_id),
            "graph_definition": graph_definition,
            "mutation": {
                "applied_operations": list(mutation.applied_operations or []),
                "changed_node_ids": list(mutation.changed_node_ids or []),
                "changed_edge_ids": list(mutation.changed_edge_ids or []),
                "warnings": list(mutation.warnings or []),
            },
            "validation": {
                "valid": bool(getattr(validation_result, "valid", False)),
                "errors": list(getattr(validation_result, "errors", []) or []),
                "warnings": list(getattr(validation_result, "warnings", []) or []),
            },
        }

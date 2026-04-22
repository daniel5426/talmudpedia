from __future__ import annotations

from typing import Any

from app.services.agent_graph_mutation_service import AgentGraphMutationService
from app.services.control_plane.agents_admin_service import AgentAdminService, CreateAgentInput, StartAgentRunInput, UpdateAgentInput
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import not_found, validation
from app.services.platform_native.runtime import NativePlatformToolRuntime, parse_uuid


_AGENT_UPDATE_FIELDS = (
    "name",
    "description",
    "graph_definition",
    "memory_config",
    "execution_constraints",
    "show_in_playground",
)


def _shell_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "agent", "type": "agent", "position": {"x": 240, "y": 0}, "config": {}},
            {"id": "end", "type": "end", "position": {"x": 480, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e_start_agent", "source": "start", "target": "agent", "type": "control"},
            {"id": "e_agent_end", "source": "agent", "target": "end", "type": "control"},
        ],
        "spec_version": "2.0",
    }


async def agents_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    page = await AgentAdminService(rt.db).list_agents(
        ctx=ctx,
        query=query,
        status=rt.payload.get("status"),
    )
    return page.to_payload()


async def agents_get(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    return await AgentAdminService(rt.db).get_agent(ctx=await rt.build_control_plane_context(), agent_id=agent_id)


async def agents_create_shell(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    return await AgentAdminService(rt.db).create_agent(
        ctx=await rt.build_control_plane_context(),
        params=CreateAgentInput(
            name=str(rt.payload.get("name") or ""),
            description=rt.payload.get("description"),
            graph_definition=_shell_graph(),
            memory_config=rt.payload.get("memory_config") if isinstance(rt.payload.get("memory_config"), dict) else {},
            execution_constraints=rt.payload.get("execution_constraints") if isinstance(rt.payload.get("execution_constraints"), dict) else {},
        ),
    )


async def agents_create(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    if not isinstance(rt.payload.get("graph_definition"), dict):
        raise validation("graph_definition is required", field="graph_definition")
    return await AgentAdminService(rt.db).create_agent(
        ctx=await rt.build_control_plane_context(),
        params=CreateAgentInput(
            name=str(rt.payload.get("name") or ""),
            description=rt.payload.get("description"),
            graph_definition=rt.payload.get("graph_definition") if isinstance(rt.payload.get("graph_definition"), dict) else {},
            memory_config=rt.payload.get("memory_config") if isinstance(rt.payload.get("memory_config"), dict) else {},
            execution_constraints=rt.payload.get("execution_constraints") if isinstance(rt.payload.get("execution_constraints"), dict) else {},
        ),
    )


async def agents_update(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}
    if "patch" in rt.payload:
        raise validation(
            "patch is not supported; send direct top-level update fields",
            field="patch",
            errors=[
                {
                    "code": "LEGACY_FIELD_NOT_ALLOWED",
                    "path": "/patch",
                    "message": "Use direct top-level update fields instead of patch.",
                }
            ],
        )
    if not any(field in rt.payload for field in _AGENT_UPDATE_FIELDS):
        raise validation(
            "At least one update field is required.",
            errors=[
                {
                    "code": "MISSING_UPDATE_FIELDS",
                    "path": "/",
                    "message": "Provide at least one of name, description, graph_definition, memory_config, execution_constraints, or show_in_playground.",
                }
            ],
        )
    if "graph_definition" in rt.payload and not isinstance(rt.payload.get("graph_definition"), dict):
        raise validation("graph_definition must be an object", field="graph_definition")
    if "memory_config" in rt.payload and not isinstance(rt.payload.get("memory_config"), dict):
        raise validation("memory_config must be an object", field="memory_config")
    if "execution_constraints" in rt.payload and not isinstance(rt.payload.get("execution_constraints"), dict):
        raise validation("execution_constraints must be an object", field="execution_constraints")
    if "show_in_playground" in rt.payload and not isinstance(rt.payload.get("show_in_playground"), bool):
        raise validation("show_in_playground must be a boolean", field="show_in_playground")
    return await AgentAdminService(rt.db).update_agent(
        ctx=await rt.build_control_plane_context(),
        agent_id=agent_id,
        params=UpdateAgentInput(
            name=rt.payload.get("name"),
            description=rt.payload.get("description"),
            graph_definition=rt.payload.get("graph_definition"),
            memory_config=rt.payload.get("memory_config"),
            execution_constraints=rt.payload.get("execution_constraints"),
            show_in_playground=rt.payload.get("show_in_playground"),
        ),
    )


async def agents_graph_get(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).get_graph(agent_id)


async def agents_graph_validate_patch(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).validate_patch(
        agent_id,
        list(rt.payload.get("operations") or []),
    )


async def agents_graph_apply_patch(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).apply_patch(
        agent_id,
        list(rt.payload.get("operations") or []),
        user_id=ctx.user_id,
    )


async def agents_graph_add_tool(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    node_id = str(rt.payload.get("node_id") or "").strip()
    tool_id = str(rt.payload.get("tool_id") or "").strip()
    if not node_id or not tool_id:
        raise validation("node_id and tool_id are required")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).add_tool_to_agent_node(
        agent_id,
        node_id=node_id,
        tool_id=tool_id,
        user_id=ctx.user_id,
    )


async def agents_graph_remove_tool(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).remove_tool_from_agent_node(
        agent_id,
        node_id=str(rt.payload.get("node_id") or ""),
        tool_id=str(rt.payload.get("tool_id") or ""),
        user_id=ctx.user_id,
    )


async def agents_graph_set_model(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).set_agent_model(
        agent_id,
        node_id=str(rt.payload.get("node_id") or ""),
        model_id=str(rt.payload.get("model_id") or ""),
        user_id=ctx.user_id,
    )


async def agents_graph_set_instructions(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    ctx = await rt.build_control_plane_context()
    return await AgentGraphMutationService(
        db=rt.db,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    ).set_agent_instructions(
        agent_id,
        node_id=str(rt.payload.get("node_id") or ""),
        instructions=str(rt.payload.get("instructions") or ""),
        user_id=ctx.user_id,
    )


async def agents_publish(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}
    return await AgentAdminService(rt.db).publish_agent(ctx=await rt.build_control_plane_context(), agent_id=agent_id)


async def agents_validate(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    if "validation" in rt.payload:
        raise validation(
            "validation is not supported here; validate by agent id only",
            field="validation",
            errors=[
                {
                    "code": "LEGACY_FIELD_NOT_ALLOWED",
                    "path": "/validation",
                    "message": "Use agents.validate with only agent_id or id.",
                }
            ],
        )
    return await AgentAdminService(rt.db).validate_agent(ctx=await rt.build_control_plane_context(), agent_id=agent_id)


async def agents_nodes_catalog(rt: NativePlatformToolRuntime) -> Any:
    return await AgentAdminService(rt.db).list_node_catalog()


async def agents_nodes_schema(rt: NativePlatformToolRuntime) -> Any:
    return await AgentAdminService(rt.db).get_node_schemas(node_types=list(rt.payload.get("node_types") or []))


async def agents_nodes_validate(rt: NativePlatformToolRuntime) -> Any:
    return await agents_validate(rt)


async def agents_execute(rt: NativePlatformToolRuntime) -> Any:
    agent_id = parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise not_found("Agent not found")
    return await AgentAdminService(rt.db).start_run(
        ctx=await rt.build_control_plane_context(),
        agent_id=agent_id,
        params=StartAgentRunInput(
            input=rt.payload.get("input"),
            messages=list(rt.payload.get("messages") or []),
            context=rt.payload.get("context") if isinstance(rt.payload.get("context"), dict) else {},
            thread_id=parse_uuid(rt.payload.get("thread_id")),
        ),
    )


async def agents_get_run(rt: NativePlatformToolRuntime) -> Any:
    run_id = parse_uuid(rt.payload.get("run_id") or rt.payload.get("id"))
    if run_id is None:
        raise not_found("Run not found")
    return await AgentAdminService(rt.db).get_run(ctx=await rt.build_control_plane_context(), run_id=run_id)

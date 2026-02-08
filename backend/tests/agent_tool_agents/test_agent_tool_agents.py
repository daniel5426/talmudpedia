import os

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.registry import (
    ToolRegistry,
    ToolDefinitionScope,
    ToolImplementationType,
    ToolStatus,
)

from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    execute_agent_via_service,
    get_chat_model_slug,
    graph_def,
    node_def,
    edge_def,
)


def should_keep_agents() -> bool:
    return os.getenv("TEST_KEEP_AGENTS", "").strip().lower() in {"1", "true", "yes", "y"}


async def create_tool(
    db_session,
    tenant_id,
    run_prefix: str,
    slug_suffix: str,
    name: str,
    description: str,
    schema: dict,
    execution: dict | None = None,
):
    config_schema = {"implementation": {"type": "internal"}}
    if execution:
        config_schema["execution"] = execution

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"{run_prefix}-{name}",
        slug=f"{run_prefix}-{slug_suffix}",
        description=description,
        scope=ToolDefinitionScope.TENANT,
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.INTERNAL,
        config_schema=config_schema,
        schema=schema,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def cleanup_tools(db_session, tools: list[ToolRegistry]):
    if should_keep_agents():
        return
    try:
        for tool in tools:
            await db_session.delete(tool)
        await db_session.commit()
    except Exception:
        try:
            await db_session.rollback()
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_support_tool_loop_with_audit_tool_node(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for agent tool loop tests.")

    lookup_schema = {
        "input": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "request": {"type": "string"},
            },
            "required": ["ticket_id"],
        }
    }
    audit_schema = {
        "input": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["status"],
        }
    }

    lookup_tool = await create_tool(
        db_session,
        test_tenant_id,
        run_prefix,
        "support-lookup",
        "support-lookup",
        "Support lookup tool for agent tool loop",
        lookup_schema,
        execution={"is_pure": True, "concurrency_group": "support", "max_concurrency": 1},
    )
    audit_tool = await create_tool(
        db_session,
        test_tenant_id,
        run_prefix,
        "audit-log",
        "audit-log",
        "Audit log tool for post-processing",
        audit_schema,
        execution={"is_pure": True, "concurrency_group": "audit", "max_concurrency": 1},
    )

    lookup_instructions = (
        "You are a support lookup agent. Follow these steps exactly.\n"
        "Step 1: If you have not called a tool yet, respond ONLY with this JSON object:\n"
        f"{{\"tool_id\": \"{lookup_tool.id}\", \"input\": {{\"ticket_id\": \"T-100\", \"request\": \"status\"}}}}\n"
        "Step 2: After you receive the tool output, respond ONLY with the text LOOKUP_DONE."
    )

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def(
                "lookup_agent",
                "agent",
                {
                    "name": "Support Lookup Agent",
                    "model_id": chat_model,
                    "instructions": lookup_instructions,
                    "include_chat_history": True,
                    "output_format": "text",
                    "tools": [str(lookup_tool.id)],
                    "tool_execution_mode": "sequential",
                    "max_tool_iterations": 2,
                    "temperature": 0,
                },
            ),
            node_def("audit_tool", "tool", {"tool_id": str(audit_tool.id)}),
            node_def("end", "end", {"output_message": "done"}),
        ],
        [
            edge_def("e1", "start", "lookup_agent"),
            edge_def("e2", "lookup_agent", "audit_tool"),
            edge_def("e3", "audit_tool", "end"),
        ],
    )

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-support-tool-loop",
        f"{run_prefix}-support-tool-loop",
        graph,
    )

    try:
        result = await execute_agent_via_service(
            db_session,
            test_tenant_id,
            agent.id,
            test_user_id,
            input_text="Customer says order T-100 is missing.",
        )
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        lookup_output = outputs.get("lookup_agent", {})
        tool_outputs = lookup_output.get("tool_outputs", [])
        assert tool_outputs
        assert tool_outputs[0].get("tool") == lookup_tool.name

        audit_output = outputs.get("audit_tool", {})
        audit_tool_outputs = audit_output.get("tool_outputs", [])
        assert audit_tool_outputs
        assert audit_tool_outputs[0].get("tool") == audit_tool.name
    finally:
        if not should_keep_agents():
            await delete_agent(db_session, test_tenant_id, agent.id)
        await cleanup_tools(db_session, [lookup_tool, audit_tool])


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_multi_agent_tool_handoff(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for agent tool handoff tests.")

    action_schema = {
        "input": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "ticket_id": {"type": "string"},
                "priority": {"type": "string"},
            },
            "required": ["action"],
        }
    }
    notify_schema = {
        "input": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["channel"],
        }
    }

    action_tool = await create_tool(
        db_session,
        test_tenant_id,
        run_prefix,
        "action-executor",
        "action-executor",
        "Executes the triaged support action",
        action_schema,
        execution={"is_pure": False, "concurrency_group": "action", "max_concurrency": 1},
    )
    notify_tool = await create_tool(
        db_session,
        test_tenant_id,
        run_prefix,
        "notify-sender",
        "notify-sender",
        "Sends a customer notification",
        notify_schema,
        execution={"is_pure": True, "concurrency_group": "notify", "max_concurrency": 1},
    )

    action_instructions = (
        "You are a support triage agent. Respond ONLY with a JSON object.\n"
        "Use exactly: {\"action\": \"create_case\", \"ticket_id\": \"T-200\", \"priority\": \"high\"}."
    )
    notify_instructions = (
        "You are a notification agent. Respond ONLY with a JSON object.\n"
        "Use exactly: {\"channel\": \"email\", \"message\": \"Case T-200 created\"}."
    )

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def(
                "draft_agent",
                "agent",
                {
                    "name": "Draft Action Agent",
                    "model_id": chat_model,
                    "instructions": action_instructions,
                    "include_chat_history": False,
                    "output_format": "text",
                    "temperature": 0,
                },
            ),
            node_def("execute_tool", "tool", {"tool_id": str(action_tool.id)}),
            node_def(
                "notify_agent",
                "agent",
                {
                    "name": "Notify Agent",
                    "model_id": chat_model,
                    "instructions": notify_instructions,
                    "include_chat_history": False,
                    "output_format": "text",
                    "temperature": 0,
                },
            ),
            node_def("notify_tool", "tool", {"tool_id": str(notify_tool.id)}),
            node_def("end", "end", {"output_message": "done"}),
        ],
        [
            edge_def("e1", "start", "draft_agent"),
            edge_def("e2", "draft_agent", "execute_tool"),
            edge_def("e3", "execute_tool", "notify_agent"),
            edge_def("e4", "notify_agent", "notify_tool"),
            edge_def("e5", "notify_tool", "end"),
        ],
    )

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-multi-agent-tools",
        f"{run_prefix}-multi-agent-tools",
        graph,
    )

    try:
        result = await execute_agent_via_service(
            db_session,
            test_tenant_id,
            agent.id,
            test_user_id,
            input_text="Create a high priority support case for T-200 and notify the customer.",
        )
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        execute_output = outputs.get("execute_tool", {})
        execute_tool_outputs = execute_output.get("tool_outputs", [])
        assert execute_tool_outputs
        assert execute_tool_outputs[0].get("tool") == action_tool.name

        notify_output = outputs.get("notify_tool", {})
        notify_tool_outputs = notify_output.get("tool_outputs", [])
        assert notify_tool_outputs
        assert notify_tool_outputs[0].get("tool") == notify_tool.name
    finally:
        if not should_keep_agents():
            await delete_agent(db_session, test_tenant_id, agent.id)
        await cleanup_tools(db_session, [action_tool, notify_tool])

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


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_agent_node_tool_binding_executes_tool(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for agent tool binding test.")

    tool = ToolRegistry(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-tool",
        slug=f"{run_prefix}-tool",
        description="agent tool binding test",
        scope=ToolDefinitionScope.TENANT,
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.INTERNAL,
        config_schema={"implementation": {"type": "internal"}},
        schema={},
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    agent_config = {
        "name": "Tool Agent",
        "model_id": chat_model,
        "instructions": (
            "You must respond with ONLY a JSON object.\n"
            f"Use tool_id \"{tool.id}\".\n"
            "Use input {\"text\": \"hello\"}.\n"
            "No extra keys and no extra text."
        ),
        "include_chat_history": False,
        "reasoning_effort": "low",
        "output_format": "text",
        "tools": [str(tool.id)],
        "temperature": 0,
    }

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("agent", "agent", agent_config),
            node_def("end", "end", {"output_message": "tool_status={{ state.last_agent_output.status }}"}),
        ],
        [
            edge_def("e1", "start", "agent"),
            edge_def("e2", "agent", "end"),
        ],
    )

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-tool-agent",
        f"{run_prefix}-tool-agent",
        graph,
    )
    try:
        result = await execute_agent_via_service(
            db_session,
            test_tenant_id,
            agent.id,
            test_user_id,
            input_text="call the tool",
        )
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        agent_output = outputs.get("agent", {})
        tool_outputs = agent_output.get("tool_outputs", [])
        assert tool_outputs
        assert tool_outputs[0].get("tool") == tool.name
        assert tool_outputs[0].get("input", {}).get("text") == "hello"

        end_output = outputs.get("end", {})
        assert end_output.get("final_output") == "tool_status=executed"
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)
        try:
            await db_session.delete(tool)
            await db_session.commit()
        except Exception:
            pass

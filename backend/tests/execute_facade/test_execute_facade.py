import pytest
from uuid import UUID

from app.agent.executors.standard import register_standard_operators
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.agent_service import AgentService, CreateAgentData, ExecuteAgentData


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_execute_agent_facade_runs_and_persists(db_session, test_tenant_id, test_user_id, run_prefix):
    register_standard_operators()

    graph_definition = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
            {
                "id": "transform",
                "type": "transform",
                "position": {"x": 120, "y": 0},
                "config": {
                    "mode": "object",
                    "mappings": [{"key": "status", "value": "ok"}],
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 240, "y": 0},
                "config": {"output_message": "done"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "transform"},
            {"id": "e2", "source": "transform", "target": "end"},
        ],
    }

    service = AgentService(db=db_session, tenant_id=test_tenant_id)
    agent = await service.create_agent(
        CreateAgentData(
            name=f"{run_prefix}-execute",
            slug=f"{run_prefix}-execute",
            description="Execute facade test",
            graph_definition=graph_definition,
        ),
        user_id=test_user_id,
    )

    result = await service.execute_agent(
        agent_id=agent.id,
        data=ExecuteAgentData(input="hello"),
        user_id=test_user_id,
    )

    run_id = UUID(result.run_id)
    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert run.output_result is not None
    node_outputs = run.output_result.get("_node_outputs", {})
    assert node_outputs.get("transform", {}).get("transform_output", {}).get("status") == "ok"
    assert node_outputs.get("end", {}).get("final_output") == "done"

import pytest

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.stream_contract_v2 import normalize_filtered_event_to_v2
from app.agent.execution.types import ExecutionMode
from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    graph_def,
    node_def,
    edge_def,
    minimal_config_for,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_node_events_emitted_for_start_approval_end(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("approval", "user_approval"),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "approval"),
            edge_def("e2", "approval", "end", source_handle="approve"),
        ],
    )

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-events",
        f"{run_prefix}-events",
        graph,
    )

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={"approval": "approve"},
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        events = []
        async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            if event.event in {"node_start", "node_end"}:
                events.append((event.event, event.span_id))

        for node_id in ("start", "approval", "end"):
            assert ("node_start", node_id) in events
            assert ("node_end", node_id) in events
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_workflow_contract_events_emitted_for_v3_set_state_flow(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    graph = {
        "spec_version": "3.0",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "config": {"state_variables": [{"key": "copied_input", "type": "string"}]},
            },
            {
                "id": "set_state",
                "type": "set_state",
                "position": {"x": 1, "y": 0},
                "config": {
                    "assignments": [
                        {
                            "key": "copied_input",
                            "type": "string",
                            "value_ref": {"namespace": "workflow_input", "key": "input_as_text"},
                        }
                    ]
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 2, "y": 0},
                "config": {
                    "output_schema": {
                        "name": "result",
                        "mode": "simple",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"reply": {"type": "string"}},
                            "required": ["reply"],
                        },
                    },
                    "output_bindings": [
                        {
                            "json_pointer": "/reply",
                            "value_ref": {"namespace": "state", "key": "copied_input"},
                        }
                    ],
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "set_state"},
            {"id": "e2", "source": "set_state", "target": "end"},
        ],
    }

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-workflow-contract-events",
        f"{run_prefix}-workflow-contract-events",
        graph,
    )

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={"input": "hello"},
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        internal_events: list[str] = []
        async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            if event.event in {
                "workflow.inventory_snapshot",
                "workflow.start_seeded",
                "workflow.set_state_written",
                "workflow.node_output_published",
                "workflow.end_materialized",
            }:
                internal_events.append(event.event)

        assert "workflow.inventory_snapshot" in internal_events
        assert "workflow.start_seeded" in internal_events
        assert "workflow.set_state_written" in internal_events
        assert "workflow.node_output_published" in internal_events
        assert "workflow.end_materialized" in internal_events
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


def test_run_status_stream_contract_preserves_authoritative_final_output():
    event, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "run_status",
            "data": {
                "status": "completed",
                "final_output": {"answer": "authoritative"},
            },
        }
    )

    assert event == "run.completed"
    assert stage == "run"
    assert payload["final_output"] == {"answer": "authoritative"}
    assert diagnostics == []

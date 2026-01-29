import pytest
import pytest_asyncio
import uuid
import asyncio
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import select

from app.services.agent_service import AgentService, CreateAgentData
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, RunStatus
from app.agent.graph.schema import NodeType, AgentGraph, AgentNode, AgentEdge, AgentNodePosition

# Mock for AgentExecutorRegistry to avoid needing real LLM executors
from app.agent.registry import AgentExecutorRegistry, AgentOperatorRegistry, AgentOperatorSpec
from app.agent.executors.base import BaseNodeExecutor

class MockTransformExecutor(BaseNodeExecutor):
    async def execute(self, state, config, context):
        # Allow state mutability for testing
        messages = list(state.get("messages", []))
        messages.append({"role": "system", "content": "Transformed"})
        return {"messages": messages}

class MockHumanInputExecutor(BaseNodeExecutor):
    async def execute(self, state, config, context):
        # This will be interrupted before execution in the real graph
        # But if it executes (after resume), it just passes through or adds user input
        # The 'resume' payload typically gets injected as a Command result or state update.
        # For this test, we assume the node function returns the input
        # Note: In LangGraph, if we interrupt, the node function is not called until resumed?
        # Actually interrupt_before means we stop *before* this node runs.
        # When we resume, we run this node.
        return {} 

# Fixtures for DB
@pytest_asyncio.fixture
async def setup_env(db_session):
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()
    
    user = User(email="test@example.com", full_name="Tester", role="admin")
    db_session.add(user)
    await db_session.flush()
    
    return tenant, user

@pytest.fixture(autouse=True)
def mock_registry():
    # Inject mock executors
    # We patch the registry's get_executor_cls to return our mocks for testing
    original_get_exec = AgentExecutorRegistry.get_executor_cls
    original_get_op = AgentOperatorRegistry.get
    
    def side_effect_exec(node_type):
        if node_type == "transform": return MockTransformExecutor
        if node_type == "human_input": return MockHumanInputExecutor
        return original_get_exec(node_type)

    def side_effect_op(node_type):
        # Return a basic spec for any type we use in tests
        specs = {
            "start": AgentOperatorSpec(type="start", category="core", display_name="Start", description="S"),
            "end": AgentOperatorSpec(type="end", category="core", display_name="End", description="E"),
            "transform": AgentOperatorSpec(type="transform", category="logic", display_name="T", description="D"),
            "human_input": AgentOperatorSpec(type="human_input", category="logic", display_name="H", description="D"),
        }
        return specs.get(node_type) or original_get_op(node_type)
        
    with patch.object(AgentExecutorRegistry, 'get_executor_cls', side_effect=side_effect_exec), \
         patch.object(AgentOperatorRegistry, 'get', side_effect=side_effect_op):
        yield

@pytest.mark.asyncio
async def test_full_execution_flow(db_session, setup_env):
    """
    Test a complete execution flow: Start -> Transform -> End.
    Verifies that the run completes and traces are saved.
    """
    tenant, user = setup_env
    
    # 1. Create Agent Definition
    nodes = [
        AgentNode(id="start_1", type=NodeType.START, position=AgentNodePosition(x=0, y=0)),
        AgentNode(id="trans_1", type=NodeType.TRANSFORM, position=AgentNodePosition(x=100, y=0)),
        AgentNode(id="end_1", type=NodeType.END, position=AgentNodePosition(x=200, y=0))
    ]
    edges = [
        AgentEdge(id="e1", source="start_1", target="trans_1"),
        AgentEdge(id="e2", source="trans_1", target="end_1")
    ]
    
    agent_data = CreateAgentData(
        name="Flow Agent",
        slug="flow-agent",
        graph_definition={"nodes": [n.dict() for n in nodes], "edges": [e.dict() for e in edges]},
        memory_config={}
    )
    
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(agent_data, user_id=user.id)
    
    # 2. Start Run
    executor_service = AgentExecutorService(db=db_session)
    run_id = await executor_service.start_run(
        agent.id, 
        input_params={"messages": [{"role": "user", "content": "Hello"}]}, 
        user_id=user.id
    )
    
    # Wait for async execution (it runs in background task in the service)
    # We need to wait for it to finish.
    # Since we use asyncio.create_task in the service, we can't await the task object directly here easily
    # unless we expose it.
    # Workaround: Polling DB.
    
    for _ in range(20):
        await asyncio.sleep(0.1)
        result = await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalars().first()
        if run.status in [RunStatus.completed, RunStatus.failed]:
            break
            
    assert run.status == RunStatus.completed
    assert run.output_result is not None
    # Check if transform happened (MockTransformExecutor appends a message)
    # Note: 'messages' in output depends on how state flows.
    # Our AgentState has 'messages'.
    
    # 3. Check Traces
    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run_id))
    traces = result.scalars().all()
    assert len(traces) > 0
    # Verify that we have some start/end events
    event_types = [t.span_type for t in traces]
    assert "on_chain_start" in event_types
    
    # Check if messages in traces are sanitized (dicts, not HumanMessage objects)
    for trace in traces:
        if trace.name == "Flow Agent" and trace.outputs:
            messages = trace.outputs.get("messages", [])
            for msg in messages:
                assert isinstance(msg, dict)
                assert "role" in msg
                assert "content" in msg

@pytest.mark.asyncio
async def test_human_interruption_and_resume(db_session, setup_env):
    """
    Test interruption: Start -> HumanInput -> End.
    """
    tenant, user = setup_env
    
    # 1. Create Agent with Human Input
    nodes = [
        AgentNode(id="start_1", type=NodeType.START, position=AgentNodePosition(x=0, y=0)),
        AgentNode(id="human_1", type=NodeType.HUMAN_INPUT, position=AgentNodePosition(x=100, y=0)),
        AgentNode(id="end_1", type=NodeType.END, position=AgentNodePosition(x=200, y=0))
    ]
    edges = [
        AgentEdge(id="e1", source="start_1", target="human_1"),
        AgentEdge(id="e2", source="human_1", target="end_1")
    ]
    
    agent_data = CreateAgentData(
        name="Human Agent",
        slug="human-agent",
        graph_definition={"nodes": [n.dict() for n in nodes], "edges": [e.dict() for e in edges]},
        memory_config={}
    )
    
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(agent_data, user_id=user.id)
    
    # 2. Start Run
    executor_service = AgentExecutorService(db=db_session)
    run_id = await executor_service.start_run(
        agent.id, 
        input_params={"input": "start"}, 
        user_id=user.id
    )
    
    # 3. Poll for Paused State
    for _ in range(20):
        await asyncio.sleep(0.1)
        # Force expire to reload from DB
        db_session.expire_all()
        result = await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalars().first()
        if run.status == RunStatus.paused:
            break
    
    assert run.status == RunStatus.paused
    assert run.checkpoint is not None
    
    # 4. Resume Run
    # Provide the input the human node is waiting for
    await executor_service.resume_run(run_id, user_input={"input": "Human says hi"})
    
    # 5. Poll for Completion
    for _ in range(20):
        await asyncio.sleep(0.1)
        db_session.expire_all()
        result = await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalars().first()
        if run.status == RunStatus.completed:
            break
            
    assert run.status == RunStatus.completed


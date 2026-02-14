from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.rag import (
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    PipelineType,
    VisualPipeline,
)
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)
from app.rag.pipeline.executor import PipelineExecutor
from app.services.agent_service import AgentService, CreateAgentData
from app.services.model_resolver import ModelResolver


class _FakeProvider:
    def __init__(self, responses: list[list[AIMessageChunk]]):
        self._responses = responses
        self._idx = 0

    async def stream(self, _messages, _system_prompt=None, **_kwargs):
        response = self._responses[self._idx]
        self._idx += 1
        for chunk in response:
            yield chunk


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _create_simple_agent_with_tools(
    db_session,
    tenant_id: UUID,
    user_id: UUID,
    tool_ids: list[UUID],
    slug_suffix: str,
):
    graph = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "agent",
                "type": "agent",
                "position": {"x": 180, "y": 0},
                "config": {
                    "name": "Agent",
                    "model_id": "unit-model",
                    "tools": [str(tool_id) for tool_id in tool_ids],
                    "max_tool_iterations": 2,
                    "tool_execution_mode": "sequential",
                    "output_format": "text",
                },
            },
            {"id": "end", "type": "end", "position": {"x": 360, "y": 0}, "config": {"output_message": "done"}},
        ],
        "edges": [
            {"id": f"e1-{slug_suffix}", "source": "start", "target": "agent"},
            {"id": f"e2-{slug_suffix}", "source": "agent", "target": "end"},
        ],
    }

    service = AgentService(db=db_session, tenant_id=tenant_id)
    return await service.create_agent(
        CreateAgentData(
            name=f"agent-{slug_suffix}",
            slug=f"agent-{slug_suffix}",
            description="tool flow test",
            graph_definition=graph,
        ),
        user_id=user_id,
    )


async def _create_simple_agent(db_session, tenant_id: UUID, user_id: UUID, tool_id: UUID, slug_suffix: str):
    return await _create_simple_agent_with_tools(
        db_session=db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        tool_ids=[tool_id],
        slug_suffix=slug_suffix,
    )


def _tool_call_chunks(tool_name: str, args_payload: str):
    return [
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"id": "call-1", "name": tool_name, "args": args_payload}],
        )
    ]


@pytest.mark.asyncio
async def test_agent_web_search_full_flow_accepts_scalar_tool_args(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Web Search",
        slug=f"web-search-{uuid4().hex[:8]}",
        description="search the web",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        config_schema={
            "implementation": {
                "type": "builtin",
                "builtin": "web_search",
                "provider": "serper",
                "api_key": "unit-test-key",
            }
        },
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.CUSTOM,
        builtin_key="web_search",
        builtin_template_id=None,
        is_builtin_template=False,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    provider = _FakeProvider(
        responses=[
            _tool_call_chunks(tool.slug, "search weather in jerusalem"),
            [AIMessageChunk(content="Done")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    class _FakeWebSearchProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {
                "query": query,
                "provider": "serper",
                "results": [{"title": "Jerusalem weather", "url": "https://example.com", "top_k": top_k}],
            }

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    agent = await _create_simple_agent(db_session, tenant.id, user.id, tool.id, slug_suffix=uuid4().hex[:8])

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=agent.id,
        input_params={"messages": [{"role": "user", "content": "search weather"}], "context": {}},
        user_id=user.id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    streamed_events = []
    async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        streamed_events.append(event)

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed

    error_texts = [str(e.data.get("error")) for e in streamed_events if getattr(e, "event", "") == "error"]
    assert not any("requires query" in text for text in error_texts)

    tool_end_events = [e for e in streamed_events if getattr(e, "event", "") == "on_tool_end" and getattr(e, "name", "") == tool.name]
    assert tool_end_events
    output_payload = tool_end_events[-1].data.get("output") or {}
    context_payload = output_payload.get("context") if isinstance(output_payload, dict) else None
    if context_payload is None:
        context_payload = output_payload
    assert context_payload["provider"] == "serper"
    assert context_payload["query"] == "search weather in jerusalem"


@pytest.mark.asyncio
async def test_agent_retrieval_tool_full_flow_with_visual_pipeline(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)

    visual = VisualPipeline(
        tenant_id=tenant.id,
        name=f"retrieval-{uuid4().hex[:8]}",
        description="retrieval",
        nodes=[],
        edges=[],
        version=1,
        is_published=True,
        pipeline_type=PipelineType.RETRIEVAL,
        created_by=user.id,
    )
    db_session.add(visual)
    await db_session.commit()
    await db_session.refresh(visual)

    executable = ExecutablePipeline(
        visual_pipeline_id=visual.id,
        tenant_id=tenant.id,
        version=1,
        compiled_graph={"dag": []},
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user.id,
    )
    db_session.add(executable)
    await db_session.commit()
    await db_session.refresh(executable)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Retrieval Pipeline",
        slug=f"retrieval-pipeline-{uuid4().hex[:8]}",
        description="retrieval tool",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        config_schema={
            "implementation": {
                "type": "rag_retrieval",
                "pipeline_id": str(visual.id),
            }
        },
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.RAG_RETRIEVAL,
        builtin_key="retrieval_pipeline",
        builtin_template_id=None,
        is_builtin_template=False,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    provider = _FakeProvider(
        responses=[
            _tool_call_chunks(tool.slug, "sugya about eidim"),
            [AIMessageChunk(content="Done")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    async def fake_execute_job(self, job_id: UUID):
        job = await self.db.get(PipelineJob, job_id)
        job.status = PipelineJobStatus.COMPLETED
        job.output = {
            "results": [
                {
                    "id": "doc-1",
                    "text": "eidim relevant passage",
                    "score": 0.92,
                }
            ]
        }
        await self.db.commit()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr(PipelineExecutor, "execute_job", fake_execute_job)

    agent = await _create_simple_agent(db_session, tenant.id, user.id, tool.id, slug_suffix=uuid4().hex[:8])

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=agent.id,
        input_params={"messages": [{"role": "user", "content": "find sugya"}], "context": {}},
        user_id=user.id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    streamed_events = []
    async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        streamed_events.append(event)

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed

    error_texts = [str(e.data.get("error")) for e in streamed_events if getattr(e, "event", "") == "error"]
    assert not any("requires a query" in text for text in error_texts)

    tool_end_events = [e for e in streamed_events if getattr(e, "event", "") == "on_tool_end" and getattr(e, "name", "") == tool.name]
    assert tool_end_events
    output_payload = tool_end_events[-1].data.get("output") or {}
    context_payload = output_payload.get("context") if isinstance(output_payload, dict) else None
    if context_payload is None:
        context_payload = output_payload
    assert context_payload["query"] == "sugya about eidim"
    assert context_payload["pipeline_id"] == str(visual.id)
    assert context_payload["count"] == 1


@pytest.mark.asyncio
async def test_agent_reasoning_loop_invokes_agent_call_tool_and_consumes_compact_result(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)

    child_agent = await _create_simple_agent_with_tools(
        db_session=db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[],
        slug_suffix=f"child-{uuid4().hex[:8]}",
    )
    child_agent.status = AgentStatus.published
    child_agent.published_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(child_agent)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Agent Call Tool",
        slug=f"agent-call-{uuid4().hex[:8]}",
        description="call child agent",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={
            "implementation": {
                "type": "agent_call",
                "target_agent_slug": child_agent.slug,
            },
            "execution": {"timeout_s": 30},
        },
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.AGENT_CALL,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    parent_agent = await _create_simple_agent(
        db_session=db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_id=tool.id,
        slug_suffix=f"parent-{uuid4().hex[:8]}",
    )

    provider = _FakeProvider(
        responses=[
            _tool_call_chunks(tool.slug, '{"input":"ask child"}'),
            [AIMessageChunk(content="child final output")],
            [AIMessageChunk(content="parent final output")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=parent_agent.id,
        input_params={"messages": [{"role": "user", "content": "call child"}], "context": {}},
        user_id=user.id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    streamed_events = []
    async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        streamed_events.append(event)

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed

    tool_end_events = [e for e in streamed_events if getattr(e, "event", "") == "on_tool_end" and getattr(e, "name", "") == tool.name]
    assert tool_end_events
    output_payload = tool_end_events[-1].data.get("output") or {}
    compact_payload = output_payload if isinstance(output_payload, dict) else {}
    if isinstance(compact_payload.get("context"), dict) and "mode" in compact_payload["context"]:
        compact_payload = compact_payload["context"]
    if isinstance(compact_payload.get("tool_outputs"), list) and compact_payload["tool_outputs"]:
        first_output = compact_payload["tool_outputs"][0]
        if isinstance(first_output, dict):
            compact_payload = first_output

    assert compact_payload["mode"] == "sync"
    assert compact_payload["target_agent_slug"] == child_agent.slug
    assert compact_payload["status"] == "completed"
    assert compact_payload.get("output") is not None

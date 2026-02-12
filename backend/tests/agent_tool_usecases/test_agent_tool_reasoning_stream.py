from __future__ import annotations

import json
from collections import defaultdict
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import AgentRun, RunStatus
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


def _single_tool_call_chunk(tool_name: str, args_payload: str, *, call_id: str) -> list[AIMessageChunk]:
    return [
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"id": call_id, "name": tool_name, "args": args_payload}],
        )
    ]


def _multi_tool_call_chunk(calls: list[dict[str, str]]) -> list[AIMessageChunk]:
    return [AIMessageChunk(content="", tool_call_chunks=calls)]


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _create_tool(
    db_session,
    *,
    tenant_id: UUID,
    name: str,
    slug: str,
    builtin_key: str,
    schema: dict,
    implementation: dict,
    execution: dict | None = None,
) -> ToolRegistry:
    config_schema = {"implementation": implementation}
    if isinstance(execution, dict):
        config_schema["execution"] = execution

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=f"{name} tool",
        scope=ToolDefinitionScope.TENANT,
        schema=schema,
        config_schema=config_schema,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.CUSTOM,
        builtin_key=builtin_key,
        builtin_template_id=None,
        is_builtin_template=False,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def _create_retrieval_pipeline(db_session, *, tenant_id: UUID, user_id: UUID, suffix: str) -> VisualPipeline:
    visual = VisualPipeline(
        tenant_id=tenant_id,
        name=f"retrieval-pipeline-{suffix}",
        description="retrieval test pipeline",
        nodes=[],
        edges=[],
        version=1,
        is_published=True,
        pipeline_type=PipelineType.RETRIEVAL,
        created_by=user_id,
    )
    db_session.add(visual)
    await db_session.commit()
    await db_session.refresh(visual)

    executable = ExecutablePipeline(
        visual_pipeline_id=visual.id,
        tenant_id=tenant_id,
        version=1,
        compiled_graph={"dag": []},
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user_id,
    )
    db_session.add(executable)
    await db_session.commit()
    return visual


async def _create_agent_with_tools(
    db_session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    tool_ids: list[UUID],
    slug_suffix: str,
    tool_execution_mode: str = "sequential",
    max_parallel_tools: int = 2,
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
                    "tools": [str(tid) for tid in tool_ids],
                    "max_tool_iterations": 5,
                    "tool_execution_mode": tool_execution_mode,
                    "max_parallel_tools": max_parallel_tools,
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
            description="agent tool reasoning stream tests",
            graph_definition=graph,
        ),
        user_id=user_id,
    )


async def _run_filtered_stream_events(
    db_session,
    *,
    agent_id: UUID,
    user_id: UUID,
    mode: ExecutionMode,
    user_input: str,
) -> tuple[AgentRun, list[dict]]:
    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=agent_id,
        input_params={"messages": [{"role": "user", "content": user_input}], "context": {}},
        user_id=user_id,
        background=False,
        mode=mode,
    )

    filtered_events: list[dict] = []
    raw_stream = executor.run_and_stream(run_id, db_session, mode=mode)
    async for event in StreamAdapter.filter_stream(raw_stream, mode):
        filtered_events.append(event)

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    return run, filtered_events


def _reasoning_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "reasoning"]


def _events_by_name(events: list[dict], event_name: str, tool_name: str | None = None) -> list[dict]:
    filtered = [e for e in events if e.get("event") == event_name]
    if tool_name is not None:
        filtered = [e for e in filtered if e.get("name") == tool_name]
    return filtered


def _assert_active_complete_reasoning_lifecycle(events: list[dict], *, expected_tool_names: list[str]) -> None:
    reasoning = _reasoning_events(events)
    statuses_by_step: dict[str, list[str]] = defaultdict(list)
    names_by_step: dict[str, str] = {}
    for item in reasoning:
        data = item.get("data", {})
        step_id = data.get("step_id")
        status = data.get("status")
        if step_id:
            statuses_by_step[step_id].append(status)
            names_by_step[step_id] = data.get("step")

    assert len(statuses_by_step) == len(expected_tool_names)
    for step_statuses in statuses_by_step.values():
        assert step_statuses == ["active", "complete"]
    assert sorted(names_by_step.values()) == sorted(expected_tool_names)


@pytest.mark.asyncio
async def test_debug_stream_generates_reasoning_steps_for_each_tool_and_step(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    suffix = uuid4().hex[:8]

    web_search_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Web Search",
        slug=f"web-search-{suffix}",
        builtin_key="web_search",
        schema={
            "input": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        implementation={
            "type": "builtin",
            "builtin": "web_search",
            "provider": "serper",
            "api_key": "unit-test-key",
        },
    )

    datetime_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Datetime Utils",
        slug=f"datetime-utils-{suffix}",
        builtin_key="datetime_utils",
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "value": {"type": "string"},
                    "amount": {"type": "integer"},
                    "unit": {"type": "string"},
                },
            },
            "output": {"type": "object"},
        },
        implementation={"type": "builtin", "builtin": "datetime_utils"},
    )

    provider = _FakeProvider(
        responses=[
            _single_tool_call_chunk(web_search_tool.slug, "weather in jerusalem", call_id="call-1"),
            _single_tool_call_chunk(
                datetime_tool.slug,
                json.dumps(
                    {
                        "operation": "add",
                        "value": "2026-02-10T00:00:00Z",
                        "amount": 2,
                        "unit": "days",
                    }
                ),
                call_id="call-2",
            ),
            [AIMessageChunk(content="Combined answer ready")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    class _FakeWebSearchProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {
                "query": query,
                "provider": "serper",
                "top_k": top_k,
                "results": [{"title": "Jerusalem weather", "url": "https://example.com"}],
            }

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    agent = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[web_search_tool.id, datetime_tool.id],
        slug_suffix=suffix,
    )

    run, events = await _run_filtered_stream_events(
        db_session,
        agent_id=agent.id,
        user_id=user.id,
        mode=ExecutionMode.DEBUG,
        user_input="Check weather then add two days",
    )

    assert run.status == RunStatus.completed

    tool_start_events = _events_by_name(events, "on_tool_start")
    tool_end_events = _events_by_name(events, "on_tool_end")
    assert len(tool_start_events) == 2
    assert len(tool_end_events) == 2

    reasoning = _reasoning_events(events)
    assert len(reasoning) == 4

    statuses_by_step: dict[str, list[str]] = defaultdict(list)
    names_by_step: dict[str, str] = {}
    for item in reasoning:
        data = item.get("data", {})
        step_id = data.get("step_id")
        status = data.get("status")
        if step_id:
            statuses_by_step[step_id].append(status)
            names_by_step[step_id] = data.get("step")

    assert len(statuses_by_step) == 2
    for step_statuses in statuses_by_step.values():
        assert step_statuses == ["active", "complete"]

    assert set(names_by_step.values()) == {web_search_tool.name, datetime_tool.name}

    completed_web_step = next(
        item for item in reasoning if item.get("data", {}).get("step") == web_search_tool.name and item.get("data", {}).get("status") == "complete"
    )
    assert completed_web_step["data"]["output"]["query"] == "weather in jerusalem"


@pytest.mark.asyncio
async def test_production_stream_includes_internal_tool_and_reasoning_events(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    suffix = uuid4().hex[:8]

    web_search_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Web Search",
        slug=f"web-search-prod-{suffix}",
        builtin_key="web_search",
        schema={
            "input": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        implementation={
            "type": "builtin",
            "builtin": "web_search",
            "provider": "serper",
            "api_key": "unit-test-key",
        },
    )

    provider = _FakeProvider(
        responses=[
            _single_tool_call_chunk(web_search_tool.slug, "latest halacha news", call_id="prod-call-1"),
            [AIMessageChunk(content="Here is the summary")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    class _FakeWebSearchProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {"query": query, "provider": "serper", "top_k": top_k, "results": []}

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    agent = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[web_search_tool.id],
        slug_suffix=f"prod-{suffix}",
    )

    run, events = await _run_filtered_stream_events(
        db_session,
        agent_id=agent.id,
        user_id=user.id,
        mode=ExecutionMode.PRODUCTION,
        user_input="Need current updates",
    )

    assert run.status == RunStatus.completed
    assert len(_events_by_name(events, "on_tool_start", tool_name=web_search_tool.name)) == 1
    assert len(_events_by_name(events, "on_tool_end", tool_name=web_search_tool.name)) == 1
    _assert_active_complete_reasoning_lifecycle(events, expected_tool_names=[web_search_tool.name])

    completed_step = next(
        item
        for item in _reasoning_events(events)
        if item.get("data", {}).get("step") == web_search_tool.name and item.get("data", {}).get("status") == "complete"
    )
    assert completed_step["data"]["output"]["query"] == "latest halacha news"
    assert any(e.get("event") == "run_status" for e in events)


@pytest.mark.asyncio
async def test_debug_stream_tool_error_has_active_reasoning_step_without_complete(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    suffix = uuid4().hex[:8]

    web_fetch_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Web Fetch",
        slug=f"web-fetch-{suffix}",
        builtin_key="web_fetch",
        schema={
            "input": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            "output": {"type": "object"},
        },
        implementation={"type": "builtin", "builtin": "web_fetch"},
    )

    provider = _FakeProvider(
        responses=[
            _single_tool_call_chunk(web_fetch_tool.slug, "ftp://example.com/resource", call_id="err-call-1"),
            [AIMessageChunk(content="Handled fallback path")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    agent = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[web_fetch_tool.id],
        slug_suffix=f"err-{suffix}",
    )

    run, events = await _run_filtered_stream_events(
        db_session,
        agent_id=agent.id,
        user_id=user.id,
        mode=ExecutionMode.DEBUG,
        user_input="Try invalid scheme",
    )

    assert run.status == RunStatus.completed
    assert not _events_by_name(events, "on_tool_end", tool_name=web_fetch_tool.name)

    error_events = _events_by_name(events, "error")
    assert error_events
    assert any("http/https" in str((e.get("data") or {}).get("error")) for e in error_events)

    reasoning_for_tool = [
        e for e in _reasoning_events(events) if (e.get("data") or {}).get("step") == web_fetch_tool.name
    ]
    assert reasoning_for_tool
    assert [e["data"]["status"] for e in reasoning_for_tool] == ["active"]


@pytest.mark.asyncio
async def test_parallel_tool_calls_emit_reasoning_steps_for_each_call(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    suffix = uuid4().hex[:8]

    datetime_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Datetime Utils",
        slug=f"datetime-utils-par-{suffix}",
        builtin_key="datetime_utils",
        schema={
            "input": {
                "type": "object",
                "properties": {"operation": {"type": "string"}, "value": {"type": "string"}},
            },
            "output": {"type": "object"},
        },
        implementation={"type": "builtin", "builtin": "datetime_utils"},
        execution={"is_pure": True, "concurrency_group": "g1", "max_concurrency": 1},
    )

    json_transform_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="JSON Transform",
        slug=f"json-transform-{suffix}",
        builtin_key="json_transform",
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "data": {"type": "object"},
                    "pick": {"type": "array"},
                },
            },
            "output": {"type": "object"},
        },
        implementation={"type": "builtin", "builtin": "json_transform"},
        execution={"is_pure": True, "concurrency_group": "g2", "max_concurrency": 1},
    )

    provider = _FakeProvider(
        responses=[
            _multi_tool_call_chunk(
                [
                    {
                        "id": "par-call-1",
                        "name": datetime_tool.slug,
                        "args": json.dumps({"operation": "add", "value": "2026-02-01T00:00:00Z", "amount": 1, "unit": "days"}),
                    },
                    {
                        "id": "par-call-2",
                        "name": json_transform_tool.slug,
                        "args": json.dumps({"data": {"a": 1, "b": 2}, "pick": ["a"]}),
                    },
                ]
            ),
            [AIMessageChunk(content="Parallel calls complete")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    agent = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[datetime_tool.id, json_transform_tool.id],
        slug_suffix=f"parallel-{suffix}",
        tool_execution_mode="parallel_safe",
        max_parallel_tools=2,
    )

    run, events = await _run_filtered_stream_events(
        db_session,
        agent_id=agent.id,
        user_id=user.id,
        mode=ExecutionMode.DEBUG,
        user_input="Run both tools in one step",
    )

    assert run.status == RunStatus.completed
    reasoning = _reasoning_events(events)
    assert len(reasoning) == 4

    statuses_by_step: dict[str, list[str]] = defaultdict(list)
    for item in reasoning:
        data = item.get("data", {})
        step_id = data.get("step_id")
        if step_id:
            statuses_by_step[step_id].append(data.get("status"))

    assert len(statuses_by_step) == 2
    for statuses in statuses_by_step.values():
        assert statuses == ["active", "complete"]


@pytest.mark.asyncio
async def test_multiple_agents_web_search_and_retrieval_calls_reflect_in_production_reasoning(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    suffix = uuid4().hex[:8]

    retrieval_pipeline = await _create_retrieval_pipeline(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        suffix=suffix,
    )

    web_search_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Web Search",
        slug=f"web-search-multi-{suffix}",
        builtin_key="web_search",
        schema={
            "input": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        implementation={
            "type": "builtin",
            "builtin": "web_search",
            "provider": "serper",
            "api_key": "unit-test-key",
        },
    )

    retrieval_tool = await _create_tool(
        db_session,
        tenant_id=tenant.id,
        name="Retrieval Pipeline",
        slug=f"retrieval-multi-{suffix}",
        builtin_key="retrieval_pipeline",
        schema={
            "input": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "output": {"type": "object"},
        },
        implementation={
            "type": "rag_retrieval",
            "pipeline_id": str(retrieval_pipeline.id),
        },
    )

    provider_queue = [
        _FakeProvider(
            responses=[
                _single_tool_call_chunk(web_search_tool.slug, "daf yomi updates", call_id="agent-web-call-1"),
                [AIMessageChunk(content="web agent complete")],
            ]
        ),
        _FakeProvider(
            responses=[
                _single_tool_call_chunk(retrieval_tool.slug, "sugya about eidim", call_id="agent-ret-call-1"),
                [AIMessageChunk(content="retrieval agent complete")],
            ]
        ),
        _FakeProvider(
            responses=[
                _single_tool_call_chunk(web_search_tool.slug, "berakhot headlines", call_id="agent-mix-call-1"),
                _single_tool_call_chunk(retrieval_tool.slug, "sugya about shomer", call_id="agent-mix-call-2"),
                [AIMessageChunk(content="mixed agent complete")],
            ]
        ),
    ]

    async def fake_resolve(_self, _model_id):
        assert provider_queue, "Unexpected model resolve calls"
        return provider_queue.pop(0)

    class _FakeWebSearchProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {
                "query": query,
                "provider": "serper",
                "top_k": top_k,
                "results": [{"title": f"Result for {query}", "url": "https://example.com"}],
            }

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    async def fake_execute_job(self, job_id: UUID):
        job = await self.db.get(PipelineJob, job_id)
        query = str((job.input_params or {}).get("query") or "")
        job.status = PipelineJobStatus.COMPLETED
        job.output = {
            "results": [
                {
                    "id": f"doc-{query[:8] or 'x'}",
                    "text": f"retrieved passage for {query}",
                    "score": 0.91,
                }
            ]
        }
        await self.db.commit()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)
    monkeypatch.setattr(PipelineExecutor, "execute_job", fake_execute_job)

    agent_web = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[web_search_tool.id],
        slug_suffix=f"multi-web-{suffix}",
    )
    agent_retrieval = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[retrieval_tool.id],
        slug_suffix=f"multi-retrieval-{suffix}",
    )
    agent_mixed = await _create_agent_with_tools(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_ids=[web_search_tool.id, retrieval_tool.id],
        slug_suffix=f"multi-mixed-{suffix}",
    )

    run_web, events_web = await _run_filtered_stream_events(
        db_session,
        agent_id=agent_web.id,
        user_id=user.id,
        mode=ExecutionMode.PRODUCTION,
        user_input="find daf yomi updates",
    )
    run_retrieval, events_retrieval = await _run_filtered_stream_events(
        db_session,
        agent_id=agent_retrieval.id,
        user_id=user.id,
        mode=ExecutionMode.PRODUCTION,
        user_input="find eidim sources",
    )
    run_mixed, events_mixed = await _run_filtered_stream_events(
        db_session,
        agent_id=agent_mixed.id,
        user_id=user.id,
        mode=ExecutionMode.PRODUCTION,
        user_input="get headlines and sugya references",
    )

    assert run_web.status == RunStatus.completed
    assert run_retrieval.status == RunStatus.completed
    assert run_mixed.status == RunStatus.completed

    assert [e.get("name") for e in _events_by_name(events_web, "on_tool_start")] == [web_search_tool.name]
    assert [e.get("name") for e in _events_by_name(events_web, "on_tool_end")] == [web_search_tool.name]
    _assert_active_complete_reasoning_lifecycle(events_web, expected_tool_names=[web_search_tool.name])

    assert [e.get("name") for e in _events_by_name(events_retrieval, "on_tool_start")] == [retrieval_tool.name]
    assert [e.get("name") for e in _events_by_name(events_retrieval, "on_tool_end")] == [retrieval_tool.name]
    _assert_active_complete_reasoning_lifecycle(events_retrieval, expected_tool_names=[retrieval_tool.name])

    assert [e.get("name") for e in _events_by_name(events_mixed, "on_tool_start")] == [
        web_search_tool.name,
        retrieval_tool.name,
    ]
    assert [e.get("name") for e in _events_by_name(events_mixed, "on_tool_end")] == [
        web_search_tool.name,
        retrieval_tool.name,
    ]
    _assert_active_complete_reasoning_lifecycle(
        events_mixed,
        expected_tool_names=[web_search_tool.name, retrieval_tool.name],
    )

    web_output = (_events_by_name(events_web, "on_tool_end", web_search_tool.name)[0].get("data") or {}).get("output") or {}
    assert web_output.get("query") == "daf yomi updates"
    assert web_output.get("provider") == "serper"

    retrieval_output = (_events_by_name(events_retrieval, "on_tool_end", retrieval_tool.name)[0].get("data") or {}).get("output") or {}
    assert retrieval_output.get("query") == "sugya about eidim"
    assert retrieval_output.get("pipeline_id") == str(retrieval_pipeline.id)
    assert retrieval_output.get("count") == 1

    mixed_retrieval_output = (_events_by_name(events_mixed, "on_tool_end", retrieval_tool.name)[0].get("data") or {}).get("output") or {}
    assert mixed_retrieval_output.get("query") == "sugya about shomer"
    assert mixed_retrieval_output.get("pipeline_id") == str(retrieval_pipeline.id)
    assert any(e.get("event") == "run_status" for e in events_web)
    assert any(e.get("event") == "run_status" for e in events_retrieval)
    assert any(e.get("event") == "run_status" for e in events_mixed)

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk

from app.core.security import create_access_token
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)
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


def _tool_call_chunk(tool_name: str, args_payload: str, *, call_id: str) -> list[AIMessageChunk]:
    return [
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"id": call_id, "name": tool_name, "args": args_payload}],
        )
    ]


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for block in payload.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def _seed_execution_panel_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Panel Tenant {suffix}", slug=f"panel-tenant-{suffix}")
    user = User(email=f"panel-user-{suffix}@example.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(
        tenant_id=tenant.id,
        parent_id=None,
        name=f"Root {suffix}",
        slug=f"root-{suffix}",
        type=OrgUnitType.org,
    )
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)

    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        org_unit_id=str(root.id),
        org_role="owner",
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(tenant.id),
    }
    return tenant, user, headers


async def _create_web_search_tool(db_session, *, tenant_id: UUID, suffix: str) -> ToolRegistry:
    tool = ToolRegistry(
        tenant_id=tenant_id,
        name="Web Search",
        slug=f"panel-web-search-{suffix}",
        description="execution panel web search tool",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
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
        implementation_type=ToolImplementationType.CUSTOM,
        builtin_key="web_search",
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def _create_panel_agent(
    db_session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    tool_id: UUID,
    suffix: str,
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
                    "name": "Simple Agent",
                    "model_id": "gpt-5.2",
                    "tools": [str(tool_id)],
                    "max_tool_iterations": 2,
                    "tool_execution_mode": "sequential",
                    "output_format": "text",
                },
            },
            {"id": "end", "type": "end", "position": {"x": 360, "y": 0}, "config": {"output_message": "done"}},
        ],
        "edges": [
            {"id": f"e1-{suffix}", "source": "start", "target": "agent"},
            {"id": f"e2-{suffix}", "source": "agent", "target": "end"},
        ],
    }
    service = AgentService(db=db_session, tenant_id=tenant_id)
    return await service.create_agent(
        CreateAgentData(
            name=f"panel-agent-{suffix}",
            slug=f"panel-agent-{suffix}",
            description="execution panel parity test agent",
            graph_definition=graph,
        ),
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_execution_panel_stream_user_path_web_search_success(client, db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant, user, headers = await _seed_execution_panel_user(db_session)
    tool = await _create_web_search_tool(db_session, tenant_id=tenant.id, suffix=suffix)
    agent = await _create_panel_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_id=tool.id,
        suffix=suffix,
    )

    provider = _FakeProvider(
        responses=[
            _tool_call_chunk(tool.slug, json.dumps({"query": "weather in jerusalem"}), call_id="panel-call-1"),
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
                "results": [{"title": "Weather", "url": "https://example.com", "top_k": top_k}],
            }

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    response = await client.post(
        f"/agents/{agent.id}/stream?mode=debug",
        json={"input": "find me weather", "messages": []},
        headers=headers,
    )
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    assert any(item.get("event") == "run_id" for item in events)
    assert any(item.get("event") == "on_tool_start" and item.get("name") == "Web Search" for item in events)
    assert any(item.get("event") == "on_tool_end" and item.get("name") == "Web Search" for item in events)
    assert any(item.get("type") == "reasoning" and item.get("data", {}).get("status") == "active" for item in events)
    assert any(item.get("type") == "reasoning" and item.get("data", {}).get("status") == "complete" for item in events)
    assert not any(
        "web_search requires query" in str((item.get("data") or {}).get("error"))
        for item in events
        if item.get("event") == "error"
    )


@pytest.mark.asyncio
async def test_execution_panel_stream_user_path_web_search_can_fail_when_model_omits_query(client, db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant, user, headers = await _seed_execution_panel_user(db_session)
    tool = await _create_web_search_tool(db_session, tenant_id=tenant.id, suffix=suffix)
    agent = await _create_panel_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        tool_id=tool.id,
        suffix=suffix,
    )

    provider = _FakeProvider(
        responses=[
            _tool_call_chunk(tool.slug, "{}", call_id="panel-call-missing-query"),
            [AIMessageChunk(content="Done")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    class _FakeWebSearchProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {"query": query, "provider": "serper", "results": []}

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "unit-test-key"
        return _FakeWebSearchProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    response = await client.post(
        f"/agents/{agent.id}/stream?mode=debug",
        json={"input": "find me weather", "messages": []},
        headers=headers,
    )
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    assert any(item.get("event") == "on_tool_start" and item.get("name") == "Web Search" for item in events)
    assert not any(item.get("event") == "on_tool_end" and item.get("name") == "Web Search" for item in events)

    query_error_events = [
        item
        for item in events
        if item.get("event") == "error"
        and "web_search requires query" in str((item.get("data") or {}).get("error"))
    ]
    assert query_error_events

    assert any(
        item.get("type") == "reasoning"
        and item.get("data", {}).get("step") == "Web Search"
        and item.get("data", {}).get("status") == "active"
        for item in events
    )

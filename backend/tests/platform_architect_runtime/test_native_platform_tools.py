from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import platform_native_tools
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.context import ControlPlaneContext
from app.services.platform_native import agents as native_agents
from app.services.platform_native import rag as native_rag


@pytest.mark.asyncio
async def test_native_platform_dispatch_passes_runtime_context(monkeypatch):
    captured = {}

    async def fake_handler(runtime):
        captured["builtin_key"] = runtime.builtin_key
        captured["action"] = runtime.action
        captured["organization_id"] = runtime.runtime_context.get("organization_id")
        captured["token"] = runtime.runtime_context.get("token")
        return {"status": "ok"}

    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def commit(self):
            return None

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setitem(platform_native_tools._ACTION_HANDLERS, "agents.list", fake_handler)

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 5},
            "__tool_runtime_context__": {
                "organization_id": "tenant-1",
                "user_id": "user-1",
                "token": "bearer-123",
            },
        }
    )

    assert result["result"]["status"] == "ok"
    assert captured["builtin_key"] == "platform-agents"
    assert captured["action"] == "agents.list"
    assert captured["organization_id"] == "tenant-1"
    assert captured["token"] == "bearer-123"


@pytest.mark.asyncio
async def test_native_platform_dispatch_rejects_tool_action_mismatch(monkeypatch):
    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def commit(self):
            return None

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "artifacts.list",
            "payload": {},
            "__tool_runtime_context__": {"organization_id": "tenant-1", "requested_scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "SCOPE_DENIED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "expected_builtin_key", "expected_action", "payload"),
    [
        (
            "platform_action_agents_create",
            "platform-agents",
            "agents.create",
            {"name": "Demo Agent", "graph_definition": {"nodes": [], "edges": []}},
        ),
        (
            "platform_action_rag_create_visual_pipeline",
            "platform-rag",
            "rag.create_visual_pipeline",
            {"name": "Demo Pipeline", "nodes": [], "edges": []},
        ),
        (
            "platform_action_artifacts_create",
            "platform-assets",
            "artifacts.create",
            {"kind": "tool_impl", "title_prompt": "Create a tool"},
        ),
        (
            "platform_action_tools_create_or_update",
            "platform-assets",
            "tools.create_or_update",
            {"name": "Demo Tool"},
        ),
    ],
)
async def test_action_level_wrappers_reconstruct_fixed_dispatch_shape(
    monkeypatch,
    function_name,
    expected_builtin_key,
    expected_action,
    payload,
):
    captured = {}

    async def fake_dispatch(*, db, builtin_key, inputs, handlers):
        captured["db"] = db
        captured["builtin_key"] = builtin_key
        captured["inputs"] = inputs
        captured["handlers"] = handlers
        return {"result": {"status": "ok"}, "errors": [], "action": inputs["action"], "meta": {}}

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(platform_native_tools, "dispatch_native_platform_tool", fake_dispatch)

    tool_fn = getattr(platform_native_tools, function_name)
    result = await tool_fn(
        {
            **payload,
            "dry_run": True,
            "idempotency_key": "idem-1",
            "request_metadata": {"trace_id": "trace-1"},
            "__tool_runtime_context__": {"organization_id": "tenant-1"},
        }
    )

    assert result["result"]["status"] == "ok"
    assert captured["builtin_key"] == expected_builtin_key
    assert captured["inputs"]["action"] == expected_action
    assert captured["inputs"]["payload"] == payload
    assert captured["inputs"]["dry_run"] is True
    assert captured["inputs"]["idempotency_key"] == "idem-1"
    assert captured["inputs"]["request_metadata"] == {"trace_id": "trace-1"}
    assert captured["inputs"]["__tool_runtime_context__"] == {"organization_id": "tenant-1"}


def _runtime(payload: dict, *, dry_run: bool = False):
    ctx = ControlPlaneContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        auth_token=None,
        scopes=("*",),
    )

    async def _ctx():
        return ctx

    return SimpleNamespace(
        db=object(),
        payload=payload,
        dry_run=dry_run,
        build_control_plane_context=_ctx,
    )


@pytest.mark.asyncio
async def test_agents_update_accepts_direct_top_level_fields(monkeypatch):
    captured = {}

    async def fake_update_agent(self, *, ctx, agent_id, params):
        captured["ctx"] = ctx
        captured["agent_id"] = agent_id
        captured["params"] = params
        return {"status": "updated"}

    monkeypatch.setattr(native_agents.AgentAdminService, "update_agent", fake_update_agent)

    result = await native_agents.agents_update(
        _runtime(
            {
                "agent_id": str(uuid4()),
                "description": "updated",
                "graph_definition": {"nodes": [], "edges": []},
                "show_in_playground": False,
            }
        )
    )

    assert result["status"] == "updated"
    assert captured["params"].description == "updated"
    assert captured["params"].graph_definition == {"nodes": [], "edges": []}
    assert captured["params"].show_in_playground is False


@pytest.mark.asyncio
async def test_agents_update_rejects_patch_shape():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_agents.agents_update(
            _runtime(
                {
                    "agent_id": str(uuid4()),
                    "patch": {"description": "updated"},
                }
            )
        )

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "LEGACY_FIELD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_agents_update_rejects_missing_update_fields():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_agents.agents_update(_runtime({"agent_id": str(uuid4())}))

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "MISSING_UPDATE_FIELDS"


@pytest.mark.asyncio
async def test_agents_validate_rejects_legacy_validation_bag():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_agents.agents_validate(
            _runtime({"agent_id": str(uuid4()), "validation": {"strict": True}})
        )

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "LEGACY_FIELD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rag_create_visual_pipeline_accepts_top_level_nodes_and_edges(monkeypatch):
    captured = {}

    async def fake_create_pipeline(self, *, ctx, params):
        captured["ctx"] = ctx
        captured["params"] = params
        return {"status": "created"}

    monkeypatch.setattr(native_rag.RagAdminService, "create_pipeline", fake_create_pipeline)

    result = await native_rag.rag_create_visual_pipeline(
        _runtime(
            {
                "name": "FAQ Pipeline",
                "nodes": [{"id": "n1"}],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )
    )

    assert result["status"] == "created"
    assert captured["params"].nodes == [{"id": "n1"}]
    assert captured["params"].edges == [{"id": "e1", "source": "n1", "target": "n2"}]


@pytest.mark.asyncio
async def test_rag_create_visual_pipeline_rejects_legacy_graph_definition():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_rag.rag_create_visual_pipeline(
            _runtime(
                {
                    "name": "FAQ Pipeline",
                    "graph_definition": {"nodes": [], "edges": []},
                }
            )
        )

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "LEGACY_FIELD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rag_update_visual_pipeline_accepts_direct_top_level_fields(monkeypatch):
    captured = {}

    async def fake_update_pipeline(self, *, ctx, pipeline_id, params):
        captured["ctx"] = ctx
        captured["pipeline_id"] = pipeline_id
        captured["params"] = params
        return {"status": "updated"}

    monkeypatch.setattr(native_rag.RagAdminService, "update_pipeline", fake_update_pipeline)

    result = await native_rag.rag_update_visual_pipeline(
        _runtime(
            {
                "pipeline_id": str(uuid4()),
                "description": "updated",
                "nodes": [{"id": "n1"}],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )
    )

    assert result["status"] == "updated"
    assert captured["params"].description == "updated"
    assert captured["params"].nodes == [{"id": "n1"}]
    assert captured["params"].edges == [{"id": "e1", "source": "n1", "target": "n2"}]


@pytest.mark.asyncio
async def test_rag_update_visual_pipeline_rejects_patch_shape():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_rag.rag_update_visual_pipeline(
            _runtime({"pipeline_id": str(uuid4()), "patch": {"description": "updated"}})
        )

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "LEGACY_FIELD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rag_update_visual_pipeline_rejects_partial_graph_update():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_rag.rag_update_visual_pipeline(
            _runtime({"pipeline_id": str(uuid4()), "nodes": [{"id": "n1"}]})
        )

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "PARTIAL_GRAPH_UPDATE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rag_update_visual_pipeline_rejects_missing_update_fields():
    with pytest.raises(ControlPlaneError) as exc_info:
        await native_rag.rag_update_visual_pipeline(_runtime({"pipeline_id": str(uuid4())}))

    assert exc_info.value.to_payload()["details"]["errors"][0]["code"] == "MISSING_UPDATE_FIELDS"

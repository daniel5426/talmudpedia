from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.files import FileAccessMode
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry, ToolStatus
from app.db.postgres.models.workspace import Project, ProjectStatus
from app.agent.executors.standard import _file_space_prompt_preamble_from_state
from app.services.control_plane.agents_admin_service import AgentAdminService, StartAgentRunInput
from app.services.control_plane.context import ControlPlaneContext
from app.agent.execution.tool_invocation import build_tool_invocation_envelope, compile_tool_arguments
from app.services.file_spaces.service import FileSpaceService
from app.services.file_space_tools import (
    FILE_SPACE_TOOL_SPECS,
    FILE_SPACE_TOOLSET_ID,
    ensure_file_space_tools,
    files_list,
    files_read,
    files_write,
)


async def _seed_runtime_workspace(db_session):
    tenant = Organization(name="Runtime Organization", slug=f"runtime-tenant-{uuid4().hex[:8]}")
    user = User(email=f"runtime-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    project = Project(
        organization_id=tenant.id,
        name="Runtime Project",
        slug=f"runtime-project-{uuid4().hex[:8]}",
        status=ProjectStatus.active,
        is_default=True,
        created_by=user.id,
    )
    agent = Agent(
        organization_id=tenant.id,
        name="Runtime Workflow",
        slug=f"runtime-workflow-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
        memory_config={},
        execution_constraints={},
        created_by=user.id,
    )
    db_session.add_all([project, agent])
    await db_session.flush()

    file_service = FileSpaceService(db_session)
    space = await file_service.create_space(
        organization_id=tenant.id,
        project_id=project.id,
        name="Runtime Space",
        description=None,
        created_by=user.id,
    )
    await file_service.upsert_agent_link(
        organization_id=tenant.id,
        project_id=project.id,
        agent_id=agent.id,
        space_id=space.id,
        access_mode=FileAccessMode.read_write,
        user_id=user.id,
    )
    await db_session.commit()
    return tenant, project, user, agent, space


@pytest.mark.asyncio
async def test_agent_admin_run_start_injects_file_space_grants(db_session, monkeypatch):
    tenant, project, user, agent, space = await _seed_runtime_workspace(db_session)
    captured_context: dict = {}

    async def _fake_start_run(self, agent_id, input_params, **kwargs):  # noqa: ANN001
        nonlocal captured_context
        captured_context = dict(input_params.get("context") or {})
        run_id = uuid4()
        self.db.add(
            AgentRun(
                id=run_id,
                organization_id=tenant.id,
                agent_id=agent_id,
                initiator_user_id=user.id,
                status=RunStatus.queued,
                input_params=input_params,
            )
        )
        await self.db.flush()
        return run_id

    monkeypatch.setattr("app.services.control_plane.agents_admin_service.AgentExecutorService.start_run", _fake_start_run)

    service = AgentAdminService(db_session)
    await service.start_run(
        ctx=ControlPlaneContext(organization_id=tenant.id, project_id=project.id, user=user, user_id=user.id, auth_token="token"),
        agent_id=agent.id,
        params=StartAgentRunInput(input="hello", context={}),
    )

    assert captured_context["organization_id"] == str(tenant.id)
    assert captured_context["project_id"] == str(project.id)
    assert captured_context["file_spaces"] == [
        {"id": str(space.id), "name": space.name, "access_mode": "read_write"}
    ]


@pytest.mark.asyncio
async def test_file_tools_enforce_workflow_access_modes(db_session):
    tenant, project, user, _agent, space = await _seed_runtime_workspace(db_session)

    read_only_payload = {
        "space_id": str(space.id),
        "path": "notes.md",
        "content": "hello",
        "__tool_runtime_context__": {
            "organization_id": str(tenant.id),
            "project_id": str(project.id),
            "initiator_user_id": str(user.id),
            "run_id": str(uuid4()),
            "file_spaces": [{"id": str(space.id), "name": space.name, "access_mode": "read"}],
        },
    }
    denied = await files_write(read_only_payload)
    assert denied["code"] == "FILE_SPACE_FORBIDDEN"

    read_write_context = {
        "organization_id": str(tenant.id),
        "project_id": str(project.id),
        "initiator_user_id": str(user.id),
        "run_id": str(uuid4()),
        "file_spaces": [{"id": str(space.id), "name": space.name, "access_mode": "read_write"}],
    }
    write_result = await files_write(
        {
            "space_id": str(space.id),
            "path": "notes.md",
            "content": "hello world",
            "__tool_runtime_context__": read_write_context,
        }
    )
    assert write_result["entry"]["path"] == "notes.md"

    read_result = await files_read(
        {
            "space_id": str(space.id),
            "path": "notes.md",
            "__tool_runtime_context__": read_write_context,
        }
    )
    assert read_result["content"] == "hello world"

    list_result = await files_list(
        {
            "space_id": str(space.id),
            "__tool_runtime_context__": read_write_context,
        }
    )
    assert [item["path"] for item in list_result["items"]] == ["notes.md"]


@pytest.mark.asyncio
async def test_files_list_strips_runtime_metadata_before_strict_validation(db_session):
    tenant, project, user, _agent, space = await _seed_runtime_workspace(db_session)

    envelope = build_tool_invocation_envelope(
        tool=type(
            "Tool",
            (),
            {
                "id": uuid4(),
                "slug": "files-list",
                "name": "Files List",
                "schema": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "space_id": {"type": "string"},
                            "path_prefix": {"type": "string"},
                        },
                        "required": ["space_id"],
                        "additionalProperties": False,
                    },
                    "output": {"type": "object", "additionalProperties": True},
                },
                "config_schema": {"execution": {"validation_mode": "strict"}},
            },
        )(),
        raw_input={
            "space_id": "default",
            "project_id": str(project.id),
            "file_spaces": [{"id": str(space.id), "name": space.name, "access_mode": "read"}],
        },
        node_context={
            "organization_id": str(tenant.id),
            "project_id": str(project.id),
            "initiator_user_id": str(user.id),
            "run_id": str(uuid4()),
            "file_spaces": [{"id": str(space.id), "name": space.name, "access_mode": "read"}],
        },
        implementation_type="function",
        config_schema={"execution": {"validation_mode": "strict"}},
        implementation_config={"function_name": "files_list"},
        execution_config={"validation_mode": "strict"},
    )

    compile_failure = compile_tool_arguments(envelope)
    assert compile_failure is None
    assert envelope.model_input_compiled == {"space_id": "default"}


@pytest.mark.asyncio
async def test_files_list_accepts_default_space_alias(db_session):
    tenant, project, user, _agent, space = await _seed_runtime_workspace(db_session)
    read_write_context = {
        "organization_id": str(tenant.id),
        "project_id": str(project.id),
        "initiator_user_id": str(user.id),
        "run_id": str(uuid4()),
        "file_spaces": [{"id": str(space.id), "name": space.name, "access_mode": "read_write"}],
    }

    await files_write(
        {
            "space_id": "default",
            "path": "notes.md",
            "content": "hello world",
            "__tool_runtime_context__": read_write_context,
        }
    )

    list_result = await files_list(
        {
            "space_id": "default",
            "__tool_runtime_context__": read_write_context,
        }
    )

    assert [item["path"] for item in list_result["items"]] == ["notes.md"]


@pytest.mark.asyncio
async def test_seed_file_space_tools_creates_global_function_rows(db_session):
    tool_ids = await ensure_file_space_tools(db_session)

    rows = (
        await db_session.execute(
            select(ToolRegistry).where(
                ToolRegistry.organization_id.is_(None),
                ToolRegistry.builtin_key.in_([spec["builtin_key"] for spec in FILE_SPACE_TOOL_SPECS]),
            )
        )
    ).scalars().all()

    assert len(rows) == len(FILE_SPACE_TOOL_SPECS)
    assert {str(row.id) for row in rows} == set(tool_ids)

    by_key = {str(row.builtin_key): row for row in rows}
    assert set(by_key.keys()) == {spec["builtin_key"] for spec in FILE_SPACE_TOOL_SPECS}

    for spec in FILE_SPACE_TOOL_SPECS:
        row = by_key[spec["builtin_key"]]
        assert row.implementation_type == ToolImplementationType.FUNCTION
        assert row.status == ToolStatus.PUBLISHED
        assert row.is_system is True
        assert row.is_active is True
        assert row.config_schema["implementation"]["function_name"] == spec["function_name"]
        assert row.config_schema["toolset"]["id"] == FILE_SPACE_TOOLSET_ID
        assert set(row.config_schema["toolset"]["member_ids"]) == set(tool_ids)


def test_standard_agent_prompt_preamble_includes_linked_file_spaces():
    preamble = _file_space_prompt_preamble_from_state(
        {
            "context": {
                "file_spaces": [
                    {
                        "id": "b357f63e-2d42-470d-9a5d-bf07db26a6e9",
                        "name": "research workspace",
                        "access_mode": "read",
                    }
                ]
            }
        }
    )

    assert "Linked file spaces available for this run:" in preamble
    assert 'default => research workspace' in preamble
    assert 'space_id: "default"' in preamble

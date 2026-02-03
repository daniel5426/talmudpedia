import asyncio
import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.services.artifact_registry import get_artifact_registry
from app.rag.pipeline.registry import OperatorRegistry
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.executor import PipelineExecutor
from app.db.postgres.models.identity import Tenant, User, OrgMembership
from app.db.postgres.models.rag import VisualPipeline, ExecutablePipeline, PipelineJob, PipelineJobStatus, PipelineStepExecution, PipelineStepStatus, PipelineType
from app.db.postgres.models.registry import ToolRegistry, ToolDefinitionScope
from app.services.agent_service import AgentService, CreateAgentData
from app.agent.graph.schema import AgentNodePosition, AgentGraph
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.agent.graph.compiler import AgentCompiler
from app.agent.executors.standard import register_standard_operators
from app.db.postgres.models.agents import AgentRun, AgentTrace, RunStatus


@pytest_asyncio.fixture
async def tenant_user(db_session):
    if os.getenv("TEST_USE_REAL_DB") == "1":
        email = os.getenv("TEST_USER_EMAIL", "danielbenassaya2626@gmail.com")
        user_result = await db_session.execute(select(User).where(User.email == email))
        user = user_result.scalars().first()
        assert user, f"User with email {email} not found in DB"

        membership_result = await db_session.execute(
            select(OrgMembership, Tenant)
            .join(Tenant, OrgMembership.tenant_id == Tenant.id)
            .where(OrgMembership.user_id == user.id)
        )
        membership_row = membership_result.first()
        assert membership_row, f"No tenant membership found for user {email}"
        membership, tenant = membership_row
        return tenant, user

    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()

    user = User(email="tester@example.com", full_name="Tester", role="admin")
    db_session.add(user)
    await db_session.flush()

    return tenant, user


@pytest.fixture(scope="session", autouse=True)
def register_artifacts_and_executors():
    registry = get_artifact_registry()
    registry.refresh()
    OperatorRegistry.reset_instance()
    OperatorRegistry.get_instance()
    register_standard_operators()


def _build_retrieval_pipeline(name, nodes, edges, tenant_id):
    return VisualPipeline(
        tenant_id=tenant_id,
        name=name,
        description=f"{name} test pipeline",
        nodes=nodes,
        edges=edges,
        pipeline_type=PipelineType.RETRIEVAL,
    )


def _node(node_id, category, operator, x=0, y=0, config=None):
    return {
        "id": node_id,
        "category": category,
        "operator": operator,
        "position": {"x": x, "y": y},
        "config": config or {},
    }


def _edge(edge_id, source, target):
    return {
        "id": edge_id,
        "source": source,
        "target": target,
    }


@pytest.mark.asyncio
async def test_rag_pipelines_compile_execute_and_trace(db_session, tenant_user):
    tenant, user = tenant_user
    tenant_id = tenant.id
    user_id = user.id

    pipelines = []

    # Pipeline 1: query_input -> fake_retrieval -> retrieval_result
    pipelines.append(
        _build_retrieval_pipeline(
            "retrieval-basic",
            nodes=[
                _node("input_1", "input", "query_input", x=0, y=0),
                _node("retrieval_1", "retrieval", "custom/rag_fake_retrieval", x=200, y=0, config={"result_count": 1, "source": "basic"}),
                _node("output_1", "output", "retrieval_result", x=400, y=0),
            ],
            edges=[
                _edge("e1", "input_1", "retrieval_1"),
                _edge("e2", "retrieval_1", "output_1"),
            ],
            tenant_id=tenant_id,
        )
    )

    # Pipeline 2: query_input -> query_passthrough -> fake_retrieval -> retrieval_result
    pipelines.append(
        _build_retrieval_pipeline(
            "retrieval-with-passthrough",
            nodes=[
                _node("input_2", "input", "query_input", x=0, y=0),
                _node("pass_2", "enrichment", "custom/rag_query_passthrough", x=200, y=0, config={"tag": "pipeline-2"}),
                _node("retrieval_2", "retrieval", "custom/rag_fake_retrieval", x=400, y=0, config={"result_count": 2, "source": "passthrough"}),
                _node("output_2", "output", "retrieval_result", x=600, y=0),
            ],
            edges=[
                _edge("e3", "input_2", "pass_2"),
                _edge("e4", "pass_2", "retrieval_2"),
                _edge("e5", "retrieval_2", "output_2"),
            ],
            tenant_id=tenant_id,
        )
    )

    # Pipeline 3: query_input -> fake_retrieval (alt config) -> retrieval_result
    pipelines.append(
        _build_retrieval_pipeline(
            "retrieval-alt-config",
            nodes=[
                _node("input_3", "input", "query_input", x=0, y=0),
                _node("retrieval_3", "retrieval", "custom/rag_fake_retrieval", x=200, y=0, config={"result_count": 3, "source": "alt"}),
                _node("output_3", "output", "retrieval_result", x=400, y=0),
            ],
            edges=[
                _edge("e6", "input_3", "retrieval_3"),
                _edge("e7", "retrieval_3", "output_3"),
            ],
            tenant_id=tenant_id,
        )
    )

    compiler = PipelineCompiler()
    executor = PipelineExecutor(db_session)

    for pipeline in pipelines:
        db_session.add(pipeline)
        await db_session.commit()
        await db_session.refresh(pipeline)
        node_count = len(pipeline.nodes)

        compilation = compiler.compile(pipeline, compiled_by=str(user_id), tenant_id=str(tenant_id))
        assert compilation.success, f"Pipeline compilation failed: {compilation.errors}"

        executable = compilation.executable_pipeline
        executable_db = ExecutablePipeline(
            visual_pipeline_id=pipeline.id,
            tenant_id=tenant_id,
            version=pipeline.version,
            compiled_graph={
                "dag": [step.model_dump() for step in executable.dag],
                "config_snapshot": executable.config_snapshot,
                "locked_operator_versions": executable.locked_operator_versions,
                "dag_hash": executable.dag_hash,
            },
            pipeline_type=pipeline.pipeline_type,
            compiled_by=user_id,
            is_valid=True,
        )
        db_session.add(executable_db)
        await db_session.commit()
        await db_session.refresh(executable_db)

        job = PipelineJob(
            tenant_id=tenant_id,
            executable_pipeline_id=executable_db.id,
            input_params={"text": f"hello-{pipeline.name}"},
            triggered_by=user_id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        job_id = job.id
        await executor.execute_job(job_id)
        db_session.expire_all()
        refreshed = await db_session.get(PipelineJob, job_id)

        assert refreshed.status == PipelineJobStatus.COMPLETED
        assert refreshed.output is not None

        result = await db_session.execute(select(PipelineStepExecution).where(PipelineStepExecution.job_id == job_id))
        steps = result.scalars().all()

        assert len(steps) == node_count
        for step in steps:
            assert step.status == PipelineStepStatus.COMPLETED
            assert step.input_data is not None
            assert step.output_data is not None


@pytest.mark.asyncio
async def test_agent_artifacts_tools_mapping_and_tracing(db_session, tenant_user):
    tenant, user = tenant_user
    user_id = user.id
    if os.getenv("TEST_USE_REAL_DB") == "1":
        # Ensure tool_registry has artifact columns, otherwise fail with a clear message
        from sqlalchemy import text
        col_check = await db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name IN ('artifact_id', 'artifact_version')
                """
            )
        )
        cols = {row[0] for row in col_check.all()}
        has_artifact_columns = "artifact_id" in cols and "artifact_version" in cols
    else:
        has_artifact_columns = True

    # Create tool registry entries for artifact-backed tools
    slug_suffix = str(uuid.uuid4())[:8]
    tool_alpha_config = {}
    tool_beta_config = {}
    if not has_artifact_columns:
        tool_alpha_config = {
            "implementation": {
                "type": "artifact",
                "artifact_id": "custom/tool_alpha",
                "artifact_version": "1.0.0",
            }
        }
        tool_beta_config = {
            "implementation": {
                "type": "artifact",
                "artifact_id": "custom/tool_beta",
                "artifact_version": "1.0.0",
            }
        }

    tool_alpha_id = uuid.uuid4()
    tool_beta_id = uuid.uuid4()
    tool_alpha_slug = f"tool-alpha-{slug_suffix}"
    tool_beta_slug = f"tool-beta-{slug_suffix}"

    if has_artifact_columns:
        tool_alpha = ToolRegistry(
            id=tool_alpha_id,
            tenant_id=tenant.id,
            name="Tool Alpha",
            slug=tool_alpha_slug,
            description="Tool Alpha test",
            scope=ToolDefinitionScope.TENANT,
            schema={"input": {}, "output": {}},
            config_schema=tool_alpha_config,
            artifact_id="custom/tool_alpha",
            artifact_version="1.0.0",
            is_active=True,
            is_system=False,
        )
        tool_beta = ToolRegistry(
            id=tool_beta_id,
            tenant_id=tenant.id,
            name="Tool Beta",
            slug=tool_beta_slug,
            description="Tool Beta test",
            scope=ToolDefinitionScope.TENANT,
            schema={"input": {}, "output": {}},
            config_schema=tool_beta_config,
            artifact_id="custom/tool_beta",
            artifact_version="1.0.0",
            is_active=True,
            is_system=False,
        )
        db_session.add_all([tool_alpha, tool_beta])
        await db_session.commit()
        await db_session.refresh(tool_alpha)
        await db_session.refresh(tool_beta)
        tool_alpha_id = tool_alpha.id
        tool_beta_id = tool_beta.id
        assert tool_alpha.status is not None
        assert tool_alpha.version is not None
        assert tool_alpha.implementation_type is not None
    else:
        from sqlalchemy import text
        import json
        insert_stmt = text(
            """
            INSERT INTO tool_registry
                (id, tenant_id, name, slug, description, scope, schema, config_schema, is_active, is_system)
            VALUES
                (:id, :tenant_id, :name, :slug, :description, :scope, CAST(:schema AS jsonb), CAST(:config_schema AS jsonb), :is_active, :is_system)
            """
        )
        await db_session.execute(
            insert_stmt,
            {
                "id": tool_alpha_id,
                "tenant_id": tenant.id,
                "name": "Tool Alpha",
                "slug": tool_alpha_slug,
                "description": "Tool Alpha test",
                "scope": ToolDefinitionScope.TENANT.name,
                "schema": json.dumps({"input": {}, "output": {}}),
                "config_schema": json.dumps(tool_alpha_config),
                "is_active": True,
                "is_system": False,
            },
        )
        await db_session.execute(
            insert_stmt,
            {
                "id": tool_beta_id,
                "tenant_id": tenant.id,
                "name": "Tool Beta",
                "slug": tool_beta_slug,
                "description": "Tool Beta test",
                "scope": ToolDefinitionScope.TENANT.name,
                "schema": json.dumps({"input": {}, "output": {}}),
                "config_schema": json.dumps(tool_beta_config),
                "is_active": True,
                "is_system": False,
            },
        )
        await db_session.commit()

    service = AgentService(db=db_session, tenant_id=tenant.id)

    agent1_graph = {
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "position": AgentNodePosition(x=0, y=0).model_dump(),
                "config": {},
            },
            {
                "id": "transform_1",
                "type": "transform",
                "position": AgentNodePosition(x=150, y=0).model_dump(),
                "config": {
                    "mode": "object",
                    "mappings": [
                        {"key": "note", "value": "note-from-transform"},
                    ],
                },
            },
            {
                "id": "artifact_echo",
                "type": "artifact:custom/agent_echo",
                "position": AgentNodePosition(x=300, y=0).model_dump(),
                "config": {
                    "_artifact_id": "custom/agent_echo",
                    "_artifact_version": "1.0.0",
                    "label": "Agent Echo",
                    "prefix": "echo:",
                },
                "input_mappings": {
                    "user_text": "{{ state.messages[-1].content }}",
                    "upstream_note": "{{ upstream.transform_1.transform_output.note }}",
                    "tagged": "User said: {{ state.messages[-1].content }} / {{ upstream.transform_1.transform_output.note }}",
                    "default_tag": "override-default",
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "position": AgentNodePosition(x=450, y=0).model_dump(),
                "config": {},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "transform_1"},
            {"id": "e2", "source": "transform_1", "target": "artifact_echo"},
            {"id": "e3", "source": "artifact_echo", "target": "end_1"},
        ],
    }

    agent2_graph = {
        "nodes": [
            {
                "id": "start_2",
                "type": "start",
                "position": AgentNodePosition(x=0, y=0).model_dump(),
                "config": {},
            },
            {
                "id": "artifact_defaults",
                "type": "artifact:custom/agent_defaults",
                "position": AgentNodePosition(x=200, y=0).model_dump(),
                "config": {
                    "_artifact_id": "custom/agent_defaults",
                    "_artifact_version": "1.0.0",
                    "label": "Agent Defaults",
                },
            },
            {
                "id": "end_2",
                "type": "end",
                "position": AgentNodePosition(x=400, y=0).model_dump(),
                "config": {},
            },
        ],
        "edges": [
            {"id": "e4", "source": "start_2", "target": "artifact_defaults"},
            {"id": "e5", "source": "artifact_defaults", "target": "end_2"},
        ],
    }

    agent3_graph = {
        "nodes": [
            {
                "id": "start_3",
                "type": "start",
                "position": AgentNodePosition(x=0, y=0).model_dump(),
                "config": {},
            },
            {
                "id": "tool_1",
                "type": "tool",
                "position": AgentNodePosition(x=200, y=0).model_dump(),
                "config": {
                    "tool_id": str(tool_alpha_id),
                },
                "input_mappings": {
                    "text": "{{ state.messages[-1].content }}",
                    "suffix": "",
                },
            },
            {
                "id": "tool_2",
                "type": "tool",
                "position": AgentNodePosition(x=400, y=0).model_dump(),
                "config": {
                    "tool_id": str(tool_beta_id),
                },
                "input_mappings": {
                    "number": "{{ upstream.tool_1.context.tool_alpha }}",
                    "multiplier": "3",
                },
            },
            {
                "id": "end_3",
                "type": "end",
                "position": AgentNodePosition(x=600, y=0).model_dump(),
                "config": {},
            },
        ],
        "edges": [
            {"id": "e6", "source": "start_3", "target": "tool_1"},
            {"id": "e7", "source": "tool_1", "target": "tool_2"},
            {"id": "e8", "source": "tool_2", "target": "end_3"},
        ],
    }

    slug_suffix = str(uuid.uuid4())[:8]
    agent1 = await service.create_agent(
        CreateAgentData(
            name="Agent Echo",
            slug=f"agent-echo-{slug_suffix}",
            graph_definition=agent1_graph,
            memory_config={},
        ),
        user_id=user_id,
    )
    agent2 = await service.create_agent(
        CreateAgentData(
            name="Agent Defaults",
            slug=f"agent-defaults-{slug_suffix}",
            graph_definition=agent2_graph,
            memory_config={},
        ),
        user_id=user_id,
    )
    agent3 = await service.create_agent(
        CreateAgentData(
            name="Agent Tools",
            slug=f"agent-tools-{slug_suffix}",
            graph_definition=agent3_graph,
            memory_config={},
        ),
        user_id=user_id,
    )
    agent1_id = agent1.id
    agent2_id = agent2.id
    agent3_id = agent3.id

    compiler = AgentCompiler(db=db_session, tenant_id=tenant.id)
    for agent in (agent1, agent2, agent3):
        graph = AgentGraph(**agent.graph_definition)
        compiled = await compiler.compile(agent.id, agent.version, graph=graph)
        assert compiled.workflow is not None

    executor_service = AgentExecutorService(db=db_session)

    async def run_and_wait(agent_id, input_params):
        run_id = await executor_service.start_run(
            agent_id,
            input_params=input_params,
            user_id=user_id,
            background=False,
            mode=ExecutionMode.DEBUG,
        )
        # Execute synchronously in this session to avoid async background session issues
        await executor_service._execute(run_id, db=db_session, mode=ExecutionMode.DEBUG)
        db_session.expire_all()
        result = await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))
        return result.scalars().first()

    run1 = await run_and_wait(agent1_id, {"messages": [{"role": "user", "content": "hello"}]})
    run1_id = run1.id
    assert run1.status == RunStatus.completed
    assert run1.output_result is not None
    assert run1.output_result.get("context", {}).get("echo") == "echo: hello"
    assert "note-from-transform" in run1.output_result.get("context", {}).get("tagged", "")

    run2 = await run_and_wait(agent2_id, {"messages": [{"role": "user", "content": "defaults"}]})
    run2_id = run2.id
    assert run2.status == RunStatus.completed
    assert run2.output_result.get("context", {}).get("static_value") == "static-default"
    assert run2.output_result.get("context", {}).get("feature_flag") is True

    run3 = await run_and_wait(agent3_id, {"messages": [{"role": "user", "content": "5"}]})
    run3_id = run3.id
    assert run3.status == RunStatus.completed
    assert run3.output_result.get("context", {}).get("tool_alpha") == "5"
    assert run3.output_result.get("context", {}).get("tool_beta") == 15

    # Trace persistence checks
    traces1 = (await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run1_id))).scalars().all()
    traces2 = (await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run2_id))).scalars().all()
    traces3 = (await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run3_id))).scalars().all()

    assert any(t.span_type == "on_chain_start" for t in traces1)
    assert any(t.span_type == "on_chain_start" for t in traces2)
    assert any(t.span_type == "on_chain_start" for t in traces3)
    tool_start_traces = [t for t in traces3 if t.span_type == "on_tool_start"]
    tool_end_traces = [t for t in traces3 if t.span_type == "on_tool_end"]
    assert tool_start_traces or tool_end_traces
    assert any(t.end_time is not None for t in tool_start_traces) or tool_end_traces

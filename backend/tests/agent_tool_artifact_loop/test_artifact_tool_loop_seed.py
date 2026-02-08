import os

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.registry import (
    ToolRegistry,
    ToolDefinitionScope,
    ToolImplementationType,
    ToolStatus,
)
from app.services.agent_service import AgentService, CreateAgentData
from tests.agent_builder_helpers import (
    execute_agent_via_service,
    get_chat_model_slug,
    graph_def,
    node_def,
    edge_def,
)


ARTIFACT_ID = "custom/reading_time_estimator"
ARTIFACT_VERSION = "1.0.0"
DEFAULT_TOOL_SLUG = "reading-time-estimator"
DEFAULT_AGENT_SLUG = "reading-time-agent"


def should_keep_agents() -> bool:
    return os.getenv("TEST_KEEP_AGENTS", "").strip().lower() in {"1", "true", "yes", "y"}


async def create_artifact_tool(db_session, tenant_id, run_prefix: str) -> tuple[ToolRegistry, bool]:
    base_slug = os.getenv("TEST_ARTIFACT_TOOL_SLUG", DEFAULT_TOOL_SLUG)
    existing = await db_session.scalar(select(ToolRegistry).where(ToolRegistry.slug == base_slug))
    if existing and existing.tenant_id == tenant_id and existing.artifact_id == ARTIFACT_ID:
        return existing, False

    slug = base_slug
    if existing:
        slug = f"{base_slug}-{run_prefix}"

    schema = {
        "input": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "wpm": {"type": "number"},
            },
            "required": ["text"],
        },
        "output": {
            "type": "object",
            "properties": {
                "word_count": {"type": "integer"},
                "minutes": {"type": "number"},
                "seconds": {"type": "integer"},
                "summary": {"type": "string"},
            },
        },
    }
    config_schema = {
        "implementation": {
            "type": "artifact",
            "artifact_id": ARTIFACT_ID,
            "artifact_version": ARTIFACT_VERSION,
        },
        "execution": {
            "is_pure": True,
            "concurrency_group": "reading_time",
            "max_concurrency": 1,
            "timeout_s": 10,
        },
    }

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name="Reading Time Estimator",
        slug=slug,
        description="Estimate reading time from text input.",
        scope=ToolDefinitionScope.TENANT,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.ARTIFACT,
        config_schema=config_schema,
        schema=schema,
        artifact_id=ARTIFACT_ID,
        artifact_version=ARTIFACT_VERSION,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool, True


async def create_agent_for_tool(
    db_session,
    tenant_id,
    user_id,
    run_prefix: str,
    tool_id: str,
    model_id: str,
) -> Agent:
    base_slug = os.getenv("TEST_ARTIFACT_AGENT_SLUG", DEFAULT_AGENT_SLUG)
    existing = await db_session.scalar(
        select(Agent).where(Agent.slug == base_slug, Agent.tenant_id == tenant_id)
    )

    slug = base_slug if not existing else f"{base_slug}-{run_prefix}"

    instructions = (
        "You are a reading time estimator. Follow these steps exactly.\n"
        "Step 1: If you have not called a tool yet, respond ONLY with this JSON object:\n"
        f"{{\"tool_id\": \"{tool_id}\", \"input\": {{\"text\": \"{{{{ messages[-1].content }}}}\", \"wpm\": 200}}}}\n"
        "Step 2: After you receive the tool output, respond with a short sentence that includes "
        "the word_count and minutes values."
    )

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def(
                "reading_agent",
                "agent",
                {
                    "name": "Reading Time Agent",
                    "model_id": model_id,
                    "instructions": instructions,
                    "include_chat_history": True,
                    "output_format": "text",
                    "tools": [str(tool_id)],
                    "tool_execution_mode": "sequential",
                    "max_tool_iterations": 3,
                    "temperature": 0,
                },
            ),
            node_def("end", "end", {"output_message": "done"}),
        ],
        [
            edge_def("e1", "start", "reading_agent"),
            edge_def("e2", "reading_agent", "end"),
        ],
    )

    service = AgentService(db=db_session, tenant_id=tenant_id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Reading Time Agent",
            slug=slug,
            description="Artifact tool loop demo for reading time estimation.",
            graph_definition=graph,
        ),
        user_id=user_id,
    )
    return agent


async def cleanup_records(
    db_session,
    agent: Agent | None,
    tool: ToolRegistry | None,
    tool_created: bool,
):
    if should_keep_agents():
        return
    try:
        if agent:
            await db_session.delete(agent)
        if tool and tool_created:
            await db_session.delete(tool)
        await db_session.commit()
    except Exception:
        try:
            await db_session.rollback()
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_seed_artifact_tool_loop_agent(db_session, test_tenant_id, test_user_id, run_prefix):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for artifact tool loop test.")

    tool, tool_created = await create_artifact_tool(db_session, test_tenant_id, run_prefix)
    agent = await create_agent_for_tool(
        db_session,
        test_tenant_id,
        test_user_id,
        run_prefix,
        str(tool.id),
        chat_model,
    )

    print(
        "Seeded artifact tool loop demo:",
        f"tool_slug={tool.slug}",
        f"tool_id={tool.id}",
        f"agent_slug={agent.slug}",
        f"agent_id={agent.id}",
    )

    try:
        result = await execute_agent_via_service(
            db_session,
            test_tenant_id,
            agent.id,
            test_user_id,
            input_text="Estimate reading time for this short status update.",
        )
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        agent_output = outputs.get("reading_agent", {})
        tool_outputs = agent_output.get("tool_outputs", [])
        assert tool_outputs
        assert tool_outputs[0].get("artifact_id") == ARTIFACT_ID
        assert tool_outputs[0].get("word_count") is not None
    finally:
        await cleanup_records(db_session, agent, tool, tool_created)

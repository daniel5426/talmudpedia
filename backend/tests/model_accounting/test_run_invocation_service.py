from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, AgentRunInvocation, AgentStatus, RunStatus
from app.db.postgres.models.identity import Organization, User
from app.services.context_window_service import ContextWindowService
from app.services.run_invocation_service import RunInvocationService


async def _seed_run(db_session) -> AgentRun:
    suffix = uuid4().hex[:8]
    tenant = Organization(name=f"Organization {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"user-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    agent = Agent(
        organization_id=tenant.id,
        name=f"Agent {suffix}",
        slug=f"agent-{suffix}",
        status=AgentStatus.draft,
        is_active=True,
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.flush()

    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={},
        resolved_provider="openai",
        resolved_provider_model_id="gpt-5.4-mini",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


def test_usage_from_payload_keeps_multimodal_usage_dimensions():
    usage = RunInvocationService.usage_from_payload(
        {
            "audio_input_tokens": 2048,
            "audio_output_tokens": 64,
            "image_input_units": 3,
            "image_output_units": 1,
            "vendor_metric": 9,
        }
    )

    assert usage.audio_input_tokens == 2048
    assert usage.audio_output_tokens == 64
    assert usage.image_input_units == 3
    assert usage.image_output_units == 1
    assert usage.extra == {"vendor_metric": 9}


@pytest.mark.asyncio
async def test_non_llm_invocations_do_not_replace_run_level_chat_context_window(db_session):
    run = await _seed_run(db_session)
    service = RunInvocationService(db_session)

    chat_payload = RunInvocationService.build_invocation_payload(
        model_id="chat-model",
        resolved_provider="openai",
        resolved_provider_model_id="gpt-5.4-mini",
        node_id="llm_1",
        node_name="LLM",
        node_type="llm",
        max_context_tokens=128000,
        max_context_tokens_source="provider_metadata",
        context_input_tokens=120,
        context_source="provider_count_api",
        exact_usage_payload={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        estimated_output_tokens=None,
    )
    stt_payload = RunInvocationService.build_invocation_payload(
        model_id="stt-model",
        resolved_provider="google",
        resolved_provider_model_id="chirp_3",
        node_id="stt_1",
        node_name="Speech to Text",
        node_type="speech_to_text",
        max_context_tokens=None,
        max_context_tokens_source="not_applicable",
        context_input_tokens=None,
        context_source="unknown",
        exact_usage_payload={"audio_input_tokens": 2048},
        estimated_output_tokens=None,
    )

    await service.append_from_payload(run=run, payload=chat_payload)
    await service.append_from_payload(run=run, payload=stt_payload)
    usage_payload, context_window = await service.recompute_run_aggregates(run)
    await db_session.flush()

    invocations = list(
        (
            await db_session.execute(
                select(AgentRunInvocation)
                .where(AgentRunInvocation.run_id == run.id)
                .order_by(AgentRunInvocation.sequence.asc())
            )
        ).scalars()
    )

    assert len(invocations) == 2
    assert invocations[1].payload_json["usage"]["audio_input_tokens"] == 2048
    assert usage_payload == {
        "cached_input_tokens": 0,
        "cached_output_tokens": 0,
        "input_tokens": 120,
        "output_tokens": 30,
        "reasoning_tokens": 0,
        "total_tokens": 150,
    }
    assert context_window["source"] == "provider_count_api"
    assert context_window["model_id"] == "chat-model"
    assert context_window["max_tokens"] == 128000
    assert context_window["max_tokens_source"] == "provider_metadata"
    assert context_window["input_tokens"] == 120
    assert context_window["remaining_tokens"] == 127880
    assert ContextWindowService.read_from_run(run) == context_window
    assert run.resolved_provider == "openai"
    assert run.resolved_provider_model_id == "gpt-5.4-mini"
    assert run.input_tokens == 120
    assert run.output_tokens == 30
    assert run.total_tokens == 150

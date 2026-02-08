import os

import pytest
from sqlalchemy import delete, select, case, or_

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, AgentVersion, RunStatus
from app.db.postgres.models.rag import (
    ExecutablePipeline,
    KnowledgeStore,
    KnowledgeStoreStatus,
    PipelineType,
    StorageBackend,
    VisualPipeline,
)
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelCapabilityType,
    ModelProviderType,
    ModelStatus,
)
from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    edge_def,
    graph_def,
    minimal_config_for,
    node_def,
)

def should_keep_agents() -> bool:
    return os.getenv("TEST_KEEP_AGENTS", "").strip().lower() in {"1", "true", "yes", "y"}


async def purge_tenant_agents(db_session, tenant_id):
    if should_keep_agents():
        return
    agent_ids = select(Agent.id).where(Agent.tenant_id == tenant_id)
    run_ids = select(AgentRun.id).where(AgentRun.agent_id.in_(agent_ids))

    await db_session.execute(delete(AgentTrace).where(AgentTrace.run_id.in_(run_ids)))
    await db_session.execute(delete(AgentRun).where(AgentRun.agent_id.in_(agent_ids)))
    await db_session.execute(delete(AgentVersion).where(AgentVersion.agent_id.in_(agent_ids)))
    await db_session.execute(delete(Agent).where(Agent.id.in_(agent_ids)))
    await db_session.commit()


async def get_openai_model_slug(db_session, tenant_id, capability: ModelCapabilityType) -> str | None:
    tenant_priority = case((ModelRegistry.tenant_id == tenant_id, 1), else_=0).desc()
    provider_priority = case((ModelProviderBinding.tenant_id == tenant_id, 1), else_=0).desc()

    stmt = (
        select(ModelRegistry.slug)
        .join(ModelProviderBinding, ModelProviderBinding.model_id == ModelRegistry.id)
        .where(
            ModelRegistry.is_active == True,
            ModelRegistry.status == ModelStatus.ACTIVE,
            ModelRegistry.capability_type == capability,
            ModelProviderBinding.provider == ModelProviderType.OPENAI,
            ModelProviderBinding.is_enabled == True,
            or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None)),
            or_(ModelProviderBinding.tenant_id == tenant_id, ModelProviderBinding.tenant_id.is_(None)),
        )
        .order_by(tenant_priority, provider_priority, ModelRegistry.updated_at.desc())
        .limit(1)
    )

    result = await db_session.execute(stmt)
    row = result.first()
    return row[0] if row else None


async def get_platform_sdk_tool_id(db_session) -> str:
    from app.db.postgres.models.registry import ToolRegistry

    stmt = select(ToolRegistry.id).where(ToolRegistry.slug == "platform-sdk", ToolRegistry.tenant_id.is_(None))
    row = (await db_session.execute(stmt)).first()
    if not row:
        pytest.skip("Platform SDK tool missing; seed required.")
    return str(row[0])


async def pick_retrieval_assets(db_session, tenant_id):
    exec_stmt = (
        select(ExecutablePipeline, VisualPipeline)
        .join(VisualPipeline, ExecutablePipeline.visual_pipeline_id == VisualPipeline.id)
        .where(
            VisualPipeline.tenant_id == tenant_id,
            VisualPipeline.pipeline_type == PipelineType.RETRIEVAL,
            VisualPipeline.is_published == True,
            ExecutablePipeline.is_valid == True,
        )
        .order_by(ExecutablePipeline.created_at.desc())
    )
    exec_row = (await db_session.execute(exec_stmt)).first()
    if not exec_row:
        pytest.skip("No valid executable retrieval pipeline found for tenant.")

    executable, pipeline = exec_row

    store_stmt = (
        select(KnowledgeStore)
        .where(
            KnowledgeStore.tenant_id == tenant_id,
            KnowledgeStore.status == KnowledgeStoreStatus.ACTIVE,
            KnowledgeStore.backend == StorageBackend.PINECONE,
        )
        .order_by(KnowledgeStore.updated_at.desc())
    )
    stores = (await db_session.execute(store_stmt)).scalars().all()
    if not stores:
        pytest.skip("No active Pinecone knowledge store found for tenant.")

    preferred_store = next((s for s in stores if "openai" in (s.name or "").lower()), None)
    suffix = (pipeline.name or "").split()[-1] if pipeline.name else None
    if suffix:
        matched = next((s for s in stores if suffix in (s.name or "")), None)
        if matched:
            preferred_store = matched

    store = preferred_store or stores[0]
    return str(pipeline.id), str(store.id)


async def assert_no_compile_errors(db_session, tenant_id, graph):
    compiler = AgentCompiler(db=db_session, tenant_id=tenant_id)
    errors = await compiler.validate(AgentGraph(**graph))
    critical = [e for e in errors if e.severity == "error"]
    assert not critical


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_support_router_fullstack_agent(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
    monkeypatch,
):
    await purge_tenant_agents(db_session, test_tenant_id)

    chat_model = await get_openai_model_slug(db_session, test_tenant_id, ModelCapabilityType.CHAT)
    if not chat_model:
        pytest.skip("OpenAI chat model missing; add one for fullstack agent tests.")
    pipeline_id, store_id = await pick_retrieval_assets(db_session, test_tenant_id)

    tool_id = await get_platform_sdk_tool_id(db_session)

    guardrail_config = {
        "conditions": [
            {"name": "pass", "expression": "not contains(input, \"jailbreak\")"},
        ],
    }
    classify_config = {
        "model_id": chat_model,
        "instructions": "Classify the user intent based on the message.",
        "categories": [
            {"name": "return_item", "description": "Returns or refunds"},
            {"name": "cancel_subscription", "description": "Cancel or pause subscription"},
            {"name": "get_information", "description": "General information requests"},
        ],
    }
    info_agent_config = {
        "name": "Information agent",
        "model_id": chat_model,
        "instructions": (
            "Return JSON only. "
            "Respond with {\"action\": \"respond\", \"payload\": {\"message\": \"Here is the info\"}}."
        ),
        "output_format": "json",
        "write_output_to_context": True,
        "temperature": 0,
    }
    tool_config = {"tool_id": tool_id, "input_source": "last_agent_output"}

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("seed_state", "set_state", {
                "assignments": [{"variable": "intent", "value": "support_router"}],
                "is_expression": False,
            }),
            node_def("guardrail", "if_else", guardrail_config),
            node_def("classify", "classify", classify_config),
            node_def("return_agent", "agent", {"name": "Return agent", "model_id": chat_model, "temperature": 0}),
            node_def("retention_agent", "agent", {"name": "Retention agent", "model_id": chat_model, "temperature": 0}),
            node_def("info_agent", "agent", info_agent_config),
            node_def("rag_lookup", "rag", minimal_config_for("rag", pipeline_id=pipeline_id)),
            node_def("vector_guardrail", "vector_search", minimal_config_for("vector_search", knowledge_store_id=store_id)),
            node_def("tool_offer", "tool", tool_config),
            node_def("user_approval", "user_approval"),
            node_def("end_approved", "end", {"output_message": "Approved for {{ state.intent }}"}),
            node_def("end_rejected", "end", {"output_message": "Rejected for {{ state.intent }}"}),
            node_def("end_guardrail", "end", {"output_message": "Blocked by guardrail"}),
        ],
        [
            edge_def("e1", "start", "seed_state"),
            edge_def("e2", "seed_state", "guardrail"),
            edge_def("e3", "guardrail", "classify", source_handle="pass"),
            edge_def("e4", "guardrail", "end_guardrail", source_handle="else"),
            edge_def("e5", "classify", "return_agent", source_handle="return_item"),
            edge_def("e6", "classify", "retention_agent", source_handle="cancel_subscription"),
            edge_def("e7", "classify", "info_agent", source_handle="get_information"),
            edge_def("e8", "return_agent", "user_approval"),
            edge_def("e9", "retention_agent", "user_approval"),
            edge_def("e10", "info_agent", "rag_lookup"),
            edge_def("e11", "rag_lookup", "vector_guardrail"),
            edge_def("e12", "vector_guardrail", "tool_offer"),
            edge_def("e13", "tool_offer", "user_approval"),
            edge_def("e14", "user_approval", "end_approved", source_handle="approve"),
            edge_def("e15", "user_approval", "end_rejected", source_handle="reject"),
        ],
    )

    await assert_no_compile_errors(db_session, test_tenant_id, graph)

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-support-router",
        f"{run_prefix}-support-router",
        graph,
    )
    agent_id = agent.id

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={
                "input": "I need information about my order status.",
                "messages": [{"role": "user", "content": "I need information about my order status."}],
                "approval": "approve",
            },
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        events = []
        async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            if event.event in {"node_start", "node_end"}:
                events.append((event.event, event.span_id))

        run = await db_session.get(AgentRun, run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        assert "guardrail" in outputs
        assert outputs["guardrail"].get("branch_taken") == "pass"
        assert run.output_result.get("state", {}).get("intent") == "support_router"

        classify_branch = outputs.get("classify", {}).get("branch_taken") or outputs.get("classify", {}).get("next")
        if classify_branch == "return_item":
            assert "return_agent" in outputs
        elif classify_branch == "cancel_subscription":
            assert "retention_agent" in outputs
        else:
            assert "info_agent" in outputs
            assert "rag_lookup" in outputs
            assert "vector_guardrail" in outputs
            assert "tool_offer" in outputs

        assert "user_approval" in outputs
        assert "end_approved" in outputs
        assert outputs["end_approved"].get("final_output") == "Approved for support_router"

        # Ensure node_start/end events exist for key nodes along the executed path
        for node_id in ("start", "seed_state", "guardrail", "classify", "user_approval"):
            assert ("node_start", node_id) in events
            assert ("node_end", node_id) in events
    finally:
        if not should_keep_agents():
            await delete_agent(db_session, test_tenant_id, agent_id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_query_triage_fullstack_agent(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
    monkeypatch,
):
    await purge_tenant_agents(db_session, test_tenant_id)

    chat_model = await get_openai_model_slug(db_session, test_tenant_id, ModelCapabilityType.CHAT)
    if not chat_model:
        pytest.skip("OpenAI chat model missing; add one for fullstack agent tests.")
    pipeline_id, store_id = await pick_retrieval_assets(db_session, test_tenant_id)
    tool_id = await get_platform_sdk_tool_id(db_session)

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("rewrite", "agent", {
                "name": "Query rewrite",
                "model_id": chat_model,
                "instructions": "Rewrite the user question briefly.",
                "temperature": 0,
            }),
            node_def("route_state", "set_state", {
                "assignments": [{"variable": "route", "value": "external_fact_finding"}],
                "is_expression": False,
            }),
            node_def("classify", "classify", {
                "model_id": chat_model,
                "instructions": "Always output external_fact_finding.",
                "categories": [
                    {"name": "internal_qa", "description": "Internal knowledge base"},
                    {"name": "external_fact_finding", "description": "Needs external sources"},
                ],
            }),
            node_def("triage", "if_else", {
                "conditions": [
                    {"name": "internal_qa", "expression": "state.route == \"internal_qa\""},
                    {"name": "external_fact_finding", "expression": "state.route == \"external_fact_finding\""},
                ],
            }),
            node_def("internal_agent", "agent", {"name": "Internal Q&A", "model_id": chat_model, "temperature": 0}),
            node_def("external_agent", "agent", {
                "name": "External fact finding",
                "model_id": chat_model,
                "instructions": (
                    "Return JSON only. "
                    "Respond with {\"action\": \"respond\", \"payload\": {\"message\": \"External facts ready\"}}."
                ),
                "output_format": "json",
                "write_output_to_context": True,
                "temperature": 0,
            }),
            node_def("rag_lookup", "rag", minimal_config_for("rag", pipeline_id=pipeline_id)),
            node_def("vector_lookup", "vector_search", minimal_config_for("vector_search", knowledge_store_id=store_id)),
            node_def("tool_respond", "tool", {"tool_id": tool_id, "input_source": "last_agent_output"}),
            node_def("finalize", "transform", {
                "mode": "object",
                "mappings": [{"key": "answer", "value": "external_answer"}],
            }),
            node_def("end", "end", {"output_message": "Final: {{ state.answer }}"}),
        ],
        [
            edge_def("e1", "start", "rewrite"),
            edge_def("e2", "rewrite", "route_state"),
            edge_def("e3", "route_state", "classify"),
            edge_def("e4", "classify", "triage", source_handle="external_fact_finding"),
            edge_def("e5", "classify", "triage", source_handle="internal_qa"),
            edge_def("e6", "triage", "internal_agent", source_handle="internal_qa"),
            edge_def("e7", "triage", "external_agent", source_handle="external_fact_finding"),
            edge_def("e7b", "triage", "internal_agent", source_handle="else"),
            edge_def("e8", "external_agent", "rag_lookup"),
            edge_def("e9", "rag_lookup", "vector_lookup"),
            edge_def("e10", "vector_lookup", "tool_respond"),
            edge_def("e11", "tool_respond", "finalize"),
            edge_def("e12", "internal_agent", "finalize"),
            edge_def("e13", "finalize", "end"),
        ],
    )

    await assert_no_compile_errors(db_session, test_tenant_id, graph)

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-query-triage",
        f"{run_prefix}-query-triage",
        graph,
    )
    agent_id = agent.id

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={
                "input": "What are the refund policies?",
                "messages": [{"role": "user", "content": "What are the refund policies?"}],
            },
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        async for _ in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            pass

        run = await db_session.get(AgentRun, run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        assert "rewrite" in outputs
        assert "route_state" in outputs
        assert "classify" in outputs
        assert "triage" in outputs
        assert run.output_result.get("state", {}).get("route") == "external_fact_finding"
        assert "external_agent" in outputs
        assert "rag_lookup" in outputs
        assert "vector_lookup" in outputs
        assert "tool_respond" in outputs
        assert "finalize" in outputs
        assert outputs["end"].get("final_output") == "Final: external_answer"
    finally:
        if not should_keep_agents():
            await delete_agent(db_session, test_tenant_id, agent_id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_document_compare_fullstack_agent(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
    monkeypatch,
):
    await purge_tenant_agents(db_session, test_tenant_id)

    chat_model = await get_openai_model_slug(db_session, test_tenant_id, ModelCapabilityType.CHAT)
    if not chat_model:
        pytest.skip("OpenAI chat model missing; add one for fullstack agent tests.")
    pipeline_id, store_id = await pick_retrieval_assets(db_session, test_tenant_id)
    tool_id = await get_platform_sdk_tool_id(db_session)

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("human_input", "human_input"),
            node_def("request_state", "set_state", {
                "assignments": [{"variable": "request_type", "value": "compare"}],
                "is_expression": False,
            }),
            node_def("triage", "if_else", {
                "conditions": [
                    {"name": "compare", "expression": "state.request_type == \"compare\""},
                    {"name": "answer_question", "expression": "state.request_type == \"answer_question\""},
                ],
            }),
            node_def("propose_reconciliation", "agent", {
                "name": "Propose reconciliation",
                "model_id": chat_model,
                "instructions": (
                    "Return JSON only. "
                    "Respond with {\"action\": \"respond\", \"payload\": {\"message\": \"Reconciliation proposal\"}}."
                ),
                "output_format": "json",
                "write_output_to_context": True,
                "temperature": 0,
            }),
            node_def("rag_lookup", "rag", minimal_config_for("rag", pipeline_id=pipeline_id)),
            node_def("vector_lookup", "vector_search", minimal_config_for("vector_search", knowledge_store_id=store_id)),
            node_def("tool_respond", "tool", {"tool_id": tool_id, "input_source": "last_agent_output"}),
            node_def("provide_explanation", "agent", {
                "name": "Provide explanation",
                "model_id": chat_model,
                "instructions": "Provide a short explanation.",
                "temperature": 0,
            }),
            node_def("retry_agent", "agent", {
                "name": "Retry agent",
                "model_id": chat_model,
                "instructions": "Ask for clarification.",
                "temperature": 0,
            }),
            node_def("approval", "user_approval"),
            node_def("approval_agent", "agent", {
                "name": "Approval agent",
                "model_id": chat_model,
                "instructions": "Confirm approval and summarize next steps.",
                "temperature": 0,
            }),
            node_def("rejection_agent", "agent", {
                "name": "Rejection agent",
                "model_id": chat_model,
                "instructions": "Acknowledge rejection and suggest alternatives.",
                "temperature": 0,
            }),
            node_def("end_approved", "end", {"output_message": "Approved request: {{ state.request_type }}"}),
            node_def("end_rejected", "end", {"output_message": "Rejected request: {{ state.request_type }}"}),
            node_def("end_else", "end", {"output_message": "Fallback: {{ state.request_type }}"}),
        ],
        [
            edge_def("e1", "start", "human_input"),
            edge_def("e2", "human_input", "request_state"),
            edge_def("e3", "request_state", "triage"),
            edge_def("e4", "triage", "propose_reconciliation", source_handle="compare"),
            edge_def("e5", "triage", "provide_explanation", source_handle="answer_question"),
            edge_def("e6", "triage", "retry_agent", source_handle="else"),
            edge_def("e7", "propose_reconciliation", "rag_lookup"),
            edge_def("e8", "rag_lookup", "vector_lookup"),
            edge_def("e9", "vector_lookup", "tool_respond"),
            edge_def("e10", "tool_respond", "approval"),
            edge_def("e11", "approval", "approval_agent", source_handle="approve"),
            edge_def("e12", "approval", "rejection_agent", source_handle="reject"),
            edge_def("e13", "approval_agent", "end_approved"),
            edge_def("e14", "rejection_agent", "end_rejected"),
            edge_def("e15", "provide_explanation", "end_else"),
            edge_def("e16", "retry_agent", "end_else"),
        ],
    )

    await assert_no_compile_errors(db_session, test_tenant_id, graph)

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-doc-compare",
        f"{run_prefix}-doc-compare",
        graph,
    )
    agent_id = agent.id

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={
                "input": "Compare two lease documents.",
                "messages": [{"role": "user", "content": "Compare two lease documents."}],
                "approval": "approve",
            },
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        async for _ in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            pass

        run = await db_session.get(AgentRun, run_id)
        assert run.status == RunStatus.completed

        outputs = run.output_result.get("_node_outputs", {})
        assert "human_input" in outputs
        assert "request_state" in outputs
        assert outputs["request_state"].get("state", {}).get("request_type") == "compare"
        assert "propose_reconciliation" in outputs
        assert "rag_lookup" in outputs
        assert "vector_lookup" in outputs
        assert "tool_respond" in outputs
        assert "approval" in outputs
        assert "approval_agent" in outputs
        assert "end_approved" in outputs
        assert outputs["end_approved"].get("final_output") == "Approved request: compare"
    finally:
        if not should_keep_agents():
            await delete_agent(db_session, test_tenant_id, agent_id)

import argparse
import asyncio
import os
import sys
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import select, case, or_
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

# Load env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db.postgres.engine import engine
from app.db.postgres.models.identity import User, OrgMembership, MembershipStatus
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.registry import (
    ToolRegistry,
    ToolDefinitionScope,
    ToolImplementationType,
    ToolStatus,
    ModelRegistry,
    ModelCapabilityType,
    ModelStatus,
    ModelProviderBinding,
)
from app.services.agent_service import AgentService, CreateAgentData, UpdateAgentData


def node_def(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge_def(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    data = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        data["source_handle"] = source_handle
    return data


def graph_def(nodes: list[dict], edges: list[dict]) -> dict:
    return {"spec_version": "1.0", "nodes": nodes, "edges": edges}


def _env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None


async def resolve_tenant_and_user(
    session: AsyncSession,
    email: str | None,
    tenant_id: str | None,
    user_id: str | None,
) -> tuple[UUID, UUID]:
    if tenant_id and user_id:
        return UUID(tenant_id), UUID(user_id)

    if tenant_id and not user_id:
        user = await session.scalar(select(User).where(User.tenant_id == UUID(tenant_id)))
        if not user:
            raise ValueError("No user found for provided tenant_id; pass --user-id or --email.")
        return UUID(tenant_id), user.id

    if not email:
        raise ValueError("Provide --email or --tenant-id/--user-id.")

    user = await session.scalar(select(User).where(User.email == email))
    if not user:
        raise ValueError(f"No user found for email {email}")

    membership = await session.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.status == MembershipStatus.active,
        )
    )
    if not membership:
        membership = await session.scalar(select(OrgMembership).where(OrgMembership.user_id == user.id))
    if not membership:
        raise ValueError(f"No org membership found for user {email}")

    return membership.tenant_id, user.id


async def get_chat_model_slug(session: AsyncSession, tenant_id: UUID, override_slug: str | None) -> str:
    if override_slug:
        return override_slug

    tenant_priority = case((ModelRegistry.tenant_id == tenant_id, 1), else_=0).desc()
    binding_priority = case((ModelProviderBinding.tenant_id == tenant_id, 1), else_=0).desc()

    stmt = (
        select(ModelRegistry.slug)
        .join(ModelProviderBinding, ModelProviderBinding.model_id == ModelRegistry.id)
        .where(
            ModelRegistry.is_active == True,
            ModelRegistry.status == ModelStatus.ACTIVE,
            ModelRegistry.capability_type == ModelCapabilityType.CHAT,
            ModelProviderBinding.is_enabled == True,
            or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None)),
            or_(ModelProviderBinding.tenant_id == tenant_id, ModelProviderBinding.tenant_id.is_(None)),
        )
        .order_by(tenant_priority, binding_priority, ModelRegistry.updated_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        raise ValueError("No active chat model found for tenant.")
    return row[0]


async def upsert_tool(
    session: AsyncSession,
    tenant_id: UUID,
    slug: str,
    name: str,
    description: str,
    schema: dict,
    execution: dict,
) -> ToolRegistry:
    existing = await session.scalar(select(ToolRegistry).where(ToolRegistry.slug == slug))
    config_schema = {"implementation": {"type": "internal"}, "execution": execution}

    if existing:
        if existing.tenant_id != tenant_id:
            raise ValueError(f"Tool slug {slug} already exists for a different tenant.")
        existing.name = name
        existing.description = description
        existing.schema = schema
        existing.config_schema = config_schema
        existing.status = ToolStatus.PUBLISHED
        existing.implementation_type = ToolImplementationType.INTERNAL
        existing.is_active = True
        existing.is_system = False
        await session.commit()
        await session.refresh(existing)
        return existing

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=description,
        scope=ToolDefinitionScope.TENANT,
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.INTERNAL,
        config_schema=config_schema,
        schema=schema,
        is_active=True,
        is_system=False,
    )
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def upsert_agent(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    name: str,
    slug: str,
    description: str,
    graph: dict,
) -> Agent:
    existing = await session.scalar(select(Agent).where(Agent.slug == slug, Agent.tenant_id == tenant_id))
    service = AgentService(db=session, tenant_id=tenant_id)

    if existing:
        return await service.update_agent(
            existing.id,
            UpdateAgentData(
                name=name,
                description=description,
                graph_definition=graph,
            ),
        )

    return await service.create_agent(
        CreateAgentData(
            name=name,
            slug=slug,
            description=description,
            graph_definition=graph,
        ),
        user_id=user_id,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create or अपडेट a support triage agent that uses tool loop features.")
    parser.add_argument("--email", help="User email to resolve tenant")
    parser.add_argument("--tenant-id", help="Tenant ID (UUID)")
    parser.add_argument("--user-id", help="User ID (UUID)")
    parser.add_argument("--agent-slug", default="usecase-support-triage", help="Agent slug")
    parser.add_argument("--tool-prefix", default="usecase-support", help="Prefix for tool slugs")
    parser.add_argument("--chat-model-slug", help="Override chat model slug")
    args = parser.parse_args()

    env_email = _env("AGENT_SEED_EMAIL", "TEST_TENANT_EMAIL")
    env_tenant_id = _env("AGENT_SEED_TENANT_ID", "TEST_TENANT_ID")
    env_user_id = _env("AGENT_SEED_USER_ID", "TEST_USER_ID")
    env_chat_model_slug = _env("AGENT_CHAT_MODEL_SLUG", "TEST_CHAT_MODEL_SLUG")

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        tenant_id, user_id = await resolve_tenant_and_user(
            session,
            args.email or env_email,
            args.tenant_id or env_tenant_id,
            args.user_id or env_user_id,
        )

        chat_model = await get_chat_model_slug(session, tenant_id, args.chat_model_slug or env_chat_model_slug)

        lookup_schema = {
            "input": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "customer_email": {"type": "string"},
                },
                "required": ["ticket_id"],
            }
        }
        policy_schema = {
            "input": {
                "type": "object",
                "properties": {
                    "policy_type": {"type": "string"},
                    "region": {"type": "string"},
                },
                "required": ["policy_type"],
            }
        }
        risk_schema = {
            "input": {
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string"},
                    "days_active": {"type": "integer"},
                },
            }
        }
        case_schema = {
            "input": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "priority": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["ticket_id", "priority"],
            }
        }
        notify_schema = {
            "input": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["channel", "message"],
            }
        }

        prefix = args.tool_prefix
        order_lookup = await upsert_tool(
            session,
            tenant_id,
            f"{prefix}-order-lookup",
            "Order Lookup",
            "Fetches order and shipment status.",
            lookup_schema,
            {"is_pure": True, "concurrency_group": "lookup", "max_concurrency": 2},
        )
        policy_lookup = await upsert_tool(
            session,
            tenant_id,
            f"{prefix}-policy-lookup",
            "Policy Lookup",
            "Fetches refund/return policy details.",
            policy_schema,
            {"is_pure": True, "concurrency_group": "policy", "max_concurrency": 1},
        )
        risk_lookup = await upsert_tool(
            session,
            tenant_id,
            f"{prefix}-risk-lookup",
            "Customer Risk Check",
            "Checks account risk and prior disputes.",
            risk_schema,
            {"is_pure": True, "concurrency_group": "risk", "max_concurrency": 1},
        )
        case_create = await upsert_tool(
            session,
            tenant_id,
            f"{prefix}-case-create",
            "Create Support Case",
            "Creates a support case in the CRM.",
            case_schema,
            {"is_pure": False, "concurrency_group": "write", "max_concurrency": 1, "timeout_s": 10},
        )
        notify_tool = await upsert_tool(
            session,
            tenant_id,
            f"{prefix}-notify",
            "Notify Customer",
            "Sends a customer notification.",
            notify_schema,
            {"is_pure": True, "concurrency_group": "notify", "max_concurrency": 1},
        )

        instructions = (
            "You are a support triage agent. Use the bound tools to resolve issues.\n"
            "Step 1: Call the tools Order Lookup, Policy Lookup, and Customer Risk Check in a single response.\n"
            "Step 2: After tool results arrive, call Create Support Case with a priority and summary.\n"
            "Step 3: After the case is created, reply with ONLY a JSON object like:\n"
            "{\n"
            "  \"channel\": \"email\",\n"
            "  \"message\": \"...\"\n"
            "}\n"
        )

        graph = graph_def(
            [
                node_def("start", "start"),
                node_def(
                    "triage_agent",
                    "agent",
                    {
                        "name": "Support Triage Agent",
                        "model_id": chat_model,
                        "instructions": instructions,
                        "include_chat_history": True,
                        "output_format": "text",
                        "tools": [
                            str(order_lookup.id),
                            str(policy_lookup.id),
                            str(risk_lookup.id),
                            str(case_create.id),
                        ],
                        "tool_execution_mode": "parallel_safe",
                        "max_parallel_tools": 2,
                        "tool_timeout_s": 10,
                        "max_tool_iterations": 3,
                        "write_output_to_context": True,
                        "temperature": 0,
                    },
                ),
                node_def(
                    "notify_customer",
                    "tool",
                    {
                        "tool_id": str(notify_tool.id),
                        "input_source": "last_agent_output",
                    },
                ),
                node_def("end", "end", {"output_message": "done"}),
            ],
            [
                edge_def("e1", "start", "triage_agent"),
                edge_def("e2", "triage_agent", "notify_customer"),
                edge_def("e3", "notify_customer", "end"),
            ],
        )

        agent = await upsert_agent(
            session,
            tenant_id,
            user_id,
            "Support Triage Orchestrator",
            args.agent_slug,
            "Triage support requests using parallel tool calls and multi-step tool loops.",
            graph,
        )

        print("Created/updated agent:")
        print(f"- id: {agent.id}")
        print(f"- slug: {agent.slug}")
        print(f"- tenant_id: {agent.tenant_id}")


if __name__ == "__main__":
    asyncio.run(main())

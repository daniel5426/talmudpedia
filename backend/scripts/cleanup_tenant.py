import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.db.postgres.engine import engine
from app.db.postgres.models.identity import User, OrgMembership, OrgUnit, OrgInvite
from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, AgentVersion
from app.db.postgres.models.chat import Chat, Message
from app.db.postgres.models.rag import (
    KnowledgeStore,
    RAGPipeline,
    VisualPipeline,
    ExecutablePipeline,
    PipelineJob,
    PipelineStepExecution,
)
from app.db.postgres.models.registry import (
    ToolRegistry,
    ToolVersion,
    ModelRegistry,
    ModelProviderBinding,
    ProviderConfig,
)
from app.db.postgres.models.operators import CustomOperator
from app.db.postgres.models.rbac import Role, RolePermission, RoleAssignment
from app.db.postgres.models.audit import AuditLog


async def resolve_tenant_id(session: AsyncSession, email: str | None, tenant_id: str | None) -> UUID:
    if tenant_id:
        return UUID(tenant_id)
    if not email:
        raise ValueError("Provide --email or --tenant-id.")

    user = await session.scalar(select(User).where(User.email == email))
    if not user:
        raise ValueError(f"No user found for email {email}")

    membership = await session.scalar(
        select(OrgMembership).where(OrgMembership.user_id == user.id)
    )
    if not membership:
        raise ValueError(f"No org membership found for user {email}")

    return membership.tenant_id


async def count_where(session: AsyncSession, stmt):
    result = await session.execute(stmt)
    return result.scalar_one()


async def main():
    parser = argparse.ArgumentParser(description="Cleanup all tenant-scoped data.")
    parser.add_argument("--email", help="User email to resolve tenant")
    parser.add_argument("--tenant-id", help="Tenant ID (UUID)")
    parser.add_argument("--confirm", action="store_true", help="Actually delete rows")
    args = parser.parse_args()

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        tenant_id = await resolve_tenant_id(session, args.email, args.tenant_id)

        run_ids = select(AgentRun.id).where(AgentRun.tenant_id == tenant_id)
        agent_ids = select(Agent.id).where(Agent.tenant_id == tenant_id)
        chat_ids = select(Chat.id).where(Chat.tenant_id == tenant_id)
        tool_ids = select(ToolRegistry.id).where(ToolRegistry.tenant_id == tenant_id)
        model_ids = select(ModelRegistry.id).where(ModelRegistry.tenant_id == tenant_id)
        role_ids = select(Role.id).where(Role.tenant_id == tenant_id)

        counts = [
            ("agent_traces", await count_where(session, select(func.count()).select_from(AgentTrace).where(AgentTrace.run_id.in_(run_ids)))),
            ("agent_runs", await count_where(session, select(func.count()).select_from(AgentRun).where(AgentRun.tenant_id == tenant_id))),
            ("agent_versions", await count_where(session, select(func.count()).select_from(AgentVersion).where(AgentVersion.agent_id.in_(agent_ids)))),
            ("agents", await count_where(session, select(func.count()).select_from(Agent).where(Agent.tenant_id == tenant_id))),
            ("messages", await count_where(session, select(func.count()).select_from(Message).where(Message.chat_id.in_(chat_ids)))),
            ("chats", await count_where(session, select(func.count()).select_from(Chat).where(Chat.tenant_id == tenant_id))),
            ("pipeline_step_executions", await count_where(session, select(func.count()).select_from(PipelineStepExecution).where(PipelineStepExecution.tenant_id == tenant_id))),
            ("pipeline_jobs", await count_where(session, select(func.count()).select_from(PipelineJob).where(PipelineJob.tenant_id == tenant_id))),
            ("executable_pipelines", await count_where(session, select(func.count()).select_from(ExecutablePipeline).where(ExecutablePipeline.tenant_id == tenant_id))),
            ("visual_pipelines", await count_where(session, select(func.count()).select_from(VisualPipeline).where(VisualPipeline.tenant_id == tenant_id))),
            ("rag_pipelines", await count_where(session, select(func.count()).select_from(RAGPipeline).where(RAGPipeline.tenant_id == tenant_id))),
            ("knowledge_stores", await count_where(session, select(func.count()).select_from(KnowledgeStore).where(KnowledgeStore.tenant_id == tenant_id))),
            ("tool_versions", await count_where(session, select(func.count()).select_from(ToolVersion).where(ToolVersion.tool_id.in_(tool_ids)))),
            ("tools", await count_where(session, select(func.count()).select_from(ToolRegistry).where(ToolRegistry.tenant_id == tenant_id))),
            ("model_provider_bindings", await count_where(session, select(func.count()).select_from(ModelProviderBinding).where(ModelProviderBinding.model_id.in_(model_ids)))),
            ("models", await count_where(session, select(func.count()).select_from(ModelRegistry).where(ModelRegistry.tenant_id == tenant_id))),
            ("provider_configs", await count_where(session, select(func.count()).select_from(ProviderConfig).where(ProviderConfig.tenant_id == tenant_id))),
            ("custom_operators", await count_where(session, select(func.count()).select_from(CustomOperator).where(CustomOperator.tenant_id == tenant_id))),
            ("role_permissions", await count_where(session, select(func.count()).select_from(RolePermission).where(RolePermission.role_id.in_(role_ids)))),
            ("role_assignments", await count_where(session, select(func.count()).select_from(RoleAssignment).where(RoleAssignment.tenant_id == tenant_id))),
            ("roles", await count_where(session, select(func.count()).select_from(Role).where(Role.tenant_id == tenant_id))),
            ("audit_logs", await count_where(session, select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant_id))),
            ("org_invites", await count_where(session, select(func.count()).select_from(OrgInvite).where(OrgInvite.tenant_id == tenant_id))),
            ("org_memberships", await count_where(session, select(func.count()).select_from(OrgMembership).where(OrgMembership.tenant_id == tenant_id))),
            ("org_units", await count_where(session, select(func.count()).select_from(OrgUnit).where(OrgUnit.tenant_id == tenant_id))),
        ]

        print(f"Tenant cleanup summary for tenant_id={tenant_id}")
        for name, count in counts:
            print(f"- {name}: {count}")

        if not args.confirm:
            print("Dry run only. Re-run with --confirm to delete.")
            return

        await session.execute(delete(AgentTrace).where(AgentTrace.run_id.in_(run_ids)))
        await session.execute(delete(AgentRun).where(AgentRun.tenant_id == tenant_id))
        await session.execute(delete(AgentVersion).where(AgentVersion.agent_id.in_(agent_ids)))
        await session.execute(delete(Agent).where(Agent.tenant_id == tenant_id))

        await session.execute(delete(Message).where(Message.chat_id.in_(chat_ids)))
        await session.execute(delete(Chat).where(Chat.tenant_id == tenant_id))

        await session.execute(delete(PipelineStepExecution).where(PipelineStepExecution.tenant_id == tenant_id))
        await session.execute(delete(PipelineJob).where(PipelineJob.tenant_id == tenant_id))
        await session.execute(delete(ExecutablePipeline).where(ExecutablePipeline.tenant_id == tenant_id))
        await session.execute(delete(VisualPipeline).where(VisualPipeline.tenant_id == tenant_id))
        await session.execute(delete(RAGPipeline).where(RAGPipeline.tenant_id == tenant_id))
        await session.execute(delete(KnowledgeStore).where(KnowledgeStore.tenant_id == tenant_id))

        await session.execute(delete(ToolVersion).where(ToolVersion.tool_id.in_(tool_ids)))
        await session.execute(delete(ToolRegistry).where(ToolRegistry.tenant_id == tenant_id))
        await session.execute(delete(ModelProviderBinding).where(ModelProviderBinding.model_id.in_(model_ids)))
        await session.execute(delete(ModelRegistry).where(ModelRegistry.tenant_id == tenant_id))
        await session.execute(delete(ProviderConfig).where(ProviderConfig.tenant_id == tenant_id))
        await session.execute(delete(CustomOperator).where(CustomOperator.tenant_id == tenant_id))

        await session.execute(delete(RolePermission).where(RolePermission.role_id.in_(role_ids)))
        await session.execute(delete(RoleAssignment).where(RoleAssignment.tenant_id == tenant_id))
        await session.execute(delete(Role).where(Role.tenant_id == tenant_id))
        await session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))

        await session.execute(delete(OrgInvite).where(OrgInvite.tenant_id == tenant_id))
        await session.execute(delete(OrgMembership).where(OrgMembership.tenant_id == tenant_id))
        await session.execute(delete(OrgUnit).where(OrgUnit.tenant_id == tenant_id))

        await session.commit()
        print("Tenant cleanup completed.")


if __name__ == "__main__":
    asyncio.run(main())

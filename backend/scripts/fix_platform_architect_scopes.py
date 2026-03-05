#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text

from app.core.scope_registry import PLATFORM_ARCHITECT_SCOPE_PROFILE_V1, normalize_scope_list
from app.db.postgres.engine import sessionmaker as async_sessionmaker
from app.db.postgres.models.security import (
    WorkloadPolicyStatus,
    WorkloadPrincipalType,
    WorkloadPrincipalBinding,
    WorkloadResourceType,
    WorkloadScopePolicy,
)
from app.services.workload_identity_service import WorkloadIdentityService


async def _agents_table_columns(db) -> set[str]:
    res = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'agents'
            """
        )
    )
    return {str(row[0]) for row in res.all()}


async def _resolve_architect_agent(db, *, tenant_id: UUID | None, agent_id: UUID | None) -> tuple[UUID, UUID, str]:
    if agent_id is not None:
        res = await db.execute(
            text(
                """
                SELECT id, tenant_id, slug
                FROM agents
                WHERE id = CAST(:agent_id AS uuid)
                LIMIT 1
                """
            ),
            {"agent_id": str(agent_id)},
        )
        row = res.first()
        if row is None:
            raise RuntimeError(f"Agent not found by id: {agent_id}")
        return UUID(str(row[0])), UUID(str(row[1])), str(row[2])

    query = """
        SELECT id, tenant_id, slug
        FROM agents
        WHERE slug = 'platform-architect'
    """
    params: dict[str, str] = {}
    if tenant_id is not None:
        query += " AND tenant_id = CAST(:tenant_id AS uuid)"
        params["tenant_id"] = str(tenant_id)
    query += " ORDER BY created_at ASC LIMIT 1"
    res = await db.execute(text(query), params)
    row = res.first()
    if row is None:
        raise RuntimeError("platform-architect agent not found")
    return UUID(str(row[0])), UUID(str(row[1])), str(row[2])


async def _apply_fix(*, tenant_id: UUID | None, agent_id: UUID | None, dry_run: bool) -> int:
    target_scopes = normalize_scope_list(list(PLATFORM_ARCHITECT_SCOPE_PROFILE_V1))
    target_scope_set = set(target_scopes)

    async with async_sessionmaker() as db:
        agents_cols = await _agents_table_columns(db)
        agent_uuid, resolved_tenant_id, agent_slug = await _resolve_architect_agent(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
        effective_tenant_id = tenant_id or resolved_tenant_id

        print(f"tenant_id={effective_tenant_id}")
        print(f"agent_id={agent_uuid}")
        print(f"agent_slug={agent_slug}")
        print(f"target_scope_count={len(target_scopes)}")

        identity = WorkloadIdentityService(db)
        principal = await identity.get_bound_principal(
            tenant_id=effective_tenant_id,
            resource_type=WorkloadResourceType.AGENT,
            resource_id=str(agent_uuid),
        )
        if principal is None:
            principal = await identity.ensure_principal(
                tenant_id=effective_tenant_id,
                slug=f"agent:{agent_slug}",
                name=f"Agent Workload ({agent_slug})",
                principal_type=WorkloadPrincipalType.AGENT,
                created_by=None,
                requested_scopes=target_scopes,
                auto_approve_system=False,
            )
            await identity.ensure_binding(
                tenant_id=effective_tenant_id,
                principal_id=principal.id,
                resource_type=WorkloadResourceType.AGENT,
                resource_id=str(agent_uuid),
            )
            print(f"principal_created: {principal.id}")
        else:
            print(f"principal_existing: {principal.id}")
            bind_res = await db.execute(
                select(WorkloadPrincipalBinding).where(
                    WorkloadPrincipalBinding.tenant_id == effective_tenant_id,
                    WorkloadPrincipalBinding.principal_id == principal.id,
                    WorkloadPrincipalBinding.resource_type == WorkloadResourceType.AGENT,
                    WorkloadPrincipalBinding.resource_id == str(agent_uuid),
                )
            )
            if bind_res.scalars().first() is None:
                await identity.ensure_binding(
                    tenant_id=effective_tenant_id,
                    principal_id=principal.id,
                    resource_type=WorkloadResourceType.AGENT,
                    resource_id=str(agent_uuid),
                )
                print("binding_created: true")
            else:
                print("binding_created: false")

        latest_policy = await identity.get_latest_policy(principal.id)
        if latest_policy is None:
            next_version = 1
            current_status = "none"
            current_scopes: set[str] = set()
        else:
            next_version = int(latest_policy.version or 0) + 1
            current_status = latest_policy.status.value
            current_scopes = set(latest_policy.approved_scopes or [])
        missing_from_current = sorted(target_scope_set - current_scopes)
        print(f"current_policy_status={current_status}")
        print(f"current_scope_count={len(current_scopes)}")
        print(f"missing_scope_count={len(missing_from_current)}")
        if missing_from_current:
            print(f"missing_scopes={missing_from_current}")

        if dry_run:
            await db.rollback()
            print("dry_run=true (no changes committed)")
            return 0

        if "workload_scope_profile" in agents_cols:
            await db.execute(
                text(
                    """
                    UPDATE agents
                    SET workload_scope_profile = 'platform_architect_v1'
                    WHERE id = :agent_id
                    """
                ),
                {"agent_id": str(agent_uuid)},
            )
            print("profile_updated: true")
        else:
            print("profile_updated: skipped (column missing)")

        if "workload_scope_overrides" in agents_cols:
            await db.execute(
                text(
                    """
                    UPDATE agents
                    SET workload_scope_overrides = '[]'::jsonb
                    WHERE id = :agent_id
                    """
                ),
                {"agent_id": str(agent_uuid)},
            )
            print("overrides_cleared: true")
        else:
            print("overrides_cleared: skipped (column missing)")

        policy = WorkloadScopePolicy(
            principal_id=principal.id,
            requested_scopes=target_scopes,
            approved_scopes=target_scopes,
            status=WorkloadPolicyStatus.APPROVED,
            approved_by=None,
            approved_at=datetime.now(timezone.utc),
            version=next_version,
        )
        db.add(policy)
        await db.commit()
        print(f"policy_written_version={next_version}")
        print("status=ok")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile and approve platform-architect workload scopes."
    )
    parser.add_argument("--tenant-id", help="Tenant UUID (optional if --agent-id is provided).")
    parser.add_argument("--agent-id", help="platform-architect agent UUID (optional).")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only.")
    args = parser.parse_args()

    parsed_tenant: UUID | None = None
    parsed_agent: UUID | None = None
    if args.tenant_id:
        parsed_tenant = UUID(str(args.tenant_id))
    if args.agent_id:
        parsed_agent = UUID(str(args.agent_id))

    return asyncio.run(
        _apply_fix(
            tenant_id=parsed_tenant,
            agent_id=parsed_agent,
            dry_run=bool(args.dry_run),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

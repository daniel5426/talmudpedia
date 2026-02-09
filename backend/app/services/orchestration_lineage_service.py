from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.orchestration import OrchestrationGroup, OrchestrationGroupMember


@dataclass
class LineageContext:
    root_run_id: UUID
    parent_run_id: UUID
    depth: int


class OrchestrationLineageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        return await self.db.get(AgentRun, run_id)

    async def derive_child_context(self, parent_run: AgentRun) -> LineageContext:
        root_run_id = parent_run.root_run_id or parent_run.id
        depth = int(parent_run.depth or 0) + 1
        return LineageContext(root_run_id=root_run_id, parent_run_id=parent_run.id, depth=depth)

    async def query_tree(self, run_id: UUID) -> dict[str, Any]:
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise ValueError("Run not found")

        root_run_id = run.root_run_id or run.id

        runs_res = await self.db.execute(
            select(AgentRun).where(AgentRun.root_run_id == root_run_id).order_by(AgentRun.created_at.asc())
        )
        runs = list(runs_res.scalars().all())

        if not any(r.id == root_run_id for r in runs):
            root_run = await self.db.get(AgentRun, root_run_id)
            if root_run is not None:
                runs.insert(0, root_run)

        groups_res = await self.db.execute(
            select(OrchestrationGroup).where(OrchestrationGroup.orchestrator_run_id.in_([r.id for r in runs] or [root_run_id]))
        )
        groups = list(groups_res.scalars().all())

        group_ids = [g.id for g in groups]
        members: list[OrchestrationGroupMember] = []
        if group_ids:
            members_res = await self.db.execute(
                select(OrchestrationGroupMember).where(OrchestrationGroupMember.group_id.in_(group_ids))
            )
            members = list(members_res.scalars().all())

        runs_by_id = {r.id: r for r in runs}
        child_map: dict[UUID, list[UUID]] = {}
        for item in runs:
            if item.parent_run_id is not None:
                child_map.setdefault(item.parent_run_id, []).append(item.id)

        group_members_map: dict[UUID, list[dict[str, Any]]] = {}
        for member in members:
            group_members_map.setdefault(member.group_id, []).append(
                {
                    "id": str(member.id),
                    "run_id": str(member.run_id),
                    "ordinal": member.ordinal,
                    "status": member.status,
                }
            )

        groups_by_orchestrator: dict[UUID, list[dict[str, Any]]] = {}
        for group in groups:
            groups_by_orchestrator.setdefault(group.orchestrator_run_id, []).append(
                {
                    "group_id": str(group.id),
                    "status": group.status,
                    "failure_policy": group.failure_policy,
                    "join_mode": group.join_mode,
                    "quorum_threshold": group.quorum_threshold,
                    "timeout_s": group.timeout_s,
                    "parent_node_id": group.parent_node_id,
                    "members": group_members_map.get(group.id, []),
                }
            )

        def _serialize(node_id: UUID) -> dict[str, Any]:
            item = runs_by_id[node_id]
            return {
                "run_id": str(item.id),
                "agent_id": str(item.agent_id),
                "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                "depth": int(item.depth or 0),
                "parent_run_id": str(item.parent_run_id) if item.parent_run_id else None,
                "parent_node_id": item.parent_node_id,
                "spawn_key": item.spawn_key,
                "orchestration_group_id": str(item.orchestration_group_id) if item.orchestration_group_id else None,
                "created_at": item.created_at,
                "children": [_serialize(child_id) for child_id in child_map.get(node_id, [])],
                "groups": groups_by_orchestrator.get(node_id, []),
            }

        return {
            "root_run_id": str(root_run_id),
            "tree": _serialize(root_run_id),
            "node_count": len(runs_by_id),
        }

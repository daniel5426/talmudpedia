from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    ArtifactCodingRunSnapshot,
    ArtifactCodingSession,
    ArtifactCodingSharedDraft,
)


class ArtifactCodingSharedDraftService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_for_artifact(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        artifact_id: UUID,
    ) -> ArtifactCodingSharedDraft | None:
        stmt = select(ArtifactCodingSharedDraft).where(
            ArtifactCodingSharedDraft.organization_id == organization_id,
            ArtifactCodingSharedDraft.project_id == project_id,
        )
        stmt = stmt.where(
            or_(
                ArtifactCodingSharedDraft.artifact_id == artifact_id,
                ArtifactCodingSharedDraft.linked_artifact_id == artifact_id,
            )
        )
        result = await self.db.execute(stmt.order_by(desc(ArtifactCodingSharedDraft.updated_at)).limit(1))
        return result.scalar_one_or_none()

    async def _get_for_draft_key(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        draft_key: str,
    ) -> ArtifactCodingSharedDraft | None:
        result = await self.db.execute(
            select(ArtifactCodingSharedDraft)
            .where(
                ArtifactCodingSharedDraft.organization_id == organization_id,
                ArtifactCodingSharedDraft.project_id == project_id,
                ArtifactCodingSharedDraft.draft_key == draft_key,
            )
            .order_by(desc(ArtifactCodingSharedDraft.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_for_scope(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSharedDraft | None:
        if artifact_id is not None and draft_key:
            artifact_shared = await self._get_for_artifact(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact_id,
            )
            draft_shared = await self._get_for_draft_key(
                organization_id=organization_id,
                project_id=project_id,
                draft_key=draft_key,
            )
            return draft_shared or artifact_shared
        if artifact_id is not None:
            return await self._get_for_artifact(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact_id,
            )
        if draft_key:
            return await self._get_for_draft_key(
                organization_id=organization_id,
                project_id=project_id,
                draft_key=draft_key,
            )
        return None

    async def get_or_create_for_scope(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        artifact_id: UUID | None,
        draft_key: str | None,
        initial_snapshot: dict[str, Any] | None = None,
    ) -> ArtifactCodingSharedDraft:
        shared = await self.get_for_scope(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            draft_key=draft_key,
        )
        if shared is not None:
            return shared

        shared = ArtifactCodingSharedDraft(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            draft_key=draft_key,
            linked_artifact_id=artifact_id,
            linked_at=datetime.now(timezone.utc) if artifact_id is not None else None,
            working_draft_snapshot=dict(initial_snapshot or {}),
        )
        self.db.add(shared)
        await self.db.flush()
        return shared

    async def resolve_for_session(
        self,
        *,
        session: ArtifactCodingSession,
    ) -> ArtifactCodingSharedDraft:
        if session.shared_draft_id is not None:
            shared = await self.db.get(ArtifactCodingSharedDraft, session.shared_draft_id)
            if shared is None or shared.organization_id != session.organization_id:
                raise ValueError("Artifact coding shared draft not found")
            return shared

        return await self.get_or_create_for_scope(
            organization_id=session.organization_id,
            project_id=session.project_id,
            artifact_id=session.artifact_id or session.linked_artifact_id,
            draft_key=session.draft_key,
            initial_snapshot=None,
        )

    async def update_snapshot(
        self,
        *,
        shared_draft: ArtifactCodingSharedDraft,
        draft_snapshot: dict[str, Any],
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSharedDraft:
        shared_draft.working_draft_snapshot = dict(draft_snapshot or {})
        if artifact_id is not None:
            shared_draft.artifact_id = artifact_id
            shared_draft.linked_artifact_id = artifact_id
            shared_draft.linked_at = shared_draft.linked_at or datetime.now(timezone.utc)
        if draft_key:
            shared_draft.draft_key = draft_key
        shared_draft.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return shared_draft

    async def link_scope_to_artifact(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        draft_key: str,
        artifact_id: UUID,
    ) -> None:
        if not draft_key:
            return
        shared = await self.get_for_scope(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            draft_key=draft_key,
        )
        if shared is None:
            return
        shared.artifact_id = artifact_id
        shared.linked_artifact_id = artifact_id
        shared.linked_at = shared.linked_at or datetime.now(timezone.utc)
        shared.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def set_last_test_run(
        self,
        *,
        shared_draft: ArtifactCodingSharedDraft,
        test_run_id: UUID | None,
    ) -> None:
        shared_draft.last_test_run_id = test_run_id
        shared_draft.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def set_last_run(
        self,
        *,
        shared_draft: ArtifactCodingSharedDraft,
        run_id: UUID | None,
    ) -> None:
        shared_draft.last_run_id = run_id
        shared_draft.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def create_run_snapshot(
        self,
        *,
        shared_draft: ArtifactCodingSharedDraft,
        run_id: UUID,
        session_id: UUID | None,
        snapshot_kind: str = "pre_run",
    ) -> ArtifactCodingRunSnapshot:
        snapshot = ArtifactCodingRunSnapshot(
            organization_id=shared_draft.organization_id,
            project_id=shared_draft.project_id,
            shared_draft_id=shared_draft.id,
            run_id=run_id,
            session_id=session_id,
            artifact_id=shared_draft.artifact_id or shared_draft.linked_artifact_id,
            draft_key=shared_draft.draft_key,
            snapshot_kind=snapshot_kind,
            draft_snapshot=deepcopy(shared_draft.working_draft_snapshot or {}),
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def get_run_snapshot(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        run_id: UUID,
        snapshot_kind: str = "pre_run",
    ) -> ArtifactCodingRunSnapshot | None:
        result = await self.db.execute(
            select(ArtifactCodingRunSnapshot).where(
                ArtifactCodingRunSnapshot.organization_id == organization_id,
                ArtifactCodingRunSnapshot.project_id == project_id,
                ArtifactCodingRunSnapshot.run_id == run_id,
                ArtifactCodingRunSnapshot.snapshot_kind == snapshot_kind,
            )
        )
        return result.scalar_one_or_none()

    async def restore_run_snapshot(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        run_id: UUID,
        snapshot_kind: str = "pre_run",
    ) -> ArtifactCodingSharedDraft:
        snapshot = await self.get_run_snapshot(
            organization_id=organization_id,
            project_id=project_id,
            run_id=run_id,
            snapshot_kind=snapshot_kind,
        )
        if snapshot is None:
            raise ValueError("Artifact coding run snapshot not found")
        shared_draft = await self.db.get(ArtifactCodingSharedDraft, snapshot.shared_draft_id)
        if shared_draft is None or shared_draft.organization_id != organization_id:
            raise ValueError("Artifact coding shared draft not found")
        shared_draft.working_draft_snapshot = deepcopy(snapshot.draft_snapshot or {})
        shared_draft.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return shared_draft

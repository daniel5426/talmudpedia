from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select, update
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
        tenant_id: UUID,
        artifact_id: UUID,
    ) -> ArtifactCodingSharedDraft | None:
        stmt = select(ArtifactCodingSharedDraft).where(ArtifactCodingSharedDraft.tenant_id == tenant_id)
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
        tenant_id: UUID,
        draft_key: str,
    ) -> ArtifactCodingSharedDraft | None:
        result = await self.db.execute(
            select(ArtifactCodingSharedDraft)
            .where(
                ArtifactCodingSharedDraft.tenant_id == tenant_id,
                ArtifactCodingSharedDraft.draft_key == draft_key,
            )
            .order_by(desc(ArtifactCodingSharedDraft.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _merge_shared_drafts(
        self,
        *,
        primary: ArtifactCodingSharedDraft,
        secondary: ArtifactCodingSharedDraft,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSharedDraft:
        if primary.id == secondary.id:
            return primary
        primary_snapshot = dict(primary.working_draft_snapshot or {})
        secondary_snapshot = dict(secondary.working_draft_snapshot or {})
        primary_updated_at = primary.updated_at
        secondary_updated_at = secondary.updated_at
        target_artifact_id = artifact_id or primary.artifact_id or secondary.artifact_id
        target_linked_artifact_id = artifact_id or primary.linked_artifact_id or secondary.linked_artifact_id
        target_draft_key = draft_key or primary.draft_key or secondary.draft_key
        target_linked_at = primary.linked_at or secondary.linked_at or (datetime.now(timezone.utc) if artifact_id is not None else None)
        target_last_run_id = primary.last_run_id or secondary.last_run_id
        target_last_test_run_id = primary.last_test_run_id or secondary.last_test_run_id

        await self.db.execute(
            update(ArtifactCodingRunSnapshot)
            .where(ArtifactCodingRunSnapshot.shared_draft_id == secondary.id)
            .values(shared_draft_id=primary.id)
        )
        secondary.artifact_id = None
        secondary.linked_artifact_id = None
        secondary.draft_key = None
        await self.db.flush()

        if not primary_snapshot and secondary_snapshot:
            primary.working_draft_snapshot = secondary_snapshot
        elif secondary_updated_at and (primary_updated_at is None or secondary_updated_at > primary_updated_at):
            primary.working_draft_snapshot = secondary_snapshot or primary_snapshot
        primary.artifact_id = target_artifact_id
        primary.linked_artifact_id = target_linked_artifact_id
        primary.linked_at = target_linked_at
        primary.draft_key = target_draft_key
        primary.last_run_id = target_last_run_id
        primary.last_test_run_id = target_last_test_run_id
        primary.updated_at = datetime.now(timezone.utc)
        await self.db.delete(secondary)
        await self.db.flush()
        return primary

    async def get_for_scope(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSharedDraft | None:
        if artifact_id is not None and draft_key:
            artifact_shared = await self._get_for_artifact(tenant_id=tenant_id, artifact_id=artifact_id)
            draft_shared = await self._get_for_draft_key(tenant_id=tenant_id, draft_key=draft_key)
            if artifact_shared is not None and draft_shared is not None and artifact_shared.id != draft_shared.id:
                return await self._merge_shared_drafts(
                    primary=draft_shared,
                    secondary=artifact_shared,
                    artifact_id=artifact_id,
                    draft_key=draft_key,
                )
            return draft_shared or artifact_shared
        if artifact_id is not None:
            return await self._get_for_artifact(tenant_id=tenant_id, artifact_id=artifact_id)
        if draft_key:
            return await self._get_for_draft_key(tenant_id=tenant_id, draft_key=draft_key)
        return None

    async def get_or_create_for_scope(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID | None,
        draft_key: str | None,
        initial_snapshot: dict[str, Any] | None = None,
    ) -> ArtifactCodingSharedDraft:
        shared = await self.get_for_scope(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            draft_key=draft_key,
        )
        if shared is not None:
            return shared

        shared = ArtifactCodingSharedDraft(
            tenant_id=tenant_id,
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
        return await self.get_or_create_for_scope(
            tenant_id=session.tenant_id,
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
        tenant_id: UUID,
        draft_key: str,
        artifact_id: UUID,
    ) -> None:
        if not draft_key:
            return
        shared = await self.get_for_scope(tenant_id=tenant_id, artifact_id=artifact_id, draft_key=draft_key)
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
            tenant_id=shared_draft.tenant_id,
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
        tenant_id: UUID,
        run_id: UUID,
        snapshot_kind: str = "pre_run",
    ) -> ArtifactCodingRunSnapshot | None:
        result = await self.db.execute(
            select(ArtifactCodingRunSnapshot).where(
                ArtifactCodingRunSnapshot.tenant_id == tenant_id,
                ArtifactCodingRunSnapshot.run_id == run_id,
                ArtifactCodingRunSnapshot.snapshot_kind == snapshot_kind,
            )
        )
        return result.scalar_one_or_none()

    async def restore_run_snapshot(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        snapshot_kind: str = "pre_run",
    ) -> ArtifactCodingSharedDraft:
        snapshot = await self.get_run_snapshot(
            tenant_id=tenant_id,
            run_id=run_id,
            snapshot_kind=snapshot_kind,
        )
        if snapshot is None:
            raise ValueError("Artifact coding run snapshot not found")
        shared_draft = await self.db.get(ArtifactCodingSharedDraft, snapshot.shared_draft_id)
        if shared_draft is None or shared_draft.tenant_id != tenant_id:
            raise ValueError("Artifact coding shared draft not found")
        shared_draft.working_draft_snapshot = deepcopy(snapshot.draft_snapshot or {})
        shared_draft.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return shared_draft

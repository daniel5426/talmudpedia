from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_revision_store import PublishedAppRevisionStore


async def _next_version_seq(db: AsyncSession, *, app_id: UUID) -> int:
    result = await db.execute(
        select(func.max(PublishedAppRevision.version_seq)).where(
            PublishedAppRevision.published_app_id == app_id
        )
    )
    return int(result.scalar() or 0) + 1


async def create_app_version(
    db: AsyncSession,
    *,
    revision_id: Optional[UUID] = None,
    app: PublishedApp,
    kind: PublishedAppRevisionKind,
    template_key: str,
    entry_file: str,
    files: Dict[str, str],
    created_by: Optional[UUID],
    source_revision_id: Optional[UUID],
    origin_kind: str,
    origin_run_id: Optional[UUID] = None,
    restored_from_revision_id: Optional[UUID] = None,
    build_status: PublishedAppRevisionBuildStatus = PublishedAppRevisionBuildStatus.queued,
    build_seq: int = 0,
    build_error: Optional[str] = None,
    build_started_at: Optional[datetime] = None,
    build_finished_at: Optional[datetime] = None,
    dist_storage_prefix: Optional[str] = None,
    dist_manifest: Optional[Dict[str, Any]] = None,
    template_runtime: str = "vite_static",
    compiled_bundle: Optional[str] = None,
) -> PublishedAppRevision:
    normalized_files: Dict[str, str] = {
        str(path): str(content if isinstance(content, str) else str(content))
        for path, content in (files or {}).items()
        if isinstance(path, str) and str(path).strip()
    }
    revision_store = PublishedAppRevisionStore(db)
    manifest_json, bundle_hash = await revision_store.build_manifest_and_store_blobs(normalized_files)

    revision_kwargs: Dict[str, Any] = {}
    if revision_id is not None:
        revision_kwargs["id"] = revision_id

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=kind,
        template_key=template_key,
        entry_file=entry_file,
        files=normalized_files,
        manifest_json=manifest_json,
        build_status=build_status,
        build_seq=int(build_seq or 0),
        build_error=build_error,
        build_started_at=build_started_at,
        build_finished_at=build_finished_at,
        dist_storage_prefix=dist_storage_prefix,
        dist_manifest=dist_manifest,
        template_runtime=template_runtime,
        compiled_bundle=compiled_bundle,
        bundle_hash=bundle_hash,
        source_revision_id=source_revision_id,
        created_by=created_by,
        version_seq=await _next_version_seq(db, app_id=app.id),
        origin_kind=str(origin_kind or "unknown").strip() or "unknown",
        origin_run_id=origin_run_id,
        restored_from_revision_id=restored_from_revision_id,
        **revision_kwargs,
    )
    db.add(revision)
    await db.flush()
    return revision

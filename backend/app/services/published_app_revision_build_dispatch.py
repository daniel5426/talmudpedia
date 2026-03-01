from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
)

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def builder_auto_enqueue_enabled() -> bool:
    return _env_flag("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", False)


def mark_revision_build_enqueue_failed(
    *,
    revision: PublishedAppRevision,
    reason: str,
) -> None:
    normalized_reason = (reason or "").strip()
    if len(normalized_reason) > 4000:
        normalized_reason = f"{normalized_reason[:4000]}... [truncated]"
    revision.build_status = PublishedAppRevisionBuildStatus.failed
    revision.build_error = normalized_reason or "Build enqueue failed"
    revision.build_started_at = None
    revision.build_finished_at = datetime.now(timezone.utc)
    revision.dist_storage_prefix = None
    revision.dist_manifest = None


def enqueue_revision_build(
    *,
    revision: PublishedAppRevision,
    app: PublishedApp,
    build_kind: str,
) -> Optional[str]:
    if not builder_auto_enqueue_enabled():
        return (
            "Build automation is disabled (`APPS_BUILDER_BUILD_AUTOMATION_ENABLED=0`). "
            "Enable it and retry build."
        )

    try:
        from app.workers.tasks import build_published_app_revision_task
    except Exception as exc:
        return f"Build worker task import failed: {exc}"

    try:
        build_published_app_revision_task.delay(
            revision_id=str(revision.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            slug=app.slug,
            build_kind=build_kind,
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue published app build task",
            extra={
                "revision_id": str(revision.id),
                "app_id": str(app.id),
                "build_kind": build_kind,
                "error": str(exc),
            },
        )
        return f"Failed to enqueue build task: {exc}"
    return None

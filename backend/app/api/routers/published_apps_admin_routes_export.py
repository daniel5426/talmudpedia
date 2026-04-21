from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.published_app_export_service import PublishedAppExportService

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _get_app_for_tenant,
    _resolve_organization_admin_context,
)
from .published_apps_admin_shared import router


class ExportOptionsResponse(BaseModel):
    supported: bool
    ready: bool
    template_key: str
    source_kind: Optional[str] = None
    default_archive_name: str
    reason: Optional[str] = None


@router.get("/{app_id}/export/options", response_model=ExportOptionsResponse)
async def get_export_options(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    options = await PublishedAppExportService(db).resolve_options(app=app)
    return ExportOptionsResponse(**options.__dict__)


@router.post("/{app_id}/export/archive")
async def download_export_archive(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    try:
        archive = await PublishedAppExportService(db).build_archive(app=app)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = archive.to_zip_bytes()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive.filename}"',
            "X-Export-Source-Kind": archive.source_kind,
        },
    )

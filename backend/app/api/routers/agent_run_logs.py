from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.api.routers.agents import get_agent_context
from app.db.postgres.session import get_db
from app.services.runtime_surface import RuntimeRunControlContext, RuntimeSurfaceService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/runs/{run_id}/events", response_model=Dict[str, Any])
async def get_run_events(
    run_id: UUID,
    after_sequence: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=1000),
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    return await RuntimeSurfaceService(db).get_run_events(
        run_id=run_id,
        control=RuntimeRunControlContext(organization_id=context["organization_id"]),
        after_sequence=after_sequence,
        limit=limit,
    )

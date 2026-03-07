from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.api.routers.agents import get_agent_context
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/runs/{run_id}/events", response_model=Dict[str, Any])
async def get_run_events(
    run_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run.tenant_id) != str(context.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    events = await recorder.list_events(db, run_id)
    return {
        "run_id": str(run_id),
        "event_count": len(events),
        "events": events,
    }

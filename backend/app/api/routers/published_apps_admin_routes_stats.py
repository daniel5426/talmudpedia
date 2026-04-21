from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.published_app_analytics_service import PublishedAppAnalyticsService

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _get_app_for_tenant,
    _resolve_organization_admin_context,
)
from .published_apps_admin_shared import router


class PublishedAppStatsSeries(BaseModel):
    date: str
    value: float


class PublishedAppStatsSummaryResponse(BaseModel):
    app_id: str
    start_date: str
    end_date: str
    approximate: bool = False
    visits: int
    unique_visitors: int
    agent_runs: int
    failed_runs: int
    tokens: int
    threads: int
    app_accounts: int
    active_sessions: int
    visits_by_day: List[PublishedAppStatsSeries]
    runs_by_day: List[PublishedAppStatsSeries]
    tokens_by_day: List[PublishedAppStatsSeries]
    visit_surface_breakdown: Dict[str, int]
    visit_auth_state_breakdown: Dict[str, int]


class PublishedAppsStatsResponse(BaseModel):
    start_date: str
    end_date: str
    items: List[PublishedAppStatsSummaryResponse]


def _parse_iso_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(value.split("T")[0], "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if len(value) <= 10:
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed


def _resolve_period(days: int, start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if start_date or end_date:
        start = _parse_iso_datetime(start_date, end_of_day=False) if start_date else None
        end = _parse_iso_datetime(end_date, end_of_day=True) if end_date else None
        if start and not end:
            end = now
        if end and not start:
            start = end - timedelta(days=days)
    else:
        end = now
        start = end - timedelta(days=max(0, days - 1))
    if start is None or end is None:
        raise HTTPException(status_code=400, detail="Invalid date range")
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if end - start > timedelta(days=90):
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")
    return start, end


def _to_response(item) -> PublishedAppStatsSummaryResponse:
    return PublishedAppStatsSummaryResponse(
        app_id=item.app_id,
        start_date=item.start_date,
        end_date=item.end_date,
        approximate=item.approximate,
        visits=item.visits,
        unique_visitors=item.unique_visitors,
        agent_runs=item.agent_runs,
        failed_runs=item.failed_runs,
        tokens=item.tokens,
        threads=item.threads,
        app_accounts=item.app_accounts,
        active_sessions=item.active_sessions,
        visits_by_day=item.visits_by_day,
        runs_by_day=item.runs_by_day,
        tokens_by_day=item.tokens_by_day,
        visit_surface_breakdown=item.visit_surface_breakdown,
        visit_auth_state_breakdown=item.visit_auth_state_breakdown,
    )


@router.get("/stats", response_model=PublishedAppsStatsResponse)
async def list_published_app_stats(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    start, end = _resolve_period(days, start_date, end_date)
    service = PublishedAppAnalyticsService(db)
    items = await service.build_stats_for_tenant(
        organization_id=ctx["organization_id"],
        start=start,
        end=end,
    )
    return PublishedAppsStatsResponse(
        start_date=start.date().isoformat(),
        end_date=end.date().isoformat(),
        items=[_to_response(item) for item in items],
    )


@router.get("/{app_id}/stats", response_model=PublishedAppStatsSummaryResponse)
async def get_published_app_stats(
    app_id: UUID,
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    start, end = _resolve_period(days, start_date, end_date)
    service = PublishedAppAnalyticsService(db)
    items = await service.build_stats_for_tenant(
        organization_id=ctx["organization_id"],
        start=start,
        end=end,
        app_id=app_id,
    )
    if not items:
        raise HTTPException(status_code=404, detail="Published app not found")
    return _to_response(items[0])

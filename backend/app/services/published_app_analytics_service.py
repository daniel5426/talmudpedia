from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface
from app.db.postgres.models.published_app_analytics import (
    PublishedAppAnalyticsEvent,
    PublishedAppAnalyticsEventType,
    PublishedAppAnalyticsSurface,
)
from app.services.model_accounting import billable_total_tokens
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount, PublishedAppSession


VISITOR_COOKIE_NAME = (os.getenv("PUBLISHED_APP_VISITOR_COOKIE_NAME") or "published_app_visitor").strip() or "published_app_visitor"
VISIT_COOKIE_NAME = (os.getenv("PUBLISHED_APP_VISIT_COOKIE_NAME") or "published_app_visit").strip() or "published_app_visit"
VISIT_WINDOW_MINUTES = max(1, int((os.getenv("PUBLISHED_APP_VISIT_WINDOW_MINUTES") or "30").strip() or "30"))
VISITOR_COOKIE_MAX_AGE_SECONDS = max(86400, int((os.getenv("PUBLISHED_APP_VISITOR_COOKIE_MAX_AGE_SECONDS") or str(60 * 60 * 24 * 365)).strip() or str(60 * 60 * 24 * 365)))
CODING_AGENT_SURFACE = "published_app_coding_agent"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _date_label(value: datetime) -> str:
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.date().isoformat()


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass(slots=True)
class PublishedAppStatsSummary:
    app_id: str
    start_date: str
    end_date: str
    approximate: bool
    visits: int
    unique_visitors: int
    agent_runs: int
    failed_runs: int
    tokens: int
    threads: int
    app_accounts: int
    active_sessions: int
    visits_by_day: list[dict[str, Any]]
    runs_by_day: list[dict[str, Any]]
    tokens_by_day: list[dict[str, Any]]
    visit_surface_breakdown: dict[str, int]
    visit_auth_state_breakdown: dict[str, int]


class PublishedAppAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_ip_hash(*, request: Request) -> str | None:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        client_host = forwarded or (request.client.host if request.client else "")
        if not client_host:
            return None
        salt = (os.getenv("PUBLISHED_APP_ANALYTICS_SALT") or "").strip()
        digest = hashlib.sha256(f"{salt}:{client_host}".encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def _build_fallback_visitor_key(*, request: Request, app_id: UUID) -> str:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        client_host = forwarded or (request.client.host if request.client else "")
        user_agent = (request.headers.get("user-agent") or "").strip()
        salt = (os.getenv("PUBLISHED_APP_ANALYTICS_SALT") or "").strip()
        digest = hashlib.sha256(f"{salt}:{app_id}:{client_host}:{user_agent}".encode("utf-8")).hexdigest()
        return f"approx:{digest}"

    @staticmethod
    def _set_tracking_cookies(*, request: Request, response: Response, visitor_key: str, visit_key: str) -> None:
        secure = request.url.scheme == "https"
        response.set_cookie(
            key=VISITOR_COOKIE_NAME,
            value=visitor_key,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=VISITOR_COOKIE_MAX_AGE_SECONDS,
        )
        response.set_cookie(
            key=VISIT_COOKIE_NAME,
            value=visit_key,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=VISITOR_COOKIE_MAX_AGE_SECONDS,
        )

    async def record_bootstrap(
        self,
        *,
        request: Request,
        response: Response,
        app: PublishedApp,
        surface: PublishedAppAnalyticsSurface,
        app_account_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None:
        visitor_key = ""
        approximate = False
        if app_account_id is not None:
            visitor_key = f"app_account:{app_account_id}"
        else:
            visitor_key = str(request.cookies.get(VISITOR_COOKIE_NAME) or "").strip()
            if not visitor_key:
                if surface == PublishedAppAnalyticsSurface.external_runtime:
                    visitor_key = self._build_fallback_visitor_key(request=request, app_id=app.id)
                    approximate = True
                else:
                    visitor_key = uuid4().hex
        visit_key = str(request.cookies.get(VISIT_COOKIE_NAME) or "").strip()
        if not visit_key:
            visit_key = uuid4().hex

        now = _utc_now()
        visit_window_start = now - timedelta(minutes=VISIT_WINDOW_MINUTES)
        latest_visit_result = await self.db.execute(
            select(PublishedAppAnalyticsEvent)
            .where(
                and_(
                    PublishedAppAnalyticsEvent.published_app_id == app.id,
                    PublishedAppAnalyticsEvent.visitor_key == visitor_key,
                    PublishedAppAnalyticsEvent.event_type == PublishedAppAnalyticsEventType.visit_started,
                    PublishedAppAnalyticsEvent.occurred_at >= visit_window_start,
                )
            )
            .order_by(PublishedAppAnalyticsEvent.occurred_at.desc())
            .limit(1)
        )
        latest_visit = latest_visit_result.scalar_one_or_none()
        if latest_visit is not None:
            visit_key = latest_visit.visit_key
        else:
            visit_key = uuid4().hex

        metadata = {
            "approximate_visitor": approximate,
            "auth_state": "authenticated" if app_account_id else "anonymous",
        }
        common = dict(
            organization_id=app.organization_id,
            published_app_id=app.id,
            app_account_id=app_account_id,
            session_id=session_id,
            surface=surface,
            visitor_key=visitor_key,
            visit_key=visit_key,
            path=request.url.path,
            referer=(request.headers.get("referer") or "").strip() or None,
            user_agent=(request.headers.get("user-agent") or "").strip() or None,
            ip_hash=self._build_ip_hash(request=request),
            metadata_=metadata,
            occurred_at=now,
        )
        self.db.add(
            PublishedAppAnalyticsEvent(
                event_type=PublishedAppAnalyticsEventType.bootstrap_view,
                **common,
            )
        )
        if latest_visit is None:
            self.db.add(
                PublishedAppAnalyticsEvent(
                    event_type=PublishedAppAnalyticsEventType.visit_started,
                    **common,
                )
            )
        await self.db.commit()
        self._set_tracking_cookies(
            request=request,
            response=response,
            visitor_key=visitor_key,
            visit_key=visit_key,
        )

    async def build_stats_for_tenant(
        self,
        *,
        organization_id: UUID,
        start: datetime,
        end: datetime,
        app_id: UUID | None = None,
    ) -> list[PublishedAppStatsSummary]:
        apps_query = select(PublishedApp).where(PublishedApp.organization_id == organization_id).order_by(PublishedApp.updated_at.desc())
        if app_id is not None:
            apps_query = apps_query.where(PublishedApp.id == app_id)
        apps = list((await self.db.execute(apps_query)).scalars().all())
        if not apps:
            return []

        app_ids = [app.id for app in apps]
        analytics_events = list(
            (
                await self.db.execute(
                    select(PublishedAppAnalyticsEvent).where(
                        and_(
                            PublishedAppAnalyticsEvent.organization_id == organization_id,
                            PublishedAppAnalyticsEvent.published_app_id.in_(app_ids),
                            PublishedAppAnalyticsEvent.occurred_at >= start,
                            PublishedAppAnalyticsEvent.occurred_at <= end,
                            PublishedAppAnalyticsEvent.surface != PublishedAppAnalyticsSurface.preview_runtime,
                        )
                    )
                )
            ).scalars().all()
        )
        run_rows = list(
            (
                await self.db.execute(
                    select(AgentRun).where(
                        and_(
                            AgentRun.organization_id == organization_id,
                            AgentRun.published_app_id.in_(app_ids),
                            AgentRun.created_at >= start,
                            AgentRun.created_at <= end,
                            or_(AgentRun.surface.is_(None), AgentRun.surface != CODING_AGENT_SURFACE),
                        )
                    )
                )
            ).scalars().all()
        )
        thread_rows = list(
            (
                await self.db.execute(
                    select(AgentThread).where(
                        and_(
                            AgentThread.organization_id == organization_id,
                            AgentThread.published_app_id.in_(app_ids),
                            AgentThread.created_at >= start,
                            AgentThread.created_at <= end,
                            AgentThread.app_account_id.is_not(None),
                            AgentThread.surface != AgentThreadSurface.preview_runtime,
                        )
                    )
                )
            ).scalars().all()
        )
        app_accounts = list(
            (
                await self.db.execute(
                    select(PublishedAppAccount).where(PublishedAppAccount.published_app_id.in_(app_ids))
                )
            ).scalars().all()
        )
        active_sessions = list(
            (
                await self.db.execute(
                    select(PublishedAppSession).where(
                        and_(
                            PublishedAppSession.published_app_id.in_(app_ids),
                            PublishedAppSession.revoked_at.is_(None),
                            PublishedAppSession.expires_at > _utc_now(),
                        )
                    )
                )
            ).scalars().all()
        )

        range_dates = []
        cursor = start.date()
        end_date = end.date()
        while cursor <= end_date:
            range_dates.append(cursor.isoformat())
            cursor += timedelta(days=1)

        analytics_by_app: dict[str, list[PublishedAppAnalyticsEvent]] = defaultdict(list)
        for event in analytics_events:
            analytics_by_app[str(event.published_app_id)].append(event)

        runs_by_app: dict[str, list[AgentRun]] = defaultdict(list)
        for run in run_rows:
            preview_flag = _is_truthy_flag(((run.input_params or {}).get("context") or {}).get("published_app_preview"))
            if preview_flag:
                continue
            runs_by_app[str(run.published_app_id)].append(run)

        threads_by_app: dict[str, list[AgentThread]] = defaultdict(list)
        for thread in thread_rows:
            threads_by_app[str(thread.published_app_id)].append(thread)

        account_counts: dict[str, int] = defaultdict(int)
        for account in app_accounts:
            account_counts[str(account.published_app_id)] += 1

        session_counts: dict[str, int] = defaultdict(int)
        for session in active_sessions:
            session_counts[str(session.published_app_id)] += 1

        summaries: list[PublishedAppStatsSummary] = []
        for app in apps:
            app_key = str(app.id)
            app_events = analytics_by_app.get(app_key, [])
            app_runs = runs_by_app.get(app_key, [])
            app_threads = threads_by_app.get(app_key, [])

            visit_dates: dict[str, int] = defaultdict(int)
            run_dates: dict[str, int] = defaultdict(int)
            token_dates: dict[str, int] = defaultdict(int)
            visit_surface_breakdown: dict[str, int] = defaultdict(int)
            visit_auth_state_breakdown: dict[str, int] = defaultdict(int)

            visits = 0
            unique_visitors: set[str] = set()
            approximate = False
            for event in app_events:
                if event.visitor_key:
                    unique_visitors.add(str(event.visitor_key))
                event_date = _date_label(event.occurred_at)
                if event.event_type == PublishedAppAnalyticsEventType.visit_started:
                    visits += 1
                    visit_dates[event_date] += 1
                    visit_surface_breakdown[str(getattr(event.surface, "value", event.surface))] += 1
                    auth_state = str((event.metadata_ or {}).get("auth_state") or ("authenticated" if event.app_account_id else "anonymous"))
                    visit_auth_state_breakdown[auth_state] += 1
                if bool((event.metadata_ or {}).get("approximate_visitor")):
                    approximate = True

            agent_runs = 0
            failed_runs = 0
            tokens = 0
            for run in app_runs:
                agent_runs += 1
                if str(getattr(run.status, "value", run.status)) == "failed":
                    failed_runs += 1
                run_tokens = billable_total_tokens(run)
                tokens += run_tokens
                date_key = _date_label(run.created_at)
                run_dates[date_key] += 1
                token_dates[date_key] += run_tokens

            def _series(data_map: dict[str, int]) -> list[dict[str, Any]]:
                return [{"date": date_key, "value": float(data_map.get(date_key, 0))} for date_key in range_dates]

            summaries.append(
                PublishedAppStatsSummary(
                    app_id=app_key,
                    start_date=range_dates[0],
                    end_date=range_dates[-1],
                    approximate=approximate,
                    visits=visits,
                    unique_visitors=len(unique_visitors),
                    agent_runs=agent_runs,
                    failed_runs=failed_runs,
                    tokens=tokens,
                    threads=len(app_threads),
                    app_accounts=account_counts.get(app_key, 0),
                    active_sessions=session_counts.get(app_key, 0),
                    visits_by_day=_series(visit_dates),
                    runs_by_day=_series(run_dates),
                    tokens_by_day=_series(token_dates),
                    visit_surface_breakdown=dict(visit_surface_breakdown),
                    visit_auth_state_breakdown=dict(visit_auth_state_breakdown),
                )
            )

        return summaries

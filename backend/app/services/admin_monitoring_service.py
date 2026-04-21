from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agent_threads import AgentThread
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.agents import Agent as AgentModel
from app.db.postgres.models.identity import OrgMembership, User
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.services.model_accounting import usage_total_expr


ACTOR_TYPE_PLATFORM_USER = "platform_user"
ACTOR_TYPE_PUBLISHED_APP_ACCOUNT = "published_app_account"
ACTOR_TYPE_EMBEDDED_EXTERNAL_USER = "embedded_external_user"
ACTOR_TYPE_UNKNOWN = "unknown"


@dataclass(slots=True)
class MonitoredActorSummary:
    actor_id: str
    actor_type: str
    display_name: str
    email: str | None
    avatar: str | None
    platform_user_id: str | None
    source_app_count: int
    last_activity_at: datetime | None
    threads_count: int
    tokens_used_this_month: int
    is_manageable: bool
    created_at: datetime | None
    role: str | None = None


@dataclass(slots=True)
class MonitoredActorDetail:
    actor: MonitoredActorSummary
    stats: dict[str, Any]
    sources: list[dict[str, Any]]


@dataclass(slots=True)
class MonitoringThreadRow:
    id: str
    title: str | None
    created_at: datetime | None
    updated_at: datetime | None
    agent_id: str | None
    agent_name: str | None
    agent_system_key: str | None
    surface: str | None
    actor_id: str | None
    actor_type: str | None
    actor_display: str | None
    actor_email: str | None
    user_id: str | None
    root_thread_id: str | None
    parent_thread_id: str | None
    parent_thread_turn_id: str | None
    spawned_by_run_id: str | None
    lineage_depth: int


@dataclass(slots=True)
class _ThreadContext:
    thread: AgentThread
    actor_id: str | None
    actor_type: str | None
    actor_display: str | None
    actor_email: str | None
    agent_name: str | None
    agent_system_key: str | None
    app_id: UUID | None


@dataclass(slots=True)
class _ActorAggregate:
    actor_id: str
    actor_type: str
    display_name: str
    email: str | None
    avatar: str | None
    platform_user_id: str | None
    created_at: datetime | None
    role: str | None
    is_manageable: bool
    source_app_ids: set[str] = field(default_factory=set)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    threads_count: int = 0
    tokens_used_this_month: int = 0
    last_activity_at: datetime | None = None

    def to_summary(self) -> MonitoredActorSummary:
        return MonitoredActorSummary(
            actor_id=self.actor_id,
            actor_type=self.actor_type,
            display_name=self.display_name,
            email=self.email,
            avatar=self.avatar,
            platform_user_id=self.platform_user_id,
            source_app_count=len(self.source_app_ids),
            last_activity_at=self.last_activity_at,
            threads_count=self.threads_count,
            tokens_used_this_month=self.tokens_used_this_month,
            is_manageable=self.is_manageable,
            created_at=self.created_at,
            role=self.role,
        )


def _b64url_encode(value: str) -> str:
    raw = value.encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def build_published_app_account_actor_id(account_id: UUID | str) -> str:
    return f"app_account:{account_id}"


def build_embedded_external_actor_id(agent_id: UUID | str, external_user_id: str) -> str:
    return f"embed:{agent_id}:{_b64url_encode(external_user_id)}"


def parse_monitored_actor_id(actor_id: str) -> tuple[str, str | None, str | None]:
    try:
        UUID(str(actor_id))
        return ACTOR_TYPE_PLATFORM_USER, str(actor_id), None
    except Exception:
        pass

    if actor_id.startswith("app_account:"):
        return ACTOR_TYPE_PUBLISHED_APP_ACCOUNT, actor_id.removeprefix("app_account:"), None

    if actor_id.startswith("embed:"):
        parts = actor_id.split(":", 2)
        if len(parts) == 3:
            return ACTOR_TYPE_EMBEDDED_EXTERNAL_USER, parts[1], _b64url_decode(parts[2])

    raise ValueError("Invalid monitored actor id")


def _sort_datetime(value: datetime | None) -> datetime:
    return value if value is not None else datetime.min.replace(tzinfo=timezone.utc)


class AdminMonitoringService:
    def __init__(self, db: AsyncSession, organization_id: UUID | None):
        self.db = db
        self.organization_id = organization_id

    async def list_monitored_actors(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        search: str | None = None,
        actor_type: str | None = None,
        agent_id: UUID | None = None,
        app_id: UUID | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[MonitoredActorSummary], int]:
        aggregates = await self._build_actor_aggregates(
            month_start=month_start,
            month_end=month_end,
            actor_type=actor_type,
            agent_id=agent_id,
            app_id=app_id,
        )
        items = list(aggregates.values())
        if search:
            needle = search.strip().lower()
            items = [
                item
                for item in items
                if needle in (item.display_name or "").lower()
                or needle in (item.email or "").lower()
                or any(needle in (source.get("display_name") or "").lower() for source in item.source_records)
                or any(needle in (source.get("email") or "").lower() for source in item.source_records)
            ]
        items.sort(
            key=lambda item: (
                _sort_datetime(item.last_activity_at),
                _sort_datetime(item.created_at),
                item.display_name.lower(),
            ),
            reverse=True,
        )
        total = len(items)
        page = items[max(0, skip): max(0, skip) + max(1, limit)]
        return [item.to_summary() for item in page], total

    async def get_monitored_actor_detail(
        self,
        actor_id: str,
        *,
        month_start: datetime,
        month_end: datetime,
    ) -> MonitoredActorDetail | None:
        aggregates = await self._build_actor_aggregates(month_start=month_start, month_end=month_end)
        actor = aggregates.get(actor_id)
        if actor is None:
            return None
        return MonitoredActorDetail(
            actor=actor.to_summary(),
            stats={
                "threads_count": actor.threads_count,
                "tokens_used_this_month": actor.tokens_used_this_month,
            },
            sources=actor.source_records,
        )

    async def list_threads(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        search: str | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
        agent_id: UUID | None = None,
        app_id: UUID | None = None,
        surface: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[MonitoringThreadRow], int]:
        contexts = await self._load_thread_contexts(month_start=month_start, month_end=month_end, agent_id=agent_id, app_id=app_id)
        rows: list[MonitoringThreadRow] = []
        for context in contexts:
            thread = context.thread
            surface_value = thread.surface.value if hasattr(thread.surface, "value") else str(thread.surface or "")
            if actor_type and context.actor_type != actor_type:
                continue
            if actor_id and context.actor_id != actor_id:
                continue
            if surface and surface_value != surface:
                continue
            if search:
                needle = search.strip().lower()
                haystacks = [
                    thread.title or "",
                    context.actor_display or "",
                    context.actor_email or "",
                    context.agent_name or "",
                    context.agent_system_key or "",
                ]
                if not any(needle in value.lower() for value in haystacks if value):
                    continue
            rows.append(
                MonitoringThreadRow(
                    id=str(thread.id),
                    title=thread.title,
                    created_at=thread.created_at,
                    updated_at=thread.last_activity_at or thread.updated_at,
                    agent_id=str(thread.agent_id) if thread.agent_id else None,
                    agent_name=context.agent_name,
                    agent_system_key=context.agent_system_key,
                    surface=surface_value or None,
                    actor_id=context.actor_id,
                    actor_type=context.actor_type,
                    actor_display=context.actor_display,
                    actor_email=context.actor_email,
                    user_id=str(thread.user_id) if thread.user_id else None,
                    root_thread_id=str(thread.root_thread_id or thread.id),
                    parent_thread_id=str(thread.parent_thread_id) if thread.parent_thread_id else None,
                    parent_thread_turn_id=str(thread.parent_thread_turn_id) if thread.parent_thread_turn_id else None,
                    spawned_by_run_id=str(thread.spawned_by_run_id) if thread.spawned_by_run_id else None,
                    lineage_depth=int(thread.lineage_depth or 0),
                )
            )
        rows.sort(
            key=lambda row: (_sort_datetime(row.updated_at), _sort_datetime(row.created_at)),
            reverse=True,
        )
        total = len(rows)
        return rows[max(0, skip): max(0, skip) + max(1, limit)], total

    async def get_thread_row(
        self,
        thread_id: UUID,
        *,
        month_start: datetime,
        month_end: datetime,
    ) -> MonitoringThreadRow | None:
        rows, _ = await self.list_threads(
            month_start=month_start,
            month_end=month_end,
            skip=0,
            limit=100000,
        )
        for row in rows:
            if row.id == str(thread_id):
                return row
        return None

    async def count_threads(
        self,
        *,
        start: datetime,
        end: datetime,
        agent_id: UUID | None = None,
    ) -> int:
        query = select(func.count(AgentThread.id)).where(
            and_(AgentThread.created_at >= start, AgentThread.created_at <= end)
        )
        if self.organization_id:
            query = query.where(AgentThread.organization_id == self.organization_id)
        if agent_id:
            query = query.where(AgentThread.agent_id == agent_id)
        return int((await self.db.execute(query)).scalar() or 0)

    async def top_actor_summaries_by_runs(
        self,
        *,
        start: datetime,
        end: datetime,
        agent_id: UUID | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        contexts = await self._load_thread_contexts(month_start=start, month_end=end, agent_id=agent_id, app_id=None)
        context_by_thread_id = {str(context.thread.id): context for context in contexts}

        query = select(AgentRun.thread_id, func.count(AgentRun.id)).where(
            and_(
                AgentRun.created_at >= start,
                AgentRun.created_at <= end,
                AgentRun.thread_id.is_not(None),
            )
        )
        if self.organization_id:
            query = query.where(AgentRun.organization_id == self.organization_id)
        if agent_id:
            query = query.where(AgentRun.agent_id == agent_id)
        query = query.group_by(AgentRun.thread_id)
        rows = (await self.db.execute(query)).all()

        aggregated: dict[str, dict[str, Any]] = {}
        for thread_id, run_count in rows:
            if thread_id is None:
                continue
            context = context_by_thread_id.get(str(thread_id))
            if context is None or context.actor_id is None:
                continue
            item = aggregated.setdefault(
                context.actor_id,
                {
                    "user_id": context.actor_id,
                    "display_name": context.actor_display or "Unknown actor",
                    "email": context.actor_email,
                    "actor_type": context.actor_type,
                    "count": 0,
                },
            )
            item["count"] += int(run_count or 0)
        return sorted(aggregated.values(), key=lambda item: item["count"], reverse=True)[:limit]

    async def active_actor_count(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        top = await self.top_actor_summaries_by_runs(start=start, end=end, limit=100000)
        return len(top)

    async def daily_active_actor_counts(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        contexts = await self._load_thread_contexts(month_start=start, month_end=end, agent_id=None, app_id=None)
        context_by_thread_id = {str(context.thread.id): context for context in contexts if context.actor_id}
        query = (
            select(func.date(AgentRun.created_at), AgentRun.thread_id)
            .where(
                and_(
                    AgentRun.thread_id.is_not(None),
                    AgentRun.created_at >= start,
                    AgentRun.created_at <= end,
                )
            )
        )
        if self.organization_id:
            query = query.where(AgentRun.organization_id == self.organization_id)
        rows = (await self.db.execute(query)).all()

        by_day: dict[str, set[str]] = defaultdict(set)
        for day_value, thread_id in rows:
            if thread_id is None or day_value is None:
                continue
            context = context_by_thread_id.get(str(thread_id))
            if context is None or context.actor_id is None:
                continue
            by_day[str(day_value)].add(context.actor_id)
        return [{"date": date_str, "count": len(actor_ids)} for date_str, actor_ids in sorted(by_day.items())]

    async def actor_count(self, *, month_start: datetime, month_end: datetime) -> int:
        aggregates = await self._build_actor_aggregates(month_start=month_start, month_end=month_end)
        return len(aggregates)

    async def latest_thread_summaries(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows, _ = await self.list_threads(month_start=month_start, month_end=month_end, limit=limit)
        return [
            {
                "id": row.id,
                "title": row.title,
                "created_at": row.created_at,
                "user_email": row.actor_email or row.actor_display or "Unknown actor",
            }
            for row in rows[:limit]
        ]

    async def _build_actor_aggregates(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        actor_type: str | None = None,
        agent_id: UUID | None = None,
        app_id: UUID | None = None,
    ) -> dict[str, _ActorAggregate]:
        platform_users = await self._load_platform_users()
        app_accounts = await self._load_published_app_accounts(app_id=app_id)
        thread_contexts = await self._load_thread_contexts(month_start=month_start, month_end=month_end, agent_id=agent_id, app_id=app_id)
        usage_by_thread = await self._load_usage_by_thread(start=month_start, end=month_end)

        aggregates: dict[str, _ActorAggregate] = {}

        for user in platform_users:
            actor_id = str(user.id)
            aggregates[actor_id] = _ActorAggregate(
                actor_id=actor_id,
                actor_type=ACTOR_TYPE_PLATFORM_USER,
                display_name=user.full_name or user.email or actor_id,
                email=user.email,
                avatar=user.avatar,
                platform_user_id=str(user.id),
                created_at=user.created_at,
                role=getattr(user, "role", None),
                is_manageable=True,
                source_records=[
                    {
                        "type": ACTOR_TYPE_PLATFORM_USER,
                        "id": actor_id,
                        "display_name": user.full_name or user.email or actor_id,
                        "email": user.email,
                    }
                ],
            )

        for account, published_app in app_accounts:
            mapped_platform_id = str(account.global_user_id) if account.global_user_id else None
            target_actor_id = mapped_platform_id or build_published_app_account_actor_id(account.id)
            aggregate = aggregates.get(target_actor_id)
            if aggregate is None:
                aggregate = _ActorAggregate(
                    actor_id=target_actor_id,
                    actor_type=ACTOR_TYPE_PUBLISHED_APP_ACCOUNT,
                    display_name=account.full_name or account.email or str(account.id),
                    email=account.email,
                    avatar=account.avatar,
                    platform_user_id=mapped_platform_id,
                    created_at=account.created_at,
                    role=None,
                    is_manageable=False,
                )
                aggregates[target_actor_id] = aggregate
            if published_app is not None:
                aggregate.source_app_ids.add(str(published_app.id))
            aggregate.source_records.append(
                {
                    "type": ACTOR_TYPE_PUBLISHED_APP_ACCOUNT,
                    "id": str(account.id),
                    "display_name": account.full_name or account.email or str(account.id),
                    "email": account.email,
                    "published_app_id": str(published_app.id) if published_app else None,
                    "published_app_name": published_app.name if published_app else None,
                    "published_app_public_id": published_app.public_id if published_app else None,
                    "mapped_platform_user_id": mapped_platform_id,
                }
            )
            if aggregate.actor_type == ACTOR_TYPE_PLATFORM_USER:
                aggregate.platform_user_id = aggregate.platform_user_id or mapped_platform_id

        for context in thread_contexts:
            if context.actor_id is None:
                continue
            aggregate = aggregates.get(context.actor_id)
            if aggregate is None:
                aggregate = _ActorAggregate(
                    actor_id=context.actor_id,
                    actor_type=context.actor_type or ACTOR_TYPE_UNKNOWN,
                    display_name=context.actor_display or context.actor_id,
                    email=context.actor_email,
                    avatar=None,
                    platform_user_id=None,
                    created_at=context.thread.created_at,
                    role=None,
                    is_manageable=False,
                )
                aggregates[context.actor_id] = aggregate
            aggregate.threads_count += 1
            aggregate.tokens_used_this_month += usage_by_thread.get(str(context.thread.id), 0)
            if context.app_id is not None:
                aggregate.source_app_ids.add(str(context.app_id))
            if aggregate.last_activity_at is None or (
                context.thread.last_activity_at and context.thread.last_activity_at > aggregate.last_activity_at
            ):
                aggregate.last_activity_at = context.thread.last_activity_at or context.thread.updated_at
            if context.actor_type == ACTOR_TYPE_EMBEDDED_EXTERNAL_USER and not aggregate.source_records:
                aggregate.source_records.append(
                    {
                        "type": ACTOR_TYPE_EMBEDDED_EXTERNAL_USER,
                        "id": context.actor_id,
                        "display_name": context.actor_display,
                        "email": context.actor_email,
                        "agent_id": str(context.thread.agent_id) if context.thread.agent_id else None,
                        "agent_name": context.agent_name,
                        "agent_system_key": context.agent_system_key,
                        "external_user_id": context.thread.external_user_id,
                    }
                )

        if actor_type:
            aggregates = {
                actor_id: aggregate
                for actor_id, aggregate in aggregates.items()
                if aggregate.actor_type == actor_type
            }
        return aggregates

    async def _load_platform_users(self) -> list[User]:
        query = select(User)
        if self.organization_id:
            query = query.join(OrgMembership).where(OrgMembership.organization_id == self.organization_id)
        query = query.order_by(User.created_at.desc())
        return list((await self.db.execute(query)).scalars().all())

    async def _load_published_app_accounts(
        self,
        *,
        app_id: UUID | None,
    ) -> list[tuple[PublishedAppAccount, PublishedApp | None]]:
        query = (
            select(PublishedAppAccount, PublishedApp)
            .join(PublishedApp, PublishedAppAccount.published_app_id == PublishedApp.id)
        )
        if self.organization_id:
            query = query.where(PublishedApp.organization_id == self.organization_id)
        if app_id:
            query = query.where(PublishedApp.id == app_id)
        query = query.order_by(PublishedAppAccount.updated_at.desc())
        return list((await self.db.execute(query)).all())

    async def _load_usage_by_thread(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        query = (
            select(AgentRun.thread_id, func.coalesce(func.sum(usage_total_expr(AgentRun)), 0))
            .where(
                and_(
                    AgentRun.thread_id.is_not(None),
                    AgentRun.created_at >= start,
                    AgentRun.created_at < end,
                )
            )
            .group_by(AgentRun.thread_id)
        )
        if self.organization_id:
            query = query.where(AgentRun.organization_id == self.organization_id)
        rows = (await self.db.execute(query)).all()
        return {str(thread_id): int(tokens or 0) for thread_id, tokens in rows if thread_id is not None}

    async def _load_thread_contexts(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        agent_id: UUID | None,
        app_id: UUID | None,
    ) -> list[_ThreadContext]:
        del month_start, month_end
        published_app_alias = PublishedApp
        query = (
            select(
                AgentThread,
                User,
                PublishedAppAccount,
                published_app_alias,
                AgentModel,
            )
            .outerjoin(User, AgentThread.user_id == User.id)
            .outerjoin(PublishedAppAccount, AgentThread.app_account_id == PublishedAppAccount.id)
            .outerjoin(published_app_alias, AgentThread.published_app_id == published_app_alias.id)
            .outerjoin(AgentModel, AgentThread.agent_id == AgentModel.id)
        )
        if self.organization_id:
            query = query.where(AgentThread.organization_id == self.organization_id)
        if agent_id:
            query = query.where(AgentThread.agent_id == agent_id)
        if app_id:
            query = query.where(AgentThread.published_app_id == app_id)
        query = query.order_by(AgentThread.last_activity_at.desc().nullslast(), AgentThread.updated_at.desc())
        rows = (await self.db.execute(query)).all()
        contexts: list[_ThreadContext] = []
        for thread, user, account, published_app, agent in rows:
            resolved_app = published_app
            if resolved_app is None and account is not None:
                resolved_app = await self.db.get(PublishedApp, account.published_app_id)
            resolved_actor_id = None
            resolved_actor_type = None
            resolved_display = None
            resolved_email = None

            if user is not None and thread.user_id is not None:
                resolved_actor_id = str(thread.user_id)
                resolved_actor_type = ACTOR_TYPE_PLATFORM_USER
                resolved_display = user.full_name or user.email or str(thread.user_id)
                resolved_email = user.email
            elif account is not None and thread.app_account_id is not None:
                if account.global_user_id:
                    resolved_actor_id = str(account.global_user_id)
                    resolved_actor_type = ACTOR_TYPE_PLATFORM_USER
                else:
                    resolved_actor_id = build_published_app_account_actor_id(thread.app_account_id)
                    resolved_actor_type = ACTOR_TYPE_PUBLISHED_APP_ACCOUNT
                resolved_display = account.full_name or account.email or str(thread.app_account_id)
                resolved_email = account.email
            elif thread.external_user_id and thread.agent_id:
                resolved_actor_id = build_embedded_external_actor_id(thread.agent_id, thread.external_user_id)
                resolved_actor_type = ACTOR_TYPE_EMBEDDED_EXTERNAL_USER
                resolved_display = thread.external_user_id
                resolved_email = None

            contexts.append(
                _ThreadContext(
                    thread=thread,
                    actor_id=resolved_actor_id,
                    actor_type=resolved_actor_type,
                    actor_display=resolved_display,
                    actor_email=resolved_email,
                    agent_name=agent.name if agent is not None else None,
                    agent_system_key=agent.system_key if agent is not None else None,
                    app_id=resolved_app.id if resolved_app is not None else None,
                )
            )
        return contexts

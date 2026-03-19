from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func, desc, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.session import get_db
from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.identity import User, OrgMembership
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn
from app.db.postgres.models.agents import AgentRun
from app.core.scope_registry import is_platform_admin_role
from app.services.admin_monitoring_service import AdminMonitoringService
from app.services.thread_service import ThreadService
from pydantic import BaseModel

router = APIRouter()


def _current_month_bounds_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)
    return period_start, period_end

# --- Dependencies & Helpers ---

async def get_admin_context(
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns admin context.
    - platform admin users can access global view (tenant_id=None)
    - tenant users require membership and operate within token tenant context
    """
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only user principals can access admin APIs")

    current_user = await db.get(User, UUID(str(principal["user_id"])))
    if current_user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if is_platform_admin_role(getattr(current_user, "role", None)):
        return {"user": current_user, "tenant_id": None}

    tenant_id_raw = principal.get("tenant_id")
    if not tenant_id_raw:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        tenant_id = UUID(str(tenant_id_raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid tenant context")

    result = await db.execute(select(OrgMembership).where(
        OrgMembership.user_id == current_user.id,
        OrgMembership.tenant_id == tenant_id,
    ).limit(1))
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not authorized for tenant")
    return {"user": current_user, "tenant_id": membership.tenant_id}

class UserUpdate(BaseModel):
    full_name: Optional[str] = None

# --- Endpoints ---

@router.get("/stats")
async def get_admin_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("stats.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    
    # Date Filtering Logic
    now = datetime.now(timezone.utc)
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            # Fallback to simple date parsing if ISO fails
            start = datetime.strptime(start_date.split('T')[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_date.split('T')[0], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    else:
        end = now
        start = end - timedelta(days=180) # Default 6 months
    
    seven_days_ago = now - timedelta(days=7)

    # 1. Total Active Users (Last 7 Days) based on run-native thread activity.
    q_active = (
        select(func.count(func.distinct(AgentRun.user_id)))
        .where(
            and_(
                AgentRun.user_id.isnot(None),
                AgentRun.created_at >= seven_days_ago,
            )
        )
    )
    if tenant_id:
        q_active = q_active.where(AgentRun.tenant_id == tenant_id)
    total_active_users = int((await db.execute(q_active)).scalar() or 0)

    # 2. Total Threads
    q_threads = select(func.count(AgentThread.id))
    if tenant_id:
        q_threads = q_threads.where(AgentThread.tenant_id == tenant_id)
    total_chats = int((await db.execute(q_threads)).scalar() or 0)

    # 3. Total Turns (treated as message units for dashboard continuity).
    q_turns = select(func.count(AgentThreadTurn.id)).join(AgentThread, AgentThreadTurn.thread_id == AgentThread.id)
    if tenant_id:
        q_turns = q_turns.where(AgentThread.tenant_id == tenant_id)
    total_messages = int((await db.execute(q_turns)).scalar() or 0)

    # 4. Avg Turns/Thread
    avg_messages_per_chat = round(total_messages / total_chats, 1) if total_chats > 0 else 0

    # 5. Token Usage from run ledger.
    q_tokens = select(func.coalesce(func.sum(AgentRun.usage_tokens), 0))
    if tenant_id:
        q_tokens = q_tokens.where(AgentRun.tenant_id == tenant_id)
    estimated_tokens = int((await db.execute(q_tokens)).scalar() or 0)

    # 6. Daily Active Users (DAU) from run activity.
    q_dau = (
        select(
            func.date_trunc(text("'day'"), AgentRun.created_at).label("date"),
            func.count(func.distinct(AgentRun.user_id)).label("count"),
        )
        .where(
            and_(
                AgentRun.user_id.isnot(None),
                AgentRun.created_at >= start,
                AgentRun.created_at <= end,
            )
        )
        .group_by(func.date_trunc(text("'day'"), AgentRun.created_at))
        .order_by(text("date ASC"))
    )
    if tenant_id:
        q_dau = q_dau.where(AgentRun.tenant_id == tenant_id)
    dau_result = (await db.execute(q_dau)).all()
    daily_active_users = [{"date": r.date.strftime("%Y-%m-%d"), "count": int(r.count or 0)} for r in dau_result]

    # 7. New Users (Last 7 Days)
    q_new_users = select(func.count(User.id)).where(User.created_at >= seven_days_ago)
    if tenant_id:
        q_new_users = q_new_users.join(OrgMembership).where(OrgMembership.tenant_id == tenant_id)
    new_users_count = int((await db.execute(q_new_users)).scalar() or 0)

    # 8. Thread Volume Trend
    q_vol = (
        select(
            func.date_trunc(text("'day'"), AgentThread.created_at).label("date"),
            func.count(AgentThread.id).label("count"),
        )
        .where(and_(AgentThread.created_at >= start, AgentThread.created_at <= end))
        .group_by(func.date_trunc(text("'day'"), AgentThread.created_at))
        .order_by(text("date ASC"))
    )
    if tenant_id:
        q_vol = q_vol.where(AgentThread.tenant_id == tenant_id)
    vol_result = (await db.execute(q_vol)).all()
    daily_chat_stats = [{"date": r.date.strftime("%Y-%m-%d"), "chats": int(r.count or 0)} for r in vol_result]

    # 9. Top Active Users by runs.
    q_top = (
        select(User.email, func.count(AgentRun.id).label("msg_count"))
        .select_from(User)
        .join(AgentRun, AgentRun.user_id == User.id)
        .group_by(User.id, User.email)
        .order_by(desc("msg_count"))
        .limit(5)
    )
    if tenant_id:
        q_top = q_top.where(AgentRun.tenant_id == tenant_id)
    top_users_res = (await db.execute(q_top)).all()
    top_users = [{"email": r.email, "count": int(r.msg_count or 0)} for r in top_users_res]

    # 10. Recent Threads
    q_recent = (
        select(AgentThread)
        .order_by(AgentThread.created_at.desc())
        .limit(5)
        .options(selectinload(AgentThread.user))
    )
    if tenant_id:
        q_recent = q_recent.where(AgentThread.tenant_id == tenant_id)
    recent_threads_res = (await db.execute(q_recent)).scalars().all()

    latest_chats = [
        {
            "id": str(thread.id),
            "title": thread.title,
            "created_at": thread.created_at,
            "user_email": thread.user.email if thread.user else "Unknown",
        }
        for thread in recent_threads_res
    ]

    # Total Users Count
    q_total_users = select(func.count(User.id))
    if tenant_id:
        q_total_users = q_total_users.join(OrgMembership).where(OrgMembership.tenant_id == tenant_id)
    total_users = int((await db.execute(q_total_users)).scalar() or 0)

    return {
        "total_users": total_users,
        "total_active_users": total_active_users,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "avg_messages_per_chat": avg_messages_per_chat,
        "estimated_tokens": estimated_tokens,
        "new_users_last_7_days": new_users_count,
        "daily_active_users": daily_active_users,
        "daily_stats": daily_chat_stats,
        "top_users": top_users,
        "latest_chats": latest_chats
    }

@router.post("/users/bulk-delete")
async def bulk_delete_users(
    user_ids: List[str], 
    _: Dict[str, Any] = Depends(require_scopes("users.write")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Convert strings to UUIDs
        uuids = [UUID(uid) for uid in user_ids]
        
        # Security: If tenant admin, verify these users belong to tenant
        tenant_id = context["tenant_id"]
        if tenant_id:
            # Subquery to check membership
            verify_q = select(OrgMembership.user_id).where(
                and_(OrgMembership.tenant_id == tenant_id, OrgMembership.user_id.in_(uuids))
            )
            verified_ids = (await db.execute(verify_q)).scalars().all()
            if len(verified_ids) != len(uuids):
                raise HTTPException(status_code=403, detail="Cannot delete users outside your organization")
                
        # Delete Users (Cascade should handle chats/messages/memberships)
        # Note: If User model has cascading relationships set up correctly.
        q = text("DELETE FROM users WHERE id = ANY(:ids)")
        await db.execute(q, {"ids": uuids})
        await db.commit()
        
        return {"deleted_count": len(user_ids)}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/threads/bulk-delete")
async def bulk_delete_threads(
    thread_ids: List[str], 
    _: Dict[str, Any] = Depends(require_scopes("threads.write")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    try:
        uuids = [UUID(tid) for tid in thread_ids]
        tenant_id = context["tenant_id"]

        q = text("DELETE FROM agent_threads WHERE id = ANY(:ids)")
        params = {"ids": uuids}

        if tenant_id:
             # Safer for tenant: delete with and clause
             q = text("DELETE FROM agent_threads WHERE id = ANY(:ids) AND tenant_id = :tenant_id")
             params["tenant_id"] = tenant_id

        result = await db.execute(q, params)
        await db.commit()
        return {"deleted_count": result.rowcount}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users")
async def get_users(
    skip: int = 0, 
    limit: int = 20, 
    search: Optional[str] = None,
    actor_type: Optional[str] = None,
    agent_id: Optional[UUID] = None,
    app_id: Optional[UUID] = None,
    _: Dict[str, Any] = Depends(require_scopes("users.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    period_start, period_end = _current_month_bounds_utc()

    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    users, total = await monitoring.list_monitored_actors(
        month_start=period_start,
        month_end=period_end,
        search=search,
        actor_type=actor_type,
        agent_id=agent_id,
        app_id=app_id,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [
            {
                "id": user.actor_id,
                "actor_id": user.actor_id,
                "actor_type": user.actor_type,
                "email": user.email,
                "display_name": user.display_name,
                "full_name": user.display_name,
                "role": user.role,
                "avatar": user.avatar,
                "created_at": user.created_at,
                "token_usage": user.tokens_used_this_month,
                "platform_user_id": user.platform_user_id,
                "source_app_count": user.source_app_count,
                "last_activity_at": user.last_activity_at,
                "threads_count": user.threads_count,
                "is_manageable": user.is_manageable,
            }
            for user in users
        ],
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if limit else 1
    }

@router.get("/threads")
async def get_threads(
    skip: int = 0, 
    limit: int = 20, 
    search: Optional[str] = None,
    actor_type: Optional[str] = None,
    surface: Optional[str] = None,
    agent_id: Optional[UUID] = None,
    app_id: Optional[UUID] = None,
    _: Dict[str, Any] = Depends(require_scopes("threads.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    period_start, period_end = _current_month_bounds_utc()
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    rows, total = await monitoring.list_threads(
        month_start=period_start,
        month_end=period_end,
        search=search,
        actor_type=actor_type,
        agent_id=agent_id,
        app_id=app_id,
        surface=surface,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "agent_id": row.agent_id,
                "agent_name": row.agent_name,
                "agent_slug": row.agent_slug,
                "surface": row.surface,
                "actor_id": row.actor_id,
                "actor_type": row.actor_type,
                "actor_display": row.actor_display,
                "actor_email": row.actor_email,
                "user_id": row.user_id,
            }
            for row in rows
        ],
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if limit else 1
    }


@router.get("/threads/{thread_id}")
async def get_thread_details(
    thread_id: str,
    _: Dict[str, Any] = Depends(require_scopes("threads.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = UUID(thread_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid thread ID")

    tenant_id = context["tenant_id"]
    service = ThreadService(db)
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    period_start, period_end = _current_month_bounds_utc()
    repaired = await service.repair_thread_turn_indices(thread_id=tid)
    if repaired:
        await db.commit()
    thread = await service.get_thread_with_turns(
        tenant_id=tenant_id,
        thread_id=tid,
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread_row = await monitoring.get_thread_row(tid, month_start=period_start, month_end=period_end)
    turns = list(thread.turns or [])
    return {
        "id": str(thread.id),
        "title": thread.title,
        "status": thread.status.value if hasattr(thread.status, "value") else str(thread.status),
        "surface": thread.surface.value if hasattr(thread.surface, "value") else str(thread.surface),
        "user_id": str(thread.user_id) if thread.user_id else None,
        "agent_id": str(thread.agent_id) if thread.agent_id else None,
        "agent_name": thread_row.agent_name if thread_row else None,
        "agent_slug": thread_row.agent_slug if thread_row else None,
        "actor_id": thread_row.actor_id if thread_row else None,
        "actor_type": thread_row.actor_type if thread_row else None,
        "actor_display": thread_row.actor_display if thread_row else None,
        "actor_email": thread_row.actor_email if thread_row else None,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "last_activity_at": thread.last_activity_at,
        "turns": [
            {
                "id": str(turn.id),
                "run_id": str(turn.run_id),
                "turn_index": int(turn.turn_index or 0),
                "status": turn.status.value if hasattr(turn.status, "value") else str(turn.status),
                "user_input_text": turn.user_input_text,
                "assistant_output_text": turn.assistant_output_text,
                "usage_tokens": int(turn.usage_tokens or 0),
                "created_at": turn.created_at,
                "completed_at": turn.completed_at,
                "metadata": turn.metadata_,
            }
            for turn in turns
        ],
    }

@router.get("/users/{user_id}")
async def get_user_details(
    user_id: str, 
    _: Dict[str, Any] = Depends(require_scopes("users.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    period_start, period_end = _current_month_bounds_utc()
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    detail = await monitoring.get_monitored_actor_detail(
        user_id,
        month_start=period_start,
        month_end=period_end,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user": {
            "id": detail.actor.actor_id,
            "actor_id": detail.actor.actor_id,
            "actor_type": detail.actor.actor_type,
            "email": detail.actor.email,
            "display_name": detail.actor.display_name,
            "full_name": detail.actor.display_name,
            "created_at": detail.actor.created_at,
            "role": detail.actor.role,
            "avatar": detail.actor.avatar,
            "token_usage": detail.actor.tokens_used_this_month,
            "platform_user_id": detail.actor.platform_user_id,
            "source_app_count": detail.actor.source_app_count,
            "last_activity_at": detail.actor.last_activity_at,
            "threads_count": detail.actor.threads_count,
            "is_manageable": detail.actor.is_manageable,
        },
        "stats": detail.stats,
        "sources": detail.sources,
    }

@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, 
    user_update: UserUpdate,
    _: Dict[str, Any] = Depends(require_scopes("users.write")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    try:
        uid = UUID(user_id)
        tenant_id = context["tenant_id"]
        
         # Verify tenant access
        if tenant_id:
             check_mem = await db.execute(
                 select(OrgMembership).where(
                     OrgMembership.user_id == uid, 
                     OrgMembership.tenant_id == tenant_id
                 )
             )
             if not check_mem.scalar_one_or_none():
                 raise HTTPException(status_code=404, detail="User not found")

        q = select(User).where(User.id == uid)
        user = (await db.execute(q)).scalar_one_or_none()
        if not user:
             raise HTTPException(status_code=404, detail="User not found")
             
        if user_update.full_name is not None:
            user.full_name = user_update.full_name
        
        await db.commit()
        return {"status": "success"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.get("/users/{user_id}/threads")
async def get_user_threads(
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    agent_id: Optional[UUID] = None,
    _: Dict[str, Any] = Depends(require_scopes("threads.read")),
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    period_start, period_end = _current_month_bounds_utc()
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    rows, total = await monitoring.list_threads(
        month_start=period_start,
        month_end=period_end,
        search=search,
        actor_id=user_id,
        agent_id=agent_id,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "agent_id": row.agent_id,
                "agent_name": row.agent_name,
                "agent_slug": row.agent_slug,
                "surface": row.surface,
                "actor_id": row.actor_id,
                "actor_type": row.actor_type,
                "actor_display": row.actor_display,
                "actor_email": row.actor_email,
                "user_id": row.user_id,
            }
            for row in rows
        ],
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if limit else 1
    }

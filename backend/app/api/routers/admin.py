from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func, desc, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import User, OrgMembership, OrgRole
from app.db.postgres.models.chat import Chat, Message, MessageRole
from pydantic import BaseModel

router = APIRouter()

# --- Dependencies & Helpers ---

async def get_admin_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns a context dict with 'user' and 'tenant_id'.
    If user is System Admin (role='admin'), tenant_id is None (Global View).
    If user is Tenant Admin/Owner, tenant_id is set to their tenant.
    Otherwise raises 403.
    """
    if current_user.role == "admin":
        return {"user": current_user, "tenant_id": None}

    # Check Tenant Admin/Owner Role via Postgres
    result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1)
    )
    membership = result.scalar_one_or_none()
    
    if membership and membership.role in [OrgRole.owner, OrgRole.admin]:
        return {"user": current_user, "tenant_id": membership.tenant_id}
        
    raise HTTPException(status_code=403, detail="Not authorized")

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None

# --- Endpoints ---

@router.get("/stats")
async def get_admin_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
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

    # Helper to apply filters
    def apply_tenant_filter(query, model):
        if tenant_id:
            if hasattr(model, 'tenant_id'):
                return query.where(model.tenant_id == tenant_id)
            # For Message, join Chat
            if model == Message:
                return query.join(Chat).where(Chat.tenant_id == tenant_id)
            # For User, join OrgMembership
            if model == User:
                return query.join(OrgMembership).where(OrgMembership.tenant_id == tenant_id)
        return query

    # 1. Total Active Users (Last 7 Days)
    q_active = select(func.count(func.distinct(Chat.user_id))).where(Chat.updated_at >= seven_days_ago)
    q_active = apply_tenant_filter(q_active, Chat)
    total_active_users = (await db.execute(q_active)).scalar() or 0

    # 2. Total Conversations
    q_chats = select(func.count(Chat.id))
    q_chats = apply_tenant_filter(q_chats, Chat)
    total_chats = (await db.execute(q_chats)).scalar() or 0

    # 3. Total Messages
    q_msgs = select(func.count(Message.id))
    q_msgs = apply_tenant_filter(q_msgs, Message)
    total_messages = (await db.execute(q_msgs)).scalar() or 0

    # 4. Avg Messages/Chat
    avg_messages_per_chat = round(total_messages / total_chats, 1) if total_chats > 0 else 0

    # 5. Token Usage (Estimate: 1 token ~= 4 chars)
    # Using Postgres length function
    q_tokens = select(func.sum(func.length(Message.content)))
    q_tokens = apply_tenant_filter(q_tokens, Message)
    total_chars = (await db.execute(q_tokens)).scalar() or 0
    estimated_tokens = total_chars // 4

    # 6. Daily Active Users (DAU)
    # Postgres date_trunc
    q_dau = (
        select(
            func.date_trunc(text("'day'"), Chat.updated_at).label('date'),
            func.count(func.distinct(Chat.user_id)).label('count')
        )
        .where(and_(Chat.updated_at >= start, Chat.updated_at <= end))
        .group_by(func.date_trunc(text("'day'"), Chat.updated_at))
        .order_by(text("date ASC"))
    )
    q_dau = apply_tenant_filter(q_dau, Chat)
    dau_result = (await db.execute(q_dau)).all()
    daily_active_users = [{"date": r.date.strftime("%Y-%m-%d"), "count": r.count} for r in dau_result]

    # 7. New Users (Last 7 Days)
    q_new_users = select(func.count(User.id)).where(User.created_at >= seven_days_ago)
    q_new_users = apply_tenant_filter(q_new_users, User)
    new_users_count = (await db.execute(q_new_users)).scalar() or 0

    # 8. Chat Volume Trend
    q_vol = (
        select(
            func.date_trunc(text("'day'"), Chat.created_at).label('date'),
            func.count(Chat.id).label('count')
        )
        .where(and_(Chat.created_at >= start, Chat.created_at <= end))
        .group_by(func.date_trunc(text("'day'"), Chat.created_at))
        .order_by(text("date ASC"))
    )
    q_vol = apply_tenant_filter(q_vol, Chat)
    vol_result = (await db.execute(q_vol)).all()
    daily_chat_stats = [{"date": r.date.strftime("%Y-%m-%d"), "chats": r.count} for r in vol_result]

    # 9. Top Active Users (by message count)
    q_top = (
        select(User.email, func.count(Message.id).label('msg_count'))
        .select_from(User)
        .join(Chat, Chat.user_id == User.id)
        .join(Message, Message.chat_id == Chat.id)
        .group_by(User.id, User.email)
        .order_by(desc('msg_count'))
        .limit(5)
    )
    # Apply tenant filter logic manually for complex join
    if tenant_id:
        q_top = q_top.join(OrgMembership, OrgMembership.user_id == User.id).where(OrgMembership.tenant_id == tenant_id)
        
    top_users_res = (await db.execute(q_top)).all()
    top_users = [{"email": r.email, "count": r.msg_count} for r in top_users_res]

    # 10. Recent Chats
    q_recent = select(Chat).order_by(Chat.created_at.desc()).limit(5).options(selectinload(Chat.user))
    q_recent = apply_tenant_filter(q_recent, Chat)
    recent_chats_res = (await db.execute(q_recent)).scalars().all()
    
    latest_chats = []
    for c in recent_chats_res:
        latest_chats.append({
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at,
            "user_email": c.user.email if c.user else "Unknown"
        })

    # Total Users Count
    q_total_users = select(func.count(User.id))
    q_total_users = apply_tenant_filter(q_total_users, User)
    total_users = (await db.execute(q_total_users)).scalar() or 0

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

@router.post("/chats/bulk-delete")
async def bulk_delete_chats(
    chat_ids: List[str], 
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    try:
        uuids = [UUID(cid) for cid in chat_ids]
        tenant_id = context["tenant_id"]

        q = text("DELETE FROM chats WHERE id = ANY(:ids)")
        params = {"ids": uuids}

        if tenant_id:
             # Safer for tenant: delete with and clause
             q = text("DELETE FROM chats WHERE id = ANY(:ids) AND tenant_id = :tenant_id")
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
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    
    query = select(User)
    if tenant_id:
        query = query.join(OrgMembership).where(OrgMembership.tenant_id == tenant_id)
        
    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%"))
        )
        
    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    
    # Paginate
    query = query.offset(skip).limit(limit)
    users = (await db.execute(query)).scalars().all()
    
    items = []
    for u in users:
        items.append({
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "avatar": u.avatar,
            "created_at": u.created_at,
            "token_usage": u.token_usage
        })
        
    return {
        "items": items,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if limit else 1
    }

@router.get("/chats")
async def get_chats(
    skip: int = 0, 
    limit: int = 20, 
    search: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = context["tenant_id"]
    
    query = select(Chat).order_by(Chat.updated_at.desc())
    if tenant_id:
        query = query.where(Chat.tenant_id == tenant_id)
        
    if search:
        query = query.where(Chat.title.ilike(f"%{search}%"))
        
    # Total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    
    # Paginate
    query = query.offset(skip).limit(limit)
    chats = (await db.execute(query)).scalars().all()
    
    items = []
    for c in chats:
        items.append({
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "user_id": str(c.user_id)
        })
        
    return {
        "items": items,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if limit else 1
    }

@router.get("/users/{user_id}")
async def get_user_details(
    user_id: str, 
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    try:
        uid = UUID(user_id)
        tenant_id = context["tenant_id"]
        
        query = select(User).where(User.id == uid)
        
        # Verify tenant access
        if tenant_id:
             # Check if this user is in the admin's tenant
             check_mem = await db.execute(
                 select(OrgMembership).where(
                     OrgMembership.user_id == uid, 
                     OrgMembership.tenant_id == tenant_id
                 )
             )
             if not check_mem.scalar_one_or_none():
                 raise HTTPException(status_code=404, detail="User not found")

        user = (await db.execute(query)).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Stats
        chat_count = (await db.execute(
            select(func.count(Chat.id)).where(Chat.user_id == uid)
        )).scalar() or 0
        
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at,
                "role": user.role,
                "avatar": user.avatar,
                "token_usage": user.token_usage
            },
            "stats": {
                "chats_count": chat_count,
                "tokens_used_this_month": user.token_usage
            }
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, 
    user_update: UserUpdate,
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
        # Note: Role updates might need more security logic (e.g. can't promote to system admin)
        
        await db.commit()
        return {"status": "success"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.get("/users/{user_id}/chats")
async def get_user_chats(
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_admin_context),
    db: AsyncSession = Depends(get_db)
):
    # Reuse get_chats logic but filtered by specific user
    try:
        uid = UUID(user_id)
        # We reuse the get_user_details verification logic effectively by just querying
        # If tenant admin requests a user outside tenant, the query below returns nothing if we add tenant check
        
        tenant_id = context["tenant_id"]
        
        query = select(Chat).where(Chat.user_id == uid).order_by(Chat.updated_at.desc())
        
        if tenant_id:
            # Ensure the chat belongs to the tenant (implicitly confirms user does too for that chat)
            query = query.where(Chat.tenant_id == tenant_id)
            
        if search:
            query = query.where(Chat.title.ilike(f"%{search}%"))
            
        # Total
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0
        
        # Paginate
        query = query.offset(skip).limit(limit)
        chats = (await db.execute(query)).scalars().all()
        
        items = []
        for c in chats:
            items.append({
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "user_id": str(c.user_id)
            })
            
        return {
            "items": items,
            "total": total,
            "page": skip // limit + 1,
            "pages": (total + limit - 1) // limit if limit else 1
        }
            
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

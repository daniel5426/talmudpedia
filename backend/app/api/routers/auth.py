from typing import Any, Optional, Dict
import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.db.postgres.models.identity import User, UserRole, Tenant, OrgUnit, OrgMembership, OrgUnitType, OrgRole, MembershipStatus
from app.db.postgres.session import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = None

class Token(BaseModel):
    access_token: str
    token_type: str

class GoogleToken(BaseModel):
    credential: str

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str = None
    avatar: str = None
    role: str = "user" # System role
    tenant_id: Optional[str] = None
    org_unit_id: Optional[str] = None
    org_role: Optional[str] = None # Role within the tenant (owner, admin, member)


# Simple in-memory cache: {user_id: (User, expires_at)}
_user_cache: Dict[str, Any] = {}
CACHE_TTL = 300  # 5 minutes

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)  # Kept for initial fetch and dependency compatibility
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # start_time = time.time()
    try:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id_str: str = payload.get("sub")
            if user_id_str is None:
                raise credentials_exception
            
            # Check Cache
            now = time.time()
            if user_id_str in _user_cache:
                cached_user, expires_at = _user_cache[user_id_str]
                if now < expires_at:
                    # print(f"DEBUG: get_current_user cache hit for {user_id_str}")
                    return cached_user
                else:
                    del _user_cache[user_id_str]

            try:
                user_id = UUID(user_id_str)
            except ValueError:
                raise credentials_exception
                
        except jwt.PyJWTError:
            raise credentials_exception

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception
        
        # Expunge from session to make it safe to cache and reuse across sessions
        db.expunge(user)
        
        # Update Cache
        _user_cache[user_id_str] = (user, now + CACHE_TTL)
        
        # duration = time.time() - start_time
        # print(f"DEBUG: get_current_user took {duration:.4f} seconds (Cache Miss)")
        return user
    except Exception as e:
        # duration = time.time() - start_time
        # print(f"DEBUG: get_current_user failed after {duration:.4f} seconds with error: {e}")
        raise e

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role="admin",
        avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={user_in.full_name or user_in.email}"
    )
    db.add(user)
    await db.flush() # Get user.id

    # Create default tenant and org unit for the new user
    tenant = Tenant(
        name=f"{user.full_name or user.email}'s Organization",
        slug=f"org-{str(user.id)[:8]}"
    )
    db.add(tenant)
    await db.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug="root",
        type=OrgUnitType.org
    )
    db.add(org_unit)
    await db.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active
    )
    db.add(membership)
    
    await db.commit()
    
    return UserResponse(
        id=str(user.id), 
        email=user.email, 
        full_name=user.full_name, 
        avatar=user.avatar, 
        role=user.role,
        tenant_id=str(tenant.id),
        org_unit_id=str(org_unit.id),
        org_role=OrgRole.owner.value
    )

@router.post("/login", response_model=Token)
async def login(db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Get user membership for context
    msg_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id).limit(1)
    )
    membership = msg_result.scalar_one_or_none()
    
    tenant_id = str(membership.tenant_id) if membership else None
    org_unit_id = str(membership.org_unit_id) if membership else None
    org_role = membership.role.value if membership and hasattr(membership, 'role') else None

    # If role is Enum, we access .value, if it's string (legacy or fallback) it's direct.
    # In Pydantic response we need string.
    
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role=org_role
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", response_model=Token)
async def google_auth(token_in: GoogleToken, db: AsyncSession = Depends(get_db)):
    try:
        # Verify the ID token
        id_info = id_token.verify_oauth2_token(
            token_in.credential, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        email = id_info['email']
        google_id = id_info['sub']
        full_name = id_info.get('name')
        avatar = id_info.get('picture')

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}",
        )

    result = await db.execute(select(User).where(or_(User.google_id == google_id, User.email == email)))
    user = result.scalar_one_or_none()
    
    if not user:
        # Create new user
        user = User(
            email=email,
            google_id=google_id,
            full_name=full_name,
            role="admin",
            avatar=avatar or f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or email}"
        )
        db.add(user)
        await db.flush()

        # Create default tenant and org unit for the new user
        tenant = Tenant(
            name=f"{user.full_name or user.email}'s Organization",
            slug=f"org-{str(user.id)[:8]}"
        )
        db.add(tenant)
        await db.flush()

        org_unit = OrgUnit(
            tenant_id=tenant.id,
            name="Root",
            slug="root",
            type=OrgUnitType.org
        )
        db.add(org_unit)
        await db.flush()

        membership = OrgMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            org_unit_id=org_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active
        )
        db.add(membership)
        
        await db.commit()
        await db.refresh(user)
        user_id = str(user.id)
    else:
        user_id = str(user.id)
        # Update google_id if it was missing (e.g. user existed with email but first time using Google)
        if not user.google_id:
            user.google_id = google_id
            await db.commit()

    # Get user membership for context
    try:
        if isinstance(user_id, str):
            user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )

    msg_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user_id).limit(1)
    )
    membership = msg_result.scalar_one_or_none()
    
    tenant_id = str(membership.tenant_id) if membership else None
    org_unit_id = str(membership.org_unit_id) if membership else None
    org_role = membership.role.value if membership and hasattr(membership, 'role') else None

    access_token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role=org_role
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    # Extract context from token if available, or fetch from DB
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    tenant_id = payload.get("tenant_id")
    org_unit_id = payload.get("org_unit_id")

    org_role = payload.get("org_role")

    if not tenant_id or not org_role:
        result = await db.execute(
            select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1)
        )
        membership = result.scalar_one_or_none()
        if membership:
            tenant_id = str(membership.tenant_id)
            org_unit_id = str(membership.org_unit_id)
            # Ensure we get the string value of the Enum
            org_role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)

    return UserResponse(
        id=str(current_user.id), 
        email=current_user.email, 
        full_name=current_user.full_name, 
        avatar=current_user.avatar, 
        role=current_user.role,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role=org_role
    )

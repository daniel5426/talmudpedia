from typing import Any, Optional
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

from app.db.postgres.models.identity import User, UserRole
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
    role: str = "user"

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

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
        avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={user_in.full_name or user_in.email}"
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=str(user.id), email=user.email, full_name=user.full_name, avatar=user.avatar, role=user.role)

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
    access_token = create_access_token(subject=str(user.id))
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
            avatar=avatar or f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or email}"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = str(user.id)
    else:
        user_id = str(user.id)
        # Update google_id if it was missing (e.g. user existed with email but first time using Google)
        if not user.google_id:
            user.google_id = google_id
            await db.commit()

    access_token = create_access_token(subject=user_id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(id=str(current_user.id), email=current_user.email, full_name=current_user.full_name, avatar=current_user.avatar, role=current_user.role)

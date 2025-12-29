from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from app.db.models.user import User
from app.db.connection import MongoDatabase
from app.core.security import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM
from bson import ObjectId
import jwt
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

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

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
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

    db = MongoDatabase.get_db()
    user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if user_doc is None:
        raise credentials_exception
    return User(**user_doc)

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate):
    db = MongoDatabase.get_db()
    existing_user = await db.users.find_one({"email": user_in.email})
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
    result = await db.users.insert_one(user.model_dump(by_alias=True))
    user.id = result.inserted_id
    return UserResponse(id=str(user.id), email=user.email, full_name=user.full_name, avatar=user.avatar, role=user.role)

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = MongoDatabase.get_db()
    user_doc = await db.users.find_one({"email": form_data.username})
    if not user_doc or not verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = User(**user_doc)
    access_token = create_access_token(subject=str(user.id))
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", response_model=Token)
async def google_auth(token_in: GoogleToken):
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

    db = MongoDatabase.get_db()
    
    # Check if user exists by google_id or email
    user_doc = await db.users.find_one({"$or": [{"google_id": google_id}, {"email": email}]})
    
    if not user_doc:
        # Create new user
        user = User(
            email=email,
            google_id=google_id,
            full_name=full_name,
            avatar=avatar or f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or email}"
        )
        result = await db.users.insert_one(user.model_dump(by_alias=True))
        user_id = str(result.inserted_id)
    else:
        user_id = str(user_doc["_id"])
        # Update google_id if it was missing (e.g. user existed with email but first time using Google)
        if not user_doc.get("google_id"):
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"google_id": google_id}}
            )

    access_token = create_access_token(subject=user_id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(id=str(current_user.id), email=current_user.email, full_name=current_user.full_name, avatar=current_user.avatar, role=current_user.role)

from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import jwt
import os
import uuid
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

SECRET_KEY = os.getenv("SECRET_KEY", "YOUR_SECRET_KEY_HERE_CHANGE_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 90 # 90 days (approx 3 months)
PUBLISHED_APP_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("PUBLISHED_APP_ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
PUBLISHED_APP_TOKEN_USE = "published_app_session"
PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES = int(os.getenv("PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES", "5"))
PUBLISHED_APP_PREVIEW_TOKEN_USE = "published_app_preview"

# uses Argon2id for new hashes, but can verify old bcrypt hashes
password_hash = PasswordHash((
    Argon2Hasher(),
))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def create_access_token(
    subject: Union[str, Any], 
    tenant_id: Optional[str] = None,
    org_unit_id: Optional[str] = None,
    org_role: Optional[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    if tenant_id:
        to_encode["tenant_id"] = str(tenant_id)
    if org_unit_id:
        to_encode["org_unit_id"] = str(org_unit_id)
    if org_role:
        to_encode["org_role"] = str(org_role)
        
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_published_app_session_token(
    *,
    subject: Union[str, Any],
    tenant_id: str,
    app_id: str,
    session_id: str,
    provider: str,
    scopes: Optional[list[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=PUBLISHED_APP_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "app_id": str(app_id),
        "session_id": str(session_id),
        "provider": str(provider),
        "token_use": PUBLISHED_APP_TOKEN_USE,
        "scope": scopes or ["public.chat"],
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_published_app_session_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("token_use") != PUBLISHED_APP_TOKEN_USE:
        raise jwt.InvalidTokenError("Invalid token_use")
    if not payload.get("tenant_id") or not payload.get("app_id") or not payload.get("session_id"):
        raise jwt.InvalidTokenError("Invalid published app token claims")
    return payload


def create_published_app_preview_token(
    *,
    subject: Union[str, Any],
    tenant_id: str,
    app_id: str,
    revision_id: str,
    scopes: Optional[list[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "app_id": str(app_id),
        "revision_id": str(revision_id),
        "token_use": PUBLISHED_APP_PREVIEW_TOKEN_USE,
        "scope": scopes or ["apps.preview"],
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_published_app_preview_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("token_use") != PUBLISHED_APP_PREVIEW_TOKEN_USE:
        raise jwt.InvalidTokenError("Invalid token_use")
    if not payload.get("tenant_id") or not payload.get("app_id") or not payload.get("revision_id"):
        raise jwt.InvalidTokenError("Invalid published app preview token claims")
    return payload

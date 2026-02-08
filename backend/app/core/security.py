from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import jwt
import os
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

SECRET_KEY = os.getenv("SECRET_KEY", "YOUR_SECRET_KEY_HERE_CHANGE_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 90 # 90 days (approx 3 months)

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

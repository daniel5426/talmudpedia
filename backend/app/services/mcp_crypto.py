from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.security import SECRET_KEY


def _fernet() -> Fernet:
    raw_key = (os.getenv("MCP_ENCRYPTION_KEY") or "").strip() or SECRET_KEY
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(value: str | None) -> str | None:
    if value in {None, ""}:
        return None
    return _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    if value in {None, ""}:
        return None
    try:
        return _fernet().decrypt(str(value).encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt MCP secret payload") from exc


def encrypt_json(value: Any) -> str | None:
    if value is None or value == "" or value == {} or value == []:
        return None
    return encrypt_text(json.dumps(value))


def decrypt_json(value: str | None) -> Any:
    raw = decrypt_text(value)
    if raw in {None, ""}:
        return None
    return json.loads(raw)


def generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def build_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

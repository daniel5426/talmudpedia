from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException, Request, Response
from jwt import ExpiredSignatureError, PyJWTError

from app.core.security import (
    PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES,
    create_published_app_preview_token,
    decode_published_app_preview_token,
)

PREVIEW_COOKIE_NAME = "published_app_preview_token"
PREVIEW_SCOPE = "apps.preview"
PREVIEW_TARGET_DRAFT_DEV_SESSION = "draft_dev_session"
PREVIEW_TARGET_REVISION = "revision"


def append_preview_runtime_token(url: str, token: str | None) -> str:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        return url
    parsed = urlparse(str(url or "").strip())
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["runtime_token"] = normalized_token
    return urlunparse(parsed._replace(query=urlencode(query)))


def create_preview_token(
    *,
    subject: str,
    organization_id: str,
    app_id: str,
    preview_target_type: str,
    preview_target_id: str,
    revision_id: str | None = None,
) -> str:
    return create_published_app_preview_token(
        subject=subject,
        organization_id=organization_id,
        app_id=app_id,
        preview_target_type=preview_target_type,
        preview_target_id=preview_target_id,
        revision_id=revision_id,
        scopes=[PREVIEW_SCOPE],
        expires_delta=timedelta(minutes=PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES),
    )


def set_preview_cookie(*, response: Response, request: Request, token: str | None) -> None:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        return
    response.set_cookie(
        key=PREVIEW_COOKIE_NAME,
        value=normalized_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def clear_preview_cookie(*, response: Response) -> None:
    response.delete_cookie(
        key=PREVIEW_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        path="/",
    )


def decode_preview_token(token: str) -> dict[str, Any]:
    try:
        payload = decode_published_app_preview_token(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Preview token has expired") from exc
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Preview token is invalid") from exc
    scopes = payload.get("scope") or []
    if PREVIEW_SCOPE not in scopes:
        raise HTTPException(status_code=403, detail="Preview token is missing apps.preview scope")
    return payload


def token_matches_target(
    payload: dict[str, Any],
    *,
    app_id: str,
    preview_target_type: str,
    preview_target_id: str,
    revision_id: str | None = None,
) -> bool:
    if str(payload.get("app_id") or "").strip() != str(app_id):
        return False
    if str(payload.get("preview_target_type") or "").strip() != str(preview_target_type):
        return False
    if str(payload.get("preview_target_id") or "").strip() != str(preview_target_id):
        return False
    if revision_id is None:
        return True
    return str(payload.get("revision_id") or "").strip() == str(revision_id)


def resolve_preview_token(
    *,
    request: Request,
    matcher: Callable[[dict[str, Any]], bool],
) -> tuple[str, dict[str, Any], str]:
    cookie_token = str(request.cookies.get(PREVIEW_COOKIE_NAME) or "").strip()
    query_token = str(request.query_params.get("runtime_token") or "").strip()
    first_auth_error: HTTPException | None = None
    mismatch_seen = False

    for source, token in (("cookie", cookie_token), ("query", query_token)):
        if not token:
            continue
        try:
            payload = decode_preview_token(token)
        except HTTPException as exc:
            if first_auth_error is None:
                first_auth_error = exc
            continue
        if not matcher(payload):
            mismatch_seen = True
            continue
        return token, payload, source

    if first_auth_error is not None:
        raise first_auth_error
    if mismatch_seen:
        raise HTTPException(status_code=403, detail="Preview token does not match preview target scope")
    raise HTTPException(status_code=401, detail="Preview authentication required")

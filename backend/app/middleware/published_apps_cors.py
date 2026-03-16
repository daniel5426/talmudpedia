from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.published_apps import PublishedApp


def _normalize_origin(origin: str) -> str:
    parsed = urlparse((origin or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")


def _match_public_app_slug(path: str) -> Optional[str]:
    normalized = (path or "").strip()
    for prefix in ("/public/apps/", "/public/external/apps/"):
        if not normalized.startswith(prefix):
            continue
        suffix = normalized[len(prefix) :]
        if not suffix:
            return None
        slug = suffix.split("/", 1)[0].strip().lower()
        if prefix == "/public/apps/" and slug in {"preview", "resolve"}:
            return None
        return slug or None
    return None


class PublishedAppsCORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        origin = _normalize_origin(request.headers.get("origin") or "")
        if not origin:
            return await call_next(request)

        slug = _match_public_app_slug(request.url.path)
        if not slug:
            return await call_next(request)

        allowed = await self._is_allowed_origin(slug=slug, origin=origin, request=request)

        is_preflight = (
            request.method.upper() == "OPTIONS"
            and bool(request.headers.get("access-control-request-method"))
        )

        if is_preflight:
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origin is not allowed for this published app"},
                )
            return self._build_preflight_response(origin)

        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": "Origin is not allowed for this published app"},
            )

        response = await call_next(request)
        self._apply_cors_headers(response=response, origin=origin)
        return response

    async def _is_allowed_origin(self, *, slug: str, origin: str, request: Request) -> bool:
        request_origin = _normalize_origin(str(request.base_url).rstrip("/"))
        if request_origin and request_origin == origin:
            return True

        async with sessionmaker() as db:
            result = await db.execute(select(PublishedApp).where(PublishedApp.slug == slug).limit(1))
            app = result.scalar_one_or_none()
        if app is None:
            return False

        allowed_origins = {
            _normalize_origin(item)
            for item in list(app.allowed_origins or [])
            if isinstance(item, str)
        }
        if app.published_url:
            allowed_origins.add(_normalize_origin(app.published_url))
        allowed_origins.discard("")

        return origin in allowed_origins

    @staticmethod
    def _apply_cors_headers(response: Response, origin: str) -> None:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,X-Requested-With"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "X-Thread-ID"
        vary = response.headers.get("Vary")
        if vary:
            if "Origin" not in vary:
                response.headers["Vary"] = f"{vary}, Origin"
        else:
            response.headers["Vary"] = "Origin"

    def _build_preflight_response(self, origin: str) -> Response:
        response = Response(status_code=204)
        self._apply_cors_headers(response=response, origin=origin)
        return response

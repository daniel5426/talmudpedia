from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.dependencies import get_current_principal
from app.core.scope_registry import get_required_scopes_for_action
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError, feature_disabled, policy_denied, scope_denied, tenant_mismatch, validation
from app.services.orchestration_policy_service import ORCHESTRATION_SURFACE_OPTION_B, is_orchestration_surface_enabled
from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS


logger = logging.getLogger("platform.native")

PUBLISH_ACTIONS = {"agents.publish", "tools.publish", "artifacts.publish"}


def parse_uuid(raw: Any) -> UUID | None:
    if raw in (None, ""):
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


def request_stub() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/internal/platform-tools", "headers": []})


def serialize_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_value(val) for key, val in value.items()}
    return value


class NativePlatformToolRuntime:
    def __init__(self, *, db: AsyncSession, tool_slug: str, inputs: dict[str, Any]):
        self.db = db
        self.tool_slug = tool_slug
        self.raw_inputs = dict(inputs or {})
        self.runtime_context = dict(self.raw_inputs.get("__tool_runtime_context__") or {})
        self.inputs = {key: value for key, value in self.raw_inputs.items() if key != "__tool_runtime_context__"}
        self.payload = dict(self.inputs.get("payload") or {})
        self.action = str(self.inputs.get("action") or "").strip()
        self.dry_run = bool(self.inputs.get("dry_run") or self.payload.get("dry_run", False))
        self._principal: dict[str, Any] | None = None

    async def resolve_principal(self) -> dict[str, Any]:
        if self._principal is not None:
            return self._principal
        token = self.runtime_context.get("token") or self.runtime_context.get("auth_token")
        architect_scopes = self.runtime_context.get("architect_effective_scopes")
        if isinstance(token, str) and token.strip():
            try:
                principal = await get_current_principal(token=token.strip(), db=self.db)
                if isinstance(architect_scopes, list):
                    principal = {
                        **principal,
                        "scopes": [str(item) for item in architect_scopes if str(item).strip()],
                        "architect_mode": self.runtime_context.get("architect_mode"),
                    }
                self._principal = principal
                return principal
            except Exception:
                pass
        tenant_id = self.runtime_context.get("tenant_id")
        user_id = self.runtime_context.get("user_id") or self.runtime_context.get("initiator_user_id")
        scopes = (
            [str(item) for item in architect_scopes if str(item).strip()]
            if isinstance(architect_scopes, list)
            else [str(item) for item in (self.runtime_context.get("scopes") or ["*"])]
        )
        self._principal = {
            "type": "user",
            "tenant_id": str(tenant_id) if tenant_id is not None else None,
            "user_id": str(user_id) if user_id is not None else None,
            "user": None,
            "scopes": scopes,
            "auth_token": token,
            "architect_mode": self.runtime_context.get("architect_mode"),
        }
        return self._principal

    async def build_control_plane_context(self) -> ControlPlaneContext:
        principal = await self.resolve_principal()
        tenant_id = principal.get("tenant_id")
        if tenant_id is None:
            raise validation("Tenant context required", field="tenant_id")
        return ControlPlaneContext(
            tenant_id=UUID(str(tenant_id)),
            user=principal.get("user"),
            user_id=parse_uuid(principal.get("user_id") or getattr(principal.get("user"), "id", None)),
            auth_token=principal.get("auth_token"),
            scopes=tuple(principal.get("scopes") or ()),
            is_service=bool(principal.get("type") == "workload"),
        )

    async def build_agent_context(self) -> dict[str, Any]:
        principal = await self.resolve_principal()
        return {
            "user": principal.get("user"),
            "tenant_id": principal.get("tenant_id"),
            "auth_token": principal.get("auth_token"),
            "initiator_user_id": principal.get("initiator_user_id"),
            "scopes": principal.get("scopes", []),
            "architect_mode": principal.get("architect_mode"),
        }

    async def build_tools_context(self) -> dict[str, Any]:
        principal = await self.resolve_principal()
        tenant_id = principal.get("tenant_id")
        return {
            "tenant_id": str(tenant_id) if tenant_id else None,
            "tenant": SimpleNamespace(id=UUID(str(tenant_id))) if tenant_id else None,
            "user": principal.get("user"),
            "is_service": bool(principal.get("type") == "workload"),
        }

    async def validate(self) -> None:
        if not self.action:
            raise validation("Missing required field: action", field="action")
        allowed = PLATFORM_ARCHITECT_DOMAIN_TOOLS.get(self.tool_slug, {}).get("actions", {})
        if self.action not in allowed:
            raise scope_denied(
                f"Action '{self.action}' is not allowed by tool '{self.tool_slug}'.",
                action=self.action,
                tool_slug=self.tool_slug,
            )
        explicit_tenant_id = self.payload.get("tenant_id") or self.inputs.get("tenant_id")
        runtime_tenant_id = self.runtime_context.get("tenant_id")
        if explicit_tenant_id and runtime_tenant_id and str(explicit_tenant_id) != str(runtime_tenant_id):
            raise tenant_mismatch(
                "Tenant override is not allowed; runtime tenant context is authoritative.",
                runtime_tenant_id=str(runtime_tenant_id),
                requested_tenant_id=str(explicit_tenant_id),
            )
        principal = await self.resolve_principal()
        required_scopes = sorted(set(get_required_scopes_for_action(self.action)))
        scopes = set(principal.get("scopes") or [])
        if required_scopes and "*" not in scopes and any(scope not in scopes for scope in required_scopes):
            raise scope_denied(
                f"Action '{self.action}' requires scopes: {', '.join(required_scopes)}",
                required_scopes=required_scopes,
            )
        if self.action in PUBLISH_ACTIONS and not bool((self.payload.get("objective_flags") or {}).get("allow_publish") or self.payload.get("allow_publish") or self.inputs.get("allow_publish")):
            raise policy_denied(
                f"Action '{self.action}' requires explicit publish intent.",
            )
        if self.action.startswith("orchestration."):
            tenant_id = principal.get("tenant_id")
            if not is_orchestration_surface_enabled(surface=ORCHESTRATION_SURFACE_OPTION_B, tenant_id=tenant_id):
                raise feature_disabled("Runtime orchestration primitives are disabled by feature flag for this tenant")


def _finalize_success(*, action: str, tool_slug: str, result: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    request_metadata = inputs.get("payload", {}).get("request_metadata") if isinstance(inputs.get("payload"), dict) else {}
    return {
        "result": serialize_value(result),
        "errors": [],
        "action": action,
        "dry_run": bool(inputs.get("dry_run")),
        "meta": {
            "trace_id": str(request_metadata.get("trace_id")) if isinstance(request_metadata, dict) and request_metadata.get("trace_id") else None,
            "request_id": str(request_metadata.get("request_id")) if isinstance(request_metadata, dict) and request_metadata.get("request_id") else None,
            "idempotency_key": str(inputs.get("idempotency_key")) if inputs.get("idempotency_key") else None,
            "idempotency_provided": bool(inputs.get("idempotency_key")),
            "tool_slug": tool_slug,
        },
    }


def _finalize_error(*, action: str, tool_slug: str, error: ControlPlaneError | HTTPException | Exception, inputs: dict[str, Any]) -> dict[str, Any]:
    if isinstance(error, ControlPlaneError):
        payload = error.to_payload()
    elif isinstance(error, HTTPException):
        payload = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
        payload.setdefault("code", "HTTP_ERROR")
        payload.setdefault("message", str(payload.get("message") or "Request failed"))
        payload.setdefault("http_status", error.status_code)
        payload.setdefault("retryable", False)
    else:
        payload = {"code": "INTERNAL_ERROR", "message": str(error), "http_status": 500, "retryable": False}
    request_metadata = inputs.get("payload", {}).get("request_metadata") if isinstance(inputs.get("payload"), dict) else {}
    return {
        "result": {
            "status": "validation_error" if int(payload.get("http_status") or 500) < 500 else "failed",
            "message": payload.get("message"),
        },
        "errors": [payload],
        "action": action,
        "dry_run": bool(inputs.get("dry_run")),
        "meta": {
            "trace_id": str(request_metadata.get("trace_id")) if isinstance(request_metadata, dict) and request_metadata.get("trace_id") else None,
            "request_id": str(request_metadata.get("request_id")) if isinstance(request_metadata, dict) and request_metadata.get("request_id") else None,
            "idempotency_key": str(inputs.get("idempotency_key")) if inputs.get("idempotency_key") else None,
            "idempotency_provided": bool(inputs.get("idempotency_key")),
            "tool_slug": tool_slug,
        },
    }


async def dispatch_native_platform_tool(
    *,
    db: AsyncSession,
    tool_slug: str,
    inputs: dict[str, Any],
    handlers: dict[str, Callable[[NativePlatformToolRuntime], Awaitable[Any]]],
) -> dict[str, Any]:
    runtime = NativePlatformToolRuntime(db=db, tool_slug=tool_slug, inputs=inputs)
    try:
        await runtime.validate()
        handler = handlers[runtime.action]
        logger.info(
            "platform_native.dispatch",
            extra={
                "tool_slug": tool_slug,
                "action": runtime.action,
                "payload_keys": sorted(runtime.payload.keys()),
                "runtime_context_keys": sorted(runtime.runtime_context.keys()),
                "dispatch_target": f"{handler.__module__}.{handler.__name__}",
            },
        )
        result = await handler(runtime)
        logger.info(
            "platform_native.result",
            extra={"tool_slug": tool_slug, "action": runtime.action, "result_category": "success"},
        )
        return _finalize_success(action=runtime.action, tool_slug=tool_slug, result=result, inputs=runtime.inputs)
    except Exception as exc:
        logger.info(
            "platform_native.result",
            extra={
                "tool_slug": tool_slug,
                "action": runtime.action,
                "result_category": "error",
                "error_type": exc.__class__.__name__,
            },
        )
        return _finalize_error(action=runtime.action, tool_slug=tool_slug, error=exc, inputs=runtime.inputs)

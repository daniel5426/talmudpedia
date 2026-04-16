from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ControlPlaneContext:
    tenant_id: UUID
    project_id: UUID | None = None
    user: Any | None = None
    user_id: UUID | None = None
    auth_token: str | None = None
    scopes: tuple[str, ...] = ()
    is_service: bool = False
    tenant_slug: str | None = None

    @classmethod
    def from_tenant_context(
        cls,
        tenant_ctx: dict[str, Any],
        *,
        project_id: UUID | None = None,
        user: Any | None = None,
        user_id: UUID | None = None,
        auth_token: str | None = None,
        scopes: list[str] | tuple[str, ...] | None = None,
        is_service: bool = False,
        tenant_slug: str | None = None,
    ) -> "ControlPlaneContext":
        tenant_id = UUID(str(tenant_ctx["tenant_id"]))
        resolved_project_id = project_id
        if resolved_project_id is None:
            raw_project_id = tenant_ctx.get("project_id")
            try:
                resolved_project_id = UUID(str(raw_project_id)) if raw_project_id else None
            except Exception:
                resolved_project_id = None
        return cls(
            tenant_id=tenant_id,
            project_id=resolved_project_id,
            user=user,
            user_id=user_id,
            auth_token=auth_token,
            scopes=tuple(scopes or ()),
            is_service=is_service,
            tenant_slug=tenant_slug,
        )

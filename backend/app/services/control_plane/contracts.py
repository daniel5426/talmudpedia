from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.control_plane.errors import validation


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
ALLOWED_LIST_VIEWS = {"summary", "full"}


@dataclass(frozen=True)
class ListQuery:
    limit: int = DEFAULT_LIST_LIMIT
    skip: int = 0
    view: str = "summary"
    filters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
        *,
        default_limit: int = DEFAULT_LIST_LIMIT,
        max_limit: int = MAX_LIST_LIMIT,
    ) -> "ListQuery":
        source = dict(payload or {})
        raw_limit = source.get("limit", default_limit)
        raw_skip = source.get("skip", 0)
        raw_view = source.get("view", "summary")
        try:
            limit = int(raw_limit)
        except Exception as exc:
            raise validation("limit must be an integer", field="limit", value=raw_limit) from exc
        try:
            skip = int(raw_skip)
        except Exception as exc:
            raise validation("skip must be an integer", field="skip", value=raw_skip) from exc
        if limit < 1 or limit > max_limit:
            raise validation(
                f"limit must be between 1 and {max_limit}",
                field="limit",
                value=limit,
                max_limit=max_limit,
            )
        if skip < 0:
            raise validation("skip must be >= 0", field="skip", value=skip)
        view = str(raw_view or "summary").strip().lower()
        if view not in ALLOWED_LIST_VIEWS:
            raise validation(
                "view must be one of: summary, full",
                field="view",
                value=raw_view,
                allowed=sorted(ALLOWED_LIST_VIEWS),
            )
        return cls(
            limit=limit,
            skip=skip,
            view=view,
            filters={},
        )


@dataclass(frozen=True)
class ListPage:
    items: list[Any]
    total: int
    query: ListQuery

    @property
    def has_more(self) -> bool:
        return self.query.skip + len(self.items) < self.total

    def to_payload(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "has_more": self.has_more,
            "skip": self.query.skip,
            "limit": self.query.limit,
            "view": self.query.view,
        }


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    kind: str
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "operation": {
                "id": self.operation_id,
                "kind": self.kind,
                "status": self.status,
            }
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException


@dataclass
class ControlPlaneError(Exception):
    code: str
    message: str
    http_status: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_http_exception(self) -> HTTPException:
        detail = {"code": self.code, "message": self.message}
        if self.details:
            detail["details"] = self.details
        return HTTPException(status_code=self.http_status, detail=detail)


def not_found(message: str) -> ControlPlaneError:
    return ControlPlaneError(code="NOT_FOUND", message=message, http_status=404)


def conflict(message: str) -> ControlPlaneError:
    return ControlPlaneError(code="CONFLICT", message=message, http_status=409)


def validation(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="VALIDATION_ERROR", message=message, http_status=422, details=details)


def forbidden(message: str) -> ControlPlaneError:
    return ControlPlaneError(code="FORBIDDEN", message=message, http_status=403)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException


@dataclass
class ControlPlaneError(Exception):
    code: str
    message: str
    http_status: int
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def to_http_exception(self) -> HTTPException:
        return HTTPException(status_code=self.http_status, detail=self.to_payload())


def not_found(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="NOT_FOUND", message=message, http_status=404, details=details)


def conflict(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="CONFLICT", message=message, http_status=409, details=details)


def validation(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="VALIDATION_ERROR", message=message, http_status=422, details=details)


def unauthorized(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="UNAUTHORIZED", message=message, http_status=401, details=details)


def forbidden(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="FORBIDDEN", message=message, http_status=403, details=details)


def scope_denied(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="SCOPE_DENIED", message=message, http_status=403, details=details)


def tenant_mismatch(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="TENANT_MISMATCH", message=message, http_status=403, details=details)


def feature_disabled(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="FEATURE_DISABLED", message=message, http_status=403, details=details)


def policy_denied(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="POLICY_DENIED", message=message, http_status=403, details=details)


def rate_limited(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(code="RATE_LIMITED", message=message, http_status=429, details=details)


def upstream_failure(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(
        code="UPSTREAM_FAILURE",
        message=message,
        http_status=502,
        retryable=True,
        details=details,
    )


def internal_failure(message: str, **details: Any) -> ControlPlaneError:
    return ControlPlaneError(
        code="INTERNAL_ERROR",
        message=message,
        http_status=500,
        retryable=False,
        details=details,
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ControlPlaneSDKError(Exception):
    code: str
    message: str
    http_status: Optional[int] = None
    retryable: bool = False
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        status = f" (http={self.http_status})" if self.http_status is not None else ""
        return f"{self.code}: {self.message}{status}"

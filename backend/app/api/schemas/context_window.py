from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ContextWindowResponse(BaseModel):
    source: Literal["exact", "estimated", "unknown"] = "unknown"
    model_id: Optional[str] = None
    max_tokens: Optional[int] = None
    max_tokens_source: Optional[str] = None
    input_tokens: Optional[int] = None
    remaining_tokens: Optional[int] = None
    usage_ratio: Optional[float] = None

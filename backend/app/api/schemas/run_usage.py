from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class RunUsageResponse(BaseModel):
    source: Literal["exact", "estimated", "unknown"] = "unknown"
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: int = 0
    cached_input_tokens: Optional[int] = None
    cached_output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None

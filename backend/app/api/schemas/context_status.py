from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ContextStatusUsageResponse(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    cached_output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None


class ContextStatusResponse(BaseModel):
    model_id: Optional[str] = None
    max_tokens: Optional[int] = None
    max_tokens_source: Optional[str] = None
    reserved_output_tokens: Optional[int] = None
    estimated_input_tokens: Optional[int] = None
    estimated_total_tokens: Optional[int] = None
    estimated_remaining_tokens: Optional[int] = None
    estimated_usage_ratio: Optional[float] = None
    near_limit: bool = False
    compaction_recommended: bool = False
    source: Literal["estimated_pre_run", "estimated_in_flight", "estimated_plus_actual"] = "estimated_pre_run"
    actual_usage: Optional[ContextStatusUsageResponse] = None

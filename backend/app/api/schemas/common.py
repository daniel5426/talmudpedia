from typing import Optional
from pydantic import BaseModel, Field

class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)
    order_by: Optional[str] = None
    order: Optional[str] = "desc"

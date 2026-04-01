from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class StaleExecutablePipelineError(RuntimeError):
    code = "EXECUTABLE_PIPELINE_STALE"

    def __init__(
        self,
        *,
        visual_pipeline_id: Any,
        executable_pipeline_id: Any,
        visual_updated_at: datetime | None,
        executable_created_at: datetime | None,
    ) -> None:
        self.visual_pipeline_id = str(visual_pipeline_id)
        self.executable_pipeline_id = str(executable_pipeline_id)
        self.visual_updated_at = visual_updated_at
        self.executable_created_at = executable_created_at
        super().__init__(
            "Pipeline draft changed since the latest executable was created. Compile the pipeline again before running it."
        )

    def to_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "visual_pipeline_id": self.visual_pipeline_id,
            "executable_pipeline_id": self.executable_pipeline_id,
            "visual_updated_at": self.visual_updated_at.isoformat() if self.visual_updated_at else None,
            "executable_created_at": self.executable_created_at.isoformat() if self.executable_created_at else None,
        }


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_executable_pipeline_stale(visual_pipeline: Any, executable_pipeline: Any) -> bool:
    visual_updated_at = _normalize_datetime(getattr(visual_pipeline, "updated_at", None))
    executable_created_at = _normalize_datetime(getattr(executable_pipeline, "created_at", None))
    if visual_updated_at is None or executable_created_at is None:
        return False
    return visual_updated_at > executable_created_at


def ensure_executable_pipeline_is_current(visual_pipeline: Any, executable_pipeline: Any) -> None:
    if not is_executable_pipeline_stale(visual_pipeline, executable_pipeline):
        return
    raise StaleExecutablePipelineError(
        visual_pipeline_id=getattr(visual_pipeline, "id", None),
        executable_pipeline_id=getattr(executable_pipeline, "id", None),
        visual_updated_at=getattr(visual_pipeline, "updated_at", None),
        executable_created_at=getattr(executable_pipeline, "created_at", None),
    )

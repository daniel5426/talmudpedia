from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.rag_executable_state import (
    StaleExecutablePipelineError,
    ensure_executable_pipeline_is_current,
    is_executable_pipeline_stale,
)


def _visual_pipeline(updated_at: datetime):
    return SimpleNamespace(id="visual-1", updated_at=updated_at)


def _executable_pipeline(created_at: datetime):
    return SimpleNamespace(id="exec-1", created_at=created_at)


def test_is_executable_pipeline_stale_detects_newer_visual_draft():
    created_at = datetime.now(timezone.utc)
    updated_at = created_at + timedelta(minutes=5)

    assert is_executable_pipeline_stale(_visual_pipeline(updated_at), _executable_pipeline(created_at)) is True


def test_ensure_executable_pipeline_is_current_raises_for_stale_executable():
    created_at = datetime.now(timezone.utc)
    updated_at = created_at + timedelta(minutes=5)

    with pytest.raises(StaleExecutablePipelineError) as exc_info:
        ensure_executable_pipeline_is_current(_visual_pipeline(updated_at), _executable_pipeline(created_at))

    assert exc_info.value.to_detail()["code"] == "EXECUTABLE_PIPELINE_STALE"


def test_ensure_executable_pipeline_is_current_accepts_fresh_executable():
    created_at = datetime.now(timezone.utc)
    updated_at = created_at - timedelta(minutes=5)

    ensure_executable_pipeline_is_current(_visual_pipeline(updated_at), _executable_pipeline(created_at))

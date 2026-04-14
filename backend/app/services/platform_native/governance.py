from __future__ import annotations

from typing import Any

from app.services.control_plane.orchestration_admin_service import OrchestrationAdminService
from app.services.platform_native.runtime import NativePlatformToolRuntime, parse_uuid


async def orchestration_join(rt: NativePlatformToolRuntime) -> Any:
    return await OrchestrationAdminService(rt.db).join(
        caller_run_id=parse_uuid(rt.payload.get("caller_run_id")),
        orchestration_group_id=parse_uuid(rt.payload.get("orchestration_group_id")),
        mode=rt.payload.get("mode"),
        quorum_threshold=rt.payload.get("quorum_threshold"),
        timeout_s=rt.payload.get("timeout_s"),
    )


async def orchestration_cancel_subtree(rt: NativePlatformToolRuntime) -> Any:
    return await OrchestrationAdminService(rt.db).cancel_subtree(
        caller_run_id=parse_uuid(rt.payload.get("caller_run_id")),
        run_id=parse_uuid(rt.payload.get("run_id")),
        include_root=bool(rt.payload.get("include_root", True)),
        reason=rt.payload.get("reason"),
    )


async def orchestration_evaluate_and_replan(rt: NativePlatformToolRuntime) -> Any:
    return await OrchestrationAdminService(rt.db).evaluate_and_replan(
        caller_run_id=parse_uuid(rt.payload.get("caller_run_id")),
        run_id=parse_uuid(rt.payload.get("run_id")),
    )


async def orchestration_query_tree(rt: NativePlatformToolRuntime) -> Any:
    return await OrchestrationAdminService(rt.db).query_tree(run_id=parse_uuid(rt.payload.get("run_id")))

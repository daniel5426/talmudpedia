from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService

logger = logging.getLogger(__name__)

CODING_AGENT_ENGINE_OPENCODE = "opencode"
_WORKSPACE_WRITE_TOOL_HINTS = (
    "write",
    "edit",
    "replace",
    "insert",
    "append",
    "prepend",
    "rename",
    "move",
    "delete",
    "remove",
    "mkdir",
    "touch",
    "create",
    "apply_patch",
    "mv",
    "rm",
    "cp",
    "bash",
    "command",
    "exec",
)


class PublishedAppCodingAgentRuntimeSandboxMixin:
    @staticmethod
    def _normalize_workspace_path(path: str | None) -> str:
        return str(path or "").strip().rstrip("/")

    @classmethod
    def _workspace_paths_match(cls, left: str | None, right: str | None) -> bool:
        normalized_left = cls._normalize_workspace_path(left)
        normalized_right = cls._normalize_workspace_path(right)
        if not normalized_left or not normalized_right:
            return False
        return normalized_left == normalized_right

    async def _count_active_runs_for_scope(
        self,
        *,
        app_id: UUID,
        actor_id: UUID,
        exclude_run_id: UUID | None = None,
    ) -> int:
        _ = actor_id
        conditions = [
            AgentRun.surface == CODING_AGENT_SURFACE,
            AgentRun.published_app_id == app_id,
            AgentRun.status.in_([RunStatus.queued, RunStatus.running]),
        ]
        if exclude_run_id is not None:
            conditions.append(AgentRun.id != exclude_run_id)
        result = await self.db.execute(select(func.count(AgentRun.id)).where(and_(*conditions)))
        return int(result.scalar() or 0)

    @staticmethod
    def _local_telemetry_file_path() -> Path | None:
        raw = str(os.getenv("APPS_CODING_AGENT_LOCAL_TELEMETRY_FILE_PATH") or "").strip()
        disabled_values = {"0", "false", "off", "none", "disabled"}
        if raw.lower() in disabled_values:
            return None
        if raw:
            return Path(raw).expanduser()
        dev_shim_enabled = str(os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "0") or "").strip().lower()
        if dev_shim_enabled in {"1", "true", "yes", "on"}:
            return Path("/tmp/talmudpedia-coding-agent-telemetry.ndjson")
        return None

    def _append_local_telemetry_snapshot(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        terminal_event: str,
        assistant_delta_events: int,
        saw_write_tool_event: bool,
        revision_created: bool,
    ) -> None:
        path = self._local_telemetry_file_path()
        if path is None:
            return
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        timing_metrics = context.get("timing_metrics_ms") if isinstance(context.get("timing_metrics_ms"), dict) else {}
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run.id),
            "app_id": str(app.id),
            "engine": str(run.execution_engine or CODING_AGENT_ENGINE_OPENCODE),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "terminal_event": terminal_event,
            "assistant_delta_events": int(max(0, assistant_delta_events)),
            "saw_write_tool_event": bool(saw_write_tool_event),
            "revision_created": bool(revision_created),
            "error": str(run.error_message or ""),
            "timing_metrics_ms": timing_metrics,
            "started_at": run.started_at.isoformat() if isinstance(run.started_at, datetime) else None,
            "completed_at": run.completed_at.isoformat() if isinstance(run.completed_at, datetime) else None,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str, sort_keys=True))
                handle.write("\n")
        except Exception as exc:
            logger.warning("Failed to append local coding-agent telemetry snapshot path=%s error=%s", path, exc)

    @staticmethod
    def _is_workspace_write_tool_event(*, event: str, payload: dict[str, Any] | None) -> bool:
        if event not in {"tool.started", "tool.completed"}:
            return False
        tool_name = str((payload or {}).get("tool") or "").strip().lower()
        if not tool_name:
            return False
        return any(hint in tool_name for hint in _WORKSPACE_WRITE_TOOL_HINTS)

    async def _ensure_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
    ) -> dict[str, Any]:
        if actor_id is None:
            raise self._engine_unsupported_runtime_error(
                "Coding-agent preview session requires a user-scoped run."
            )
        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        try:
            session = await runtime_service.ensure_active_session(
                app=app,
                revision=base_revision,
                user_id=actor_id,
            )
        except PublishedAppDraftDevRuntimeDisabled as exc:
            raise self._engine_unsupported_runtime_error(str(exc)) from exc

        status = session.status.value if hasattr(session.status, "value") else str(session.status)
        if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
            raise self._engine_unsupported_runtime_error(
                f"Failed to initialize preview sandbox session: {session.last_error or 'unknown error'}"
            )
        sandbox_id = str(session.sandbox_id)
        live_workspace_path = str(
            await runtime_service.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or ""
        ).strip()
        started_at = datetime.now(timezone.utc).isoformat()
        context = self._run_context(run)
        context["preview_sandbox_id"] = sandbox_id
        context["preview_sandbox_status"] = status
        context["preview_sandbox_started_at"] = started_at
        context["preview_workspace_live_path"] = live_workspace_path or "/workspace"
        context["opencode_sandbox_id"] = sandbox_id
        context["opencode_workspace_path"] = live_workspace_path or "/workspace"
        return {
            "preview_sandbox_id": sandbox_id,
            "preview_sandbox_status": status,
            "preview_sandbox_started_at": started_at,
            "preview_workspace_live_path": live_workspace_path or "/workspace",
            "opencode_sandbox_id": sandbox_id,
            "opencode_workspace_path": live_workspace_path or "/workspace",
            "stage_prepare_ms": 0,
        }

    async def _recover_or_bootstrap_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
    ) -> tuple[str | None, str | None]:
        context = self._run_context(run)
        sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        if sandbox_id:
            changed = False
            if not str(context.get("opencode_sandbox_id") or "").strip():
                context["opencode_sandbox_id"] = sandbox_id
                changed = True
            live_workspace_path = str(context.get("preview_workspace_live_path") or "").strip()
            opencode_workspace_path = str(context.get("opencode_workspace_path") or "").strip()
            if not live_workspace_path:
                runtime_service = PublishedAppDraftDevRuntimeService(self.db)
                try:
                    live_workspace_path = str(
                        await runtime_service.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or ""
                    ).strip()
                except Exception as exc:
                    return None, f"Preview sandbox session is required before execution ({exc})."
                if live_workspace_path:
                    context["preview_workspace_live_path"] = live_workspace_path
                    changed = True
            if live_workspace_path and not opencode_workspace_path:
                context["opencode_workspace_path"] = live_workspace_path
                opencode_workspace_path = live_workspace_path
                changed = True
            if not live_workspace_path or not opencode_workspace_path:
                return None, "Preview sandbox session is required before execution (workspace missing)."
            if changed:
                await self.db.commit()
            return sandbox_id, None

        base_revision_id = run.base_revision_id or app.current_draft_revision_id
        if base_revision_id is None:
            return None, "Preview sandbox session is required before execution (base revision missing)."
        base_revision = await self.db.get(PublishedAppRevision, base_revision_id)
        if base_revision is None:
            return None, "Preview sandbox session is required before execution (base revision not found)."

        actor_id = run.initiator_user_id or run.user_id
        try:
            context.update(
                await self._ensure_run_sandbox_context(
                    run=run,
                    app=app,
                    base_revision=base_revision,
                    actor_id=actor_id,
                )
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            message = str(detail.get("message") or exc.detail or "preview bootstrap failed")
            return None, f"Preview sandbox session is required before execution ({message})."
        except Exception as exc:
            return None, f"Preview sandbox session is required before execution ({exc})."
        sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        await self.db.commit()
        if sandbox_id:
            return sandbox_id, None
        return None, "Preview sandbox session is required before execution."

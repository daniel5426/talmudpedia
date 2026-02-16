from __future__ import annotations

from datetime import datetime, timezone
import json
from hashlib import sha256
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionEvent, ExecutionMode
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_profile import ensure_coding_agent_profile
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.api.routers.published_apps_admin_files import _validate_builder_project_or_raise


class PublishedAppCodingAgentRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.executor = AgentExecutorService(db=db)

    @staticmethod
    def serialize_run(run: AgentRun) -> dict[str, Any]:
        return {
            "run_id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "surface": run.surface,
            "published_app_id": str(run.published_app_id) if run.published_app_id else None,
            "base_revision_id": str(run.base_revision_id) if run.base_revision_id else None,
            "result_revision_id": str(run.result_revision_id) if run.result_revision_id else None,
            "checkpoint_revision_id": str(run.checkpoint_revision_id) if run.checkpoint_revision_id else None,
            "error": run.error_message,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }

    async def create_run(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
        user_prompt: str,
        requested_scopes: list[str] | None = None,
    ) -> AgentRun:
        profile = await ensure_coding_agent_profile(self.db, app.tenant_id)

        input_params = {
            "input": user_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "context": {
                "surface": CODING_AGENT_SURFACE,
                "app_id": str(app.id),
                "base_revision_id": str(base_revision.id),
                "entry_file": base_revision.entry_file,
            },
        }

        run_id = await self.executor.start_run(
            profile.id,
            input_params,
            user_id=actor_id,
            background=False,
            mode=ExecutionMode.DEBUG,
            requested_scopes=requested_scopes,
        )

        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Failed to load created coding-agent run")

        run.surface = CODING_AGENT_SURFACE
        run.published_app_id = app.id
        run.base_revision_id = base_revision.id
        run.result_revision_id = None
        run.checkpoint_revision_id = None

        if actor_id:
            runtime_service = PublishedAppDraftDevRuntimeService(self.db)
            try:
                await runtime_service.ensure_session(
                    app=app,
                    revision=base_revision,
                    user_id=actor_id,
                    files=dict(base_revision.files or {}),
                    entry_file=base_revision.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                pass

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(self, *, app_id: UUID, limit: int = 25) -> list[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                )
            )
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_run_for_app(self, *, app_id: UUID, run_id: UUID) -> AgentRun:
        result = await self.db.execute(
            select(AgentRun).where(
                and_(
                    AgentRun.id == run_id,
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                )
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Coding-agent run not found")
        return run

    async def cancel_run(self, run: AgentRun) -> AgentRun:
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            return run
        run.status = RunStatus.cancelled
        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_checkpoints(self, *, app_id: UUID, limit: int = 25) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                    AgentRun.checkpoint_revision_id.is_not(None),
                )
            )
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        runs = list(result.scalars().all())
        payload: list[dict[str, Any]] = []
        for run in runs:
            payload.append(
                {
                    "checkpoint_id": str(run.checkpoint_revision_id),
                    "run_id": str(run.id),
                    "app_id": str(app_id),
                    "revision_id": str(run.result_revision_id) if run.result_revision_id else None,
                    "created_at": run.completed_at or run.created_at,
                }
            )
        return payload

    async def restore_checkpoint(
        self,
        *,
        app: PublishedApp,
        checkpoint_revision_id: UUID,
        actor_id: UUID | None,
        run: AgentRun | None = None,
    ) -> PublishedAppRevision:
        checkpoint_revision = await self.db.get(PublishedAppRevision, checkpoint_revision_id)
        if checkpoint_revision is None or str(checkpoint_revision.published_app_id) != str(app.id):
            raise HTTPException(status_code=404, detail="Checkpoint revision not found")

        current_revision = await self.db.get(PublishedAppRevision, app.current_draft_revision_id)
        if current_revision is None:
            current_revision = checkpoint_revision

        restored = await self._create_draft_revision_from_files(
            app=app,
            current=current_revision,
            actor_id=actor_id,
            files=dict(checkpoint_revision.files or {}),
            entry_file=checkpoint_revision.entry_file,
        )

        if actor_id is not None:
            runtime_service = PublishedAppDraftDevRuntimeService(self.db)
            try:
                await runtime_service.sync_session(
                    app=app,
                    revision=restored,
                    user_id=actor_id,
                    files=dict(restored.files or {}),
                    entry_file=restored.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                pass

        if run is not None:
            run.result_revision_id = restored.id
            run.checkpoint_revision_id = checkpoint_revision.id

        await self.db.commit()
        await self.db.refresh(restored)
        return restored

    async def _create_draft_revision_from_files(
        self,
        *,
        app: PublishedApp,
        current: PublishedAppRevision,
        actor_id: UUID | None,
        files: dict[str, str],
        entry_file: str,
    ) -> PublishedAppRevision:
        _validate_builder_project_or_raise(files, entry_file)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file,
            files=files,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=int(current.build_seq or 0) + 1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
            source_revision_id=current.id,
            created_by=actor_id,
        )
        self.db.add(revision)
        await self.db.flush()
        app.current_draft_revision_id = revision.id
        return revision

    async def auto_apply_and_checkpoint(self, run: AgentRun) -> PublishedAppRevision | None:
        if run.result_revision_id is not None:
            existing = await self.db.get(PublishedAppRevision, run.result_revision_id)
            return existing

        if run.published_app_id is None:
            return None
        actor_id = run.initiator_user_id or run.user_id
        if actor_id is None:
            return None

        app = await self.db.get(PublishedApp, run.published_app_id)
        if app is None:
            return None

        current_revision_id = app.current_draft_revision_id or run.base_revision_id
        if current_revision_id is None:
            return None
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            return None

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        try:
            session = await runtime_service.ensure_session(
                app=app,
                revision=current,
                user_id=actor_id,
                files=dict(current.files or {}),
                entry_file=current.entry_file,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            return None

        if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
            return None

        snapshot = await runtime_service.client.snapshot_files(sandbox_id=session.sandbox_id)
        raw_files = snapshot.get("files")
        if not isinstance(raw_files, dict):
            return None
        files = {path: content if isinstance(content, str) else str(content) for path, content in raw_files.items() if isinstance(path, str)}

        revision = await self._create_draft_revision_from_files(
            app=app,
            current=current,
            actor_id=actor_id,
            files=files,
            entry_file=current.entry_file,
        )
        run.result_revision_id = revision.id
        run.checkpoint_revision_id = revision.id
        await self.db.commit()
        await self.db.refresh(revision)
        return revision

    def _envelope(
        self,
        *,
        seq: int,
        event: str,
        run_id: UUID,
        app_id: UUID,
        stage: str,
        payload: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": event,
            "run_id": str(run_id),
            "app_id": str(app_id),
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "payload": payload or {},
            "diagnostics": diagnostics or [],
        }
        return data

    def _map_execution_event(self, event: ExecutionEvent) -> tuple[str, str, dict[str, Any], list[dict[str, Any]] | None] | None:
        if event.event == "token":
            return (
                "assistant.delta",
                "assistant",
                {"content": (event.data or {}).get("content", "")},
                None,
            )

        if event.event == "on_tool_start":
            data = event.data if isinstance(event.data, dict) else {}
            return (
                "tool.started",
                "tool",
                {
                    "tool": event.name,
                    "span_id": event.span_id,
                    "input": data.get("input"),
                },
                None,
            )

        if event.event == "on_tool_end":
            data = event.data if isinstance(event.data, dict) else {}
            output = data.get("output")
            if isinstance(output, dict) and output.get("error"):
                return (
                    "tool.failed",
                    "tool",
                    {
                        "tool": event.name,
                        "span_id": event.span_id,
                        "output": output,
                    },
                    [{"message": str(output.get("error"))}],
                )
            return (
                "tool.completed",
                "tool",
                {
                    "tool": event.name,
                    "span_id": event.span_id,
                    "output": output,
                },
                None,
            )

        if event.event == "node_start":
            return (
                "plan.updated",
                "plan",
                {
                    "node": event.name,
                    "span_id": event.span_id,
                    "state": event.data,
                },
                None,
            )

        if event.event == "error":
            message = str((event.data or {}).get("error") or "runtime error")
            return (
                "run.failed",
                "run",
                {
                    "error": message,
                },
                [{"message": message}],
            )

        return None

    async def stream_run_events(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        resume_payload: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        seq = 1

        def emit(
            event: str,
            stage: str,
            payload: dict[str, Any] | None = None,
            diagnostics: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            nonlocal seq
            envelope = self._envelope(
                seq=seq,
                event=event,
                run_id=run.id,
                app_id=app.id,
                stage=stage,
                payload=payload,
                diagnostics=diagnostics,
            )
            seq += 1
            return envelope

        yield emit(
            "run.accepted",
            "run",
            {
                "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                "surface": CODING_AGENT_SURFACE,
            },
        )
        yield emit("plan.updated", "plan", {"summary": "Coding-agent run started"})

        terminal_status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if terminal_status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            if terminal_status == RunStatus.completed.value:
                yield emit("run.completed", "run", self.serialize_run(run))
            else:
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": run.error_message or f"run {terminal_status}"}],
                )
            return

        try:
            if run.status == RunStatus.paused and resume_payload is not None:
                await self.executor.resume_run(run.id, resume_payload, background=False)

            async for raw in self.executor.run_and_stream(
                run.id,
                self.db,
                resume_payload,
                mode=ExecutionMode.DEBUG,
            ):
                mapped = self._map_execution_event(raw)
                if mapped is None:
                    continue
                mapped_event, stage, payload, diagnostics = mapped
                yield emit(mapped_event, stage, payload, diagnostics)

            await self.db.refresh(run)
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status == RunStatus.completed.value:
                revision = await self.auto_apply_and_checkpoint(run)
                if revision is not None:
                    yield emit(
                        "revision.created",
                        "revision",
                        {
                            "revision_id": str(revision.id),
                            "entry_file": revision.entry_file,
                            "file_count": len(revision.files or {}),
                        },
                    )
                    yield emit(
                        "checkpoint.created",
                        "checkpoint",
                        {
                            "checkpoint_id": str(run.checkpoint_revision_id or revision.id),
                            "revision_id": str(revision.id),
                        },
                    )
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            if status == RunStatus.cancelled.value:
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": "run cancelled"}],
                )
                return

            if status == RunStatus.paused.value:
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": run.error_message or "run failed"}],
            )
        except Exception as exc:
            run.status = RunStatus.failed
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": str(exc)}],
            )

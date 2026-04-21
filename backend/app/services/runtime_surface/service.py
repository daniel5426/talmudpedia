from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.persisted_stream import stream_persisted_run_events
from app.agent.execution.service import AgentExecutorService
from app.core.scope_registry import is_platform_admin_role
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.model_accounting import usage_payload_from_run
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.thread_service import ThreadService
from app.services.usage_quota_service import QuotaExceededError
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded

from .contracts import (
    RuntimeChatRequest,
    RuntimeEventView,
    RuntimeRunControlContext,
    RuntimeStreamOptions,
    RuntimeSurfaceContext,
    RuntimeThreadOptions,
    RuntimeThreadScope,
)
from .events import list_run_events
from .threads import serialize_thread_detail, serialize_turn_base, turns_to_messages


class RuntimeSurfaceService:
    def __init__(self, db: AsyncSession, *, executor_cls: type[AgentExecutorService] = AgentExecutorService):
        self.db = db
        self.executor_cls = executor_cls

    async def stream_chat(
        self,
        *,
        agent_id: UUID,
        surface_context: RuntimeSurfaceContext,
        request: RuntimeChatRequest,
        options: RuntimeStreamOptions,
    ) -> StreamingResponse:
        run_messages: list[dict[str, Any]] = []
        thread_scope = surface_context.thread_scope(agent_id=agent_id)
        if options.preload_thread_messages and request.thread_id is not None:
            existing_thread = await ThreadService(self.db).get_thread_with_turns(
                organization_id=thread_scope.organization_id,
                project_id=thread_scope.project_id,
                thread_id=request.thread_id,
                user_id=thread_scope.user_id,
                app_account_id=thread_scope.app_account_id,
                published_app_id=thread_scope.published_app_id,
                agent_id=thread_scope.agent_id,
                external_user_id=thread_scope.external_user_id,
                external_session_id=thread_scope.external_session_id,
            )
            if existing_thread is None:
                raise HTTPException(status_code=404, detail="Thread not found")
            run_messages.extend(turns_to_messages(list(existing_thread.turns or [])))
        run_messages.extend(list(request.messages or []))

        request_context = dict(request.context or {})
        request_context.setdefault("organization_id", str(surface_context.organization_id))
        request_context.setdefault("project_id", str(surface_context.project_id) if surface_context.project_id else None)
        request_context.setdefault(
            "user_id",
            surface_context.request_user_id if surface_context.request_user_id is not None else (
                str(surface_context.user_id) if surface_context.user_id else None
            ),
        )
        request_context.setdefault("thread_id", str(request.thread_id) if request.thread_id else None)
        for key, value in surface_context.context_defaults.items():
            request_context.setdefault(key, value)

        executor = self.executor_cls(db=self.db)
        run_id = request.run_id
        if run_id:
            run_row = await self.db.get(AgentRun, run_id)
            if run_row is None:
                raise HTTPException(status_code=404, detail="Run not found")
            status = self._status_text(run_row.status)
            if status == RunStatus.paused.value:
                try:
                    await executor.resume_run(run_id, request.resume_payload(), background=True)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"Cannot resume run {run_id}: {exc}") from exc
        else:
            try:
                run_id = await executor.start_run(
                    agent_id,
                    {
                        "messages": run_messages,
                        "input": request.input,
                        "attachment_ids": list(request.attachment_ids or []),
                        "state": dict(request.state or {}),
                        "thread_id": str(request.thread_id) if request.thread_id else None,
                        "context": request_context,
                    },
                    user_id=surface_context.user_id,
                    background=True,
                    mode=options.execution_mode,
                    thread_id=request.thread_id,
                )
            except (QuotaExceededError, ResourcePolicyQuotaExceeded):
                raise
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        run_row = await self.db.get(AgentRun, run_id)
        thread_id_value = str(run_row.thread_id) if run_row and run_row.thread_id else None
        cleanup_thread_ids: list[UUID] = []
        if options.cleanup_transient_thread and run_row and run_row.thread_id:
            cleanup_thread_ids.append(run_row.thread_id)

        async def event_generator():
            try:
                async for chunk in stream_persisted_run_events(
                    run_id=run_id,
                    mode=options.execution_mode,
                    stream_v2_enforced=options.stream_v2_enforced,
                    thread_id_value=thread_id_value,
                    padding_bytes=options.padding_bytes,
                ):
                    yield chunk
            finally:
                if cleanup_thread_ids:
                    await ThreadService(self.db).delete_threads(
                        organization_id=surface_context.organization_id,
                        project_id=surface_context.project_id,
                        thread_ids=cleanup_thread_ids,
                    )

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **dict(options.extra_headers or {}),
        }
        if options.include_content_encoding_identity:
            headers["Content-Encoding"] = "identity"
        if options.include_run_id_header:
            headers["X-Run-ID"] = str(run_id)
        if options.include_thread_header:
            headers["X-Thread-ID"] = thread_id_value or ""
        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)

    async def list_threads(
        self,
        *,
        scope: RuntimeThreadScope,
        skip: int,
        limit: int,
    ) -> tuple[list[Any], int]:
        return await ThreadService(self.db).list_threads(
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            user_id=scope.user_id,
            app_account_id=scope.app_account_id,
            published_app_id=scope.published_app_id,
            agent_id=scope.agent_id,
            external_user_id=scope.external_user_id,
            external_session_id=scope.external_session_id,
            skip=skip,
            limit=limit,
        )

    async def get_thread_detail(
        self,
        *,
        scope: RuntimeThreadScope,
        thread_id: UUID,
        options: RuntimeThreadOptions,
        event_view: RuntimeEventView,
    ) -> dict[str, Any]:
        service = ThreadService(self.db)
        repaired = await service.repair_thread_turn_indices(thread_id=thread_id)
        if repaired:
            await self.db.commit()
        page_result = await service.get_thread_turn_page(
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            thread_id=thread_id,
            user_id=scope.user_id,
            app_account_id=scope.app_account_id,
            published_app_id=scope.published_app_id,
            agent_id=scope.agent_id,
            external_user_id=scope.external_user_id,
            external_session_id=scope.external_session_id,
            before_turn_index=options.before_turn_index,
            limit=options.limit,
        )
        if page_result is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        subtree = None
        if options.include_subthreads:
            subtree = await service.build_subthread_tree(
                root_thread=page_result.thread,
                root_page=page_result.page,
                depth=options.subthread_depth,
                turn_limit=options.subthread_turn_limit or options.limit,
                child_limit=options.subthread_child_limit,
            )
        return await serialize_thread_detail(
            db=self.db,
            thread=page_result.thread,
            page=page_result.page,
            subthread_tree=subtree,
            serialize_turn=lambda turn: self.serialize_turn(turn=turn, event_view=event_view),
        )

    async def delete_thread(
        self,
        *,
        scope: RuntimeThreadScope,
        thread_id: UUID,
    ) -> bool:
        thread = await ThreadService(self.db).get_thread_with_turns(
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            thread_id=thread_id,
            user_id=scope.user_id,
            app_account_id=scope.app_account_id,
            published_app_id=scope.published_app_id,
            agent_id=scope.agent_id,
            external_user_id=scope.external_user_id,
            external_session_id=scope.external_session_id,
        )
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        deleted = await ThreadService(self.db).delete_threads(
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            thread_ids=[thread.id],
        )
        return bool(deleted)

    async def get_run_events(
        self,
        *,
        run_id: UUID,
        control: RuntimeRunControlContext,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        run = await self.db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if str(run.organization_id) != str(control.organization_id):
            raise HTTPException(status_code=403, detail="Organization mismatch")
        if str(run.project_id) != str(control.project_id):
            raise HTTPException(status_code=403, detail="Project mismatch")
        events = await list_run_events(
            db=self.db,
            run_id=run_id,
            view=RuntimeEventView.internal_full,
            after_sequence=after_sequence,
            limit=limit,
        )
        return {
            "run_id": str(run_id),
            "event_count": len(events),
            "events": events,
        }

    async def cancel_run(
        self,
        *,
        run_id: UUID,
        control: RuntimeRunControlContext,
        assistant_output_text: str | None = None,
    ) -> dict[str, Any]:
        run_result = await self.db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = run_result.scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if str(run.organization_id) != str(control.organization_id):
            raise HTTPException(status_code=403, detail="Organization mismatch")
        if str(run.project_id) != str(control.project_id):
            raise HTTPException(status_code=403, detail="Project mismatch")

        if not control.is_service and not control.is_platform_admin:
            allowed_user_ids = {
                str(uid)
                for uid in (run.user_id, run.initiator_user_id)
                if uid is not None
            }
            if allowed_user_ids and str(control.user_id) not in allowed_user_ids:
                raise HTTPException(status_code=403, detail="Run ownership mismatch")

        status = self._status_text(run.status)
        if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            return {
                "run_id": str(run.id),
                "status": status,
                "thread_id": str(run.thread_id) if run.thread_id else None,
            }

        partial_text = str(assistant_output_text or "").strip()
        await OrchestrationKernelService(self.db).cancel_subtree(
            caller_run_id=run.id,
            run_id=run.id,
            include_root=True,
            reason="cancelled_by_user",
        )

        await self.db.refresh(run)
        run.status = RunStatus.cancelled
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = None

        output_result = dict(run.output_result or {}) if isinstance(run.output_result, dict) else {}
        messages = output_result.get("messages")
        if not isinstance(messages, list):
            messages = []
        if partial_text:
            messages.append({"role": "assistant", "content": partial_text})
            output_result["final_output"] = partial_text
        output_result["messages"] = messages
        run.output_result = output_result

        await self.db.commit()
        return {
            "run_id": str(run.id),
            "status": RunStatus.cancelled.value,
            "thread_id": str(run.thread_id) if run.thread_id else None,
        }

    async def serialize_turn(self, *, turn: Any, event_view: RuntimeEventView) -> dict[str, Any]:
        payload = serialize_turn_base(
            turn,
            run_usage=usage_payload_from_run(getattr(turn, "run", None)),
        )
        if event_view == RuntimeEventView.public_safe:
            payload["run_events"] = await list_run_events(
                db=self.db,
                run_id=turn.run_id,
                view=RuntimeEventView.public_safe,
            )
        return payload

    @staticmethod
    def is_platform_admin(user: Any) -> bool:
        return is_platform_admin_role(getattr(user, "role", None))

    @staticmethod
    def _status_text(value: Any) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

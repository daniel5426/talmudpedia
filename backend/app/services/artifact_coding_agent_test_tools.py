from __future__ import annotations

from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactKind, ArtifactRun, ArtifactRunEvent, ArtifactRunStatus
from app.services.artifact_coding_agent_tools import (
    DEFAULT_AGENT_CONTRACT,
    DEFAULT_CAPABILITIES,
    DEFAULT_CONFIG_SCHEMA,
    DEFAULT_RAG_CONTRACT,
    DEFAULT_TOOL_CONTRACT,
    _current_contract_field,
    _default_contract_for_kind,
    _parse_json_object,
    _resolve_session_context,
    _serialize_form_state,
    get_session,
)
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.run_service import ArtifactRunService
from app.services.tool_function_registry import register_tool_function

DEFAULT_TEST_WAIT_TIMEOUT_SECONDS = 120.0
NONTERMINAL_TEST_RUN_STATUSES = {
    ArtifactRunStatus.QUEUED,
    ArtifactRunStatus.RUNNING,
    ArtifactRunStatus.CANCEL_REQUESTED,
}
TERMINAL_TEST_RUN_STATUSES = {
    ArtifactRunStatus.COMPLETED,
    ArtifactRunStatus.FAILED,
    ArtifactRunStatus.CANCELLED,
}


def _artifact_test_payload_from_snapshot(
    snapshot: dict[str, Any],
    *,
    artifact_id,
    input_data: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    normalized = _serialize_form_state(snapshot)
    kind = normalized["kind"]
    payload = {
        "artifact_id": artifact_id,
        "source_files": normalized["source_files"],
        "entry_module_path": normalized["entry_module_path"],
        "language": normalized.get("language") or "python",
        "input_data": input_data,
        "config": dict(config or {}),
        "dependencies": [
            item.strip()
            for item in str(normalized.get("dependencies") or "").split(",")
            if item.strip()
        ],
        "kind": kind,
        "runtime_target": normalized["runtime_target"],
        "capabilities": _parse_json_object(normalized["capabilities"], field="capabilities", fallback=DEFAULT_CAPABILITIES),
        "config_schema": _parse_json_object(normalized["config_schema"], field="config_schema", fallback=DEFAULT_CONFIG_SCHEMA),
        "agent_contract": None,
        "rag_contract": None,
        "tool_contract": None,
    }
    contract_field = _current_contract_field(kind)
    payload[contract_field] = _parse_json_object(
        normalized[contract_field],
        field=contract_field,
        fallback=_default_contract_for_kind(kind),
    )
    return payload


def _serialize_test_run_event(event: ArtifactRunEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "timestamp": event.timestamp.isoformat() if getattr(event, "timestamp", None) else None,
        "event_type": event.event_type,
        "payload": dict(event.payload or {}),
    }


def _summarize_test_run_failure(test_run: ArtifactRun) -> str | None:
    error_payload = dict(test_run.error_payload or {}) if test_run.error_payload is not None else {}
    message = error_payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    for excerpt in (test_run.stderr_excerpt, test_run.stdout_excerpt):
        if isinstance(excerpt, str) and excerpt.strip():
            return excerpt.strip()
    return None


def _serialize_test_run_result(
    test_run: ArtifactRun,
    *,
    events: list[ArtifactRunEvent] | None = None,
    wait_timed_out: bool = False,
    waited_seconds: float | None = None,
) -> dict[str, Any]:
    status = getattr(test_run.status, "value", str(test_run.status))
    terminal = test_run.status in TERMINAL_TEST_RUN_STATUSES
    serialized_events = [_serialize_test_run_event(event) for event in (events or [])]
    return {
        "ok": True,
        "has_test_result": True,
        "test_run_id": str(test_run.id),
        "status": status,
        "is_terminal": terminal,
        "wait_timed_out": wait_timed_out,
        "waited_seconds": waited_seconds,
        "result_payload": dict(test_run.result_payload or {}) if test_run.result_payload is not None else None,
        "error_payload": dict(test_run.error_payload or {}) if test_run.error_payload is not None else None,
        "stdout_excerpt": test_run.stdout_excerpt,
        "stderr_excerpt": test_run.stderr_excerpt,
        "duration_ms": test_run.duration_ms,
        "runtime_metadata": dict(test_run.runtime_metadata or {}),
        "failure_summary": _summarize_test_run_failure(test_run),
        "event_count": len(serialized_events),
        "events": serialized_events,
    }


def _resolve_wait_timeout_seconds(raw_timeout: Any) -> float:
    if raw_timeout is None:
        return DEFAULT_TEST_WAIT_TIMEOUT_SECONDS
    try:
        timeout_seconds = float(raw_timeout)
    except Exception as exc:
        raise ValueError("timeout_seconds must be a number") from exc
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    return timeout_seconds


@register_tool_function("artifact_coding_run_test")
async def artifact_coding_run_test(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    input_data = tool_payload.get("input_data")
    if input_data is None:
        input_data = {}
    config = tool_payload.get("config") if isinstance(tool_payload.get("config"), dict) else {}
    async with get_session() as db:
        session, shared_draft, run, artifact = await _resolve_session_context(db, tool_payload)
        if shared_draft.last_test_run_id is not None:
            active_test_run = await db.get(ArtifactRun, shared_draft.last_test_run_id)
            if active_test_run is not None and active_test_run.status in NONTERMINAL_TEST_RUN_STATUSES:
                status = getattr(active_test_run.status, "value", str(active_test_run.status))
                raise ValueError(
                    f"TEST_RUN_ALREADY_ACTIVE: latest test run {active_test_run.id} is still {status}. "
                    "Wait for it instead of starting another run."
                )
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        execution_service = ArtifactExecutionService(db)
        test_payload = _artifact_test_payload_from_snapshot(
            snapshot,
            artifact_id=artifact.id if artifact else None,
            input_data=input_data,
            config=config,
        )
        test_run = await execution_service.start_test_run(
            tenant_id=session.tenant_id,
            created_by=run.initiator_user_id or run.user_id,
            artifact_id=test_payload["artifact_id"],
            source_files=test_payload["source_files"],
            entry_module_path=test_payload["entry_module_path"],
            input_data=test_payload["input_data"],
            config=test_payload["config"],
            dependencies=test_payload["dependencies"],
            language=test_payload["language"],
            kind=test_payload["kind"],
            runtime_target=test_payload["runtime_target"],
            capabilities=test_payload["capabilities"],
            config_schema=test_payload["config_schema"],
            agent_contract=test_payload["agent_contract"],
            rag_contract=test_payload["rag_contract"],
            tool_contract=test_payload["tool_contract"],
        )
        shared_draft.last_test_run_id = test_run.id
        await db.commit()
        return {
            "ok": True,
            "summary": "Started artifact test run.",
            "test_run_id": str(test_run.id),
            "status": getattr(test_run.status, "value", str(test_run.status)),
        }


@register_tool_function("artifact_coding_await_last_test_result")
async def artifact_coding_await_last_test_result(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    timeout_seconds = _resolve_wait_timeout_seconds(tool_payload.get("timeout_seconds"))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        if shared_draft.last_test_run_id is None:
            return {"ok": True, "has_test_result": False, "wait_timed_out": False}
        run_service = ArtifactRunService(db)
        current_test_run = await db.get(ArtifactRun, shared_draft.last_test_run_id)
        if current_test_run is None:
            return {"ok": True, "has_test_result": False, "wait_timed_out": False}
        if current_test_run.status in TERMINAL_TEST_RUN_STATUSES:
            events = await run_service.list_events(run_id=current_test_run.id)
            return _serialize_test_run_result(current_test_run, events=events, wait_timed_out=False, waited_seconds=0.0)

        execution_service = ArtifactExecutionService(db)
        waited_run = await execution_service.wait_for_terminal_state(
            current_test_run.id,
            timeout_seconds=timeout_seconds,
        )
        if waited_run is None:
            return {"ok": True, "has_test_result": False, "wait_timed_out": True, "waited_seconds": timeout_seconds}
        events = await run_service.list_events(run_id=waited_run.id)
        return _serialize_test_run_result(
            waited_run,
            events=events,
            wait_timed_out=waited_run.status not in TERMINAL_TEST_RUN_STATUSES,
            waited_seconds=timeout_seconds,
        )


@register_tool_function("artifact_coding_get_last_test_result")
async def artifact_coding_get_last_test_result(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        _session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        if shared_draft.last_test_run_id is None:
            return {"ok": True, "has_test_result": False, "wait_timed_out": False}
        test_run = await db.get(ArtifactRun, shared_draft.last_test_run_id)
        if test_run is None:
            return {"ok": True, "has_test_result": False, "wait_timed_out": False}
        events = await ArtifactRunService(db).list_events(run_id=test_run.id)
        return _serialize_test_run_result(test_run, events=events)

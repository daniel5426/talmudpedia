from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.opencode_server_client import (
    OpenCodeServerClient,
    OpenCodeServerClientConfig,
    OpenCodeServerClientError,
)
from app.services.opencode_server_launch import build_official_opencode_bootstrap_command
from app.services.published_app_draft_dev_local_runtime import (
    LocalDraftDevRuntimeError,
    get_local_draft_dev_runtime_manager,
)


def _is_truthy(value: str | None) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _require_enabled() -> None:
    if _is_truthy(os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "0")):
        return
    raise HTTPException(status_code=404, detail="Sandbox controller dev shim is disabled.")


def _expected_token() -> str | None:
    token = (os.getenv("APPS_SANDBOX_CONTROLLER_TOKEN") or "").strip()
    if token:
        return token
    token = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_TOKEN") or "").strip()
    return token or None


def _authorize(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
    _require_enabled()
    expected = _expected_token()
    if not expected:
        return
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    provided = raw.split(" ", 1)[1].strip()
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid sandbox controller token.")


router = APIRouter(
    prefix="/internal/sandbox-controller",
    tags=["sandbox-controller-dev-shim"],
    dependencies=[Depends(_authorize)],
)


class StartSessionRequest(BaseModel):
    session_id: str
    organization_id: str
    app_id: str
    user_id: str
    revision_id: str
    entry_file: str
    files: dict[str, str] = Field(default_factory=dict)
    idle_timeout_seconds: int = 180
    dependency_hash: str = ""
    draft_dev_token: str = ""
    preview_base_path: str = "/"


class SyncSessionRequest(BaseModel):
    entry_file: str
    files: dict[str, str] = Field(default_factory=dict)
    idle_timeout_seconds: int = 180
    dependency_hash: str = ""
    install_dependencies: bool = False


class HeartbeatRequest(BaseModel):
    idle_timeout_seconds: int = 180


class ListFilesRequest(BaseModel):
    limit: int = 500


class ReadFileRequest(BaseModel):
    path: str


class ReadFileRangeRequest(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    context_before: int = 0
    context_after: int = 0
    max_bytes: int = 12000
    with_line_numbers: bool = False


class SearchCodeRequest(BaseModel):
    query: str
    max_results: int = 30


class WorkspaceIndexRequest(BaseModel):
    limit: int = 500
    query: str | None = None
    max_symbols_per_file: int = 16


class ApplyPatchRequest(BaseModel):
    patch: str
    options: dict[str, Any] | None = None
    preconditions: dict[str, Any] | None = None


class WriteFileRequest(BaseModel):
    path: str
    content: str


class DeleteFileRequest(BaseModel):
    path: str


class RenameFileRequest(BaseModel):
    from_path: str
    to_path: str


class RunCommandRequest(BaseModel):
    command: list[str]
    timeout_seconds: int = 180
    max_output_bytes: int = 12000
    workspace_path: str | None = None


class OpenCodeEndpointRequest(BaseModel):
    workspace_path: str = "/workspace"


class StagePrepareRequest(BaseModel):
    reset: bool = False


class StageSnapshotRequest(BaseModel):
    workspace: str = "live"


class StagePromoteRequest(BaseModel):
    pass


class PublishDependenciesPrepareRequest(BaseModel):
    workspace_path: str


class WorkspaceArchiveRequest(BaseModel):
    workspace_path: str
    format: str = "tar.gz"


class WorkspaceSyncRequest(BaseModel):
    workspace_path: str
    files: dict[str, str] = Field(default_factory=dict)


def _build_host_opencode_client() -> OpenCodeServerClient:
    enabled_raw = (os.getenv("APPS_CODING_AGENT_OPENCODE_ENABLED") or "").strip()
    enabled = _is_truthy(enabled_raw) if enabled_raw else True
    base_url = (os.getenv("APPS_CODING_AGENT_OPENCODE_BASE_URL") or "").strip() or None
    api_key = (os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None
    request_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS") or "20").strip())
    connect_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS") or "5").strip())
    health_cache_seconds = int((os.getenv("APPS_CODING_AGENT_OPENCODE_HEALTH_CACHE_SECONDS") or "15").strip())
    config = OpenCodeServerClientConfig(
        enabled=enabled,
        base_url=base_url,
        api_key=api_key,
        request_timeout_seconds=max(3.0, request_timeout),
        connect_timeout_seconds=max(1.0, connect_timeout),
        health_cache_seconds=max(3, health_cache_seconds),
        sandbox_controller_mode_override=False,
    )
    return OpenCodeServerClient(config=config)


def _opencode_per_sandbox_enabled() -> bool:
    return _is_truthy(os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "1"))


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


async def _wait_for_port(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + float(max(1.0, timeout_seconds))
    while time.monotonic() < deadline:
        if _is_port_open(host, port):
            return True
        await asyncio.sleep(0.25)
    return _is_port_open(host, port)


def _resolve_opencode_server_command(host: str, port: int) -> list[str] | None:
    explicit = (os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_SERVER_COMMAND") or "").strip()
    if not explicit:
        explicit = (os.getenv("APPS_CODING_AGENT_OPENCODE_SERVER_COMMAND") or "").strip()
    if not explicit:
        return [
            "bash",
            "-lc",
            build_official_opencode_bootstrap_command(host=host, port=port),
        ]
    templates = [explicit]
    for template in templates:
        if not template:
            continue
        try:
            rendered = template.format(host=host, port=port)
        except Exception:
            continue
        command = [segment for segment in shlex.split(rendered) if segment]
        if not command:
            continue
        if shutil.which(command[0]) is None:
            continue
        return command
    return None


def _build_opencode_client_for_base_url(base_url: str) -> OpenCodeServerClient:
    api_key = (os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None
    request_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS") or "20").strip())
    connect_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS") or "5").strip())
    health_cache_seconds = int((os.getenv("APPS_CODING_AGENT_OPENCODE_HEALTH_CACHE_SECONDS") or "15").strip())
    config = OpenCodeServerClientConfig(
        enabled=True,
        base_url=base_url,
        api_key=api_key,
        request_timeout_seconds=max(3.0, request_timeout),
        connect_timeout_seconds=max(1.0, connect_timeout),
        health_cache_seconds=max(3, health_cache_seconds),
        sandbox_controller_mode_override=False,
    )
    return OpenCodeServerClient(config=config)


@dataclass
class _SandboxOpenCodeServerState:
    sandbox_id: str
    workspace_path: str
    base_url: str
    port: int
    process: subprocess.Popen
    started_at: datetime


class _SandboxOpenCodeServerStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._states: dict[str, _SandboxOpenCodeServerState] = {}

    async def get(self, sandbox_id: str) -> _SandboxOpenCodeServerState | None:
        async with self._lock:
            return self._states.get(str(sandbox_id))

    async def put(self, state: _SandboxOpenCodeServerState) -> None:
        async with self._lock:
            self._states[str(state.sandbox_id)] = state

    async def pop(self, sandbox_id: str) -> _SandboxOpenCodeServerState | None:
        async with self._lock:
            return self._states.pop(str(sandbox_id), None)


_sandbox_opencode_servers = _SandboxOpenCodeServerStore()


def _project_root_for_sandbox(sandbox_id: str) -> Path:
    root_dir = (os.getenv("APPS_DRAFT_DEV_LOCAL_ROOT_DIR") or "/tmp/talmudpedia-draft-dev").strip()
    return Path(root_dir).expanduser().resolve() / str(sandbox_id)


def _opencode_metadata_path_for_project(project_root: Path) -> Path:
    return project_root / ".talmudpedia" / "opencode-server.json"


def _write_opencode_metadata(*, sandbox_id: str, project_root: Path, pid: int, port: int, workspace_path: str) -> None:
    payload = {
        "sandbox_id": str(sandbox_id),
        "pid": int(pid),
        "port": int(port),
        "project_root": str(project_root),
        "workspace_path": str(workspace_path or "").strip(),
    }
    target = _opencode_metadata_path_for_project(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _clear_opencode_metadata(*, sandbox_id: str) -> None:
    _opencode_metadata_path_for_project(_project_root_for_sandbox(sandbox_id)).unlink(missing_ok=True)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _terminate_process_group(pid: int, *, sig: signal.Signals) -> None:
    try:
        os.killpg(int(pid), sig)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(int(pid), sig)
        except ProcessLookupError:
            return
        except Exception:
            return


def _terminate_opencode_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    _terminate_process_group(process.pid, sig=signal.SIGTERM)
    try:
        process.wait(timeout=3.0)
    except Exception:
        _terminate_process_group(process.pid, sig=signal.SIGKILL)
        try:
            process.wait(timeout=2.0)
        except Exception:
            pass


async def _stop_sandbox_opencode_server(*, sandbox_id: str) -> None:
    state = await _sandbox_opencode_servers.pop(sandbox_id)
    if state is None:
        _clear_opencode_metadata(sandbox_id=sandbox_id)
        return
    _terminate_opencode_process(state.process)
    _clear_opencode_metadata(sandbox_id=sandbox_id)


def reclaim_orphaned_sandbox_opencode_servers() -> None:
    root_dir = (os.getenv("APPS_DRAFT_DEV_LOCAL_ROOT_DIR") or "/tmp/talmudpedia-draft-dev").strip()
    root_path = Path(root_dir).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    for project_root in root_path.iterdir():
        if not project_root.is_dir():
            continue
        metadata_path = _opencode_metadata_path_for_project(project_root)
        if not metadata_path.exists():
            continue
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata_path.unlink(missing_ok=True)
            continue
        pid = int(payload.get("pid") or 0)
        if pid > 0 and _process_exists(pid):
            _terminate_process_group(pid, sig=signal.SIGTERM)
        metadata_path.unlink(missing_ok=True)


async def _get_per_sandbox_opencode_client(*, sandbox_id: str, workspace_path: str) -> OpenCodeServerClient:
    workspace_root = str(workspace_path or "").strip()
    if not workspace_root:
        raise OpenCodeServerClientError("Workspace path is required for sandbox-scoped OpenCode.")

    existing = await _sandbox_opencode_servers.get(sandbox_id)
    if existing is not None:
        same_workspace = str(existing.workspace_path).strip() == workspace_root
        running = existing.process.poll() is None and _is_port_open("127.0.0.1", existing.port)
        if same_workspace and running:
            return _build_opencode_client_for_base_url(existing.base_url)
        await _stop_sandbox_opencode_server(sandbox_id=sandbox_id)

    port = _pick_free_port()
    command = _resolve_opencode_server_command("127.0.0.1", port)
    if not command:
        raise OpenCodeServerClientError(
            "Sandbox-scoped OpenCode command is unavailable. Install `opencode`/`npx` "
            "or set APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_SERVER_COMMAND."
        )

    log_path = os.getenv(
        "APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_LOG_PATH_TEMPLATE",
        "/tmp/talmudpedia-opencode-shim-{sandbox_id}.log",
    ).format(sandbox_id=str(sandbox_id))
    with open(log_path, "ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=workspace_root,
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    startup_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_STARTUP_TIMEOUT_SECONDS") or "20").strip())
    if not await _wait_for_port("127.0.0.1", port, startup_timeout):
        _terminate_opencode_process(process)
        raise OpenCodeServerClientError(
            f"Sandbox-scoped OpenCode failed to start on 127.0.0.1:{port}. Check {log_path}."
        )

    base_url = f"http://127.0.0.1:{port}"
    project_root = _project_root_for_sandbox(sandbox_id)
    _write_opencode_metadata(
        sandbox_id=sandbox_id,
        project_root=project_root,
        pid=process.pid,
        port=port,
        workspace_path=workspace_root,
    )
    await _sandbox_opencode_servers.put(
        _SandboxOpenCodeServerState(
            sandbox_id=str(sandbox_id),
            workspace_path=workspace_root,
            base_url=base_url,
            port=port,
            process=process,
            started_at=datetime.now(timezone.utc),
        )
    )
    return _build_opencode_client_for_base_url(base_url)


def _resolve_requested_workspace_path(
    *,
    project_workspace_resolved: str,
    requested_workspace: str,
) -> str:
    requested = str(requested_workspace or "").strip()
    if not requested:
        return project_workspace_resolved

    candidates: list[str] = []
    if os.path.isabs(requested):
        candidates.append(os.path.realpath(os.path.abspath(requested)))
        virtual_root = "/workspace"
        if requested == virtual_root or requested.startswith(f"{virtual_root}/"):
            suffix = requested[len(virtual_root):].lstrip("/")
            mapped = os.path.join(project_workspace_resolved, suffix) if suffix else project_workspace_resolved
            candidates.append(os.path.realpath(os.path.abspath(mapped)))
    else:
        candidates.append(os.path.realpath(os.path.abspath(os.path.join(project_workspace_resolved, requested))))

    for candidate in candidates:
        try:
            in_project_scope = os.path.commonpath([project_workspace_resolved, candidate]) == project_workspace_resolved
        except Exception:
            in_project_scope = False
        if in_project_scope and os.path.isdir(candidate):
            return candidate
    raise HTTPException(
        status_code=400,
        detail="Requested workspace path is invalid or outside sandbox project scope",
    )


def _translate_runtime_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, LocalDraftDevRuntimeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, OpenCodeServerClientError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "sandbox-controller-dev-shim"}


@router.post("/sessions/start")
async def start_session(payload: StartSessionRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        started = await manager.start_session(
            session_id=payload.session_id,
            files=payload.files,
            dependency_hash=payload.dependency_hash,
            draft_dev_token=payload.draft_dev_token,
            preview_base_path=payload.preview_base_path,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc
    response = dict(started or {})
    workspace_path = str(response.get("workspace_path") or "").strip()
    if not workspace_path:
        resolver = getattr(manager, "resolve_project_dir", None)
        if callable(resolver):
            resolved = await resolver(sandbox_id=str(response.get("sandbox_id") or payload.session_id))
            if resolved:
                response["workspace_path"] = str(resolved)
    return response


@router.patch("/sessions/{sandbox_id}/sync")
async def sync_session(sandbox_id: str, payload: SyncSessionRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.sync_session(
            sandbox_id=sandbox_id,
            files=payload.files,
            dependency_hash=payload.dependency_hash,
            install_dependencies=payload.install_dependencies,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/heartbeat")
async def heartbeat_session(sandbox_id: str, payload: HeartbeatRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.heartbeat_session(sandbox_id=sandbox_id)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/stop")
async def stop_session(sandbox_id: str) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        stopped = await manager.stop_session(sandbox_id=sandbox_id)
        await _stop_sandbox_opencode_server(sandbox_id=sandbox_id)
        return stopped
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.get("/sessions/{sandbox_id}/files")
async def list_files(
    sandbox_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    payload: ListFilesRequest | None = Body(default=None),
) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    requested_limit = int(payload.limit) if payload is not None else int(limit)
    try:
        return await manager.list_files(sandbox_id=sandbox_id, limit=max(1, requested_limit))
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/read")
async def read_file(sandbox_id: str, payload: ReadFileRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.read_file(sandbox_id=sandbox_id, path=payload.path)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/read-range")
async def read_file_range(sandbox_id: str, payload: ReadFileRangeRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.read_file_range(
            sandbox_id=sandbox_id,
            path=payload.path,
            start_line=payload.start_line,
            end_line=payload.end_line,
            context_before=payload.context_before,
            context_after=payload.context_after,
            max_bytes=payload.max_bytes,
            with_line_numbers=payload.with_line_numbers,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/search")
async def search_code(sandbox_id: str, payload: SearchCodeRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.search_code(
            sandbox_id=sandbox_id,
            query=payload.query,
            max_results=payload.max_results,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/workspace-index")
async def workspace_index(sandbox_id: str, payload: WorkspaceIndexRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.workspace_index(
            sandbox_id=sandbox_id,
            limit=payload.limit,
            query=payload.query,
            max_symbols_per_file=payload.max_symbols_per_file,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/apply-patch")
async def apply_patch(sandbox_id: str, payload: ApplyPatchRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.apply_patch(
            sandbox_id=sandbox_id,
            patch=payload.patch,
            options=payload.options,
            preconditions=payload.preconditions,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/write")
async def write_file(sandbox_id: str, payload: WriteFileRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.write_file(
            sandbox_id=sandbox_id,
            path=payload.path,
            content=payload.content,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/delete")
async def delete_file(sandbox_id: str, payload: DeleteFileRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.delete_file(sandbox_id=sandbox_id, path=payload.path)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/files/rename")
async def rename_file(sandbox_id: str, payload: RenameFileRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.rename_file(
            sandbox_id=sandbox_id,
            from_path=payload.from_path,
            to_path=payload.to_path,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.get("/sessions/{sandbox_id}/files/snapshot")
async def snapshot_files(sandbox_id: str) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.snapshot_files(sandbox_id=sandbox_id)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/stage/prepare")
async def prepare_stage_workspace(sandbox_id: str, payload: StagePrepareRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.prepare_stage_workspace(
            sandbox_id=sandbox_id,
            reset=bool(payload.reset),
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/stage/snapshot")
async def snapshot_workspace(sandbox_id: str, payload: StageSnapshotRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.snapshot_workspace(
            sandbox_id=sandbox_id,
            workspace=payload.workspace,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/stage/promote")
async def promote_stage_workspace(sandbox_id: str, payload: StagePromoteRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        _ = payload
        return await manager.promote_stage_workspace(sandbox_id=sandbox_id)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/publish/dependencies/prepare")
async def prepare_publish_dependencies(
    sandbox_id: str,
    payload: PublishDependenciesPrepareRequest,
) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.prepare_publish_dependencies(
            sandbox_id=sandbox_id,
            workspace_path=payload.workspace_path,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/commands/run")
async def run_command(sandbox_id: str, payload: RunCommandRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.run_command(
            sandbox_id=sandbox_id,
            command=payload.command,
            timeout_seconds=payload.timeout_seconds,
            max_output_bytes=payload.max_output_bytes,
            workspace_path=payload.workspace_path,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/workspace/archive")
async def export_workspace_archive(sandbox_id: str, payload: WorkspaceArchiveRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.export_workspace_archive(
            sandbox_id=sandbox_id,
            workspace_path=payload.workspace_path,
            format=payload.format,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/workspace/sync")
async def sync_workspace_files(sandbox_id: str, payload: WorkspaceSyncRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    try:
        return await manager.sync_workspace_files(
            sandbox_id=sandbox_id,
            workspace_path=payload.workspace_path,
            files=payload.files,
        )
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc


@router.post("/sessions/{sandbox_id}/opencode/endpoint")
async def opencode_endpoint(sandbox_id: str, payload: OpenCodeEndpointRequest) -> dict[str, Any]:
    manager = get_local_draft_dev_runtime_manager()
    workspace_path = await manager.resolve_project_dir(sandbox_id=sandbox_id)
    project_workspace = str(workspace_path or "").strip()
    if not project_workspace:
        raise HTTPException(status_code=400, detail="Draft dev sandbox is not running")
    project_workspace_resolved = os.path.realpath(os.path.abspath(project_workspace))
    effective_workspace = _resolve_requested_workspace_path(
        project_workspace_resolved=project_workspace_resolved,
        requested_workspace=str(payload.workspace_path or "").strip(),
    )

    try:
        if _opencode_per_sandbox_enabled():
            host_client = await _get_per_sandbox_opencode_client(
                sandbox_id=sandbox_id,
                workspace_path=effective_workspace,
            )
        else:
            host_client = _build_host_opencode_client()
        await host_client.ensure_healthy(force=True)
    except Exception as exc:
        raise _translate_runtime_error(exc) from exc

    base_url = str(getattr(getattr(host_client, "_config", None), "base_url", "") or "").strip()
    if not base_url:
        raise HTTPException(status_code=500, detail="OpenCode endpoint did not provide a base URL.")
    extra_headers = getattr(getattr(host_client, "_config", None), "extra_headers", None)
    return {
        "sandbox_id": sandbox_id,
        "base_url": base_url,
        "workspace_path": effective_workspace,
        "api_key": str(getattr(getattr(host_client, "_config", None), "api_key", "") or "").strip() or None,
        "extra_headers": extra_headers if isinstance(extra_headers, dict) else None,
        "status": "ready",
    }

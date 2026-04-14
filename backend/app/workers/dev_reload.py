from __future__ import annotations

import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_WATCH_PATHS: tuple[str, ...] = ("app", "main.py", "run_celery.py", ".env")
DEFAULT_POLL_SECONDS = 0.5
_CHILD_EXIT_TIMEOUT_SECONDS = 10.0
_LOCK_DIR = Path("/tmp")


@dataclass(frozen=True)
class WorkerProcessInfo:
    pid: int
    ppid: int
    command: str
    kind: str


def build_run_celery_command(
    *,
    script_path: Path,
    celery_args: list[str],
    reload_enabled: bool,
) -> list[str]:
    command = [sys.executable, str(script_path)]
    if reload_enabled:
        command.append("--reload")
    command.extend(celery_args)
    return command


def build_worker_process_patterns(*, queue_fragment: str) -> tuple[str, str]:
    return (
        rf"run_celery\.py( --reload)? .*?-Q {queue_fragment}($| )",
        rf"celery -A app\.workers\.celery_app\.celery_app worker.*-Q {queue_fragment}($| )",
    )


def extract_queue_fragment(celery_args: list[str]) -> str | None:
    for index, value in enumerate(celery_args):
        if value == "-Q" and index + 1 < len(celery_args):
            queue_fragment = str(celery_args[index + 1] or "").strip()
            return queue_fragment or None
    return None


def managed_supervisor_lock_path(queue_fragment: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(queue_fragment or "").strip()).strip("-") or "default"
    return _LOCK_DIR / f"talmudpedia-celery-supervisor-{slug}.lock"


def acquire_supervisor_lock(queue_fragment: str):
    lock_path = managed_supervisor_lock_path(queue_fragment)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _managed_supervisor_pattern(queue_fragment: str) -> re.Pattern[str]:
    return re.compile(rf"\brun_celery\.py --reload worker\b.*-Q {re.escape(queue_fragment)}(?:\s|$)")


def _managed_worker_pattern(queue_fragment: str) -> re.Pattern[str]:
    return re.compile(rf"\brun_celery\.py worker\b.*-Q {re.escape(queue_fragment)}(?:\s|$)")


def _legacy_worker_pattern(queue_fragment: str) -> re.Pattern[str]:
    return re.compile(
        rf"\bcelery -A app\.workers\.celery_app\.celery_app worker\b.*-Q {re.escape(queue_fragment)}(?:\s|$)"
    )


def classify_worker_command(command: str, queue_fragment: str) -> str | None:
    normalized = " ".join(str(command or "").split())
    if not normalized:
        return None
    if _managed_supervisor_pattern(queue_fragment).search(normalized):
        return "supervisor"
    if _managed_worker_pattern(queue_fragment).search(normalized):
        return "managed_worker"
    if _legacy_worker_pattern(queue_fragment).search(normalized):
        return "legacy_worker"
    return None


def list_matching_worker_processes(queue_fragment: str) -> list[WorkerProcessInfo]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    processes: list[WorkerProcessInfo] = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid_raw, ppid_raw, command = parts
        kind = classify_worker_command(command, queue_fragment)
        if kind is None:
            continue
        try:
            pid = int(pid_raw)
            ppid = int(ppid_raw)
        except ValueError:
            continue
        processes.append(WorkerProcessInfo(pid=pid, ppid=ppid, command=command, kind=kind))
    return processes


def has_matching_worker_processes(queue_fragment: str, *, managed_only: bool = False) -> bool:
    processes = list_matching_worker_processes(queue_fragment)
    if not managed_only:
        return bool(processes)
    return any(process.kind in {"supervisor", "managed_worker"} for process in processes)


def plan_unmanaged_worker_cleanup(processes: list[WorkerProcessInfo]) -> list[WorkerProcessInfo]:
    pids_by_kind: dict[str, set[int]] = {}
    for process in processes:
        pids_by_kind.setdefault(process.kind, set()).add(process.pid)
    planned: list[WorkerProcessInfo] = []
    for process in processes:
        sibling_pids = pids_by_kind.get(process.kind, set())
        if process.kind == "legacy_worker" and process.ppid not in sibling_pids:
            planned.append(process)
            continue
        if process.kind == "managed_worker" and process.ppid not in sibling_pids:
            planned.append(process)
    return planned


def _terminate_process_group(pid: int) -> bool:
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.time() + _CHILD_EXIT_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return True


def cleanup_unmanaged_worker_processes(queue_fragment: str) -> list[int]:
    planned = plan_unmanaged_worker_cleanup(list_matching_worker_processes(queue_fragment))
    terminated: list[int] = []
    for process in planned:
        if _terminate_process_group(process.pid):
            terminated.append(process.pid)
    return terminated


def normalize_watch_paths(base_dir: Path, watch_paths: Iterable[str] | None) -> list[Path]:
    normalized: list[Path] = []
    seen: set[Path] = set()
    for raw_path in watch_paths or DEFAULT_WATCH_PATHS:
        candidate = Path(raw_path)
        target = candidate if candidate.is_absolute() else (base_dir / candidate)
        resolved = target.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def snapshot_watch_state(base_dir: Path, watch_paths: Iterable[str] | None) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for path in normalize_watch_paths(base_dir, watch_paths):
        if path.is_dir():
            for file_path in sorted(path.rglob("*.py")):
                if not file_path.is_file():
                    continue
                snapshot[str(file_path)] = file_path.stat().st_mtime_ns
            continue
        if path.is_file():
            snapshot[str(path)] = path.stat().st_mtime_ns
    return snapshot


def watch_state_changed(previous: dict[str, int], current: dict[str, int]) -> bool:
    return previous != current


def run_celery_with_reload(
    *,
    script_path: Path,
    celery_args: list[str],
    watch_paths: Iterable[str] | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> int:
    parent_dir = script_path.resolve().parent
    poll_interval = max(0.2, float(poll_seconds))
    child: subprocess.Popen[bytes] | None = None
    stopping = False
    queue_fragment = extract_queue_fragment(celery_args)
    lock_handle = None

    def _terminate_child() -> None:
        nonlocal child
        if child is None or child.poll() is not None:
            child = None
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            child = None
            return
        deadline = time.time() + _CHILD_EXIT_TIMEOUT_SECONDS
        while time.time() < deadline:
            if child.poll() is not None:
                child = None
                return
            time.sleep(0.1)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if child is not None:
            child.wait(timeout=5)
        child = None

    def _handle_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        _terminate_child()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    if queue_fragment:
        lock_handle = acquire_supervisor_lock(queue_fragment)
        if lock_handle is None:
            print(
                f"[run_celery] managed supervisor already owns queue set {queue_fragment}; exiting",
                flush=True,
            )
            return 0
        terminated = cleanup_unmanaged_worker_processes(queue_fragment)
        if terminated:
            print(
                f"[run_celery] terminated stale worker roots for {queue_fragment}: {terminated}",
                flush=True,
            )

    def _spawn_child() -> subprocess.Popen[bytes]:
        command = build_run_celery_command(
            script_path=script_path,
            celery_args=celery_args,
            reload_enabled=False,
        )
        print(f"[run_celery] starting worker: {' '.join(command)}", flush=True)
        return subprocess.Popen(
            command,
            cwd=str(parent_dir),
            env=os.environ.copy(),
            start_new_session=True,
        )

    state = snapshot_watch_state(parent_dir, watch_paths)
    child = _spawn_child()
    try:
        while True:
            if child.poll() is not None:
                return int(child.returncode or 0)
            time.sleep(poll_interval)
            current_state = snapshot_watch_state(parent_dir, watch_paths)
            if watch_state_changed(state, current_state):
                state = current_state
                print("[run_celery] code change detected, restarting worker", flush=True)
                _terminate_child()
                if stopping:
                    return 0
                child = _spawn_child()
    finally:
        _terminate_child()
        if lock_handle is not None:
            try:
                lock_handle.close()
            except Exception:
                pass

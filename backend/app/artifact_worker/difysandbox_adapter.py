from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DifySandboxExecutionResult:
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    stdout_excerpt: str
    stderr_excerpt: str
    duration_ms: int
    sandbox_session_id: str
    worker_id: str


class DifySandboxAdapter:
    def __init__(self) -> None:
        self._runner_path = Path(__file__).with_name("runner.py")

    def execute(
        self,
        *,
        bundle_dir: Path,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> DifySandboxExecutionResult:
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="artifact-worker-run-") as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "request.json"
            result_path = temp_path / "result.json"
            request_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
            process = subprocess.Popen(
                [sys.executable, str(self._runner_path), str(bundle_dir), str(request_path), str(result_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=max(1, int(timeout_seconds)))
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                duration_ms = int((time.perf_counter() - start) * 1000)
                return DifySandboxExecutionResult(
                    status="failed",
                    result=None,
                    error={"message": f"Execution timed out after {timeout_seconds}s", "code": "TIMEOUT"},
                    stdout_excerpt=_truncate(stdout),
                    stderr_excerpt=_truncate(stderr),
                    duration_ms=duration_ms,
                    sandbox_session_id=str(process.pid),
                    worker_id=self._worker_id(),
                )

            duration_ms = int((time.perf_counter() - start) * 1000)
            if process.returncode == 0 and result_path.exists():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    result = None
                    return DifySandboxExecutionResult(
                        status="failed",
                        result=None,
                        error={"message": f"Invalid artifact result payload: {exc}", "code": "INVALID_RESULT"},
                        stdout_excerpt=_truncate(stdout),
                        stderr_excerpt=_truncate(stderr),
                        duration_ms=duration_ms,
                        sandbox_session_id=str(process.pid),
                        worker_id=self._worker_id(),
                    )
                return DifySandboxExecutionResult(
                    status="completed",
                    result=result if isinstance(result, dict) else {"result": result},
                    error=None,
                    stdout_excerpt=_truncate(stdout),
                    stderr_excerpt=_truncate(stderr),
                    duration_ms=duration_ms,
                    sandbox_session_id=str(process.pid),
                    worker_id=self._worker_id(),
                )

            return DifySandboxExecutionResult(
                status="failed",
                result=None,
                error={
                    "message": _truncate(stderr) or "Artifact execution failed",
                    "code": "EXECUTION_FAILED",
                    "returncode": process.returncode,
                },
                stdout_excerpt=_truncate(stdout),
                stderr_excerpt=_truncate(stderr),
                duration_ms=duration_ms,
                sandbox_session_id=str(process.pid),
                worker_id=self._worker_id(),
            )

    def cancel(self, *, sandbox_session_id: str) -> None:
        pid = int(str(sandbox_session_id or "").strip())
        os.kill(pid, signal.SIGKILL)

    @staticmethod
    def _worker_id() -> str:
        return f"{socket.gethostname()}:{os.getpid()}"


def _truncate(raw: str | None, *, max_chars: int = 12000) -> str:
    text = str(raw or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"

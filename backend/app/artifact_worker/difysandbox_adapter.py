from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import socket
import time
from dataclasses import dataclass, field
from typing import Any
import zipfile

import httpx


_RESULT_START = "__TALMUDPEDIA_ARTIFACT_RESULT_START__"
_RESULT_END = "__TALMUDPEDIA_ARTIFACT_RESULT_END__"


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
    sandbox_metadata: dict[str, Any] = field(default_factory=dict)


class DifySandboxAdapter:
    def execute(
        self,
        *,
        bundle_dir: Path,
        payload: dict[str, Any],
        timeout_seconds: int,
        sandbox_session_id: str,
    ) -> DifySandboxExecutionResult:
        start = time.perf_counter()
        request_timeout_seconds = max(
            5.0,
            float(os.getenv("DIFYSANDBOX_TIMEOUT_SECONDS") or timeout_seconds or 30),
        )
        code = self._build_execution_code(bundle_dir=bundle_dir, payload=payload)
        response_payload = self._run_remote_code(
            code=code,
            timeout_seconds=request_timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        if int(response_payload.get("code", -1)) != 0:
            return DifySandboxExecutionResult(
                status="failed",
                result=None,
                error={
                    "message": str(response_payload.get("message") or "DifySandbox execution failed"),
                    "code": "DIFYSANDBOX_EXECUTION_FAILED",
                },
                stdout_excerpt="",
                stderr_excerpt=str(response_payload.get("message") or ""),
                duration_ms=duration_ms,
                sandbox_session_id=sandbox_session_id,
                worker_id=self._worker_id(),
                sandbox_metadata=self._sandbox_metadata(),
            )

        data = response_payload.get("data")
        if not isinstance(data, dict):
            return DifySandboxExecutionResult(
                status="failed",
                result=None,
                error={"message": "DifySandbox returned invalid response data", "code": "INVALID_DIFYSANDBOX_RESPONSE"},
                stdout_excerpt="",
                stderr_excerpt="",
                duration_ms=duration_ms,
                sandbox_session_id=sandbox_session_id,
                worker_id=self._worker_id(),
                sandbox_metadata=self._sandbox_metadata(),
            )

        stdout_text = str(data.get("stdout") or "")
        stderr_text = str(data.get("error") or "")
        result_payload, cleaned_stdout, parse_error = self._extract_result(stdout_text)
        if parse_error is not None:
            return DifySandboxExecutionResult(
                status="failed",
                result=None,
                error=parse_error,
                stdout_excerpt=_truncate(cleaned_stdout),
                stderr_excerpt=_truncate(stderr_text),
                duration_ms=duration_ms,
                sandbox_session_id=sandbox_session_id,
                worker_id=self._worker_id(),
                sandbox_metadata=self._sandbox_metadata(),
            )

        if result_payload is None:
            return DifySandboxExecutionResult(
                status="failed",
                result=None,
                error={"message": _truncate(stderr_text) or "Artifact execution failed", "code": "EXECUTION_FAILED"},
                stdout_excerpt=_truncate(cleaned_stdout),
                stderr_excerpt=_truncate(stderr_text),
                duration_ms=duration_ms,
                sandbox_session_id=sandbox_session_id,
                worker_id=self._worker_id(),
                sandbox_metadata=self._sandbox_metadata(),
            )

        return DifySandboxExecutionResult(
            status="completed",
            result=result_payload,
            error=None,
            stdout_excerpt=_truncate(cleaned_stdout),
            stderr_excerpt=_truncate(stderr_text),
            duration_ms=duration_ms,
            sandbox_session_id=sandbox_session_id,
            worker_id=self._worker_id(),
            sandbox_metadata=self._sandbox_metadata(),
        )

    def cancel(self, *, sandbox_session_id: str) -> None:
        _ = sandbox_session_id
        return None

    def _run_remote_code(self, *, code: str, timeout_seconds: float) -> dict[str, Any]:
        base_url = str(os.getenv("DIFYSANDBOX_API_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("DIFYSANDBOX_API_BASE_URL is required")
        api_key = str(os.getenv("DIFYSANDBOX_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("DIFYSANDBOX_API_KEY is required")

        enable_network = str(os.getenv("ARTIFACT_SANDBOX_ALLOW_NETWORK") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        request_payload = {
            "language": "python3",
            "code": code,
            "enable_network": enable_network,
        }

        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{base_url}/v1/sandbox/run",
                headers={"X-Api-Key": api_key},
                json=request_payload,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("DifySandbox returned invalid JSON payload")
        return payload

    def _build_execution_code(self, *, bundle_dir: Path, payload: dict[str, Any]) -> str:
        bundle_bytes = self._zip_bundle_dir(bundle_dir)
        bundle_b64 = base64.b64encode(bundle_bytes).decode("ascii")
        payload_b64 = base64.b64encode(
            json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return f"""
import base64
import io
import json
import pathlib
import runpy
import sys
import tempfile
import traceback
import zipfile

BUNDLE_B64 = {bundle_b64!r}
PAYLOAD_B64 = {payload_b64!r}
RESULT_START = {_RESULT_START!r}
RESULT_END = {_RESULT_END!r}

with tempfile.TemporaryDirectory(prefix="artifact-difysandbox-") as temp_dir:
    root = pathlib.Path(temp_dir)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(BUNDLE_B64)), "r") as archive:
        archive.extractall(root)
    vendor_dir = root / "vendor"
    if vendor_dir.exists():
        sys.path.insert(0, str(vendor_dir))
    request_path = root / "request.json"
    result_path = root / "result.json"
    request_path.write_text(base64.b64decode(PAYLOAD_B64).decode("utf-8"), encoding="utf-8")
    runner_path = root / "runtime" / "runner.py"
    try:
        sys.argv = [str(runner_path), str(root), str(request_path), str(result_path)]
        runpy.run_path(str(runner_path), run_name="__main__")
        print(RESULT_START)
        print(result_path.read_text(encoding="utf-8"))
        print(RESULT_END)
    except Exception:
        traceback.print_exc()
        raise
"""

    @staticmethod
    def _zip_bundle_dir(bundle_dir: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle_dir.rglob("*")):
                if not path.is_file():
                    continue
                archive.write(path, path.relative_to(bundle_dir).as_posix())
        return buffer.getvalue()

    @staticmethod
    def _extract_result(stdout_text: str) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
        start_index = stdout_text.find(_RESULT_START)
        end_index = stdout_text.find(_RESULT_END)
        if start_index < 0 or end_index < 0 or end_index < start_index:
            return None, stdout_text, None
        result_text = stdout_text[start_index + len(_RESULT_START):end_index].strip()
        cleaned_stdout = (stdout_text[:start_index] + stdout_text[end_index + len(_RESULT_END):]).strip()
        try:
            parsed = json.loads(result_text or "{}")
        except Exception as exc:
            return None, cleaned_stdout, {
                "message": f"Invalid artifact result payload from DifySandbox: {exc}",
                "code": "INVALID_RESULT",
            }
        if not isinstance(parsed, dict):
            parsed = {"result": parsed}
        return parsed, cleaned_stdout, None

    @staticmethod
    def _worker_id() -> str:
        return f"{socket.gethostname()}:{os.getpid()}"

    @staticmethod
    def _sandbox_metadata() -> dict[str, Any]:
        return {
            "provider": "difysandbox",
            "base_url": str(os.getenv("DIFYSANDBOX_API_BASE_URL") or "").strip() or None,
        }


def _truncate(raw: str | None, *, max_chars: int = 12000) -> str:
    text = str(raw or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"

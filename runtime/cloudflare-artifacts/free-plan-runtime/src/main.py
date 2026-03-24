import inspect
import json
import sys
import traceback
from pathlib import PurePosixPath
from types import ModuleType

from workers import Response, WorkerEntrypoint


RUNTIME_SDK_SOURCE = """
import json as _json

_OUTBOUND_BASE_URL = ""
_OUTBOUND_GRANT = ""
_ALLOWED_HOSTS = []

def configure_artifact_runtime(*, outbound_base_url=None, outbound_grant=None, allowed_hosts=None):
    global _OUTBOUND_BASE_URL, _OUTBOUND_GRANT, _ALLOWED_HOSTS
    _OUTBOUND_BASE_URL = str(outbound_base_url or "").rstrip("/")
    _OUTBOUND_GRANT = str(outbound_grant or "")
    _ALLOWED_HOSTS = list(allowed_hosts or [])

async def outbound_fetch(url, *, credential, method="GET", headers=None, body=None, json=None):
    from js import Headers as _JsHeaders
    from js import Object as _JsObject
    from js import fetch as _js_fetch

    if not credential:
        raise ValueError("credential is required")
    if body is not None and json is not None:
        raise ValueError("Pass either body or json, not both")

    request_headers = _JsHeaders.new()
    for key, value in dict(headers or {}).items():
        request_headers.set(str(key), str(value))
    request_headers.set("x-artifact-credential-id", str(credential))

    request_body = None
    if json is not None:
        if not request_headers.get("content-type"):
            request_headers.set("content-type", "application/json")
        request_body = _json.dumps(json)
    elif body is not None:
        request_body = body if isinstance(body, str) else _json.dumps(body)

    options = _JsObject.new()
    options.method = str(method or "GET")
    options.headers = request_headers
    if request_body is not None:
        options.body = request_body
    response = await _js_fetch(str(url), options)
    raw_text = await response.text()
    content_type = str(response.headers.get("content-type") or "")
    parsed_body = _json.loads(raw_text) if raw_text and "application/json" in content_type else raw_text
    if not response.ok:
        if isinstance(parsed_body, dict):
            detail = parsed_body.get("detail")
            if isinstance(detail, dict):
                raise RuntimeError(str(detail.get("message") or "Artifact outbound request failed"))
        detail_text = ""
        if isinstance(parsed_body, str):
            detail_text = parsed_body[:500]
        elif parsed_body is not None:
            detail_text = _json.dumps(parsed_body)[:500]
        if detail_text:
            raise RuntimeError(f"Artifact outbound request failed with status {int(response.status)}: {detail_text}")
        raise RuntimeError(f"Artifact outbound request failed with status {int(response.status)}")
    return {
        "status_code": int(response.status),
        "headers": {},
        "body": parsed_body,
    }
"""


def _module_name(path: str) -> str:
    normalized = str(PurePosixPath(path)).strip()
    if normalized.endswith("/__init__.py"):
        normalized = normalized[: -len("/__init__.py")]
    elif normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".")


def _package_dir(path: str) -> str:
    normalized = str(PurePosixPath(path)).strip()
    if normalized.endswith("/__init__.py"):
        return str(PurePosixPath(normalized).parent)
    return str(PurePosixPath(normalized).parent)


def _runtime_metadata(*, entry_module_path: str | None = None, phase: str | None = None):
    metadata = {
        "provider": "cloudflare_workers",
        "runtime_mode": "standard_worker_test",
    }
    if entry_module_path:
        metadata["entry_module_path"] = entry_module_path
    if phase:
        metadata["error_phase"] = phase
    return metadata


def _truncate_text(value, *, limit=12000):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "\n...<truncated>"


def _error_detail(*, code: str, message: str, phase: str, exc=None):
    detail = {
        "code": code,
        "message": message,
        "phase": phase,
    }
    if exc is not None:
        detail["error_class"] = type(exc).__name__
        detail["traceback"] = _truncate_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        )
    return detail


def _error_response(*, payload, status: int, code: str, message: str, phase: str, entry_module_path: str | None = None, exc=None):
    detail = _error_detail(code=code, message=message, phase=phase, exc=exc)
    data = {
        "status": "failed",
        "result": None,
        "error": detail,
        "stdout_excerpt": "",
        "stderr_excerpt": detail.get("traceback") or message,
        "duration_ms": 0,
        "worker_id": "artifact-free-plan-runtime",
        "dispatch_request_id": (payload or {}).get("run_id"),
        "events": [
            {
                "event_type": "worker_exception",
                "payload": {
                    "data": {
                        "code": code,
                        "phase": phase,
                        "message": message,
                        "error_class": detail.get("error_class"),
                    }
                },
            }
        ],
        "runtime_metadata": _runtime_metadata(entry_module_path=entry_module_path, phase=phase),
    }
    return Response(
        json.dumps({"detail": detail, "data": data}),
        status=status,
        headers={"content-type": "application/json"},
    )


def _module_execution_order(source_files, entry_module_path):
    python_paths = [
        str(item.get("path") or "")
        for item in source_files
        if str(item.get("path") or "").endswith(".py")
    ]
    package_inits = [path for path in python_paths if path.endswith("/__init__.py")]
    regular_modules = [path for path in python_paths if not path.endswith("/__init__.py")]
    ordered = []
    ordered.extend(sorted(regular_modules, key=lambda path: (path == entry_module_path, path)))
    ordered.extend(sorted(package_inits, key=lambda path: (-path.count("/"), path == entry_module_path, path)))
    if entry_module_path in ordered:
        ordered = [path for path in ordered if path != entry_module_path] + [entry_module_path]
    return ordered


def _load_modules(source_files, entry_module_path):
    module_map = {
        item["path"]: _module_name(item["path"])
        for item in source_files
        if str(item.get("path") or "").endswith(".py")
    }
    module_map["artifact_runtime_sdk.py"] = "artifact_runtime_sdk"
    modules = {}
    for path, name in module_map.items():
        module = ModuleType(name)
        module.__file__ = path
        if path.endswith("/__init__.py"):
            module.__package__ = name
            module.__path__ = [_package_dir(path)]
        else:
            module.__package__ = name.rpartition(".")[0]
        sys.modules[name] = module
        modules[path] = module

    source_files_by_path = {str(item.get("path") or ""): item for item in source_files}
    source_files_by_path["artifact_runtime_sdk.py"] = {"path": "artifact_runtime_sdk.py", "content": RUNTIME_SDK_SOURCE}
    execution_order = ["artifact_runtime_sdk.py", *_module_execution_order(source_files, entry_module_path)]
    for path in execution_order:
        item = source_files_by_path.get(path) or {}
        if path not in modules:
            continue
        code = compile(item.get("content") or "", path, "exec")
        exec(code, modules[path].__dict__)
    return modules[entry_module_path]


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        auth = request.headers.get("authorization") or ""
        expected = getattr(self.env, "BACKEND_SHARED_SECRET", "")
        if expected and auth != f"Bearer {expected}":
            return Response(json.dumps({"error": "unauthorized"}), status=401, headers={"content-type": "application/json"})

        try:
            payload = json.loads(await request.text())
        except Exception as exc:
            return _error_response(
                payload={},
                status=400,
                code="INVALID_REQUEST_JSON",
                message="Request body must be valid JSON.",
                phase="request_decode",
                exc=exc,
            )

        source_files = list(payload.get("source_files") or [])
        entry_module_path = str(payload.get("entry_module_path") or "main.py")
        try:
            module = _load_modules(source_files, entry_module_path)
        except Exception as exc:
            return _error_response(
                payload=payload,
                status=500,
                code="WORKER_MODULE_LOAD_FAILED",
                message=f"Failed to load artifact entry module '{entry_module_path}'.",
                phase="module_load",
                entry_module_path=entry_module_path,
                exc=exc,
            )
        execute = getattr(module, "execute", None)
        if execute is None:
            return Response(
                json.dumps(
                    {
                        "detail": {
                            "message": "execute not found",
                            "code": "ENTRYPOINT_NOT_FOUND",
                            "phase": "entrypoint_lookup",
                        },
                        "data": {
                            "status": "failed",
                            "result": None,
                            "error": {
                                "message": "execute not found",
                                "code": "ENTRYPOINT_NOT_FOUND",
                                "phase": "entrypoint_lookup",
                            },
                            "stdout_excerpt": "",
                            "stderr_excerpt": "execute not found",
                            "duration_ms": 0,
                            "worker_id": "artifact-free-plan-runtime",
                            "dispatch_request_id": payload.get("run_id"),
                            "events": [],
                            "runtime_metadata": _runtime_metadata(
                                entry_module_path=entry_module_path,
                                phase="entrypoint_lookup",
                            ),
                        },
                    }
                ),
                status=400,
                headers={"content-type": "application/json"},
            )

        inputs = payload.get("inputs")
        config = payload.get("config") or {}
        context = payload.get("context") or {}
        runtime_sdk = sys.modules.get("artifact_runtime_sdk")
        if runtime_sdk is not None:
            configure_runtime = getattr(runtime_sdk, "configure_artifact_runtime", None)
            if callable(configure_runtime):
                configure_runtime(
                    outbound_base_url=payload.get("outbound_base_url"),
                    outbound_grant=payload.get("outbound_grant"),
                    allowed_hosts=payload.get("allowed_hosts") or [],
                )
        try:
            result = execute(inputs, config, context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            return _error_response(
                payload=payload,
                status=500,
                code="WORKER_EXECUTION_FAILED",
                message="Artifact execution failed inside free-plan runtime worker.",
                phase="execute",
                entry_module_path=entry_module_path,
                exc=exc,
            )

        return Response(
            json.dumps(
                {
                    "data": {
                        "status": "completed",
                        "result": result if isinstance(result, dict) else {"result": result},
                        "error": None,
                        "stdout_excerpt": "",
                        "stderr_excerpt": "",
                        "duration_ms": 0,
                        "worker_id": "artifact-free-plan-runtime",
                        "dispatch_request_id": payload.get("run_id"),
                        "events": [
                            {
                                "event_type": "user_worker_invoked",
                                "payload": {"data": {"entry_module_path": entry_module_path}},
                            }
                        ],
                        "runtime_metadata": _runtime_metadata(entry_module_path=entry_module_path),
                    }
                }
            ),
            headers={"content-type": "application/json"},
        )

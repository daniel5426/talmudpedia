from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactRevision

from .runtime_secret_service import prepare_deployable_source_files
from .source_utils import source_tree_hash
from .workers_validation import is_javascript_code_path, is_python_code_path, validate_workers_compatibility

PYTHON_RUNTIME_WRAPPER_VERSION = "cloudflare-workers-w4p-python-v7"
JS_RUNTIME_WRAPPER_VERSION = "cloudflare-workers-w4p-js-v2"
JS_COMPATIBILITY_DATE = "2026-03-24"
JS_COMPATIBILITY_FLAGS = ["nodejs_compat"]
PYTHON_COMPATIBILITY_DATE = "2026-03-24"
PYTHON_COMPATIBILITY_FLAGS = ["python_workers"]


@dataclass(frozen=True)
class CloudflareArtifactPackage:
    build_hash: str
    worker_name: str
    script_name: str
    modules: list[dict[str, Any]]
    metadata: dict[str, Any]


class CloudflareArtifactPackageBuilder:
    def build_revision_package(self, revision: ArtifactRevision, *, namespace: str) -> CloudflareArtifactPackage:
        language = str(getattr(revision.language, "value", revision.language) or "python")
        source_files = list(revision.source_files or [])
        dependencies = list(revision.python_dependencies or [])
        validate_workers_compatibility(
            language=language,
            source_files=source_files,
            dependencies=dependencies,
            entry_module_path=revision.entry_module_path,
        )
        prepared = prepare_deployable_source_files(language=language, revision=revision)
        compatibility_date = JS_COMPATIBILITY_DATE if language == "javascript" else PYTHON_COMPATIBILITY_DATE
        compatibility_flags = JS_COMPATIBILITY_FLAGS if language == "javascript" else PYTHON_COMPATIBILITY_FLAGS
        runtime_wrapper_version = JS_RUNTIME_WRAPPER_VERSION if language == "javascript" else PYTHON_RUNTIME_WRAPPER_VERSION
        build_hash = source_tree_hash(
            source_files=prepared.source_files,
            entry_module_path=revision.entry_module_path,
            dependencies=dependencies,
            language=language,
            runtime_wrapper_version=runtime_wrapper_version,
            compatibility_date=compatibility_date,
            compatibility_flags=compatibility_flags,
        )
        worker_name = f"artifact-revision-{build_hash[:24]}"
        script_name = worker_name
        modules = (
            _build_javascript_modules(prepared.source_files, revision.entry_module_path)
            if language == "javascript"
            else _build_python_modules(prepared.source_files, revision.entry_module_path)
        )
        metadata = {
            "build_hash": build_hash,
            "namespace": namespace,
            "main_module": "src/index.ts" if language == "javascript" else "__artifact_bootstrap.py",
            "entry_module_path": revision.entry_module_path,
            "dependency_manifest": {"declared": dependencies},
            "revision_id": str(revision.id),
            "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
            "kind": getattr(revision.kind, "value", revision.kind),
            "language": language,
            "runtime_target": str(getattr(revision, "runtime_target", "") or "cloudflare_workers"),
            "compatibility_date": compatibility_date,
            "compatibility_flags": list(compatibility_flags),
            "credential_refs": list(((revision.manifest_json or {}).get("credential_refs") or [])),
        }
        return CloudflareArtifactPackage(
            build_hash=build_hash,
            worker_name=worker_name,
            script_name=script_name,
            modules=modules,
            metadata=metadata,
        )


def _entry_module_name(entry_module_path: str) -> str:
    normalized = str(entry_module_path or "main.py").strip().replace("\\", "/")
    if normalized.endswith("/__init__.py"):
        normalized = normalized[: -len("/__init__.py")]
    elif normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".")


def _build_python_modules(source_files: list[dict[str, str]], entry_module_path: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = [
        {"name": "__artifact_bootstrap.py", "content": _python_runtime_main_module(entry_module_path), "type": "python"}
    ]
    for item in source_files:
        modules.append({"name": item["path"], "content": item["content"], "type": "python" if is_python_code_path(item["path"]) else "text"})
    return modules


def _python_runtime_main_module(entry_module_path: str) -> str:
    module_name = _entry_module_name(entry_module_path)
    return f"""import importlib
import inspect
import json
import traceback
from workers import Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            payload = await request.json()
            inputs = payload.get("inputs")
            config = payload.get("config") or {{}}
            context = payload.get("context") or {{}}
            module = importlib.import_module("{module_name}")
            artifact_execute = getattr(module, "execute")
            result = artifact_execute(inputs, config, context)
            if inspect.isawaitable(result):
                result = await result
            return Response(
                json.dumps({{
                    "status": "completed",
                    "result": result if isinstance(result, dict) else {{"result": result}},
                    "error": None,
                    "stdout_excerpt": "",
                    "stderr_excerpt": "",
                    "duration_ms": 0,
                    "worker_id": "{module_name}",
                    "runtime_metadata": {{"provider": "cloudflare_workers", "language": "python"}},
                    "events": [{{"event_type": "user_worker_invoked", "payload": {{"data": {{"entry_module_path": "{entry_module_path}"}}}}}}],
                }}),
                headers={{"content-type": "application/json"}},
            )
        except Exception as exc:
            detail = {{
                "message": str(exc),
                "code": "WORKER_EXECUTION_FAILED",
                "error_class": type(exc).__name__,
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            }}
            return Response(
                json.dumps({{
                    "detail": detail,
                    "status": "failed",
                    "result": None,
                    "error": detail,
                    "stdout_excerpt": "",
                    "stderr_excerpt": detail["traceback"],
                    "duration_ms": 0,
                    "worker_id": "{module_name}",
                    "runtime_metadata": {{"provider": "cloudflare_workers", "language": "python"}},
                    "events": [{{"event_type": "worker_exception", "payload": {{"data": {{"code": "WORKER_EXECUTION_FAILED"}}}}}}],
                }}),
                status=500,
                headers={{"content-type": "application/json"}},
            )
"""


def _build_javascript_modules(source_files: list[dict[str, str]], entry_module_path: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = [{"name": "src/index.ts", "content": _javascript_runtime_module(entry_module_path), "type": "esm"}]
    for item in source_files:
        target = f"src/artifact/{str(PurePosixPath(item['path']))}"
        modules.append({"name": target, "content": item["content"], "type": "esm" if is_javascript_code_path(item["path"]) else "text"})
    return modules


def _javascript_runtime_module(entry_module_path: str) -> str:
    import_path = f"./artifact/{str(PurePosixPath(entry_module_path))}"
    return f"""import * as artifactModule from "{import_path}";

export default {{
  async fetch(request) {{
    try {{
      const payload = await request.json();
      const inputs = payload.inputs;
      const config = payload.config || {{}};
      const context = payload.context || {{}};
      const execute = artifactModule.execute;
      if (typeof execute !== "function") {{
        return Response.json({{
          detail: {{
            code: "WORKER_EXECUTION_FAILED",
            message: "Artifact entry module must export execute(inputs, config, context)",
          }},
        }}, {{ status: 500 }});
      }}
      const result = await execute(inputs, config, context);
      return Response.json({{
        status: "completed",
        result: result && typeof result === "object" ? result : {{ result }},
        error: null,
        stdout_excerpt: "",
        stderr_excerpt: "",
        duration_ms: 0,
        worker_id: "{entry_module_path}",
        runtime_metadata: {{ provider: "cloudflare_workers", language: "javascript" }},
        events: [{{ event_type: "user_worker_invoked", payload: {{ data: {{ entry_module_path: "{entry_module_path}" }} }} }}],
      }});
    }} catch (error) {{
      const detail = {{
        code: "WORKER_EXECUTION_FAILED",
        message: error instanceof Error ? error.message : String(error),
      }};
      return Response.json({{
        detail,
        status: "failed",
        result: null,
        error: detail,
        stdout_excerpt: "",
        stderr_excerpt: detail.message,
        duration_ms: 0,
        worker_id: "{entry_module_path}",
        runtime_metadata: {{ provider: "cloudflare_workers", language: "javascript" }},
        events: [{{ event_type: "worker_exception", payload: {{ data: {{ code: "WORKER_EXECUTION_FAILED" }} }} }}],
      }}, {{ status: 500 }});
    }}
  }},
}};
"""

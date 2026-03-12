from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactRevision

from .source_utils import source_tree_hash
from .workers_validation import validate_workers_compatibility


@dataclass(frozen=True)
class CloudflareArtifactPackage:
    build_hash: str
    worker_name: str
    script_name: str
    modules: list[dict[str, Any]]
    metadata: dict[str, Any]


class CloudflareArtifactPackageBuilder:
    def build_revision_package(self, revision: ArtifactRevision, *, namespace: str) -> CloudflareArtifactPackage:
        source_files = list(revision.source_files or [])
        python_dependencies = list(revision.python_dependencies or [])
        validate_workers_compatibility(
            source_files=source_files,
            python_dependencies=python_dependencies,
        )
        build_hash = source_tree_hash(
            source_files=source_files,
            entry_module_path=revision.entry_module_path,
            python_dependencies=python_dependencies,
        )
        worker_name = f"artifact-revision-{build_hash[:24]}"
        script_name = f"{namespace}-{worker_name}"
        modules = [
            {
                "name": "main.py",
                "content": _runtime_main_module(revision.entry_module_path),
                "type": "python",
            }
        ]
        modules.extend(
            [
                {
                    "name": item["path"],
                    "content": item["content"],
                    "type": "python",
                }
                for item in source_files
            ]
        )
        modules.append(
            {
                "name": "__talmudpedia_runtime.json",
                "content": {
                    "entry_module_path": revision.entry_module_path,
                    "python_dependencies": python_dependencies,
                },
                "type": "json",
            }
        )
        metadata = {
            "build_hash": build_hash,
            "namespace": namespace,
            "entry_module_path": revision.entry_module_path,
            "dependency_manifest": python_dependencies,
            "revision_id": str(revision.id),
            "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
            "kind": getattr(revision.kind, "value", revision.kind),
            "runtime_target": str(getattr(revision, "runtime_target", "") or "cloudflare_workers"),
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


def _runtime_main_module(entry_module_path: str) -> str:
    module_name = _entry_module_name(entry_module_path)
    return f"""import inspect
import json
import traceback
from js import Response

async def on_fetch(request, env):
    try:
        payload = await request.json()
        inputs = payload.get("inputs")
        config = payload.get("config") or {{}}
        context = payload.get("context") or {{}}
        from {module_name} import execute as artifact_execute
        result = artifact_execute(inputs, config, context)
        if inspect.isawaitable(result):
            result = await result
        return Response.new(
            json.dumps({{
                "status": "completed",
                "result": result if isinstance(result, dict) else {{"result": result}},
                "error": None,
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "duration_ms": 0,
                "worker_id": "{module_name}",
                "runtime_metadata": {{"provider": "cloudflare_workers"}},
                "events": [
                    {{
                        "event_type": "user_worker_invoked",
                        "payload": {{"data": {{"entry_module_path": "{entry_module_path}"}}}},
                    }}
                ],
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
        return Response.new(
            json.dumps({{
                "detail": detail,
                "status": "failed",
                "result": None,
                "error": detail,
                "stdout_excerpt": "",
                "stderr_excerpt": detail["traceback"],
                "duration_ms": 0,
                "worker_id": "{module_name}",
                "runtime_metadata": {{"provider": "cloudflare_workers"}},
                "events": [
                    {{
                        "event_type": "worker_exception",
                        "payload": {{"data": {{"code": "WORKER_EXECUTION_FAILED", "error_class": type(exc).__name__}}}},
                    }}
                ],
            }}),
            status=500,
            headers={{"content-type": "application/json"}},
        )
"""

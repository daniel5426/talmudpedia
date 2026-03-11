import inspect
import json
import sys
from pathlib import PurePosixPath
from types import ModuleType

from workers import Response, WorkerEntrypoint


def _module_name(path: str) -> str:
    normalized = str(PurePosixPath(path)).strip()
    if normalized.endswith("/__init__.py"):
        normalized = normalized[: -len("/__init__.py")]
    elif normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".")


def _load_modules(source_files, entry_module_path):
    module_map = {
        item["path"]: _module_name(item["path"])
        for item in source_files
        if str(item.get("path") or "").endswith(".py")
    }
    modules = {}
    for path, name in module_map.items():
        module = ModuleType(name)
        module.__file__ = path
        module.__package__ = name.rpartition(".")[0]
        sys.modules[name] = module
        modules[path] = module

    ordered = sorted(source_files, key=lambda item: (item["path"] == entry_module_path, item["path"]))
    for item in ordered:
        path = item.get("path")
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

        payload = json.loads(await request.text())
        source_files = list(payload.get("source_files") or [])
        entry_module_path = str(payload.get("entry_module_path") or "main.py")
        module = _load_modules(source_files, entry_module_path)
        execute = getattr(module, "execute", None)
        if execute is None:
            return Response(
                json.dumps(
                    {
                        "data": {
                            "status": "failed",
                            "result": None,
                            "error": {"message": "execute not found", "code": "ENTRYPOINT_NOT_FOUND"},
                            "stdout_excerpt": "",
                            "stderr_excerpt": "execute not found",
                            "duration_ms": 0,
                            "worker_id": "artifact-free-plan-runtime",
                            "dispatch_request_id": payload.get("run_id"),
                            "events": [],
                            "runtime_metadata": {"provider": "cloudflare_workers", "runtime_mode": "standard_worker_test"},
                        }
                    }
                ),
                status=400,
                headers={"content-type": "application/json"},
            )

        inputs = payload.get("inputs")
        config = payload.get("config") or {}
        context = payload.get("context") or {}
        result = execute(inputs, config, context)
        if inspect.isawaitable(result):
            result = await result

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
                        "runtime_metadata": {"provider": "cloudflare_workers", "runtime_mode": "standard_worker_test"},
                    }
                }
            ),
            headers={"content-type": "application/json"},
        )

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


WORKER_PATH = (
    Path(__file__).resolve().parents[3]
    / "runtime"
    / "cloudflare-artifacts"
    / "free-plan-runtime"
    / "src"
    / "main.py"
)


class _FakeResponse:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}


class _FakeWorkerEntrypoint:
    def __init__(self):
        self.env = SimpleNamespace(BACKEND_SHARED_SECRET="")


class _FakeRequest:
    def __init__(self, payload: dict[str, object], *, auth: str = ""):
        self._payload = payload
        self.headers = {"authorization": auth} if auth else {}

    async def text(self):
        return json.dumps(self._payload)


def _load_worker_module():
    module_name = "test_free_plan_runtime_main"
    spec = importlib.util.spec_from_file_location(module_name, WORKER_PATH)
    assert spec is not None and spec.loader is not None

    fake_workers = ModuleType("workers")
    fake_workers.Response = _FakeResponse
    fake_workers.WorkerEntrypoint = _FakeWorkerEntrypoint

    previous_workers = sys.modules.get("workers")
    sys.modules["workers"] = fake_workers
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        if previous_workers is not None:
            sys.modules["workers"] = previous_workers
        else:
            sys.modules.pop("workers", None)


def test_free_plan_runtime_executes_package_import_tree():
    module = _load_worker_module()
    worker = module.Default()
    request = _FakeRequest(
        {
            "run_id": "run-1",
            "entry_module_path": "main.py",
            "source_files": [
                {"path": "pkg/__init__.py", "content": "from . import agents\nVALUE = agents.VALUE\n"},
                {"path": "pkg/agents.py", "content": "VALUE = 42\n"},
                {
                    "path": "main.py",
                    "content": "from pkg import VALUE\n\ndef execute(inputs, config, context):\n    return {'value': VALUE}\n",
                },
            ],
            "inputs": {},
            "config": {},
            "context": {},
        }
    )

    response = asyncio.run(worker.fetch(request))
    payload = json.loads(response.body)

    assert response.status == 200
    assert payload["data"]["status"] == "completed"
    assert payload["data"]["result"]["value"] == 42


def test_free_plan_runtime_returns_json_detail_for_module_load_failure():
    module = _load_worker_module()
    worker = module.Default()
    request = _FakeRequest(
        {
            "run_id": "run-2",
            "entry_module_path": "main.py",
            "source_files": [
                {"path": "main.py", "content": "from missing_package import thing\n\ndef execute(inputs, config, context):\n    return {'ok': True}\n"},
            ],
            "inputs": {},
            "config": {},
            "context": {},
        }
    )

    response = asyncio.run(worker.fetch(request))
    payload = json.loads(response.body)

    assert response.status == 500
    assert payload["detail"]["code"] == "WORKER_MODULE_LOAD_FAILED"
    assert payload["detail"]["phase"] == "module_load"
    assert payload["detail"]["error_class"] == "ModuleNotFoundError"
    assert "missing_package" in payload["detail"]["traceback"]
    assert payload["data"]["error"]["code"] == "WORKER_MODULE_LOAD_FAILED"
    assert payload["data"]["stderr_excerpt"]

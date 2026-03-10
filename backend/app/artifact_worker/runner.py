from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class _StdoutLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("artifact-worker-runner")
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(msg, *args, **kwargs)


def _load_execute_fn(bundle_dir: Path):
    handler_path = bundle_dir / "handler.py"
    if not handler_path.exists():
        raise FileNotFoundError("handler.py not found in artifact bundle")
    spec = importlib.util.spec_from_file_location(f"artifact_bundle_{bundle_dir.name}", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load artifact bundle handler")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    execute_fn = getattr(module, "execute", None)
    if execute_fn is None:
        raise AttributeError("Artifact handler missing execute()")
    return execute_fn


def _input_summary(value: Any) -> str:
    if isinstance(value, dict):
        return f"dict:{sorted(value.keys())}"
    if isinstance(value, list):
        return f"list:{len(value)}"
    return type(value).__name__


async def _invoke(execute_fn, inputs: Any, config: dict[str, Any], context: dict[str, Any]) -> Any:
    params = list(inspect.signature(execute_fn).parameters.values())
    legacy_context = SimpleNamespace(
        input_data=inputs,
        config=config,
        logger=_StdoutLogger(),
        context=context,
    )
    if len(params) <= 1:
        call = lambda: execute_fn(legacy_context)
    elif len(params) == 2:
        call = lambda: execute_fn(inputs, config)
    else:
        call = lambda: execute_fn(inputs, config, context)

    if inspect.iscoroutinefunction(execute_fn):
        return await call()
    result = call()
    if inspect.isawaitable(result):
        return await result
    return result


async def _main(bundle_dir: Path, request_path: Path, result_path: Path) -> int:
    logger = _StdoutLogger()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    logger.info(
        "Loading artifact bundle bundle_dir=%s revision_id=%s run_id=%s",
        bundle_dir,
        payload.get("revision_id"),
        payload.get("run_id"),
    )
    execute_fn = _load_execute_fn(bundle_dir)
    logger.info(
        "Invoking artifact handler execute_fn=%s domain=%s input_summary=%s config_keys=%s",
        getattr(execute_fn, "__name__", "execute"),
        payload.get("domain"),
        _input_summary(payload.get("inputs")),
        sorted(dict(payload.get("config") or {}).keys()),
    )
    result = await _invoke(
        execute_fn,
        payload.get("inputs"),
        dict(payload.get("config") or {}),
        dict(payload.get("context") or {}),
    )
    if not isinstance(result, dict):
        result = {"result": result}
    result_path.write_text(json.dumps(result, default=str), encoding="utf-8")
    logger.info("Artifact handler completed result_keys=%s", sorted(result.keys()))
    return 0


if __name__ == "__main__":
    bundle_dir = Path(sys.argv[1])
    request_path = Path(sys.argv[2])
    result_path = Path(sys.argv[3])
    raise SystemExit(asyncio.run(_main(bundle_dir, request_path, result_path)))

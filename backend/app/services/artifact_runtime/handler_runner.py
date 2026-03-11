from __future__ import annotations

import inspect
import logging
import sys
from typing import Any


class _StdoutLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("artifact-runtime-handler")
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


async def invoke_artifact_handler(execute_fn, inputs: Any, config: dict[str, Any], context: dict[str, Any]) -> Any:
    params = list(inspect.signature(execute_fn).parameters.values())
    if len(params) != 3:
        raise TypeError("Artifact execute() must accept exactly (inputs, config, context)")

    context_with_logger = dict(context or {})
    context_with_logger.setdefault("logger", _StdoutLogger())
    call = lambda: execute_fn(inputs, config, context_with_logger)

    if inspect.iscoroutinefunction(execute_fn):
        return await call()
    result = call()
    if inspect.isawaitable(result):
        return await result
    return result

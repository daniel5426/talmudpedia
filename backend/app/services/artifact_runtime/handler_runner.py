from __future__ import annotations

import inspect
import logging
import sys
from types import SimpleNamespace
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

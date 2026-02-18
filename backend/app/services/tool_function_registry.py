from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


_TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {}


def register_tool_function(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _TOOL_FUNCTIONS[name] = fn
        return fn

    return decorator


def get_tool_function(name: str) -> Callable[..., Any] | None:
    return _TOOL_FUNCTIONS.get(name)


def list_tool_functions() -> list[str]:
    return sorted(_TOOL_FUNCTIONS.keys())


@register_tool_function("echo")
async def echo_tool(payload: Any) -> Any:
    return payload


def run_tool_function(_name: str, fn: Callable[..., Any], payload: Any) -> Any:
    if asyncio.iscoroutinefunction(fn):
        return fn(payload)
    return asyncio.to_thread(fn, payload)

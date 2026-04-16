from __future__ import annotations

import asyncio
from importlib import import_module
from threading import Lock
from collections.abc import Callable
from typing import Any


_TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {}
_BOOTSTRAPPED_MODULES: set[str] = set()
_BOOTSTRAP_LOCK = Lock()
_DEFAULT_TOOL_FUNCTION_MODULES: tuple[str, ...] = (
    "app.services.file_space_tools",
    "app.services.published_app_coding_agent_tools",
    "app.services.platform_native_tools",
    "app.services.artifact_coding_agent_tools",
    "app.services.artifact_coding_agent_test_tools",
    "app.services.platform_architect_worker_tools",
)
_TOOL_FUNCTION_MODULE_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("files_", ("app.services.file_space_tools",)),
    ("coding_agent_", ("app.services.published_app_coding_agent_tools",)),
    ("platform_native_", ("app.services.platform_native_tools",)),
    (
        "artifact_coding_",
        (
            "app.services.artifact_coding_agent_tools",
            "app.services.artifact_coding_agent_test_tools",
        ),
    ),
    ("architect_worker_", ("app.services.platform_architect_worker_tools",)),
)


def register_tool_function(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _TOOL_FUNCTIONS[name] = fn
        return fn

    return decorator


def ensure_tool_functions_registered(
    *,
    function_name: str | None = None,
    modules: tuple[str, ...] | None = None,
) -> list[str]:
    target_modules = modules
    if target_modules is None:
        if function_name:
            for prefix, prefix_modules in _TOOL_FUNCTION_MODULE_PREFIXES:
                if function_name.startswith(prefix):
                    target_modules = prefix_modules
                    break
        if target_modules is None:
            target_modules = _DEFAULT_TOOL_FUNCTION_MODULES

    imported: list[str] = []
    with _BOOTSTRAP_LOCK:
        for module_name in target_modules:
            if module_name in _BOOTSTRAPPED_MODULES:
                continue
            import_module(module_name)
            _BOOTSTRAPPED_MODULES.add(module_name)
            imported.append(module_name)

    if (
        function_name
        and function_name not in _TOOL_FUNCTIONS
        and modules is None
        and tuple(target_modules) != _DEFAULT_TOOL_FUNCTION_MODULES
    ):
        imported.extend(
            ensure_tool_functions_registered(
                modules=_DEFAULT_TOOL_FUNCTION_MODULES,
            )
        )

    return imported


def get_tool_function(name: str) -> Callable[..., Any] | None:
    return _TOOL_FUNCTIONS.get(name)


def list_tool_functions() -> list[str]:
    ensure_tool_functions_registered()
    return sorted(_TOOL_FUNCTIONS.keys())


@register_tool_function("echo")
async def echo_tool(payload: Any) -> Any:
    return payload


def run_tool_function(_name: str, fn: Callable[..., Any], payload: Any) -> Any:
    if asyncio.iscoroutinefunction(fn):
        return fn(payload)
    return asyncio.to_thread(fn, payload)

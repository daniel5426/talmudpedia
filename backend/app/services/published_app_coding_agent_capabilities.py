from __future__ import annotations

import os
from typing import Any

from app.services.published_app_coding_agent_tools import CODING_AGENT_TOOL_SPECS

CODING_AGENT_ENGINE_NATIVE = "native"
CODING_AGENT_ENGINE_OPENCODE = "opencode"


def _default_execution_engine() -> str:
    value = str(os.getenv("APPS_CODING_AGENT_DEFAULT_ENGINE", CODING_AGENT_ENGINE_OPENCODE) or "").strip().lower()
    if value == CODING_AGENT_ENGINE_NATIVE:
        return CODING_AGENT_ENGINE_NATIVE
    return CODING_AGENT_ENGINE_OPENCODE


def _native_engine_enabled() -> bool:
    value = str(os.getenv("APPS_CODING_AGENT_NATIVE_ENABLED", "0") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def build_published_app_coding_agent_capabilities() -> dict[str, Any]:
    native_tools: list[dict[str, str]] = []
    for spec in CODING_AGENT_TOOL_SPECS:
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or "").strip()
        slug = str(spec.get("slug") or "").strip()
        function_name = str(spec.get("function_name") or "").strip()
        if not (name and slug and function_name):
            continue
        native_tools.append(
            {
                "name": name,
                "slug": slug,
                "function_name": function_name,
            }
        )
    native_tools.sort(key=lambda item: item["slug"])

    return {
        "default_engine": _default_execution_engine(),
        "native_enabled": _native_engine_enabled(),
        "native_tool_count": len(native_tools),
        "native_tools": native_tools,
        "opencode_policy": {
            "tooling_mode": "delegated_to_upstream_opencode",
            "repo_tool_allowlist_configured": True,
            "workspace_permission_model": "project_local_custom_tools_and_context_file",
            "summary": (
                "OpenCode execution is delegated to the upstream runtime, with platform-managed "
                "project-local custom tools bootstrapped into each workspace."
            ),
        },
    }

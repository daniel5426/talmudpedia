from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OPENUI_MODE_OFF = "off"
OPENUI_MODE_OPENUI = "openui"
DEFAULT_OPENUI_COMPONENT_LIBRARY_ID = "openui-default-v1"
DEFAULT_OPENUI_SURFACE = "chat_inline"
DEFAULT_OPENUI_MAX_BLOCKS = 6

SUPPORTED_OPENUI_COMPONENT_LIBRARIES: dict[str, tuple[str, ...]] = {
    DEFAULT_OPENUI_COMPONENT_LIBRARY_ID: (
        "Card",
        "CardHeader",
        "TextContent",
        "Table",
        "Callout",
        "TagBlock",
        "Buttons",
        "Button",
        "ListBlock",
        "Steps",
        "BarChart",
        "LineChart",
        "AreaChart",
        "PieChart",
        "RadarChart",
        "ScatterChart",
        "Series",
        "Stack",
        "SectionBlock",
        "FollowUpBlock",
    ),
}


@dataclass(frozen=True)
class OpenUIRuntimeConfig:
    mode: str
    component_library_id: str
    surface: str
    max_blocks: int

    @property
    def enabled(self) -> bool:
        return self.mode == OPENUI_MODE_OPENUI


def resolve_openui_runtime_config(config: dict[str, Any] | None) -> OpenUIRuntimeConfig:
    source = config if isinstance(config, dict) else {}
    raw_mode = str(source.get("generative_ui_mode") or OPENUI_MODE_OFF).strip().lower()
    mode = OPENUI_MODE_OPENUI if raw_mode == OPENUI_MODE_OPENUI else OPENUI_MODE_OFF

    component_library_id = str(
        source.get("generative_ui_component_library_id") or DEFAULT_OPENUI_COMPONENT_LIBRARY_ID
    ).strip() or DEFAULT_OPENUI_COMPONENT_LIBRARY_ID
    if component_library_id not in SUPPORTED_OPENUI_COMPONENT_LIBRARIES:
        component_library_id = DEFAULT_OPENUI_COMPONENT_LIBRARY_ID

    raw_surface = str(source.get("generative_ui_surface") or DEFAULT_OPENUI_SURFACE).strip().lower()
    surface = raw_surface if raw_surface in {"chat_inline", "app_canvas"} else DEFAULT_OPENUI_SURFACE

    try:
        max_blocks = int(source.get("generative_ui_max_blocks") or DEFAULT_OPENUI_MAX_BLOCKS)
    except Exception:
        max_blocks = DEFAULT_OPENUI_MAX_BLOCKS
    if max_blocks < 1:
        max_blocks = DEFAULT_OPENUI_MAX_BLOCKS

    return OpenUIRuntimeConfig(
        mode=mode,
        component_library_id=component_library_id,
        surface=surface,
        max_blocks=max_blocks,
    )


def build_openui_system_prompt(
    *,
    base_instructions: str,
    runtime_config: OpenUIRuntimeConfig,
) -> str:
    if not runtime_config.enabled:
        return base_instructions

    components = ", ".join(SUPPORTED_OPENUI_COMPONENT_LIBRARIES[runtime_config.component_library_id])
    openui_rules = [
        "You are in OpenUI generative UI mode.",
        "Respond in OpenUI Lang only. Do not use markdown, prose paragraphs, JSON, XML, or code fences.",
        f"Use only components from the `{runtime_config.component_library_id}` library: {components}.",
        f"Target the `{runtime_config.surface}` surface.",
        f"Emit at most {runtime_config.max_blocks} top-level UI blocks unless the user explicitly asks for a larger dashboard.",
        "Prefer concise cards, tables, steps, callouts, and charts over decorative layout.",
        "If data is partial, surface the caveat in the rendered UI with a callout.",
        "If no visual is warranted, render a small content-focused UI instead of plain text.",
    ]

    base = str(base_instructions or "").strip()
    if base:
        return f"{base}\n\n" + "\n".join(openui_rules)
    return "\n".join(openui_rules)


def build_openui_payload(
    *,
    content: str | None = None,
    content_delta: str | None = None,
    runtime_config: OpenUIRuntimeConfig,
    is_final: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "format": "openui",
        "version": 1,
        "component_library_id": runtime_config.component_library_id,
        "surface": runtime_config.surface,
        "ast": None,
        "is_final": bool(is_final),
    }
    if content is not None:
        payload["content"] = content
    if content_delta is not None:
        payload["content_delta"] = content_delta
    return payload


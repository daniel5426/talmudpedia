from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


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
        "Col",
        "Callout",
        "BarChart",
        "LineChart",
        "AreaChart",
        "PieChart",
        "Slice",
        "Series",
        "Stack",
    ),
}

OPENUI_LANG_EXAMPLES: tuple[str, ...] = (
    """Example 1 — Table:
root = Card([title, tbl])
title = TextContent("Top Languages", "large-heavy")
tbl = Table(cols, rows)
cols = [Col("Language", "string"), Col("Users (M)", "number"), Col("Year", "number")]
rows = [["Python", 15.7, 1991], ["JavaScript", 14.2, 1995], ["Java", 12.1, 1995]]""",
    """Example 2 — Concise content card:
root = Card([header, note])
header = CardHeader("Data caveat", "Proxy values in use")
note = Callout("info", "Quality note", "Direct principal is sparse, so notional_proxy is used.")""",
    """Example 3 — PRICO-style chart and table:
root = Card([header, chart, tableTitle, table, note])
header = CardHeader("Bank concentration", "Atlas Medical")
chart = PieChart([slice1, slice2, slice3], "donut")
slice1 = Slice("Bank A", 44.3)
slice2 = Slice("Bank B", 24.1)
slice3 = Slice("Bank C", 19.2)
tableTitle = TextContent("Returned rows", "small-heavy")
cols = [Col("Bank", "string"), Col("Share (%)", "number")]
rows = [["Bank A", 44.3], ["Bank B", 24.1], ["Bank C", 19.2]]
table = Table(cols, rows)
note = Callout("info", "Data caveat", "Proxy values are being used.")""",
)


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
        "Respond in OpenUI Lang only. Do not use markdown, prose paragraphs, JSON, XML, YAML, arrays, objects, or code fences.",
        "OpenUI Lang is assignment-based. Use statements like `root = Card([...])`, `header = CardHeader(...)`, `chart = PieChart([...])`.",
        "Never emit JSON like `[{\"Card\": ...}]` or `{ \"PieChart\": ... }`.",
        f"Use only components from the `{runtime_config.component_library_id}` library: {components}.",
        f"Target the `{runtime_config.surface}` surface.",
        f"Emit at most {runtime_config.max_blocks} top-level UI blocks unless the user explicitly asks for a larger dashboard.",
        "Every response is a single `Card([...])` root for chat. Do not use `Stack` as the root container.",
        "Prefer concise cards, tables, callouts, and charts over decorative layout.",
        "If data is partial, surface the caveat in the rendered UI with a callout.",
        "If no visual is warranted, render a small content-focused UI instead of plain text.",
        "Define referenced nodes with `name = Component(...)` assignments.",
        "The first statement must be `root = Card(...)`. OpenUI renders the first statement as the root.",
        "For chat responses, `Card` children already stack vertically. Do not pass layout params to `Card`.",
        "For tables, use `cols = [Col(...), Col(...)]`, `rows = [[...], [...]]`, then `table = Table(cols, rows)`.",
        "Do not inline `Col(...)` constructors directly inside `Table(...)`.",
        "For pie charts, use `PieChart([Slice(...), Slice(...)])` or `PieChart([Slice(...), Slice(...)], \"donut\")`.",
        "For callouts, use exactly `Callout(variant, title, description)`.",
        "Allowed callout variants are only: neutral, info, warning, success, error.",
        "For PRICO answers, stay within these primitives: Card, CardHeader, TextContent, Table, Col, Callout, PieChart, Slice, BarChart, LineChart, AreaChart, Series.",
        "For bar charts, use `BarChart(labels, [series1, series2], \"grouped\")`.",
        "For line and area charts, use labels plus `Series(...)` assignments.",
        "Do not invent props like `title`, `unit`, `legend`, `items`, `numeric_format`, or object-shaped tag values unless shown in the examples.",
        "Do not use Buttons, Button, Steps, TagBlock, RadarChart, ScatterChart, SectionBlock, or FollowUpBlock for PRICO responses.",
        "Write statements in top-down order: root first, then referenced child nodes, then data arrays and leaf nodes.",
        "Avoid repeating the same assignments twice.",
        "Do not emit any heading before the first assignment.",
        "Do not explain the UI outside the UI. The entire assistant output must be valid OpenUI Lang.",
    ]
    openui_rules.append("Use this syntax style:")
    openui_rules.extend(OPENUI_LANG_EXAMPLES)

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


_OPENUI_ASSIGNMENT_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")
_OPENUI_ROOT_ASSIGNMENT_RE = re.compile(r"^\s*root\s*=")
def sanitize_openui_content(content: str | None) -> str:
    raw = str(content or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""

    lines = raw.split("\n")
    first_assignment = next((index for index, line in enumerate(lines) if _OPENUI_ASSIGNMENT_RE.match(line)), None)
    if first_assignment is None:
        return raw
    lines = lines[first_assignment:]

    root_index = next((index for index, line in enumerate(lines) if _OPENUI_ROOT_ASSIGNMENT_RE.match(line)), None)
    if root_index is not None and root_index > 0:
        root_line = lines[root_index]
        remaining = lines[:root_index] + lines[root_index + 1 :]
        lines = [root_line, *remaining]

    return "\n".join(lines).strip()


def is_openui_content_complete(content: str | None) -> bool:
    source = str(content or "").strip()
    if not source:
        return False

    depth_paren = 0
    depth_bracket = 0
    depth_brace = 0
    in_string = False
    escaped = False

    for char in source:
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1
        elif char == "{":
            depth_brace += 1
        elif char == "}":
            depth_brace -= 1

        if depth_paren < 0 or depth_bracket < 0 or depth_brace < 0:
            return False

    if in_string or depth_paren != 0 or depth_bracket != 0 or depth_brace != 0:
        return False

    return bool(_OPENUI_ROOT_ASSIGNMENT_RE.search(source))

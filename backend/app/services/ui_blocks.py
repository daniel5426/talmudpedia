from __future__ import annotations

from copy import deepcopy
from typing import Any


UI_BLOCKS_BUILTIN_KEY = "ui_blocks"
UI_BLOCKS_RENDERER_KIND = "ui_blocks"
UI_BLOCKS_OUTPUT_KIND = "ui_blocks_bundle"
UI_BLOCKS_CONTRACT_VERSION = "v1"
UI_BLOCKS_TOOL_SLUG = "builtin-ui-blocks"  # Legacy internal row key only; canonical identity is builtin_key.
UI_BLOCKS_PACKAGE_NAME = "@agents24/ui-blocks-react"
UI_BLOCKS_CONTRACT_PACKAGE_NAME = "@agents24/ui-blocks-contract"
UI_BLOCKS_INSTALL_COMMAND = "npx @agents24/ui-blocks-react init"
UI_BLOCKS_INSTALL_DOCS_URL = (
    "https://github.com/daniel5426/agents24-ui-blocks/blob/main/docs/install.md"
)
UI_BLOCK_KINDS = ("kpi", "pie", "bar", "compare", "table", "note")


class UIBlocksValidationError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = dict(details or {})
        self.code = "INVALID_UI_BLOCKS"


def frontend_requirements_for_tool(tool: Any) -> dict[str, Any] | None:
    builtin_key = str(getattr(tool, "builtin_key", "") or "").strip().lower()
    if builtin_key != UI_BLOCKS_BUILTIN_KEY:
        return None
    return frontend_requirements_payload()


def frontend_requirements_payload() -> dict[str, Any]:
    return {
        "required": True,
        "renderer_kind": UI_BLOCKS_RENDERER_KIND,
        "package_name": UI_BLOCKS_PACKAGE_NAME,
        "contract_package_name": UI_BLOCKS_CONTRACT_PACKAGE_NAME,
        "install_command": UI_BLOCKS_INSTALL_COMMAND,
        "hosted_template_support": {"classic_chat": True},
        "install_docs_url": UI_BLOCKS_INSTALL_DOCS_URL,
    }


def ui_blocks_tool_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "subtitle": {"type": "string"},
            "rows": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "blocks": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "object", "additionalProperties": True},
                        }
                    },
                    "required": ["blocks"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["rows"],
        "additionalProperties": False,
    }


def ui_blocks_tool_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "const": UI_BLOCKS_OUTPUT_KIND},
            "contract_version": {"type": "string", "const": UI_BLOCKS_CONTRACT_VERSION},
            "bundle": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "rows": {"type": "array"},
                },
                "required": ["rows"],
                "additionalProperties": False,
            },
        },
        "required": ["kind", "contract_version", "bundle"],
        "additionalProperties": False,
    }


def normalize_ui_blocks_tool_input(input_data: dict[str, Any]) -> dict[str, Any]:
    bundle = validate_ui_blocks_bundle(input_data)
    return {
        "kind": UI_BLOCKS_OUTPUT_KIND,
        "contract_version": UI_BLOCKS_CONTRACT_VERSION,
        "bundle": bundle,
    }


def validate_ui_blocks_bundle(input_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(input_data, dict):
        raise UIBlocksValidationError(
            "UI Blocks input must be a JSON object.",
            details={"path": "bundle", "hint": "Pass a JSON object with rows.", "retryable": True},
        )

    rows = input_data.get("rows")
    if not isinstance(rows, list) or len(rows) == 0:
        raise UIBlocksValidationError(
            "At least one row is required.",
            details={"path": "rows", "hint": "Pass rows as a non-empty JSON array.", "retryable": True},
        )

    seen_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise UIBlocksValidationError(
                "Each row must be an object.",
                details={"path": f"rows.[{row_index}]", "hint": "Each row must contain a blocks array.", "retryable": True},
            )
        blocks = row.get("blocks")
        if not isinstance(blocks, list) or len(blocks) == 0:
            raise UIBlocksValidationError(
                "Each row needs at least one block.",
                details={"path": f"rows.[{row_index}].blocks", "hint": "Add a non-empty blocks array.", "retryable": True},
            )

        row_span = 0
        normalized_blocks: list[dict[str, Any]] = []
        for block_index, block in enumerate(blocks):
            normalized_block = _validate_block(
                block,
                row_index=row_index,
                block_index=block_index,
                seen_ids=seen_ids,
            )
            row_span += int(normalized_block["span"])
            normalized_blocks.append(normalized_block)

        if row_span > 12:
            raise UIBlocksValidationError(
                f"Row span exceeds 12 (got {row_span}).",
                details={
                    "path": f"rows.[{row_index}].blocks",
                    "hint": "Each row's total span must be at most 12.",
                    "retryable": True,
                },
            )

        normalized_rows.append({"blocks": normalized_blocks})

    normalized_bundle: dict[str, Any] = {"rows": normalized_rows}
    title = str(input_data.get("title") or "").strip()
    subtitle = str(input_data.get("subtitle") or "").strip()
    if title:
        normalized_bundle["title"] = title
    if subtitle:
        normalized_bundle["subtitle"] = subtitle
    return normalized_bundle


def _validate_block(
    block: Any,
    *,
    row_index: int,
    block_index: int,
    seen_ids: set[str],
) -> dict[str, Any]:
    path_prefix = f"rows.[{row_index}].blocks.[{block_index}]"
    if not isinstance(block, dict):
        raise UIBlocksValidationError(
            "Each block must be an object.",
            details={"path": path_prefix, "hint": "Use a JSON object for each block.", "retryable": True},
        )

    normalized = deepcopy(block)
    kind = str(normalized.get("kind") or "").strip().lower()
    block_id = str(normalized.get("id") or "").strip()
    title = str(normalized.get("title") or "").strip()
    span_raw = normalized.get("span")

    if kind not in UI_BLOCK_KINDS:
        raise UIBlocksValidationError(
            f"Unsupported block kind '{kind or 'unknown'}'.",
            details={"path": f"{path_prefix}.kind", "hint": f"Use one of: {', '.join(UI_BLOCK_KINDS)}.", "retryable": True},
        )
    if not block_id:
        raise UIBlocksValidationError(
            "Block id is required.",
            details={"path": f"{path_prefix}.id", "block_kind": kind, "hint": "Every block needs a unique id.", "retryable": True},
        )
    if block_id in seen_ids:
        raise UIBlocksValidationError(
            f"Duplicate block id '{block_id}'.",
            details={"path": f"{path_prefix}.id", "block_id": block_id, "block_kind": kind, "hint": "Every block in the bundle must have a unique id.", "retryable": True},
        )
    if not title:
        raise UIBlocksValidationError(
            "Block title is required.",
            details={"path": f"{path_prefix}.title", "block_id": block_id, "block_kind": kind, "hint": "Every block requires a non-empty title.", "retryable": True},
        )
    if not isinstance(span_raw, int) or span_raw < 1 or span_raw > 12:
        raise UIBlocksValidationError(
            "Block span must be an integer between 1 and 12.",
            details={"path": f"{path_prefix}.span", "block_id": block_id, "block_kind": kind, "hint": "Use an integer span from 1 to 12.", "retryable": True},
        )

    seen_ids.add(block_id)
    normalized["kind"] = kind
    normalized["id"] = block_id
    normalized["title"] = title

    if kind == "kpi":
        value = str(normalized.get("value") or "").strip()
        if not value:
            raise UIBlocksValidationError(
                "KPI value is required.",
                details={"path": f"{path_prefix}.value", "block_id": block_id, "block_kind": kind, "hint": "KPI blocks require a non-empty value field.", "retryable": True},
            )
        normalized["value"] = value
        return normalized

    if kind in {"pie", "bar"}:
        data = normalized.get("data")
        if not isinstance(data, list) or len(data) == 0:
            raise UIBlocksValidationError(
                "Chart blocks need at least one data point.",
                details={"path": f"{path_prefix}.data", "block_id": block_id, "block_kind": kind, "hint": "Chart blocks require a non-empty data array of { label, value } items.", "retryable": True},
            )
        normalized_points: list[dict[str, Any]] = []
        for point_index, point in enumerate(data):
            if not isinstance(point, dict):
                raise UIBlocksValidationError(
                    "Chart data points must be objects.",
                    details={"path": f"{path_prefix}.data.[{point_index}]", "block_id": block_id, "block_kind": kind, "hint": "Each data point must be { label, value }.", "retryable": True},
                )
            label = str(point.get("label") or "").strip()
            value = point.get("value")
            if not label or not isinstance(value, (int, float)):
                raise UIBlocksValidationError(
                    "Chart data points require label and numeric value.",
                    details={"path": f"{path_prefix}.data.[{point_index}]", "block_id": block_id, "block_kind": kind, "hint": "Each data point must be { label, value } with numeric value.", "retryable": True},
                )
            normalized_points.append({"label": label, "value": float(value) if isinstance(value, float) else int(value)})
        normalized["data"] = normalized_points
        return normalized

    if kind == "compare":
        required_fields = ("leftLabel", "leftValue", "rightLabel", "rightValue")
        for field_name in required_fields:
            value = normalized.get(field_name)
            if field_name.endswith("Value"):
                if not isinstance(value, (int, float)):
                    raise UIBlocksValidationError(
                        f"Compare blocks need numeric {field_name}.",
                        details={"path": f"{path_prefix}.{field_name}", "block_id": block_id, "block_kind": kind, "hint": "Compare blocks require leftLabel, leftValue, rightLabel, and rightValue.", "retryable": True},
                    )
            else:
                if not str(value or "").strip():
                    raise UIBlocksValidationError(
                        f"Compare blocks need {field_name}.",
                        details={"path": f"{path_prefix}.{field_name}", "block_id": block_id, "block_kind": kind, "hint": "Compare blocks require leftLabel, leftValue, rightLabel, and rightValue.", "retryable": True},
                    )
        return normalized

    if kind == "table":
        columns = normalized.get("columns")
        rows = normalized.get("rows")
        if not isinstance(columns, list) or len(columns) == 0 or any(not str(item or "").strip() for item in columns):
            raise UIBlocksValidationError(
                "Table blocks need at least one non-empty column.",
                details={"path": f"{path_prefix}.columns", "block_id": block_id, "block_kind": kind, "hint": "Table blocks require columns and rows with matching cell counts.", "retryable": True},
            )
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise UIBlocksValidationError(
                "Table rows must be an array.",
                details={"path": f"{path_prefix}.rows", "block_id": block_id, "block_kind": kind, "hint": "Table blocks require columns and rows with matching cell counts.", "retryable": True},
            )
        expected_len = len(columns)
        normalized_rows: list[list[str]] = []
        for row_item_index, row_item in enumerate(rows):
            if not isinstance(row_item, list) or len(row_item) != expected_len:
                actual_len = len(row_item) if isinstance(row_item, list) else 0
                raise UIBlocksValidationError(
                    f"Table row {row_item_index + 1} has {actual_len} cells but expected {expected_len}.",
                    details={"path": f"{path_prefix}.rows.[{row_item_index}]", "block_id": block_id, "block_kind": kind, "hint": "Table blocks require columns and rows with matching cell counts.", "retryable": True},
                )
            normalized_rows.append([str(cell) for cell in row_item])
        normalized["columns"] = [str(item).strip() for item in columns]
        normalized["rows"] = normalized_rows
        return normalized

    text = str(normalized.get("text") or "").strip()
    if not text:
        raise UIBlocksValidationError(
            "Note blocks need text.",
            details={"path": f"{path_prefix}.text", "block_id": block_id, "block_kind": kind, "hint": "Note blocks require a text field.", "retryable": True},
        )
    normalized["text"] = text
    return normalized

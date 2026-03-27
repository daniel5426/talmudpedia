from __future__ import annotations

import ast
import re
from typing import Any


class ArtifactEntrypointContractError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__(self.errors[0] if self.errors else "Artifact entrypoint contract is invalid")


_JS_DIRECT_EXPORT_PATTERNS = (
    re.compile(r"(?m)^\s*export\s+(?:async\s+)?function\s+execute\s*\(\s*inputs\s*,\s*config\s*,\s*context\s*\)"),
    re.compile(r"(?m)^\s*export\s+const\s+execute\s*=\s*(?:async\s*)?\(\s*inputs\s*,\s*config\s*,\s*context\s*\)\s*=>"),
    re.compile(r"(?m)^\s*export\s+const\s+execute\s*=\s*(?:async\s+)?function\s*\(\s*inputs\s*,\s*config\s*,\s*context\s*\)"),
)
_JS_LOCAL_EXPORT_PATTERNS = (
    re.compile(r"(?m)^\s*(?:async\s+)?function\s+execute\s*\(\s*inputs\s*,\s*config\s*,\s*context\s*\)"),
    re.compile(r"(?m)^\s*const\s+execute\s*=\s*(?:async\s*)?\(\s*inputs\s*,\s*config\s*,\s*context\s*\)\s*=>"),
    re.compile(r"(?m)^\s*const\s+execute\s*=\s*(?:async\s+)?function\s*\(\s*inputs\s*,\s*config\s*,\s*context\s*\)"),
)
_JS_EXPORT_LIST_PATTERN = re.compile(r"export\s*\{\s*execute(?:\s+as\s+\w+)?(?:\s*,[\s\S]*?)?\}")


def get_artifact_entrypoint_contract_errors(
    *,
    language: str,
    source_files: list[dict[str, Any]],
    entry_module_path: str | None,
) -> list[str]:
    normalized_language = str(language or "python").strip().lower()
    normalized_entry_module = str(entry_module_path or "").strip()
    if not normalized_entry_module:
        return ["Artifact entry module must be set before test or publish"]

    source_map = {
        str(item.get("path") or "").strip(): str(item.get("content") or "")
        for item in (source_files or [])
        if str(item.get("path") or "").strip()
    }
    entry_content = source_map.get(normalized_entry_module)
    if entry_content is None:
        return [f"Artifact entry module {normalized_entry_module} must exist in source_files"]

    if normalized_language == "python":
        if _python_entrypoint_is_valid(entry_content):
            return []
        return [f"Artifact entry module {normalized_entry_module} must define execute(inputs, config, context)"]

    if normalized_language in {"javascript", "typescript"}:
        if _javascript_entrypoint_is_valid(entry_content):
            return []
        return [f"Artifact entry module {normalized_entry_module} must export execute(inputs, config, context)"]

    return []


def validate_artifact_entrypoint_contract(
    *,
    language: str,
    source_files: list[dict[str, Any]],
    entry_module_path: str | None,
) -> None:
    errors = get_artifact_entrypoint_contract_errors(
        language=language,
        source_files=source_files,
        entry_module_path=entry_module_path,
    )
    if errors:
        raise ArtifactEntrypointContractError(errors)


def _python_entrypoint_is_valid(content: str) -> bool:
    try:
        module = ast.parse(content or "")
    except SyntaxError:
        return False
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "execute":
            continue
        args = node.args
        if args.vararg is not None or args.kwarg is not None or args.kwonlyargs:
            return False
        positional = [*args.posonlyargs, *args.args]
        if [arg.arg for arg in positional] != ["inputs", "config", "context"]:
            return False
        return True
    return False


def _javascript_entrypoint_is_valid(content: str) -> bool:
    for pattern in _JS_DIRECT_EXPORT_PATTERNS:
        if pattern.search(content or ""):
            return True
    if not _JS_EXPORT_LIST_PATTERN.search(content or ""):
        return False
    return any(pattern.search(content or "") for pattern in _JS_LOCAL_EXPORT_PATTERNS)

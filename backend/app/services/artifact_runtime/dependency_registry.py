from __future__ import annotations

import ast
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx


PYTHON_STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}
PYTHON_RUNTIME_PROVIDED_DEFAULTS = {
    "aiohttp",
    "httpx",
    "workers",
}
JAVASCRIPT_RUNTIME_PROVIDED_DEFAULTS: set[str] = set()
JAVASCRIPT_BUILTIN_MODULES = {"cloudflare:workers"}
PYTHON_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
PYTHON_REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
JS_IMPORT_RE = re.compile(r'\b(?:import|export)\s+(?:[^"\'`]*?\s+from\s+)?["\'`]([^"\'`]+)["\'`]')
JS_DYNAMIC_IMPORT_RE = re.compile(r'\bimport\s*\(\s*["\'`]([^"\'`]+)["\'`]\s*\)')


def analyze_artifact_dependencies(
    *,
    language: str,
    source_files: list[dict[str, Any]] | None,
    dependencies: list[str] | None,
) -> list[dict[str, Any]]:
    normalized_language = str(language or "python").strip().lower()
    import_refs = collect_dependency_import_refs(language=normalized_language, source_files=source_files)
    local_modules = collect_local_modules(language=normalized_language, source_files=source_files)
    imported_names = sorted({ref["name"] for ref in import_refs if ref["name"] not in local_modules})
    declared_specs = collect_declared_dependency_specs(language=normalized_language, dependencies=dependencies)
    runtime_provided = runtime_provided_modules_for_language(normalized_language)
    runtime_catalog = runtime_catalog_modules_for_language(normalized_language)

    names = sorted(set(imported_names) | set(declared_specs.keys()))
    rows: list[dict[str, Any]] = []
    for name in names:
        imported = name in imported_names
        declared_spec = declared_specs.get(name)
        is_builtin = imported and is_builtin_module(normalized_language, name)
        is_runtime_provided = imported and name in runtime_provided
        is_runtime_catalog = imported and name in runtime_catalog
        if declared_spec:
            rows.append(
                _build_declared_row(
                    name=name,
                    declared_spec=declared_spec,
                    imported=imported,
                    is_builtin=is_builtin,
                    is_runtime_provided=is_runtime_provided,
                    is_runtime_catalog=is_runtime_catalog,
                )
            )
            continue
        if is_builtin:
            rows.append(
                {
                    "name": name,
                    "normalized_name": name,
                    "declared_spec": None,
                    "classification": "builtin",
                    "source": "builtin",
                    "status": "Built-in",
                    "note": "Imported from the runtime standard library.",
                    "imported": True,
                    "declared": False,
                    "can_remove": False,
                    "can_add": False,
                    "needs_declaration": False,
                }
            )
            continue
        if is_runtime_provided:
            rows.append(
                {
                    "name": name,
                    "normalized_name": name,
                    "declared_spec": None,
                    "classification": "runtime_provided",
                    "source": "runtime_registry",
                    "status": "Runtime-provided",
                    "note": "Available through the platform runtime registry.",
                    "imported": True,
                    "declared": False,
                    "can_remove": False,
                    "can_add": False,
                    "needs_declaration": False,
                }
            )
            continue
        if is_runtime_catalog:
            rows.append(
                {
                    "name": name,
                    "normalized_name": name,
                    "declared_spec": None,
                    "classification": "runtime_provided",
                    "source": "runtime_catalog",
                    "status": "Runtime catalog",
                    "note": "Listed in the official Pyodide package catalog, but not yet in the platform-verified runtime set.",
                    "imported": True,
                    "declared": False,
                    "can_remove": False,
                    "can_add": True,
                    "needs_declaration": True,
                }
            )
            continue
        rows.append(
            {
                "name": name,
                "normalized_name": name,
                "declared_spec": None,
                "classification": "declared",
                "source": "declared",
                "status": "Declaration required",
                "note": "Imported in source but not declared.",
                "imported": True,
                "declared": False,
                "can_remove": False,
                "can_add": True,
                "needs_declaration": True,
            }
        )
    return sorted(rows, key=_dependency_row_sort_key)


def dependency_diagnostics_for_editor(
    *,
    language: str,
    source_files: list[dict[str, Any]] | None,
    dependencies: list[str] | None,
) -> list[dict[str, Any]]:
    normalized_language = str(language or "python").strip().lower()
    local_modules = collect_local_modules(language=normalized_language, source_files=source_files)
    runtime_provided = runtime_provided_modules_for_language(normalized_language)
    runtime_catalog = runtime_catalog_modules_for_language(normalized_language)
    declared_specs = collect_declared_dependency_specs(language=normalized_language, dependencies=dependencies)
    diagnostics: list[dict[str, Any]] = []
    for ref in collect_dependency_import_refs(language=normalized_language, source_files=source_files):
        name = ref["name"]
        if (
            name in local_modules
            or is_builtin_module(normalized_language, name)
            or name in runtime_provided
            or name in declared_specs
        ):
            continue
        diagnostics.append(
            {
                "path": ref["path"],
                "message": f"Cannot resolve module '{name}'. Add it to artifact dependencies.",
                "line": ref["line"],
                "column": ref["column"],
                "end_line": ref["line"],
                "end_column": ref["end_column"],
                "severity": "error",
                "code": f"{normalized_language.upper()}_MISSING_DEPENDENCY",
            }
        )
    return diagnostics


def collect_dependency_import_refs(*, language: str, source_files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_language = str(language or "python").strip().lower()
    if normalized_language == "python":
        return _collect_python_import_refs(source_files)
    return _collect_javascript_import_refs(source_files)


def collect_declared_dependency_specs(*, language: str, dependencies: list[str] | None) -> dict[str, str]:
    normalized_language = str(language or "python").strip().lower()
    declared: dict[str, str] = {}
    for item in list(dependencies or []):
        spec = str(item or "").strip()
        if not spec:
            continue
        normalized_name = normalize_dependency_name(normalized_language, spec)
        if normalized_name:
            declared[normalized_name] = spec
    return declared


def collect_local_modules(*, language: str, source_files: list[dict[str, Any]] | None) -> set[str]:
    normalized_language = str(language or "python").strip().lower()
    modules: set[str] = set()
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "").strip("/")
        if not path:
            continue
        if normalized_language == "python" and not path.endswith(".py"):
            continue
        if normalized_language != "python" and not path.endswith((".js", ".mjs", ".ts", ".mts")):
            continue
        parts = [segment for segment in path.split("/") if segment]
        if not parts:
            continue
        stem = parts[-1].rsplit(".", 1)[0].lower()
        modules.add(stem)
        if len(parts) > 1:
            modules.add(parts[0].lower())
    return modules


def runtime_provided_modules_for_language(language: str) -> set[str]:
    normalized_language = str(language or "python").strip().lower()
    env_key = (
        "ARTIFACT_RUNTIME_PROVIDED_PYTHON_MODULES"
        if normalized_language == "python"
        else "ARTIFACT_RUNTIME_PROVIDED_JAVASCRIPT_MODULES"
    )
    env_values = {
        normalize_dependency_name(normalized_language, item)
        for item in (os.getenv(env_key) or "").split(",")
        if normalize_dependency_name(normalized_language, item)
    }
    defaults = (
        PYTHON_RUNTIME_PROVIDED_DEFAULTS
        if normalized_language == "python"
        else JAVASCRIPT_RUNTIME_PROVIDED_DEFAULTS
    )
    return set(defaults) | env_values


def runtime_catalog_modules_for_language(language: str) -> set[str]:
    normalized_language = str(language or "python").strip().lower()
    if normalized_language != "python":
        return set()
    return set(_load_pyodide_catalog_imports())


def normalize_dependency_name(language: str, raw: str | None) -> str:
    normalized_language = str(language or "python").strip().lower()
    value = str(raw or "").strip()
    if not value:
        return ""
    if normalized_language == "python":
        value = value.split("[", 1)[0].strip()
        match = PYTHON_REQUIREMENT_RE.match(value)
        if not match:
            return ""
        return match.group(1).lower().replace("-", "_")
    if value.startswith("@"):
        if value.count("@") >= 2:
            return value.rsplit("@", 1)[0].strip().lower()
        return value.lower()
    return value.split("@", 1)[0].strip().lower()


def is_builtin_module(language: str, module_name: str) -> bool:
    normalized_language = str(language or "python").strip().lower()
    if normalized_language == "python":
        return module_name in PYTHON_STDLIB_MODULES
    return module_name.startswith("node:") or module_name in JAVASCRIPT_BUILTIN_MODULES


async def verify_python_package_exists(package_name: str) -> dict[str, Any]:
    raw_name = str(package_name or "").strip()
    if not raw_name or not PYTHON_PACKAGE_RE.fullmatch(raw_name):
        return {
            "package_name": package_name,
            "normalized_name": normalize_dependency_name("python", raw_name),
            "status": "invalid",
            "exists": False,
            "error_message": "Invalid Python package name.",
        }
    normalized_name = normalize_dependency_name("python", raw_name)
    if not normalized_name or not PYTHON_PACKAGE_RE.fullmatch(normalized_name.replace("_", "-")):
        return {
            "package_name": package_name,
            "normalized_name": normalized_name or "",
            "status": "invalid",
            "exists": False,
            "error_message": "Invalid Python package name.",
        }
    url = f"https://pypi.org/pypi/{normalized_name.replace('_', '-')}/json"
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(url)
    except Exception:
        return {
            "package_name": package_name,
            "normalized_name": normalized_name,
            "status": "lookup_failed",
            "exists": False,
            "error_message": "PyPI lookup failed.",
        }
    if response.status_code == 200:
        return {
            "package_name": package_name,
            "normalized_name": normalized_name,
            "status": "exists",
            "exists": True,
            "error_message": None,
        }
    if response.status_code == 404:
        return {
            "package_name": package_name,
            "normalized_name": normalized_name,
            "status": "not_found",
            "exists": False,
            "error_message": "Package not found on PyPI.",
        }
    return {
        "package_name": package_name,
        "normalized_name": normalized_name,
        "status": "lookup_failed",
        "exists": False,
        "error_message": "PyPI lookup failed.",
    }


def _build_declared_row(
    *,
    name: str,
    declared_spec: str,
    imported: bool,
    is_builtin: bool,
    is_runtime_provided: bool,
    is_runtime_catalog: bool,
) -> dict[str, Any]:
    note = "Declared manually; not imported in current source."
    if imported and is_builtin:
        note = "Built-in module; declaration is not required."
    elif imported and is_runtime_provided:
        note = "Runtime-provided module; declaration is not required."
    elif imported and is_runtime_catalog:
        note = "Runtime catalog module; declared explicitly."
    elif imported:
        note = "Imported and declared."
    return {
        "name": name,
        "normalized_name": name,
        "declared_spec": declared_spec,
        "classification": "declared",
        "source": "declared",
        "status": "Declared",
        "note": note,
        "imported": imported,
        "declared": True,
        "can_remove": True,
        "can_add": False,
        "needs_declaration": False,
    }


def _dependency_row_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    weight = {
        "builtin": 0,
        "runtime_provided": 1,
        "declared": 2,
    }.get(str(row.get("classification") or ""), 9)
    return weight, str(row.get("name") or "")


def _collect_python_import_refs(source_files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    refs: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            imported_names: list[str] = []
            if isinstance(node, ast.Import):
                imported_names = [str(alias.name).split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_names = [str(node.module).split(".")[0]]
            for imported_name in imported_names:
                normalized_name = normalize_dependency_name("python", imported_name)
                if not normalized_name:
                    continue
                key = (
                    normalized_name,
                    path,
                    int(getattr(node, "lineno", 1) or 1),
                    int(getattr(node, "col_offset", 0) or 0) + 1,
                )
                refs[key] = {
                    "name": normalized_name,
                    "path": path,
                    "line": key[2],
                    "column": key[3],
                    "end_column": key[3] + len(normalized_name),
                }
    return list(refs.values())


def _collect_javascript_import_refs(source_files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    refs: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        refs.update(_collect_javascript_import_refs_for_regex(path=path, content=content, regex=JS_IMPORT_RE))
        refs.update(_collect_javascript_import_refs_for_regex(path=path, content=content, regex=JS_DYNAMIC_IMPORT_RE))
    return list(refs.values())


def _collect_javascript_import_refs_for_regex(*, path: str, content: str, regex: re.Pattern[str]) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    refs: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for match in regex.finditer(content):
        specifier = str(match.group(1) or "").strip()
        if not specifier or specifier.startswith(".") or specifier.startswith("/"):
            continue
        normalized_name = normalize_dependency_name("javascript", specifier)
        if not normalized_name:
            continue
        specifier_offset = match.group(0).rfind(specifier)
        absolute_offset = (match.start() if match.start() >= 0 else 0) + max(0, specifier_offset)
        line = content.count("\n", 0, absolute_offset) + 1
        previous_newline = content.rfind("\n", 0, absolute_offset)
        column = absolute_offset - previous_newline
        key = (normalized_name, path, line, column)
        refs[key] = {
            "name": normalized_name,
            "path": path,
            "line": line,
            "column": column,
            "end_column": column + len(normalized_name),
        }
    return refs


@lru_cache(maxsize=1)
def _load_pyodide_catalog_imports() -> tuple[str, ...]:
    path = Path(__file__).with_name("generated") / "pyodide_package_catalog.json"
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return tuple()
    imports = payload.get("imports")
    if not isinstance(imports, list):
        return tuple()
    normalized = [
        normalize_dependency_name("python", item)
        for item in imports
        if normalize_dependency_name("python", item)
    ]
    return tuple(sorted(set(normalized)))

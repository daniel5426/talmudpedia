from __future__ import annotations

import json
import re
from typing import Dict, List
from pathlib import PurePosixPath


IMPORT_EXPORT_RE = re.compile(
    r'^\s*(?:import|export)\s+(?:[^"\']*?\s+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)
DYNAMIC_IMPORT_RE = re.compile(r'import\(\s*["\']([^"\']+)["\']\s*\)')


def _iter_import_specs(source: str) -> List[str]:
    specs = IMPORT_EXPORT_RE.findall(source)
    specs.extend(DYNAMIC_IMPORT_RE.findall(source))
    return [spec.strip() for spec in specs if spec and spec.strip()]


def _validate_package_json(files: Dict[str, str]) -> List[Dict[str, str]]:
    diagnostics: List[Dict[str, str]] = []
    raw_package_json = files.get("package.json")
    if raw_package_json is None:
        diagnostics.append({"path": "package.json", "message": "package.json is required at project root"})
        return diagnostics

    try:
        payload = json.loads(raw_package_json)
    except json.JSONDecodeError as exc:
        diagnostics.append({"path": "package.json", "message": f"package.json is invalid JSON: {exc.msg}"})
        return diagnostics

    dependencies = payload.get("dependencies") or {}
    dev_dependencies = payload.get("devDependencies") or {}
    if not isinstance(dependencies, dict):
        diagnostics.append({"path": "package.json", "message": "dependencies must be an object"})
    if not isinstance(dev_dependencies, dict):
        diagnostics.append({"path": "package.json", "message": "devDependencies must be an object"})
    return diagnostics


def validate_builder_dependency_policy(files: Dict[str, str]) -> List[Dict[str, str]]:
    diagnostics: List[Dict[str, str]] = _validate_package_json(files)

    code_file_suffixes = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    for path, source in files.items():
        if PurePosixPath(path).suffix.lower() not in code_file_suffixes:
            continue

        for spec in _iter_import_specs(source):
            if spec.startswith(("http://", "https://")):
                diagnostics.append({"path": path, "message": f"Network import is not allowed: {spec}"})
                continue
            if spec.startswith("node:"):
                continue
            if spec.startswith("/"):
                diagnostics.append({"path": path, "message": f"Absolute import is not allowed: {spec}"})
                continue
            if spec.startswith("@/"):
                continue
            if spec.startswith("."):
                continue

    return diagnostics

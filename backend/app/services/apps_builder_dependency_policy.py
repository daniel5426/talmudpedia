from __future__ import annotations

import json
import re
from typing import Dict, List
from pathlib import PurePosixPath


# Curated semi-open package set with pinned versions.
CURATED_DEPENDENCY_CATALOG: Dict[str, str] = {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "vite": "5.4.8",
    "typescript": "5.6.2",
    "@vitejs/plugin-react": "4.3.2",
    "@types/react": "18.3.12",
    "@types/react-dom": "18.3.1",
    "@types/node": "22.10.1",
    "tailwindcss": "3.4.14",
    "tailwindcss-animate": "1.0.7",
    "postcss": "8.4.47",
    "autoprefixer": "10.4.20",
    "class-variance-authority": "0.7.1",
    "clsx": "2.1.1",
    "tailwind-merge": "3.4.0",
    "lucide-react": "0.554.0",
    "nanoid": "5.1.6",
    "ai": "5.0.95",
    "streamdown": "1.5.1",
    "cmdk": "1.1.1",
    "@radix-ui/react-slot": "1.2.4",
    "@radix-ui/react-tooltip": "1.2.8",
    "@radix-ui/react-collapsible": "1.1.12",
    "@radix-ui/react-use-controllable-state": "1.2.2",
    "@radix-ui/react-dialog": "1.1.15",
    "@radix-ui/react-dropdown-menu": "2.1.16",
    "@radix-ui/react-hover-card": "1.1.15",
    "@radix-ui/react-select": "2.2.6",
    "@radix-ui/react-label": "2.1.8",
    "@radix-ui/react-separator": "1.1.8",
}

IMPORT_EXPORT_RE = re.compile(
    r'^\s*(?:import|export)\s+(?:[^"\']*?\s+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)
DYNAMIC_IMPORT_RE = re.compile(r'import\(\s*["\']([^"\']+)["\']\s*\)')


def _extract_bare_package_name(spec: str) -> str:
    if spec.startswith("@"):
        parts = spec.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return spec
    return spec.split("/")[0]


def _iter_import_specs(source: str) -> List[str]:
    specs = IMPORT_EXPORT_RE.findall(source)
    specs.extend(DYNAMIC_IMPORT_RE.findall(source))
    return [spec.strip() for spec in specs if spec and spec.strip()]


def _parse_package_json(files: Dict[str, str]) -> tuple[Dict[str, str], Dict[str, str], List[Dict[str, str]]]:
    diagnostics: List[Dict[str, str]] = []
    raw_package_json = files.get("package.json")
    if raw_package_json is None:
        diagnostics.append({"path": "package.json", "message": "package.json is required at project root"})
        return {}, {}, diagnostics

    try:
        payload = json.loads(raw_package_json)
    except json.JSONDecodeError as exc:
        diagnostics.append({"path": "package.json", "message": f"package.json is invalid JSON: {exc.msg}"})
        return {}, {}, diagnostics

    dependencies = payload.get("dependencies") or {}
    dev_dependencies = payload.get("devDependencies") or {}
    if not isinstance(dependencies, dict):
        diagnostics.append({"path": "package.json", "message": "dependencies must be an object"})
        dependencies = {}
    if not isinstance(dev_dependencies, dict):
        diagnostics.append({"path": "package.json", "message": "devDependencies must be an object"})
        dev_dependencies = {}

    normalized_dependencies: Dict[str, str] = {}
    normalized_dev_dependencies: Dict[str, str] = {}

    for pkg, version in dependencies.items():
        if isinstance(pkg, str) and isinstance(version, str):
            normalized_dependencies[pkg] = version.strip()
    for pkg, version in dev_dependencies.items():
        if isinstance(pkg, str) and isinstance(version, str):
            normalized_dev_dependencies[pkg] = version.strip()

    return normalized_dependencies, normalized_dev_dependencies, diagnostics


def validate_builder_dependency_policy(files: Dict[str, str]) -> List[Dict[str, str]]:
    diagnostics: List[Dict[str, str]] = []
    dependencies, dev_dependencies, package_diagnostics = _parse_package_json(files)
    diagnostics.extend(package_diagnostics)

    declared = {**dependencies, **dev_dependencies}

    for package_name, declared_version in sorted(declared.items()):
        allowed_version = CURATED_DEPENDENCY_CATALOG.get(package_name)
        if allowed_version is None:
            diagnostics.append(
                {
                    "path": "package.json",
                    "message": f"Unsupported package declaration: {package_name}",
                }
            )
            continue
        if declared_version != allowed_version:
            diagnostics.append(
                {
                    "path": "package.json",
                    "message": f"Package `{package_name}` must use pinned version `{allowed_version}`",
                }
            )

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

            package_name = _extract_bare_package_name(spec)
            if package_name not in CURATED_DEPENDENCY_CATALOG:
                diagnostics.append({"path": path, "message": f"Unsupported package import: {package_name}"})
                continue
            if package_name not in declared:
                diagnostics.append(
                    {
                        "path": path,
                        "message": f"Package import must be declared in package.json: {package_name}",
                    }
                )

    return diagnostics

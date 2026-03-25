from __future__ import annotations

import os
import re


_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
_DEFAULT_BLOCKED = {
    "numpy",
    "pandas",
    "scipy",
    "torch",
    "tensorflow",
    "opencv-python",
    "psycopg2",
    "lxml",
}


class ArtifactWorkersCompatibilityError(ValueError):
    pass


def is_python_code_path(path: str) -> bool:
    return str(path or "").strip().lower().endswith(".py")


def is_javascript_code_path(path: str) -> bool:
    return str(path or "").strip().lower().endswith((".js", ".mjs", ".ts", ".mts"))


def validate_workers_compatibility(
    *,
    language: str,
    source_files: list[dict[str, str]],
    dependencies: list[str],
    entry_module_path: str | None = None,
) -> None:
    _validate_source_files(language=language, source_files=source_files, entry_module_path=entry_module_path)
    _validate_dependencies(dependencies)


def _validate_source_files(*, language: str, source_files: list[dict[str, str]], entry_module_path: str | None = None) -> None:
    normalized_language = str(language or "python").strip().lower()
    for item in source_files:
        path = str(item.get("path") or "").strip()
        if not path:
            raise ArtifactWorkersCompatibilityError("Artifact source file path is required")
        if path.startswith("/") or ".." in path.split("/"):
            raise ArtifactWorkersCompatibilityError(f"Artifact source file path `{path}` is invalid")
    normalized_entry = str(entry_module_path or "").strip()
    if not normalized_entry:
        return
    if normalized_language == "python":
        if not is_python_code_path(normalized_entry):
            raise ArtifactWorkersCompatibilityError("Python Workers artifacts must use a .py entry module")
        return
    if not is_javascript_code_path(normalized_entry):
        raise ArtifactWorkersCompatibilityError("JavaScript Workers artifacts must use a JS/TS entry module")


def _validate_dependencies(dependencies: list[str]) -> None:
    allowlist = {
        item.strip().lower()
        for item in (os.getenv("ARTIFACT_WORKERS_ALLOWED_DEPENDENCIES") or "").split(",")
        if item.strip()
    }
    for requirement in dependencies or []:
        match = _REQ_NAME_RE.match(str(requirement or ""))
        if not match:
            raise ArtifactWorkersCompatibilityError(f"Dependency `{requirement}` is invalid")
        package_name = match.group(1).lower()
        if package_name in _DEFAULT_BLOCKED:
            raise ArtifactWorkersCompatibilityError(
                f"Dependency `{package_name}` is not supported by the Workers artifact runtime"
            )
        if allowlist and package_name not in allowlist:
            raise ArtifactWorkersCompatibilityError(
                f"Dependency `{package_name}` is not in the configured Workers dependency allowlist"
            )
